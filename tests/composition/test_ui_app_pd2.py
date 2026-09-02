"""P-D.2 — end-user UI static shell composition tests.

Operator authorization (verbatim): "نفّذ P-D خيار A1." — ui/app is the
end-user counterpart of the PROVEN ui/admin shell (same StaticFiles
posture, apps/composition/admin_console.py), mounted at /app by
``build_runtime_profile``.

What must hold:

1. **Mount exists and serves**: GET /app/ returns the shell HTML; the
   asset files (app.js, styles.css) serve from the same mount.
2. **No route shadowing**: every API route (/healthz, /v1/*) answers
   exactly as before the mount — the mount is additive.
3. **Source honesty pins** (the ui/admin test posture — the honesty
   contracts are grep-able properties of the shipped artifact):
   - STATUS_CLASSES keys ⊆ backend contract enum values (loud UNKNOWN
     badge for anything else, never gray-washed);
   - the register panel names the SERVER CONSOLE as the token channel
     (never pretends an email was sent);
   - no setInterval CALL (no polling theater);
   - the profile probe targets /v1/auth/session (probed, not assumed).
4. **Absent directory ⇒ no mount** (20 §4): the mount guard is
   ``UI_APP_DIR.is_dir()`` — proven by source pin (monkeypatching module
   constants at build time would race other tests; the guard line is
   asserted verbatim instead).

Hermetic: in-memory profile, ASGI transport, no network.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.composition.runtime import UI_APP_DIR, RuntimeProfile, build_runtime_profile
from core.contracts.domain import BindingAvailability
from core.contracts.execute import ExecutionStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "ui" / "app" / "app.js"
INDEX_HTML = REPO_ROOT / "ui" / "app" / "index.html"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture()
def profile() -> RuntimeProfile:
    return build_runtime_profile(environ={})


# --- 1 + 2: the mount serves and shadows nothing -----------------------------------


class TestMount:
    def test_ui_dir_is_the_repo_ui_app(self) -> None:
        assert UI_APP_DIR == REPO_ROOT / "ui" / "app"
        assert UI_APP_DIR.is_dir()

    def test_shell_and_assets_serve(self, profile: RuntimeProfile) -> None:
        async def scenario() -> None:
            async with _client(profile.app) as c:
                index = await c.get("/app/")
                assert index.status_code == 200
                assert "AI Orchestration Platform" in index.text
                js = await c.get("/app/app.js")
                assert js.status_code == 200
                assert "STATUS_CLASSES" in js.text
                css = await c.get("/app/styles.css")
                assert css.status_code == 200

        run(scenario())

    def test_api_routes_not_shadowed(self, profile: RuntimeProfile) -> None:
        """The mount is additive: /healthz and /v1/* answer as before."""

        async def scenario() -> None:
            async with _client(profile.app) as c:
                health = await c.get("/healthz")
                assert health.status_code == 200
                assert health.json()["status"] == "alive"
                models = await c.get("/v1/models")
                assert models.status_code == 200
                execute = await c.post("/v1/execute", json={"ask": "ping"})
                assert execute.status_code == 200

        run(scenario())

    def test_mount_is_guarded_by_directory_existence(self) -> None:
        """20 §4 pin: absent dir ⇒ no mount (the guard line, verbatim)."""
        source = (REPO_ROOT / "apps" / "composition" / "runtime.py").read_text(encoding="utf-8")
        assert "if UI_APP_DIR.is_dir():" in source


# --- 3: source honesty pins (ui/admin test posture) ---------------------------------


class TestHonestyPins:
    def test_status_classes_only_contract_values(self) -> None:
        """Every STATUS_CLASSES key is a backend contract enum value."""
        source = APP_JS.read_text(encoding="utf-8")
        match = re.search(r"const STATUS_CLASSES = \{(.*?)\};", source, re.S)
        assert match is not None
        keys = re.findall(r"^\s*(\w+):", match.group(1), re.M)
        allowed = (
            {status.value for status in ExecutionStatus}
            | {availability.value for availability in BindingAvailability}
            | {"alive"}  # the /healthz literal
        )
        assert set(keys) <= allowed, set(keys) - allowed

    def test_unknown_values_render_loud_badge(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        assert "UNKNOWN: ${String(value)}" in source

    def test_register_panel_names_the_server_console(self) -> None:
        """The token channel is the server console — said, not faked."""
        assert "server console" in APP_JS.read_text(encoding="utf-8")
        assert "server console" in INDEX_HTML.read_text(encoding="utf-8")

    def test_no_polling_theater(self) -> None:
        """No setInterval CALL exists (the honesty-contract comment at the
        top of app.js may NAME the rule — the pin targets invocations)."""
        assert "setInterval(" not in APP_JS.read_text(encoding="utf-8")

    def test_profile_is_probed_not_assumed(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        assert "/v1/auth/session" in source
        assert "probeProfile" in source

    def test_sse_frames_use_contract_event_types(self) -> None:
        """The stream renderer keys on the 10 §11 discriminators."""
        source = APP_JS.read_text(encoding="utf-8")
        assert 'event.type === "final"' in source
        assert 'event.type === "error"' in source


# --- demo-profile UX: the shell can drive the whole loop -----------------------------


class TestDemoProfileLoop:
    def test_ask_then_list_then_detail(self, profile: RuntimeProfile) -> None:
        """The exact call sequence the shell makes, against the real app."""

        async def scenario() -> None:
            async with _client(profile.app) as c:
                # probe (demo: R160 hybrid ⇒ the server SAYS mode=demo)
                session = await c.get("/v1/auth/session")
                assert session.status_code == 200
                assert session.json()["mode"] == "demo"
                assert session.json()["is_admin"] is False
                # ask (sync)
                execute = await c.post("/v1/execute", json={"ask": "hello"})
                assert execute.status_code == 200
                body = execute.json()
                assert body["status"] == "succeeded"
                # the labeled echo is VERBATIM in result.content
                # (the 41 §49 label: "no real model was called")
                assert "no real model was called" in body["result"]["content"]
                assert "local-echo" in body["result"]["content"]
                execution_id = body["execution_id"]
                # executions list
                listed = await c.get("/v1/executions")
                assert listed.status_code == 200
                ids = [r["execution_id"] for r in listed.json()["executions"]]
                assert execution_id in ids
                # detail
                detail = await c.get(f"/v1/executions/{execution_id}")
                assert detail.status_code == 200
                assert detail.json()["status"] == "succeeded"
                # usage
                usage = await c.get("/v1/usage")
                assert usage.status_code == 200
                assert usage.json()["plan"] == "local-default"

        run(scenario())
