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
5. **External skill acquisition is composed (R160)**: the EXISTING 14 §3
   pipeline (SkillReviewSurface over SkillImportService) is wired over the
   SAME SkillRegistry the /v1/skills listing and /v1/execute admission
   read — so /v1/admin/skills/* exist in both profiles and an ACTIVATED
   import becomes selectable with no second registry.

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
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture()
def profile() -> RuntimeProfile:
    return build_runtime_profile(environ={})


# --- 1: the console routes and shell exist on the runtime app ----------------


class TestConsoleIsPartOfRuntime:
    def test_agent_and_notification_routes_exist(self, profile: RuntimeProfile) -> None:
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

    def test_skill_acquisition_routes_are_composed(self, profile: RuntimeProfile) -> None:
        """R160: the 14 §3 pipeline is part of the runtime (both profiles)."""
        paths = set(profile.app.openapi()["paths"])
        for step in ("import", "imports", "imports/{skill_id}/activate"):
            assert f"/v1/admin/skills/{step}" in paths, step


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
        # The ONLY constructions inside the block are the surface dataclasses
        # (AgentToolSurface; the SkillReviewSurface pipeline holder over the
        # SAME ``skills`` registry) — no service/store/registry is newly
        # built here.
        assert "AgentToolSurface(" in block
        assert "skill_review=SkillReviewSurface(" in block
        assert "registry=skills)" in block
        assert "SkillRegistry(" not in block
        assert "InMemoryExecutionStore(" not in block
        assert "AdminConfigService(" not in block
        assert "InMemoryUsageAccounting(" not in block
        assert "InMemoryAuditLog(" not in block


# --- 3: nothing shadowed ------------------------------------------------------


class TestNoShadowing:
    def test_existing_surfaces_answer_as_before(self, profile: RuntimeProfile) -> None:
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
    def test_anonymous_gets_the_one_constant_401(self, profile: RuntimeProfile) -> None:
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

    def test_garbage_token_gets_the_same_401(self, profile: RuntimeProfile) -> None:
        async def scenario() -> None:
            headers = {"Authorization": "Bearer not-a-real-session"}
            async with _client(profile.app) as c:
                anon = await c.get("/v1/agent/tools")
                bad = await c.get("/v1/agent/tools", headers=headers)
            assert bad.status_code == 401
            assert bad.json() == anon.json()

        run(scenario())


# --- 5: external skill acquisition end-to-end over the runtime ---------------


ADMIN_EMAIL = "skills-admin@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential


def _admin_token(profile: RuntimeProfile) -> str:
    """Register + verify + login an ADMIN through the runtime's own identity.

    The console sender resolves stdout lazily, so redirect_stdout captures
    the verification token — the only honest way to obtain it (20 §5).
    """
    import contextlib
    import io
    import json

    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(ADMIN_EMAIL, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(ADMIN_EMAIL, PASSWORD).token


def _manifest(skill_id: str) -> dict[str, Any]:
    return {
        "id": skill_id,
        "name": "Acquired Review Skill",
        "version": "1.0.0",
        "type": "tool_enabled",
        "source": "imported",
        "status": "imported",
        "capabilities": ["review"],
        "requires_tools": {"required": ["fs_read"]},
    }


class TestExternalSkillAcquisition:
    def test_import_review_approve_activate_then_selectable(self) -> None:
        """import → scan → validate → review → approve → activate → listed
        by /v1/skills and admissible in /v1/execute — ONE registry."""
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        token = _admin_token(profile)
        headers = {"Authorization": f"Bearer {token}"}
        skill_key = "acquired_review"

        async def scenario() -> None:
            async with _client(profile.app) as c:
                # Not selectable before acquisition (deny-by-default).
                before = await c.get("/v1/skills")
                assert skill_key not in [s["id"] for s in before.json()["skills"]]

                imported = await c.post(
                    "/v1/admin/skills/import",
                    json={
                        "manifest": _manifest(skill_key),
                        "content": "# Review skill\nReview the diff carefully.",
                        "source_url": "https://github.com/mattpocock/skills/review",
                        "source_version": "abc123",
                    },
                    headers=headers,
                )
                assert imported.status_code == 201, imported.text
                sid = imported.json()["skill_id"]
                assert imported.json()["status"] == "imported"
                assert imported.json()["source"] == "imported"

                # Still NOT selectable mid-pipeline.
                mid = await c.get("/v1/skills")
                assert skill_key not in [s["id"] for s in mid.json()["skills"]]
                # Skipping steps refuses loudly (409, core refusal verbatim).
                early = await c.post(f"/v1/admin/skills/imports/{sid}/activate", headers=headers)
                assert early.status_code == 409

                for step, body in (
                    ("scan", {"findings": []}),
                    ("validate", None),
                    ("review", None),
                    ("approve", None),
                ):
                    r = await c.post(
                        f"/v1/admin/skills/imports/{sid}/{step}", json=body, headers=headers
                    )
                    assert r.status_code == 200, (step, r.text)
                reviewed = r.json()
                assert reviewed["status"] == "approved"
                # Reviewer = the authenticated principal, never a claimed name.
                assert reviewed["provenance"]["reviewed_by"]

                activated = await c.post(
                    f"/v1/admin/skills/imports/{sid}/activate", headers=headers
                )
                assert activated.status_code == 200, activated.text
                assert activated.json()["status"] == "active"
                assert activated.json()["source"] == "local"  # 41 §16 Local Version
                # Holding area drained; registry is the single home now.
                pending = await c.get("/v1/admin/skills/imports", headers=headers)
                assert pending.status_code == 200
                assert sid not in [s["skill_id"] for s in pending.json()["imports"]]

                # SAME registry: selectable through the generic listing …
                after = await c.get("/v1/skills")
                ids = [s["id"] for s in after.json()["skills"]]
                assert skill_key in ids
                # … and admissible in /v1/execute (skill→tool disclosure rides
                # the agent strategy; here we pin admission itself).
                executed = await c.post(
                    "/v1/execute", json={"ask": "review this", "skills": [skill_key]}
                )
                assert executed.status_code == 200, executed.text
                assert executed.json()["status"] == "succeeded"
                # Control: an unacquired skill id is still refused (422).
                refused = await c.post(
                    "/v1/execute", json={"ask": "x", "skills": ["never_acquired"]}
                )
                assert refused.status_code == 422

        run(scenario())

    def test_non_admin_cannot_acquire(self) -> None:
        profile = build_runtime_profile(environ={})

        # Demo principal (in-memory profile) is NOT admin.
        async def scenario() -> None:
            async with _client(profile.app) as c:
                r = await c.post(
                    "/v1/admin/skills/import",
                    json={
                        "manifest": _manifest("x"),
                        "content": "x",
                        "source_url": "https://github.com/mattpocock/skills/x",
                        "source_version": "1",
                    },
                )
                assert r.status_code in (401, 403)

        run(scenario())

    def test_unlisted_source_is_refused(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        headers = {"Authorization": f"Bearer {_admin_token(profile)}"}

        async def scenario() -> None:
            async with _client(profile.app) as c:
                r = await c.post(
                    "/v1/admin/skills/import",
                    json={
                        "manifest": _manifest("evil"),
                        "content": "x",
                        "source_url": "https://evil.example/skills",
                        "source_version": "1",
                    },
                    headers=headers,
                )
                assert r.status_code == 422

        run(scenario())
