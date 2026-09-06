"""R175 resume: one existing AssemblyAI route, two independent completion sources.

No product changes. Gateway runs its real app with a transparent httpx observer
(real send is called once, no mock/retry); platform runs apps.main unchanged.
Only allowlisted upstream metadata is emitted. Child logs and auth tokens stay
in RAM. Refuse reuse of an output directory, including interrupted attempts.
R174 success is retained; missing independent accounting/upstream evidence is
why this additional operator-authorized attempt exists. No Groq gate promotion.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / "run1"
CODE_SHA = "64776a8915aa85ab61c92c3d5ceffa2e2daa8c5d"
CODE_PATHS = ["core", "apps", "providers", "infrastructure", "gateway-service", "pyproject.toml"]
MODEL = "assemblyai/qwen3.5-4b-32k-fast"
PF = "http://127.0.0.1:8000"
GW = "http://127.0.0.1:8800"
SECRETS: list[str] = []

# Instrument transport observation ONLY. Every response is returned unchanged.
# No model text, request headers, credential values, or auth tokens are logged.
OBSERVER = """
import hashlib, json, os, runpy
import httpx
original_send = httpx.AsyncClient.send
async def observe(self, request, *args, **kwargs):
    response = await original_send(self, request, *args, **kwargs)
    if request.url.host == "llm-gateway.assemblyai.com":
        await response.aread()
        try:
            body = response.json()
        except ValueError:
            body = {}
        choice = (body.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content", "")
        sent = json.loads(request.content)
        data = {
            "url": str(request.url), "status": response.status_code,
            "model": sent.get("model"),
            "raw_authorization_matches_gateway_env": request.headers.get("Authorization")
                == os.environ["GW_ASSEMBLYAI_API_KEY"],
            "fallback_retry": sent.get("fallback_config", {}).get("retry"),
            "finish_reason": choice.get("finish_reason"),
            "content_sha256": hashlib.sha256(str(text).encode()).hexdigest(),
            "usage": {k: v for k, v in body.get("usage", {}).items()
                      if k in ("input_tokens", "output_tokens",
                               "prompt_tokens", "completion_tokens")
                      and isinstance(v, int)},
        }
        print("R175_UPSTREAM " + json.dumps(data), flush=True)
    return response
httpx.AsyncClient.send = observe
runpy.run_path("app.py", run_name="__main__")
"""


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def save(name: str, data: object) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    for secret in SECRETS:
        text = text.replace(secret, "<redacted>")
    assert not re.search(r"ghp_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|\b[0-9a-f]{32}\b", text)
    (OUT / f"{name}.json").write_text(text + "\n")


def launch(args: list[str], cwd: Path, env: dict[str, str]) -> tuple[subprocess.Popen, list[str]]:
    proc = subprocess.Popen(
        args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    lines: list[str] = []

    def collect() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)

    threading.Thread(target=collect, daemon=True).start()
    return proc, lines


def wait_ready(url: str, proc: subprocess.Popen) -> None:
    for _ in range(150):
        assert proc.poll() is None, "child process exited; raw logs withheld"
        try:
            if httpx.get(url + "/healthz", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("readiness timeout")


def main() -> int:
    assert not git("diff", CODE_SHA, "--", *CODE_PATHS), "certified code changed"
    assert not git("diff", "--cached", "--", *CODE_PATHS), "staged product changes"
    assert not OUT.exists(), "existing/interrupted evidence: VERIFY before any repeat"
    key = os.environ.get("ASSEMBLYAI_API_KEY")
    assert key, "ASSEMBLYAI_API_KEY must be supplied as process env only"
    SECRETS.append(key)
    for port in (8000, 8800):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0, "port already in use"
    OUT.mkdir()
    save(
        "checkpoint",
        {
            "state": "PREPARED",
            "head": git("rev-parse", "HEAD"),
            "certified_code_sha": CODE_SHA,
            "paid_attempt_limit": 1,
            "existing_evidence": "R174 run3: valid history; lacks independent reads",
            "database": "not restored: this probe uses the existing in-memory profile",
        },
    )
    gw_secret, route_token, password = (secrets.token_urlsafe(30) for _ in range(3))
    SECRETS.extend((gw_secret, route_token, password))
    email = "r175-resume@example.test"
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ")}
    env.update(HOME=str(ROOT / ".venv"), PYTHONUNBUFFERED="1")
    gw_env = dict(
        env,
        GW_SECRET_CURRENT=gw_secret,
        GW_SECRET_CURRENT_VERSION="1",
        GW_ROUTE_MAP=f"{route_token}:assemblyai",
        GW_ASSEMBLYAI_API_KEY=key,
    )
    pf_env = dict(
        env,
        GATEWAY_BASE_URL=GW,
        GATEWAY_SECRET=gw_secret,
        GATEWAY_SECRET_VERSION="1",
        GATEWAY_ROUTE_TOKENS=f"r175-route-ref={route_token}",
        ADMIN_EMAILS=email,
        PORT="8000",
    )
    assert "ASSEMBLYAI_API_KEY" not in pf_env and "GW_ASSEMBLYAI_API_KEY" not in pf_env
    processes: list[subprocess.Popen] = []
    try:
        gw, gw_lines = launch([sys.executable, "-c", OBSERVER], ROOT / "gateway-service", gw_env)
        processes.append(gw)
        pf, pf_lines = launch([sys.executable, "-m", "apps.main"], ROOT, pf_env)
        processes.append(pf)
        wait_ready(GW, gw)
        wait_ready(PF, pf)
        # Allows the operator tooling to expose both test URLs before execution.
        time.sleep(15)
        with httpx.Client(base_url=PF, timeout=90) as client:

            def request(method: str, path: str, **kwargs: object) -> dict:
                response = client.request(method, path, **kwargs)
                return {"http_status": response.status_code, "body": response.json()}

            reg = request(
                "POST",
                "/v1/auth/register",
                json={"email": email, "password": password, "preferred_language": "en"},
            )
            assert reg["http_status"] == 201
            token = None
            for _ in range(50):
                for line in list(pf_lines):
                    if "email_verification_token_issued" in line:
                        token = json.loads(line[line.index("{") :])["token"]
                if token:
                    break
                time.sleep(0.1)
            assert token, "no verification event"
            SECRETS.append(token)
            assert request("POST", "/v1/auth/verify", json={"token": token})["http_status"] == 200
            login = request("POST", "/v1/auth/login", json={"email": email, "password": password})
            assert login["http_status"] == 200
            bearer = login["body"]["token"]
            SECRETS.append(bearer)
            client.headers["Authorization"] = "Bearer " + bearer
            session = request("GET", "/v1/auth/session")
            save("session", session)
            assert session["body"]["is_admin"]
            definition = {
                "provider_key": "assemblyai",
                "display_name": "AssemblyAI LLM Gateway",
                "operations": ["generate_text"],
                "capabilities": {},
                "static_models": [MODEL.split("/", 1)[1]],
                "credential_ref": "r175-opaque-credential-ref",
                "route_token_ref": "r175-route-ref",
                "credential_mode": "platform",
            }
            onboard = request("POST", "/v1/admin/providers/onboard", json=definition)
            save("onboard", {"request": definition, **onboard})
            assert onboard["http_status"] == 201
            draft = request(
                "POST",
                "/v1/admin/changes",
                json={"action": "enable_provider", "payload": {"provider_key": "assemblyai"}},
            )
            assert draft["http_status"] == 201
            steps = {"draft": draft}
            for action in ("validate", "preview", "publish"):
                step = request("POST", f"/v1/admin/changes/{draft['body']['id']}/{action}")
                steps[action] = step
                assert step["http_status"] == 200
            save("enable", steps)
            save("models", request("GET", "/v1/admin/models"))
            before = request("GET", "/v1/usage")
            save("usage_before", before)
            save("ledger_before", request("GET", "/v1/admin/usage"))
            save(
                "attempt",
                {
                    "state": "SUBMITTING_DO_NOT_REPLAY",
                    "paid_attempt_limit": 1,
                    "certified_code_sha": CODE_SHA,
                    "model": MODEL,
                },
            )
            body = {
                "ask": "Reply with exactly the two words: chain verified",
                "model_policy": {
                    "type": "explicit_model",
                    "model_id": MODEL,
                    "allow_fallback": False,
                },
            }
            result = request("POST", "/v1/execute", json=body)
            save("execute", {"request": body, **result})
            eid = result["body"].get("execution_id")
            readback = request("GET", f"/v1/executions/{eid}") if eid else {}
            save("execution_readback", readback)
            after = request("GET", "/v1/usage")
            save("usage_after", after)
            ledger = request("GET", "/v1/admin/usage")
            save("ledger_after", ledger)
            events = [
                json.loads(line.split("R175_UPSTREAM ", 1)[1])
                for line in list(gw_lines)
                if line.startswith("R175_UPSTREAM ")
            ]
            save("upstream_observations", events)
            rows = [row for row in ledger["body"].get("usage", []) if row["execution_id"] == eid]
            content = result["body"].get("result", {}).get("content", "")
            checks = {
                "one_real_upstream_response": len(events) == 1 and events[0]["status"] == 200,
                "upstream_completion_stop": len(events) == 1
                and events[0]["finish_reason"] == "stop",
                "platform_success": result["http_status"] == 200
                and result["body"].get("status") == "succeeded"
                and content.strip() == "chain verified",
                "upstream_content_matches_platform": len(events) == 1
                and events[0]["content_sha256"] == hashlib.sha256(content.encode()).hexdigest(),
                "stored_execution_completed": readback.get("http_status") == 200
                and readback.get("body", {}).get("status") == "succeeded"
                and readback.get("body", {}).get("result", {}).get("content") == content,
                "one_ledger_in_authenticated_tenant": len(rows) == 1
                and rows[0].get("ledger", {}).get("tenant_id") == session["body"]["tenant_id"],
                "upstream_raw_key_auth_and_no_retry": len(events) == 1
                and events[0]["raw_authorization_matches_gateway_env"]
                and events[0]["fallback_retry"] is False,
            }
            save("checks", checks)
            save(
                "attempt",
                {
                    "state": "COMPLETED" if all(checks.values()) else "NOT_PROMOTED",
                    "paid_attempts_submitted": 1,
                    "checks_passed": sum(checks.values()),
                    "checks_total": len(checks),
                    "certified_code_sha": CODE_SHA,
                },
            )
            print(json.dumps(checks, indent=2))
            return 0 if all(checks.values()) else 1
    finally:
        for proc in reversed(processes):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # No traceback or exception values: third-party errors may contain secrets.
        print("R175 resume stopped:", type(exc).__name__, "(details withheld; inspect checkpoint)")
        sys.exit(1)
