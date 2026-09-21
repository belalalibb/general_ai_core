"""R182-IMPL M1 "Honest topology" — first red test (R182_HANDOFF §16, verbatim).

Operator rulings that make this file legal (R182-DEC-02): D-1 ADR-0013 accepted
on Alternative C (vanilla ES modules, no framework/build/runtime dependency);
D-3 (b) Command Center at ``ui/app/command/`` under the EXISTING ``/app`` mount
(zero production change, ``round_r182`` ceiling stays 0).

Invariant (HANDOFF §16): the capability nodes rendered by
``ui/app/command/command.js`` derive from ``GET /v1/admin/capabilities`` on the
served in-memory profile — never from a roster, never from a quoted
``CAPABILITY_IDS`` literal — and the vocabulary the shell can render is the
served contract's closed set plus a LOUD ``UNKNOWN``.

Proof posture (ui/admin static-check posture, tests/ui/test_admin_static_check.py):
the UI files are read as TEXT and never executed here; the served catalog is
fetched through the real app (admin session acquired the honest way — console
token, tests/composition/test_admin_console_runtime.py pattern). Rendered-DOM
equality (node count == served capability count) is the browser proof
(D-4, tests/ui/test_command_center_browser_r182.py); this module proves that
the SOURCE has exactly one place node ids can come from — the fetched
``capabilities[]`` — and no other.

Expected first run (HANDOFF §16): RED — ``FileNotFoundError`` (file absent).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from apps.api.capabilities import CAPABILITY_IDS, CapabilityState
from apps.composition.runtime import (
    DEV_DEMO_PRINCIPAL_ENV,
    RuntimeProfile,
    build_runtime_profile,
)
from core.contracts.execute import ExecutionStatus

ROOT = Path(__file__).resolve().parents[2]
COMMAND_DIR = ROOT / "ui" / "app" / "command"
COMMAND_JS = COMMAND_DIR / "command.js"
COMMAND_HTML = COMMAND_DIR / "index.html"

ADMIN_EMAIL = "command-center-admin@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential
_ADMIN_ENV = {"ADMIN_EMAILS": ADMIN_EMAIL, DEV_DEMO_PRINCIPAL_ENV: "1"}

#: HANDOFF §8 — the closed Core vocabulary (ExecutionStatus-derived + reachability).
CORE_STATES = frozenset({"idle", "running", "waiting_approval", "failed", "unreachable"})
#: HANDOFF §9 — fabricated states that may never appear as Core/node states.
FORBIDDEN_STATES = ("thinking", "speaking", "listening", "energized", "processing", "reasoning")


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _admin_token(profile: RuntimeProfile) -> str:
    """Register + verify + login an ADMIN through the runtime's own identity (20 §5)."""
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(ADMIN_EMAIL, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(ADMIN_EMAIL, PASSWORD).token


def _served_catalog() -> dict:
    profile = build_runtime_profile(environ=_ADMIN_ENV)
    token = _admin_token(profile)

    async def scenario() -> dict:
        async with _client(profile.app) as c:
            response = await c.get(
                "/v1/admin/capabilities", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200, response.text
            return response.json()

    return asyncio.run(scenario())


def _js_map_keys(js: str, const_name: str) -> set[str]:
    match = re.search(rf"const {const_name} = Object\.freeze\(\{{(.*?)\}}\);", js, re.S)
    assert match is not None, f"{const_name} map absent from command.js"
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.M))


def test_capability_nodes_derive_from_served_contract_not_a_roster() -> None:
    # 1. The file exists (RED on the first run: FileNotFoundError).
    js = _strip_js_comments(COMMAND_JS.read_text(encoding="utf-8"))

    # 2. The served contract is the ONLY source of node ids.
    catalog = _served_catalog()
    served_ids = {c["id"] for c in catalog["capabilities"]}
    assert served_ids == set(CAPABILITY_IDS), "served catalog is not the closed set"
    assert catalog["scope"] == "process"
    quoted = sorted(
        cid for cid in CAPABILITY_IDS if re.search(rf"[\"'`]{re.escape(cid)}[\"'`]", js)
    )
    assert quoted == [], f"capability ids hardcoded in command.js (a roster): {quoted}"
    assert re.search(r"\bROSTER\b|\broster\b", js) is None, "roster array in command.js"
    # The node builder must iterate the fetched `capabilities` array and key nodes by `.id`.
    assert re.search(r"\.capabilities\b", js), "command.js never reads catalog.capabilities"
    assert re.search(r"\bcapability\.id\b|\bcap\.id\b", js), "node id is not taken from the record"
    # The route is reached through the single api() transport, not typed elsewhere.
    assert re.search(r"api\(\s*[\"'`]/v1/admin/capabilities[\"'`]", js), (
        "command.js does not fetch GET /v1/admin/capabilities through api()"
    )

    # 3. Node vocabulary ⊆ CapabilityState ∪ {UNKNOWN}; Core vocabulary ⊆ HANDOFF §8.
    node_keys = _js_map_keys(js, "NODE_STATES")
    allowed_nodes = {s.value for s in CapabilityState} | {"UNKNOWN"}
    assert node_keys <= allowed_nodes, node_keys - allowed_nodes
    assert node_keys >= {s.value for s in CapabilityState}, "a contract state has no rendering"
    assert "UNKNOWN" in node_keys, "no loud UNKNOWN fallback"
    core_keys = _js_map_keys(js, "CORE_STATES")
    assert core_keys <= CORE_STATES, core_keys - CORE_STATES
    assert core_keys >= CORE_STATES, CORE_STATES - core_keys
    # Core derivation reads ExecutionStatus values only (no invented execution statuses).
    exec_literals = set(re.findall(r"status === [\"'](\w+)[\"']", js))
    assert exec_literals <= {s.value for s in ExecutionStatus}, exec_literals

    # 4. No fabricated states anywhere in the source (HANDOFF §9).
    for word in FORBIDDEN_STATES:
        assert re.search(rf"[\"'`.]{word}\b", js) is None, f"fabricated state in command.js: {word}"


def test_command_center_shell_serves_under_existing_app_mount() -> None:
    """D-3 (b): /app/command/ serves with ZERO production change (no new mount line)."""
    profile = build_runtime_profile(environ=_ADMIN_ENV)

    async def scenario() -> None:
        async with _client(profile.app) as c:
            index = await c.get("/app/command/")
            assert index.status_code == 200
            assert "QEVION · Command" in index.text  # R199-A (D3)
            js = await c.get("/app/command/command.js")
            assert js.status_code == 200
            assert "NODE_STATES" in js.text
            css = await c.get("/app/command/command.css")
            assert css.status_code == 200
            # additive: API untouched
            health = await c.get("/healthz")
            assert health.status_code == 200

    asyncio.run(scenario())
    runtime_src = (ROOT / "apps" / "composition" / "runtime.py").read_text(encoding="utf-8")
    assert runtime_src.count("StaticFiles(") == 1, "a second mount would be a frozen-tree change"


@pytest.mark.parametrize("word", FORBIDDEN_STATES)
def test_html_carries_no_fabricated_state_vocabulary(word: str) -> None:
    html = COMMAND_HTML.read_text(encoding="utf-8")
    assert re.search(rf"\b{word}\b", html, flags=re.I) is None, f"fabricated state in HTML: {word}"
