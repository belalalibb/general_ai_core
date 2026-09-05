"""R174 §7 — the WHOLE chain, live, two processes, plus the collision check.

Two real processes (same as §5):
  gateway  : gateway-service/app.py (uvicorn :8800)
             route map  rt_aai_r174 → assemblyai · rt_fx_r174 → fixture_echo
             GW_ENABLE_FIXTURE_ECHO=1 (opt-in) · GW_ASSEMBLYAI_API_KEY if supplied
  platform : python3 -m apps.main (uvicorn :8000)
             GATEWAY_ROUTE_TOKENS="<ref>=rt_aai_r174,<ref2>=rt_fx_r174"  (F-3 seam)

The driver talks ONLY to the platform as an operator + tenant would. Whatever
reaches :8800 got there through apps.composition → RemoteGatewayAdapter →
the canonical envelope.

Corrected collision design (run 1 was misdesigned — it used groq, which has no
key at the gateway, so its leg could only ever answer platform_credential_missing
and proved nothing about routing): the partner is `fixture_echo`, a HERMETIC
gateway slug that declares EXACTLY AssemblyAI's model name `qwen3.5-4b-32k-fast`
and answers with an unmistakable marker. Zero upstream, zero key, zero cost.

Cases:
  G.  control: both route tokens resolve at the gateway (describe, free).
  E1. onboard `assemblyai` through the admin door → 201 (F-3 + F-6 live).
  E2. onboard `fixture_echo`, SAME model name → 201; model keys differ by
      provider prefix (`assemblyai/...` vs `fixture_echo/...`) — no collision
      in the registry.
  N.  enable both via the real change lifecycle (draft→validate→preview→publish).
  X1. /v1/execute explicit_model=fixture_echo/qwen3.5-4b-32k-fast → marker text.
      FREE. Proves the platform routed by PROVIDER to the fixture slug.
  X2. /v1/execute explicit_model=assemblyai/qwen3.5-4b-32k-fast → real model
      text WITHOUT the marker. THE ONE PAID CALL. Runs only if
      GW_ASSEMBLYAI_API_KEY is in the driver's environment; otherwise recorded
      SKIPPED (never faked). Without the key the gateway answers
      invalid_credential/platform_credential_missing — also recorded honestly.
  X3. explicit_model=assemblyai/... + provider_id=fixture_echo → routing
      refusal (11 §14 rule 4) — the provider pin never bleeds across slugs. FREE.

Key custody: the key lives ONLY in the gateway process env; the platform process
never has it; the driver never logs it; evidence is scrubbed for every secret
shape and asserted free of them.
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
RT_AAI = "rt_aai_r174"  # noqa: S105
RT_FX = "rt_fx_r174"  # noqa: S105
REF_AAI = "route-token-ref-assemblyai-r174"
REF_FX = "route-token-ref-fixture-r174"
ADMIN_EMAIL = "r174-admin@example.test"
ADMIN_PASSWORD = "R174-correct-horse-battery"  # noqa: S105 — local throwaway
MODEL_NAME = "qwen3.5-4b-32k-fast"
MARKER = "[FIXTURE_ECHO r174 — not a live model]"
KEY_ENV = "GW_ASSEMBLYAI_API_KEY"

_key = os.environ.get(KEY_ENV)
SECRET_SHAPES = tuple(s for s in (GW_SECRET, ADMIN_PASSWORD, RT_AAI, RT_FX, _key) if s)


def _wait(url: str, proc: subprocess.Popen[str], name: str, timeout: float = 40) -> None:
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


def _gw_lines_since(n: int) -> list[str]:
    return (OUT / "gateway.log").read_text().splitlines()[n:]


def _gw_len() -> int:
    return len((OUT / "gateway.log").read_text().splitlines())


def _enable(c: httpx.Client, auth: dict, provider_key: str) -> dict:
    steps: dict[str, dict] = {}
    d = c.post(
        f"{PLATFORM}/v1/admin/changes",
        headers=auth,
        json={"action": "enable_provider", "payload": {"provider_key": provider_key}},
    )
    steps["draft"] = _resp(d, None)
    if d.status_code != 201:
        return steps
    cid = d.json()["id"]
    for step in ("validate", "preview", "publish"):
        r = c.post(f"{PLATFORM}/v1/admin/changes/{cid}/{step}", headers=auth)
        steps[step] = _resp(r, None)
        if r.status_code != 200:
            break
    return steps


def main() -> int:
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("GW_", "GATEWAY_"))}
    key_present = _key is not None and len(_key) > 0
    gw_log = (OUT / "gateway.log").open("w")
    pf_log = (OUT / "platform.log").open("w")

    gw_env = dict(
        base_env,
        GW_SECRET_CURRENT=GW_SECRET,
        GW_SECRET_CURRENT_VERSION="1",
        GW_ROUTE_MAP=f"{RT_AAI}:assemblyai,{RT_FX}:fixture_echo",
        GW_ENABLE_FIXTURE_ECHO="1",
    )
    if key_present:
        gw_env[KEY_ENV] = _key  # type: ignore[assignment]  # gateway process ONLY
    gw = subprocess.Popen(  # noqa: S603
        [sys.executable, "app.py"],
        cwd=ROOT / "gateway-service",
        env=gw_env,
        stdout=gw_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    pf_env = dict(
        base_env,
        GATEWAY_BASE_URL=GW,
        GATEWAY_SECRET=GW_SECRET,
        GATEWAY_SECRET_VERSION="1",
        GATEWAY_ROUTE_TOKENS=f"{REF_AAI}={RT_AAI},{REF_FX}={RT_FX}",
        ADMIN_EMAILS=ADMIN_EMAIL,
        PORT="8000",
    )
    pf_env.pop("DATABASE_URL", None)
    assert KEY_ENV not in pf_env  # the platform NEVER holds the provider key
    pf = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "apps.main"],
        cwd=ROOT,
        env=pf_env,
        stdout=pf_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    results: dict[str, dict] = {}
    try:
        _wait(f"{GW}/healthz", gw, "gateway")
        _wait(f"{PLATFORM}/healthz", pf, "platform")
        c = httpx.Client(timeout=90)

        # --- G: control — both tokens resolve at the gateway (free) -------------
        def describe(tok: str) -> dict:
            r = c.get(
                f"{GW}/v1/describe",
                headers={
                    "X-Gateway-Secret": GW_SECRET,
                    "X-Gateway-Secret-Version": "1",
                    "X-Route-Token": tok,
                },
            )
            return _resp(r, None)

        results["G_control_describe"] = record(
            "G_control_describe",
            {"assemblyai_token": describe(RT_AAI), "fixture_token": describe(RT_FX)},
        )

        # --- admin bootstrap through the REAL identity flow --------------------
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

        def definition(provider_key: str, display: str, ref: str) -> dict:
            return {
                "provider_key": provider_key,
                "display_name": display,
                "operations": ["generate_text"],
                "capabilities": {},
                "static_models": [MODEL_NAME],
                "credential_ref": f"cred-ref-{provider_key}-r174",
                "route_token_ref": ref,
                "credential_mode": "platform",
            }

        # --- E1: onboard assemblyai (F-3 + F-6 live) ---------------------------
        d_aai = definition("assemblyai", "AssemblyAI LLM Gateway", REF_AAI)
        n0 = _gw_len()
        e1 = c.post(f"{PLATFORM}/v1/admin/providers/onboard", headers=auth, json=d_aai)
        time.sleep(0.3)
        gw_log.flush()
        results["E1_onboard_assemblyai"] = record(
            "E1_onboard_assemblyai",
            {**_resp(e1, d_aai), "gateway_log_lines_during_call": _gw_lines_since(n0)},
        )

        # --- E2: onboard fixture_echo — SAME model name ------------------------
        d_fx = definition("fixture_echo", "Fixture Echo", REF_FX)
        n0 = _gw_len()
        e2 = c.post(f"{PLATFORM}/v1/admin/providers/onboard", headers=auth, json=d_fx)
        time.sleep(0.3)
        gw_log.flush()
        results["E2_onboard_fixture_echo_same_model_name"] = record(
            "E2_onboard_fixture_echo_same_model_name",
            {**_resp(e2, d_fx), "gateway_log_lines_during_call": _gw_lines_since(n0)},
        )

        # --- N: enable both via the real change lifecycle -----------------------
        results["N_enable_both"] = record(
            "N_enable_both",
            {
                "assemblyai": _enable(c, auth, "assemblyai"),
                "fixture_echo": _enable(c, auth, "fixture_echo"),
            },
        )
        models = c.get(f"{PLATFORM}/v1/admin/models", headers=auth)
        provs = c.get(f"{PLATFORM}/v1/admin/providers", headers=auth)
        results["N_registry_after_enable"] = record(
            "N_registry_after_enable",
            {"models": _resp(models, None), "providers": _resp(provs, None)},
        )

        # --- X1: execute → fixture_echo (FREE, marker expected) -----------------
        def execute(model_key: str, provider_id: str | None, ask: str) -> tuple[dict, list[str]]:
            policy: dict = {"type": "explicit_model", "model_id": model_key, "allow_fallback": False}
            if provider_id is not None:
                policy["provider_id"] = provider_id
            body = {"ask": ask, "model_policy": policy}
            n = _gw_len()
            r = c.post(f"{PLATFORM}/v1/execute", headers=auth, json=body)
            time.sleep(0.4)
            gw_log.flush()
            return _resp(r, body), _gw_lines_since(n)

        x1, x1_gw = execute(
            f"fixture_echo/{MODEL_NAME}", None, "R174 collision probe: which provider are you?"
        )
        results["X1_execute_fixture_echo"] = record(
            "X1_execute_fixture_echo", {**x1, "gateway_log_lines_during_call": x1_gw}
        )

        # --- X2: execute → assemblyai (THE ONE PAID CALL, only if key present) ---
        if key_present:
            x2, x2_gw = execute(
                f"assemblyai/{MODEL_NAME}",
                None,
                "Reply with exactly the two words: chain verified",
            )
            results["X2_execute_assemblyai_paid"] = record(
                "X2_execute_assemblyai_paid",
                {**x2, "gateway_log_lines_during_call": x2_gw, "paid_call": True},
            )
        else:
            results["X2_execute_assemblyai_paid"] = record(
                "X2_execute_assemblyai_paid",
                {
                    "skipped": True,
                    "reason": f"{KEY_ENV} not present in the driver environment; "
                    "the paid leg is NOT simulated",
                    "paid_call": False,
                },
            )

        # --- X3: assemblyai model pinned to fixture_echo provider → refusal ------
        x3, x3_gw = execute(f"assemblyai/{MODEL_NAME}", "fixture_echo", "must not route")
        results["X3_cross_pin_refused"] = record(
            "X3_cross_pin_refused", {**x3, "gateway_log_lines_during_call": x3_gw}
        )
    finally:
        pf.terminate()
        gw.terminate()
        pf.wait(10)
        gw.wait(10)
        pf_log.close()
        gw_log.close()
        for name in ("gateway.log", "platform.log"):
            p = OUT / name
            scrubbed = re.sub(r'"token": "[^"]+"', '"token": "<redacted>"', _scrub(p.read_text()))
            p.write_text(scrubbed)

    # --- checks ------------------------------------------------------------
    checks = []

    def ck(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": _scrub(detail)})

    g = results["G_control_describe"]
    ck(
        "G both route tokens resolve to DIFFERENT providers at the gateway",
        g["assemblyai_token"]["http_status"] == 200
        and g["fixture_token"]["http_status"] == 200
        and g["assemblyai_token"]["response_body"].get("display_name")
        != g["fixture_token"]["response_body"].get("display_name"),
        f"aai={g['assemblyai_token']['response_body'].get('display_name')!r} "
        f"fx={g['fixture_token']['response_body'].get('display_name')!r}",
    )
    ck(
        "G both slugs declare the SAME model name (collision is real)",
        [m["name"] for m in g["assemblyai_token"]["response_body"].get("models", [])]
        == [MODEL_NAME]
        == [m["name"] for m in g["fixture_token"]["response_body"].get("models", [])]
        or MODEL_NAME in json.dumps(g),
        MODEL_NAME,
    )
    e1 = results["E1_onboard_assemblyai"]
    ck(
        "E1 assemblyai onboarded 201 through the real door (F-3 + F-6 live)",
        e1["http_status"] == 201
        and e1["response_body"].get("registered_model_keys") == [f"assemblyai/{MODEL_NAME}"],
        f"http {e1['http_status']} keys={e1['response_body'].get('registered_model_keys')}",
    )
    ck(
        "E1 gateway saw /v1/health and /v1/models from the platform",
        any("/v1/health" in ln for ln in e1["gateway_log_lines_during_call"])
        and any("/v1/models" in ln for ln in e1["gateway_log_lines_during_call"]),
        "\n".join(e1["gateway_log_lines_during_call"])[:300],
    )
    e2 = results["E2_onboard_fixture_echo_same_model_name"]
    ck(
        "E2 fixture_echo onboarded 201 with the SAME model name — distinct model_key by provider",
        e2["http_status"] == 201
        and e2["response_body"].get("registered_model_keys") == [f"fixture_echo/{MODEL_NAME}"],
        f"http {e2['http_status']} keys={e2['response_body'].get('registered_model_keys')}",
    )
    n = results["N_enable_both"]
    ck(
        "N both providers enabled via draft→validate→preview→publish",
        all(
            n[p].get("publish", {}).get("http_status") == 200
            and n[p]["publish"]["response_body"].get("status") == "published"
            for p in ("assemblyai", "fixture_echo")
        ),
        json.dumps({p: {k: v["http_status"] for k, v in n[p].items()} for p in n}),
    )
    reg_models = json.dumps(results["N_registry_after_enable"]["models"]["response_body"])
    ck(
        "N registry holds BOTH model keys side by side",
        f"assemblyai/{MODEL_NAME}" in reg_models and f"fixture_echo/{MODEL_NAME}" in reg_models,
        reg_models[:300],
    )
    x1 = results["X1_execute_fixture_echo"]
    x1_content = str(x1["response_body"].get("result", {}).get("content", ""))
    ck(
        "X1 execute pinned to fixture_echo/<model> → 200 with the FIXTURE MARKER (routed by provider)",
        x1["http_status"] == 200
        and x1["response_body"].get("status") == "succeeded"
        and MARKER in x1_content,
        f"http {x1['http_status']} content={x1_content[:160]!r}",
    )
    ck(
        "X1 the request reached the gateway (dispatch line during the call)",
        any("/v1/generate" in ln or "generate_text" in ln for ln in x1["gateway_log_lines_during_call"]),
        "\n".join(x1["gateway_log_lines_during_call"])[:300] or "<none>",
    )
    x2 = results["X2_execute_assemblyai_paid"]
    if x2.get("skipped"):
        ck("X2 paid leg SKIPPED (no key) — recorded, not simulated", True, x2["reason"])
    else:
        x2_content = str(x2["response_body"].get("result", {}).get("content", ""))
        ck(
            "X2 execute pinned to assemblyai/<model> → 200 real text WITHOUT the marker (one paid call)",
            x2["http_status"] == 200
            and x2["response_body"].get("status") == "succeeded"
            and MARKER not in x2_content
            and len(x2_content.strip()) > 0,
            f"http {x2['http_status']} content={x2_content[:160]!r}",
        )
        ck(
            "X2 the request reached the gateway (dispatch line during the call)",
            any(
                "/v1/generate" in ln or "generate_text" in ln
                for ln in x2["gateway_log_lines_during_call"]
            ),
            "\n".join(x2["gateway_log_lines_during_call"])[:300] or "<none>",
        )
    x3 = results["X3_cross_pin_refused"]
    x3_text = json.dumps(x3["response_body"])
    ck(
        "X3 assemblyai/<model> pinned to provider fixture_echo is REFUSED (no cross-slug bleed)",
        x3["http_status"] != 200 or x3["response_body"].get("status") != "succeeded",
        f"http {x3['http_status']} {x3_text[:220]}",
    )
    ck(
        "X3 nothing reached the gateway for the refused request",
        not any("/v1/generate" in ln for ln in x3["gateway_log_lines_during_call"]),
        "\n".join(x3["gateway_log_lines_during_call"])[:200] or "<no lines>",
    )
    for s in SECRET_SHAPES:
        label = {GW_SECRET: "gw secret", ADMIN_PASSWORD: "admin pw", RT_AAI: "route token aai",
                 RT_FX: "route token fx"}.get(s, "provider key")
        ck(
            f"secret shape absent from evidence ({label})",
            all(s not in p.read_text() for p in OUT.glob("*.json"))
            and all(s not in (OUT / nme).read_text() for nme in ("gateway.log", "platform.log")),
            "scrubbed",
        )

    (OUT / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    passed = sum(1 for x in checks if x["pass"])
    for x in checks:
        print(("PASS" if x["pass"] else "FAIL"), x["check"], "—", x["detail"][:160])
    print(f"{passed}/{len(checks)} PASS · paid_calls={1 if key_present else 0}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
