"""Minimal platform app — a complete external consumer in one file.

Closure GAP 2 (operator-verified): proves an OUTSIDE developer can build
on the platform using ONLY the public HTTP surface — no imports from
core/apps/infrastructure, stdlib urllib only.

What it exercises (the documented /v1 surface, RUN.md):

1. Profile probe   GET  /v1/auth/session   (demo profile ⇒ no token needed)
2. Organize        POST /v1/workspaces  →  POST /v1/projects (linked)
3. Ask             POST /v1/execute     (sync; honest labeled echo in dev)
4. Inspect         GET  /v1/executions/{id}
5. Governance      DELETE workspace-with-project ⇒ 409 refusal (RESTRICT)
6. Cleanup         DELETE project ⇒ 204, DELETE workspace ⇒ 204

Run (two terminals):

    python3 -m apps.main                       # terminal 1 (the platform)
    python3 examples/minimal-platform-app/client.py   # terminal 2

Durable profile: export PLATFORM_TOKEN=<session token from login> and the
same script authenticates every call (Bearer header).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("PLATFORM_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("PLATFORM_TOKEN")  # optional (durable profile)


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else None


def step(label: str, status: int, expect: int, payload: object = None) -> None:
    ok = "OK " if status == expect else "FAIL"
    print(f"[{ok}] {label}: HTTP {status} (expected {expect})")
    if payload is not None:
        print(f"      {json.dumps(payload, ensure_ascii=False)[:200]}")
    if status != expect:
        sys.exit(1)


def main() -> None:
    # 1. Health + profile probe
    s, _ = call("GET", "/healthz")
    step("healthz", s, 200)
    s, session = call("GET", "/v1/auth/session")
    if s == 200:
        print(f"      profile: {json.dumps(session, ensure_ascii=False)[:160]}")
    else:
        print("      demo profile (no auth surface) — proceeding without token")

    # 2. Organize: workspace + linked project
    s, ws = call("POST", "/v1/workspaces", {"name": "My App Workspace"})
    step("create workspace", s, 201, ws)
    s, prj = call(
        "POST",
        "/v1/projects",
        {
            "name": "My App Project",
            "workspace_id": ws["workspace_id"],
            "metadata": {"app": "minimal-platform-app"},
        },
    )
    step("create linked project", s, 201, prj)

    # 3. Ask (sync execute — labeled echo on the dev profile, honest)
    s, result = call("POST", "/v1/execute", {"ask": "Say hello to the example app."})
    step("execute (sync)", s, 200, {k: result.get(k) for k in ("execution_id", "status")})

    # 4. Inspect the execution record
    s, record = call("GET", f"/v1/executions/{result['execution_id']}")
    step("fetch execution", s, 200, {"status": record.get("status")})

    # 5. Governance: RESTRICT refusal is loud, never a silent cascade
    s, err = call("DELETE", f"/v1/workspaces/{ws['workspace_id']}")
    step("delete workspace WITH project (refused)", s, 409, err)

    # 6. Cleanup in the right order
    s, _ = call("DELETE", f"/v1/projects/{prj['project_id']}")
    step("delete project", s, 204)
    s, _ = call("DELETE", f"/v1/workspaces/{ws['workspace_id']}")
    step("delete workspace", s, 204)

    print("\nminimal-platform-app: ALL STEPS PASSED")


if __name__ == "__main__":
    main()
