"""V7 chunk 6 — Self-Review + Change Impact Simulator (LAST V7 chunk).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Self-Review + Change Impact Simulator
(evidence-backed proposals, never auto-apply)" plus "Agent gains the
corresponding tools":

- SELF-REVIEW = ASSEMBLY (P1): sections are the EXISTING evidence
  surfaces (catalog rows with evidence pointers, lifecycle states with
  bounded evidence, scenario posture, review state) — facts +
  provenance, no scores, no fabricated metrics (41 §49). Absent seams
  answer available:False (P6).
- THE SIMULATOR IS THE LIFECYCLE: propose runs draft→validate→preview
  through the REAL AdminConfigService; the lifecycle's own
  validation_result + impact_preview ARE the evidence; a validation
  refusal is an honest 'rejected' outcome carrying the lifecycle's own
  reason.
- NEVER AUTO-APPLY, proven: after proposing, the change is VALIDATED
  (never PUBLISHED), the registries are UNTOUCHED, and NO
  ADMIN_CONFIG_PUBLISHED audit row exists; the proposal names the
  human publish route.
- GATES: non-admin 403; absent admin surface = absent routes/tools.
- AGENT PARITY (P3): self_review R0, propose_change R2 (the existing
  draft/validate/preview tier), same service both consumers.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.admin_agent.contracts import ToolClass
from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api.self_review import SelfReviewService
from apps.api.store import InMemoryExecutionStore
from core.contracts.admin import AdminAction, ConfigLifecycleState
from core.contracts.audit import AuditEventType
from core.contracts.domain import ModelStatus
from core.execution.service import ExecutionService
from tests.api.test_admin_api import World, _no_sleep


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


async def _post(app: FastAPI, path: str, body: dict[str, object] | None = None) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(path, json=body)


REVIEW = "/v1/admin/self-review"
PROPOSE = "/v1/admin/changes/propose"
DISABLE_MODEL = {"action": "disable_model", "payload": {"model_key": "model-a"}}


# --- module ------------------------------------------------------------------------


class TestServiceModule:
    def test_absent_seams_answer_absent_never_fabricate(self) -> None:
        service = SelfReviewService()  # nothing composed
        review = service.self_review(uuid4())
        assert review["capabilities"] == {"available": False}
        assert review["config_lifecycle"] == {"available": False}
        assert review["scenarios"] == {"available": False}
        assert review["review_state"] == {"available": False}
        # The posture still rides — the reader always sees never-auto-apply.
        posture = review["posture"]
        assert isinstance(posture, dict)
        assert posture["auto_apply"] == "never"

    def test_propose_without_lifecycle_seam_fails_loudly(self) -> None:
        service = SelfReviewService()
        try:
            service.propose_change(uuid4(), uuid4(), AdminAction.DISABLE_MODEL, {"model_key": "x"})
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "lifecycle seam" in str(exc)


# --- HTTP: self-review -------------------------------------------------------------


class TestSelfReviewRoute:
    def test_review_assembles_the_existing_surfaces(self) -> None:
        world = World()
        app = world.app()
        body = run(_get(app, REVIEW)).json()
        # Capabilities: the composed catalog rows, each with evidence.
        capabilities = body["capabilities"]
        assert capabilities["available"] is True
        assert all(set(row.keys()) == {"id", "state", "evidence"} for row in capabilities["rows"])
        assert sum(capabilities["by_state"].values()) == len(capabilities["rows"])
        # Lifecycle: honest zero, evidence not truncated.
        lifecycle = body["config_lifecycle"]
        assert lifecycle["available"] is True
        assert lifecycle["total"] == 0
        assert lifecycle["evidence"] == []
        # Scenarios: none saved; the refresh act is POINTED at, not run.
        scenarios = body["scenarios"]
        assert scenarios["saved"] == 0
        assert scenarios["refresh_via"] == "POST /v1/admin/scenarios/regression-pack"
        # Review state: never reviewed, full report pointed at.
        review_state = body["review_state"]
        assert review_state["reviewed"] is False
        assert review_state["full_report"] == ("GET /v1/admin/learning/changes-since-review")
        assert body["posture"]["auto_apply"] == "never"

    def test_review_reflects_real_activity(self) -> None:
        world = World()
        app = world.app()
        # One real proposal + one real review mark change the sections.
        run(_post(app, PROPOSE, DISABLE_MODEL))
        run(_post(app, "/v1/admin/learning/mark-reviewed"))
        body = run(_get(app, REVIEW)).json()
        lifecycle = body["config_lifecycle"]
        assert lifecycle["total"] == 1
        assert lifecycle["by_state"] == {"validated": 1}
        assert lifecycle["evidence"][0]["action"] == "disable_model"
        assert body["review_state"]["reviewed"] is True


# --- HTTP: propose (the simulator) --------------------------------------------------


class TestProposeRoute:
    def test_proposal_composes_the_real_lifecycle(self) -> None:
        world = World()
        app = world.app()
        response = run(_post(app, PROPOSE, DISABLE_MODEL))
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "ready_for_review"
        change = body["change"]
        # The REAL lifecycle's artifacts are the evidence.
        assert change["state"] == "validated"
        assert body["evidence"]["validation_result"] == "passed"
        assert "routing pool" in body["evidence"]["impact_preview"]
        # Never auto-apply: the human route is NAMED, with the change id.
        assert body["apply"]["auto_apply"] == "never"
        assert body["apply"]["human_route"] == (f"POST /v1/admin/changes/{change['id']}/publish")

    def test_proposal_never_applies_anything(self) -> None:
        world = World()
        app = world.app()
        body = run(_post(app, PROPOSE, DISABLE_MODEL)).json()
        # (1) The change never reached PUBLISHED.
        stored = world.admin.get(world.principal.tenant_id, UUID(body["change"]["id"]))
        assert stored.state is ConfigLifecycleState.VALIDATED
        # (2) The live registry is UNTOUCHED — the model is still active.
        assert world.models.get("model-a").status is ModelStatus.ACTIVE
        # (3) No publish audit row exists (proposing is not applying).
        published = world.audit.read(
            world.principal.tenant_id,
            event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED,
        )
        assert published == ()
        # (4) A HUMAN can still publish the proposal through the existing
        # route — the proposal fed the real lifecycle, not a copy.
        publish = run(_post(app, f"/v1/admin/changes/{body['change']['id']}/publish"))
        assert publish.status_code == 200
        assert publish.json()["state"] == "published"

    def test_validation_refusal_is_an_honest_rejected_proposal(self) -> None:
        world = World()
        app = world.app()
        response = run(
            _post(
                app,
                PROPOSE,
                {"action": "disable_model", "payload": {"model_key": "no-such"}},
            )
        )
        assert response.status_code == 201  # the proposal HAPPENED
        body = response.json()
        assert body["outcome"] == "rejected"
        assert body["change"]["state"] == "rejected"
        # The lifecycle's own named reason IS the evidence.
        assert body["evidence"]["validation_result"].startswith("rejected:")
        assert "apply" not in body  # nothing to publish — terminal

    def test_inactive_area_is_the_requests_fault_422(self) -> None:
        world = World()
        app = world.app()
        response = run(_post(app, PROPOSE, {"action": "enable_tool", "payload": {}}))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_non_admin_denied_on_both_routes(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        for response in (
            run(_get(app, REVIEW)),
            run(_post(app, PROPOSE, DISABLE_MODEL)),
        ):
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "unauthorized"

    def test_absent_admin_surface_means_no_routes(self) -> None:
        world = World()
        app = world.app(with_admin=False)
        assert run(_get(app, REVIEW)).status_code == 404
        assert run(_post(app, PROPOSE, DISABLE_MODEL)).status_code == 404


# --- agent tools -------------------------------------------------------------------


def _agent_surface(world: World, service: SelfReviewService | None) -> AgentToolSurface:
    execution_service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return AgentToolSurface(
        providers=world.providers,
        models=world.models,
        router=world.router,
        execution_service=execution_service,
        execution_store=InMemoryExecutionStore(),
        admin=world.surface(),
        usage=world.usage,
        audit=world.audit,
        self_review=service,
    )


class TestAgentTools:
    def test_tool_classes_pinned(self) -> None:
        # self_review = R0 (pure read assembly). propose_change = R2 —
        # it creates config-lifecycle state, exactly the tier of the
        # existing draft/validate/preview tools (recorded decision).
        world = World()
        service = world.app().state.self_review_service
        registry = build_registry(_agent_surface(world, service))
        review_spec = registry.get("self_review")
        propose_spec = registry.get("propose_change")
        assert review_spec is not None
        assert review_spec.tool_class is ToolClass.R0_READ
        assert propose_spec is not None
        assert propose_spec.tool_class is ToolClass.R2_CONFIG_CHANGE
        assert propose_spec.allowed_args == frozenset({"action", "payload"})

    def test_agent_review_matches_the_route(self) -> None:
        world = World()
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.self_review_service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "self_review", {}))
        assert record.ok
        route_body = run(_get(app, REVIEW)).json()
        assert record.result == route_body

    def test_agent_proposal_runs_the_same_lifecycle(self) -> None:
        world = World()
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.self_review_service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "propose_change", dict(DISABLE_MODEL)))
        assert record.ok, record.refusal
        assert record.result is not None
        assert record.result["outcome"] == "ready_for_review"
        assert record.result["apply"]["auto_apply"] == "never"
        # The SAME lifecycle backs the HTTP surface: the change is listed.
        changes = run(_get(app, "/v1/admin/changes")).json()["changes"]
        assert len(changes) == 1
        assert changes[0]["state"] == "validated"
        # And still nothing was applied.
        assert world.models.get("model-a").status is ModelStatus.ACTIVE

    def test_agent_refusals_are_honest_content(self) -> None:
        world = World()
        service = world.app().state.self_review_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        # Unknown action.
        record = run(dispatcher.dispatch(world.principal, "propose_change", {"action": "explode"}))
        assert record.ok
        assert record.result is not None
        error = record.result["error"]
        assert isinstance(error, str) and error.startswith("unknown admin action")
        # Non-object payload.
        record = run(
            dispatcher.dispatch(
                world.principal,
                "propose_change",
                {"action": "disable_model", "payload": "not-a-dict"},
            )
        )
        assert record.ok
        assert record.result == {"error": "payload must be a JSON object"}

    def test_absent_field_means_absent_tools(self) -> None:
        world = World()
        registry = build_registry(_agent_surface(world, None))
        assert "self_review" not in registry.names()
        assert "propose_change" not in registry.names()

    def test_non_admin_dispatch_refused(self) -> None:
        world = World()
        service = world.app().state.self_review_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        non_admin = dataclasses.replace(world.principal, is_admin=False)
        for name, args in (
            ("self_review", {}),
            ("propose_change", dict(DISABLE_MODEL)),
        ):
            record = run(dispatcher.dispatch(non_admin, name, dict(args)))
            assert not record.ok, name
            assert record.refusal == "admin access required"
