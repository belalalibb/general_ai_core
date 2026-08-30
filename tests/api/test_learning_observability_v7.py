"""V7 chunk 5 — Learning observability ("what changed since last review").

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Learning observability ('what changed
since last review' with evidence)" plus "Agent gains the corresponding
tools":

- HONEST MEANING (R049 (a), 41 §49): the report surfaces what the
  platform ACTUALLY changes through — audit events, config lifecycle —
  with evidence rows for every count; the learning-machinery section
  restates the structural placeholder truth and the closed 22 §9/§11
  condition sets as data. NO fabricated metrics anywhere.
- EXPLICIT REVIEW ACT: mark_reviewed is self-evidencing (returns new +
  previous markers); the report windows on the marker; NO marker =
  "never reviewed" with the full history as the delta, loudly.
- R0 PURITY: the report reads; it never triggers executions (the
  regression-posture section POINTS at the signal source).
- TENANT SCOPE (20 §6): markers and windows are per-tenant.
- GATES: non-admin 403; absent admin surface = absent routes/tools.
- AGENT PARITY (P3): same service, two consumers; changes_since_review
  R0, mark_reviewed R1.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.admin_agent.contracts import ToolClass
from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api import create_app
from apps.api.learning_observability import LearningObservabilityService
from apps.api.store import InMemoryExecutionStore
from core.contracts.admin import AdminAction
from core.contracts.audit import AuditEvent, AuditEventType
from core.execution.service import ExecutionService
from core.learning import PROMOTION_CONDITIONS, TRAINING_ELIGIBILITY_CONDITIONS
from tests.api.test_admin_api import World, _no_sleep


def _app_with_audit(world: World) -> FastAPI:
    """World.app(), but with the audit seam on the admin surface.

    World.surface() leaves AdminSurface.audit at its None default (the
    audit routes are AA-1's concern there); the observability audit
    section composes over that seam, so these route tests inject it —
    the same pattern the aa1 guard app uses.
    """
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=dataclasses.replace(world.surface(), audit=world.audit),
    )


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


async def _post(
    app: FastAPI, path: str, body: dict[str, object] | None = None
) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(path, json=body)


REPORT = "/v1/admin/learning/changes-since-review"
MARK = "/v1/admin/learning/mark-reviewed"


def _seed_audit(world: World, count: int = 2) -> None:
    for _ in range(count):
        world.audit.append(
            AuditEvent(
                tenant_id=world.principal.tenant_id,
                event_type=AuditEventType.TOOL_CALL,
            )
        )


def _seed_config_change(world: World) -> None:
    world.admin.draft(
        tenant_id=world.principal.tenant_id,
        actor_id=world.principal.user_id,
        action=AdminAction.DISABLE_MODEL,
        payload={"model_key": "model-a"},
    )


# --- module ------------------------------------------------------------------------


class TestServiceModule:
    def test_unreviewed_report_shows_full_history_loudly(self) -> None:
        world = World()
        _seed_audit(world, 3)
        _seed_config_change(world)
        service = LearningObservabilityService(
            audit=world.audit, admin_service=world.admin
        )
        report = service.changes_since_review(world.principal.tenant_id)
        assert report["reviewed"] is False
        assert report["since"] is None
        audit = report["audit"]
        assert isinstance(audit, dict)
        assert audit["events_in_window"] == 3
        assert audit["by_type"] == {"tool_call": 3}
        assert len(audit["evidence"]) == 3
        config = report["config_changes"]
        assert isinstance(config, dict)
        assert config["changes_in_window"] == 1
        assert config["by_state"] == {"draft": 1}

    def test_mark_reviewed_is_self_evidencing_and_windows_the_report(self) -> None:
        world = World()
        _seed_audit(world, 2)
        service = LearningObservabilityService(
            audit=world.audit, admin_service=world.admin
        )
        tenant = world.principal.tenant_id
        first = service.mark_reviewed(tenant, world.principal.user_id)
        assert first["previous"] is None
        assert first["reviewed_by"] == str(world.principal.user_id)
        # The pre-review events fall OUT of the window.
        report = service.changes_since_review(tenant)
        assert report["reviewed"] is True
        assert report["since"] == first["reviewed_at"]
        audit = report["audit"]
        assert isinstance(audit, dict)
        assert audit["events_in_window"] == 0
        # New activity after the marker falls IN.
        _seed_audit(world, 1)
        audit_after = service.changes_since_review(tenant)["audit"]
        assert isinstance(audit_after, dict)
        assert audit_after["events_in_window"] == 1
        # Re-marking returns the PREVIOUS marker (the closed window).
        second = service.mark_reviewed(tenant, world.principal.user_id)
        previous = second["previous"]
        assert isinstance(previous, dict)
        assert previous["reviewed_at"] == first["reviewed_at"]

    def test_evidence_is_bounded_and_says_so(self) -> None:
        world = World()
        _seed_audit(world, 5)
        service = LearningObservabilityService(audit=world.audit, evidence_limit=2)
        audit = service.changes_since_review(world.principal.tenant_id)["audit"]
        assert isinstance(audit, dict)
        assert audit["events_in_window"] == 5  # count covers the whole window
        assert len(audit["evidence"]) == 2  # rows are bounded
        assert audit["evidence_truncated"] is True

    def test_absent_seams_answer_absent_never_fabricate(self) -> None:
        service = LearningObservabilityService()  # no stores at all
        report = service.changes_since_review(uuid4())
        assert report["audit"] == {"available": False}
        assert report["config_changes"] == {"available": False}
        # The structural truths still ride: placeholder + closed sets.
        machinery = report["learning_machinery"]
        assert isinstance(machinery, dict)
        assert machinery["placeholder"] is True
        assert machinery["training_eligibility_conditions"] == list(
            TRAINING_ELIGIBILITY_CONDITIONS
        )
        assert machinery["promotion_conditions"] == list(PROMOTION_CONDITIONS)

    def test_markers_are_tenant_scoped(self) -> None:
        world = World()
        service = LearningObservabilityService(audit=world.audit)
        tenant_a, tenant_b = uuid4(), uuid4()
        service.mark_reviewed(tenant_a, uuid4())
        assert service.changes_since_review(tenant_a)["reviewed"] is True
        assert service.changes_since_review(tenant_b)["reviewed"] is False

    def test_regression_posture_points_never_runs(self) -> None:
        service = LearningObservabilityService()
        posture = service.changes_since_review(uuid4())["regression_posture"]
        assert isinstance(posture, dict)
        assert posture["signal"] == "regression_pass"
        assert posture["produced_by"] == "POST /v1/admin/scenarios/regression-pack"


# --- HTTP surface ------------------------------------------------------------------


class TestRoutes:
    def test_report_route_serves_the_windowed_facts(self) -> None:
        world = World()
        _seed_audit(world, 1)
        app = _app_with_audit(world)
        body = run(_get(app, REPORT)).json()
        assert body["reviewed"] is False
        audit = body["audit"]
        assert audit["available"] is True
        assert audit["events_in_window"] == 1
        assert body["learning_machinery"]["placeholder"] is True

    def test_mark_then_report_windows_over_http(self) -> None:
        world = World()
        _seed_audit(world, 2)
        app = _app_with_audit(world)
        marked = run(_post(app, MARK)).json()
        assert marked["previous"] is None
        report = run(_get(app, REPORT)).json()
        assert report["reviewed"] is True
        assert report["since"] == marked["reviewed_at"]
        assert report["audit"]["events_in_window"] == 0

    def test_config_lifecycle_activity_lands_in_the_window(self) -> None:
        world = World()
        app = world.app()
        run(_post(app, MARK))
        _seed_config_change(world)
        report = run(_get(app, REPORT)).json()
        config = report["config_changes"]
        assert config["changes_in_window"] == 1
        assert config["by_state"] == {"draft": 1}
        assert config["evidence"][0]["action"] == "disable_model"

    def test_non_admin_denied_on_both_routes(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        for response in (run(_get(app, REPORT)), run(_post(app, MARK))):
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "unauthorized"

    def test_absent_admin_surface_means_no_routes(self) -> None:
        world = World()
        app = world.app(with_admin=False)
        assert run(_get(app, REPORT)).status_code == 404
        assert run(_post(app, MARK)).status_code == 404


# --- agent tools -------------------------------------------------------------------


def _agent_surface(
    world: World, service: LearningObservabilityService | None
) -> AgentToolSurface:
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
        learning_observability=service,
    )


class TestAgentTools:
    def test_tool_classes_pinned(self) -> None:
        # Reading the report is R0 (pure read). MARKING a review is a
        # state change — R1 (recorded decision: bounded reversible ops
        # act; R2 stays the config lifecycle's tier).
        world = World()
        service = world.app().state.learning_observability_service
        registry = build_registry(_agent_surface(world, service))
        report_spec = registry.get("changes_since_review")
        mark_spec = registry.get("mark_reviewed")
        assert report_spec is not None
        assert report_spec.tool_class is ToolClass.R0_READ
        assert mark_spec is not None
        assert mark_spec.tool_class is ToolClass.R1_EXECUTE_TEST

    def test_agent_report_matches_the_route(self) -> None:
        world = World()
        _seed_audit(world, 1)
        app = world.app()
        service = app.state.learning_observability_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(
            dispatcher.dispatch(world.principal, "changes_since_review", {})
        )
        assert record.ok
        route_body = run(_get(app, REPORT)).json()
        assert record.result is not None
        # Same windowed facts through both consumers (the dispatch itself
        # appends a tool_call audit row AFTER the report was computed, so
        # compare the sections, not the whole audit count).
        assert record.result["reviewed"] == route_body["reviewed"]
        assert record.result["config_changes"] == route_body["config_changes"]
        assert record.result["learning_machinery"] == (
            route_body["learning_machinery"]
        )

    def test_agent_mark_windows_the_shared_service(self) -> None:
        world = World()
        _seed_audit(world, 2)
        app = world.app()
        service = app.state.learning_observability_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "mark_reviewed", {}))
        assert record.ok
        assert record.result is not None
        assert record.result["previous"] is None
        # The SAME service backs the HTTP route: the window moved there too.
        report = run(_get(app, REPORT)).json()
        assert report["reviewed"] is True

    def test_absent_field_means_absent_tools(self) -> None:
        world = World()
        registry = build_registry(_agent_surface(world, None))
        assert "changes_since_review" not in registry.names()
        assert "mark_reviewed" not in registry.names()

    def test_non_admin_dispatch_refused(self) -> None:
        world = World()
        service = world.app().state.learning_observability_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        non_admin = dataclasses.replace(world.principal, is_admin=False)
        for name in ("changes_since_review", "mark_reviewed"):
            record = run(dispatcher.dispatch(non_admin, name, {}))
            assert not record.ok, name
            assert record.refusal == "admin access required"
