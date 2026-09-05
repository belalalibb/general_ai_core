"""R174 §5 — the LAST link: platform process → gateway process, through the REAL door.

Two real processes:
  gateway  : gateway-service/app.py (uvicorn 127.0.0.1:8800), route map rt_aai_r174:assemblyai
  platform : python3 -m apps.main   (uvicorn 127.0.0.1:8000), GATEWAY_BASE_URL → :8800

The driver talks ONLY to the platform (:8000) as an operator would: register →
verify (console token) → login (ADMIN_EMAILS) → POST /v1/admin/providers/onboard.
It never talks to the gateway itself; whatever reaches :8800 got there through
apps.composition → RemoteGatewayAdapter.

Cases (all FREE — no upstream model call is possible before onboarding succeeds):
  E. F-3 live: onboard `assemblyai` in `platform` mode with a route_token_ref.
     Prediction (RECONCILIATION F-3): runtime.py composes a FRESH
     InMemorySecretManager for onboarding secrets and nothing ever stores a route
     token into it ⇒ the adapter's first gateway call raises SecretNotFound.
  F. F-2 live: same definition with credential_mode=user_key.
     Prediction (F-2): adapter_from_definition never passes user_key_resolver ⇒
     RemoteGatewayAdapter.__init__ raises ValueError ⇒ route returns 409.
  G. control: the gateway IS reachable from this host with a correct route token
     (describe only, free) — so E's failure is the platform link, not the network.

The AssemblyAI key is NOT required for E/F/G and is not present in either process
env for this run. The gateway log is captured to show whether any request from the
platform ever arrived.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
GW = "http://127.0.0.1:8800"
PLATFORM = "http://127.0.0.1:8000"
GW_SECRET = "r174-local-gw-secret"  # throwaway, redacted in evidence  # noqa: S105
ROUTE_TOKEN = "rt_aai_r174"  # opaque; the slug never crosses the wire  # noqa: S105
ADMIN_EMAIL = "r174-admin@example.test"
ADMIN_PASSWORD = "R174-correct-horse-battery"  # noqa: S105 — local throwaway

SECRET_SHAPES = (GW_SECRET, ADMIN_PASSWORD)


def _wait(url: str, proc: subprocess.Popen[str], name: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{name} exited early with {proc.returncode}")
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError(f"{name} did not come up")


def _scrub(text: str) -> str:
    for s in SECRET_SHAPES:
        text = text.replace(s, "<redacted>")
    return text


def record(name: str, payload: dict) -> dict:
    text = _scrub(json.dumps(payload, indent=2, ensure_ascii=False))
    assert not re.search(r"\b[0-9a-f]{32}\b", text), "32-hex token shape in evidence"
    (OUT / f"{name}.json").write_text(text + "\n")
    return payload


def _resp(resp: httpx.Response, sent: dict | None) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = {"_raw_text": resp.text[:800]}
    return {"http_status": resp.status_code, "request_body": sent, "response_body": body}


def main() -> int:
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("GW_", "GATEWAY_"))}
    assert "GW_ASSEMBLYAI_API_KEY" not in base_env
    gw_log = (OUT / "gateway.log").open("w")
    pf_log = (OUT / "platform.log").open("w")

    gw_env = dict(
        base_env,
        GW_SECRET_CURRENT=GW_SECRET,
        GW_SECRET_CURRENT_VERSION="1",
        GW_ROUTE_MAP=f"{ROUTE_TOKEN}:assemblyai,rt_groq_r174:groq",
    )
    gw = subprocess.Popen(  # noqa: S603
        [sys.executable, "app.py"], cwd=ROOT / "gateway-service", env=gw_env,
        stdout=gw_log, stderr=subprocess.STDOUT, text=True,
    )
    pf_env = dict(
        base_env,
        GATEWAY_BASE_URL=GW,
        GATEWAY_SECRET=GW_SECRET,
        GATEWAY_SECRET_VERSION="1",
        ADMIN_EMAILS=ADMIN_EMAIL,
        PORT="8000",
    )
    pf_env.pop("DATABASE_URL", None)  # in-memory profile: no Postgres in this sandbox
    pf = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "apps.main"], cwd=ROOT, env=pf_env,
        stdout=pf_log, stderr=subprocess.STDOUT, text=True,
    )
    results: dict[str, dict] = {}
    try:
        _wait(f"{GW}/healthz", gw, "gateway")
        _wait(f"{PLATFORM}/healthz", pf, "platform")
        c = httpx.Client(timeout=30)

        # --- G: control — gateway reachable with the correct route token (free) ---
        g = c.get(
            f"{GW}/v1/describe",
            headers={
                "X-Gateway-Secret": GW_SECRET,
                "X-Gateway-Secret-Version": "1",
                "X-Route-Token": ROUTE_TOKEN,
            },
        )
        results["G_control_describe"] = record("G_control_describe", _resp(g, None))

        # --- admin bootstrap through the REAL identity flow -------------------
        reg = c.post(
            f"{PLATFORM}/v1/auth/register",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "preferred_language": "en"},
        )
        assert reg.status_code == 201, reg.text
        time.sleep(0.5)
        pf_log.flush()
        token = None
        for line in (OUT / "platform.log").read_text().splitlines():
            if "email_verification_token_issued" in line:
                token = json.loads(line[line.index("{") :])["token"]
        assert token, "console verification token not found"
        ver = c.post(f"{PLATFORM}/v1/auth/verify", json={"token": token})
        assert ver.status_code == 200, ver.text
        login = c.post(
            f"{PLATFORM}/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200, login.text
        auth = {"Authorization": f"Bearer {login.json()['token']}"}
        sess = c.get(f"{PLATFORM}/v1/auth/session", headers=auth)
        results["bootstrap"] = record(
            "bootstrap",
            {
                "register": reg.status_code,
                "verify": ver.status_code,
                "login": login.status_code,
                "session": _resp(sess, None),
            },
        )
        assert sess.json().get("is_admin") is True, sess.text

        definition = {
            "provider_key": "assemblyai",
            "display_name": "AssemblyAI LLM Gateway",
            "operations": ["generate_text"],
            "capabilities": {},
            "static_models": ["qwen3.5-4b-32k-fast", "gemini-2.5-flash-lite"],
            "credential_ref": "cred-ref-assemblyai-r174",
            "route_token_ref": "route-token-ref-assemblyai-r174",
            "credential_mode": "platform",
        }

        # --- E: F-3 live (platform mode, route_token_ref) ----------------------
        gw_lines_before = len((OUT / "gateway.log").read_text().splitlines())
        e = c.post(f"{PLATFORM}/v1/admin/providers/onboard", headers=auth, json=definition)
        time.sleep(0.3)
        gw_log.flush()
        gw_after = (OUT / "gateway.log").read_text().splitlines()[gw_lines_before:]
        results["E_f3_platform_mode"] = record(
            "E_f3_platform_mode",
            {**_resp(e, definition), "gateway_log_lines_during_call": gw_after},
        )

        # --- F: F-2 live (user_key mode) -------------------------------------
        f_def = dict(definition, provider_key="assemblyai-byok", credential_mode="user_key")
        f = c.post(f"{PLATFORM}/v1/admin/providers/onboard", headers=auth, json=f_def)
        results["F_f2_user_key_mode"] = record("F_f2_user_key_mode", _resp(f, f_def))

        # --- providers listing after the attempts (nothing half-registered) ----
        lst = c.get(f"{PLATFORM}/v1/admin/providers", headers=auth)
        results["after_listing"] = record("after_listing", _resp(lst, None))
    finally:
        pf.terminate()
        gw.terminate()
        pf.wait(10)
        gw.wait(10)
        pf_log.close()
        gw_log.close()
        for name in ("gateway.log", "platform.log"):
            p = OUT / name
            p.write_text(_scrub(p.read_text()))

    # --- checks ------------------------------------------------------------
    checks = []

    def ck(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    g_body = results["G_control_describe"]["response_body"]
    ck("G gateway reachable + route resolves", results["G_control_describe"]["http_status"] == 200
       and g_body.get("display_name") == "AssemblyAI LLM Gateway", str(g_body)[:200])
    e_res = results["E_f3_platform_mode"]
    e_body = e_res["response_body"]
    e_text = json.dumps(e_body)
    ck("E platform-mode onboarding did NOT succeed (F-3 predicted break)",
       e_res["http_status"] != 201, f"http {e_res['http_status']}")
    ck("E failure names the route token custody gap (SecretNotFound / unresolvable ref) or is a 500",
       "route-token-ref" in e_text or "SecretNotFound" in e_text or "secret" in e_text.lower()
       or e_res["http_status"] == 500, e_text[:300])
    ck("E no request reached the gateway (log has no route hit)",
       not any("/v1/" in ln for ln in e_res["gateway_log_lines_during_call"]),
       "\n".join(e_res["gateway_log_lines_during_call"])[:300] or "<no lines>")
    f_res = results["F_f2_user_key_mode"]
    f_text = json.dumps(f_res["response_body"])
    ck("F user_key onboarding refused 409 (F-2 predicted: no user_key_resolver)",
       f_res["http_status"] == 409 and "user_key_resolver" in f_text, f_text[:300])
    lst_text = json.dumps(results["after_listing"]["response_body"])
    ck("after: neither provider registered (no half-state)",
       "assemblyai" not in lst_text, lst_text[:300])
    for s in SECRET_SHAPES:
        ck(f"secret shape absent from evidence ({'gw secret' if s == GW_SECRET else 'admin pw'})",
           all(s not in p.read_text() for p in OUT.glob("*.json")) and s not in (OUT / "gateway.log").read_text()
           and s not in (OUT / "platform.log").read_text(), "scrubbed")

    (OUT / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    passed = sum(1 for x in checks if x["pass"])
    for x in checks:
        print(("PASS" if x["pass"] else "FAIL"), x["check"], "—", x["detail"][:160])
    print(f"{passed}/{len(checks)} PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
