"""/admin wiring into the local runtime — attach_admin_console over the
SAME composed instances (operator mandate: "اربطها دون إعادة بناء أي شيء").

What this suite pins:

1. **The console is part of the runtime**: build_runtime_profile mounts
   /admin (static shell) and includes /v1/agent/* + /v1/admin/notifications
   — enumerated via ``app.openapi()`` (FastAPI 0.141 recorded posture:
   included routers appear lazily in ``app.routes``).
2. **Nothing rebuilt**: the wiring is a source-pinned pass-through of the
   already-composed instances (store/usage/audit/admin/auth + the six
   app.state seams create_app derived — "one derivation, two consumers").
3. **Nothing shadowed**: /app, /healthz and /v1/* answer exactly as before.
4. **Honest auth posture in BOTH profiles**: anonymous ⇒ the ONE constant
   401 on every console route (session_resolver over the SAME AuthSurface).
5. **Absent seam = absent route (20 §4)**: no SkillReviewSurface is
   composed ⇒ /v1/admin/skills/* must not exist at all.

Hermetic: in-memory profile, ASGI transport, no network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.composition.runtime import RuntimeProfile, build_runtime_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PY = REPO_ROOT / "apps" / "composition" / "runtime.py"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture()
def profile() -> RuntimeProfile:
    return build_runtime_profile(environ={})


# --- 1: the console routes and shell exist on the runtime app ----------------


class TestConsoleIsPartOfRuntime:
    def test_agent_and_notification_routes_exist(
        self, profile: RuntimeProfile
    ) -> None:
        """OpenAPI enumeration (recorded posture) shows the console surface."""
        paths = set(profile.app.openapi()["paths"])
        assert "/v1/agent/tools" in paths
        assert "/v1/agent/converse" in paths
        assert "/v1/agent/executions/{execution_id}/trace" in paths
        assert "/v1/agent/executions/{execution_id}/diagnosis" in paths
        assert "/v1/admin/notifications" in paths
        assert "/v1/admin/notifications/{notification_id}/ack" in paths

    def test_admin_shell_serves(self, profile: RuntimeProfile) -> None:
        async def scenario() -> None:
            async with _client(profile.app) as c:
                index = await c.get("/admin/")
                assert index.status_code == 200
                assert "Admin Console" in index.text
                js = await c.get("/admin/app.js")
                assert js.status_code == 200

        run(scenario())

    def test_skill_review_seam_absent_means_routes_absent(
        self, profile: RuntimeProfile
    ) -> None:
        """20 §4: no SkillReviewSurface composed ⇒ no /v1/admin/skills/*."""
        paths = set(profile.app.openapi()["paths"])
        assert not any(p.startswith("/v1/admin/skills") for p in paths)


# --- 2: nothing rebuilt — same-instance pass-through, source-pinned ----------


class TestNoRebuilding:
    def test_wiring_hands_over_the_same_composed_instances(self) -> None:
        """Source pin: every AgentToolSurface field is the EXISTING object
        (locals composed above / app.state seams create_app derived) —
        no constructor call appears inside the attach block."""
        source = RUNTIME_PY.read_text(encoding="utf-8")
        block = source.split("attach_admin_console(", 1)[1].split("auth=auth,", 1)[0]
        for line in (
            "execution_store=store,",
            "admin=admin,",
            "usage=usage,",
            "audit=audit,",
            "capabilities=app.state.capability_catalog,",
            "exercise=app.state.exercise_surface,",
            "scenarios=app.state.scenario_service,",
            "context_lab=app.state.context_lab_service,",
            "learning_observability=app.state.learning_observability_service,",
            "self_review=app.state.self_review_service,",
        ):
            assert line in block, f"missing same-instance pass-through: {line}"
        # The ONLY construction inside the block is the surface dataclass
        # itself — no service/store/registry is newly built here.
        assert "AgentToolSurface(" in block
        assert "InMemoryExecutionStore(" not in block
        assert "AdminConfigService(" not in block
        assert "InMemoryUsageAccounting(" not in block
        assert "InMemoryAuditLog(" not in block


# --- 3: nothing shadowed ------------------------------------------------------


class TestNoShadowing:
    def test_existing_surfaces_answer_as_before(
        self, profile: RuntimeProfile
    ) -> None:
        async def scenario() -> None:
            async with _client(profile.app) as c:
                health = await c.get("/healthz")
                assert health.status_code == 200
                assert health.json()["status"] == "alive"
                models = await c.get("/v1/models")
                assert models.status_code == 200
                execute = await c.post("/v1/execute", json={"ask": "ping"})
                assert execute.status_code == 200
                end_user = await c.get("/app/")
                assert end_user.status_code == 200
                assert "AI Orchestration Platform" in end_user.text

        run(scenario())


# --- 4: honest auth posture on the console routes ------------------------------


class TestConsoleAuthPosture:
    def test_anonymous_gets_the_one_constant_401(
        self, profile: RuntimeProfile
    ) -> None:
        """Every console route: anonymous ⇒ the SAME constant 401 body
        (20 §6 anti-enumeration — demo profile included: the main app may
        run a fixed principal, the console still authenticates)."""

        async def scenario() -> None:
            async with _client(profile.app) as c:
                responses = [
                    await c.get("/v1/agent/tools"),
                    await c.post("/v1/agent/converse", json={"message": "hi"}),
                    await c.get("/v1/admin/notifications"),
                ]
            bodies = [(r.status_code, r.json()) for r in responses]
            assert all(status == 401 for status, _ in bodies)
            # Byte-identical rejection across routes (constant message).
            assert len({str(body) for _, body in bodies}) == 1

        run(scenario())

    def test_garbage_token_gets_the_same_401(
        self, profile: RuntimeProfile
    ) -> None:
        async def scenario() -> None:
            headers = {"Authorization": "Bearer not-a-real-session"}
            async with _client(profile.app) as c:
                anon = await c.get("/v1/agent/tools")
                bad = await c.get("/v1/agent/tools", headers=headers)
            assert bad.status_code == 401
            assert bad.json() == anon.json()

        run(scenario())
