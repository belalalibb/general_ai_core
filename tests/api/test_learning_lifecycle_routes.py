"""R158 — /v1/admin/learning/* lifecycle routes over the composed app.

Hermetic (httpx ASGI transport; asyncio.run per ADR-0001). Proves:

- The FULL lifecycle operates end-to-end over HTTP: capture is a service
  act (no ingestion route this slice — recorded: capture producers are a
  later conscious wiring; the admin manages samples that exist), then
  sanitize → admit (22 §9 signals) → promote (22 §11 signals) → learned
  keys → isolated ask — every hop a real admin route.
- Deny-by-default surfaces: non-admin principals get 403-shaped denials
  on EVERY learning route; absent seam (no memory) = absent routes (404).
- Honest refusals: an unsanitized sample's admit is a 200 with
  admitted=false naming the failed condition; promotion with default
  (all-false) signals is a 200 with promoted=false naming every gate.
- The catalog row: learning.lifecycle is AVAILABLE when composed here
  and INERT in a composition without the memory seam.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api import create_app
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryMemoryStore
from tests.api.test_admin_api import World, _no_sleep

SAMPLES = "/v1/admin/learning/samples"
LEARNED = "/v1/admin/learning/learned"
ASK = "/v1/admin/learning/ask"

ALL_ADMIT = {
    "privacy_policy_allows": True,
    "tenant_user_policy_allows": True,
    "sensitive_data_handled": True,
    "deduplicated": True,
    "not_poisoned": True,
}
ALL_PROMOTE = {
    "offline_eval_pass": True,
    "regression_pass": True,
    "security_eval_pass": True,
    "shadow_performance_acceptable": True,
    "canary_performance_acceptable": True,
    "rollback_plan_exists": True,
    "approval_required": True,
    "admin_approved": True,
}


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _app(world: World, *, with_memory: bool = True) -> FastAPI:
    """Composed app with audit + memory seams (the R158 composition)."""
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
        memory=InMemoryMemoryStore() if with_memory else None,
    )


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


async def _post(
    app: FastAPI, path: str, body: dict[str, object] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body if body is not None else {})


def _capture(app: FastAPI, world: World, key: str) -> str:
    """Capture through the composed service (the state the routes manage)."""
    service = app.state.learning_lifecycle_service
    assert service is not None
    sample = service.capture_from_execution(
        world.principal.tenant_id,
        uuid4(),
        knowledge_key=key,
        knowledge_value={"answer": f"learned answer for {key}"},
    )
    return str(sample.id)


class TestLifecycleOverHttp:
    def test_full_chain_sanitize_admit_promote_learned_ask(self) -> None:
        world = World()
        app = _app(world)
        sample_id = _capture(app, world, "ops.rollback")

        # listed + report shows PENDING everything
        listing = run(_get(app, SAMPLES))
        assert listing.status_code == 200
        assert len(listing.json()["samples"]) == 1
        report = run(_get(app, f"{SAMPLES}/{sample_id}"))
        assert report.json()["sample"]["eligibility"] == "pending"

        # sanitize (explicit act)
        sanitized = run(
            _post(app, f"{SAMPLES}/{sample_id}/sanitize", {"passed": True})
        )
        assert sanitized.status_code == 200
        assert sanitized.json()["sanitization_state"] == "passed"

        # admit through the 22 §9 gate
        admitted = run(_post(app, f"{SAMPLES}/{sample_id}/admit", ALL_ADMIT))
        assert admitted.status_code == 200
        assert admitted.json()["admitted"] is True
        assert admitted.json()["sample"]["eligibility"] == "eligible"

        # promote through the 22 §11 gate → GOLD + knowledge
        promoted = run(_post(app, f"{SAMPLES}/{sample_id}/promote", ALL_PROMOTE))
        assert promoted.status_code == 200
        assert promoted.json()["promoted"] is True
        assert promoted.json()["knowledge_key"] == "ops.rollback"

        # learned keys + the ISOLATED ask path
        keys = run(_get(app, LEARNED))
        assert keys.json()["keys"] == ["ops.rollback"]
        answer = run(_post(app, ASK, {"key": "ops.rollback"}))
        assert answer.json()["found"] is True
        assert answer.json()["answer"]["answer"] == "learned answer for ops.rollback"
        # deny-by-default: unlearned key is explicit not-found
        missing = run(_post(app, ASK, {"key": "never.taught"}))
        assert missing.json()["found"] is False

    def test_honest_gate_refusals_over_http(self) -> None:
        world = World()
        app = _app(world)
        sample_id = _capture(app, world, "k.refusals")

        # admit WITHOUT sanitization: 200, admitted=false, condition named
        refused = run(_post(app, f"{SAMPLES}/{sample_id}/admit", ALL_ADMIT))
        assert refused.status_code == 200
        assert refused.json()["admitted"] is False
        assert "sanitized" in refused.json()["reason"]

        # promote with default all-false signals after fixing eligibility
        run(_post(app, f"{SAMPLES}/{sample_id}/sanitize", {"passed": True}))
        run(_post(app, f"{SAMPLES}/{sample_id}/admit", ALL_ADMIT))
        denied = run(_post(app, f"{SAMPLES}/{sample_id}/promote", {}))
        assert denied.status_code == 200
        assert denied.json()["promoted"] is False
        assert "offline_eval_pass" in denied.json()["reason"]

    def test_unknown_sample_is_not_found(self) -> None:
        world = World()
        app = _app(world)
        response = run(_get(app, f"{SAMPLES}/{uuid4()}"))
        assert response.status_code == 404


class TestDenyByDefault:
    def test_non_admin_denied_on_every_learning_route(self) -> None:
        world = World(is_admin=False)
        app = _app(world)
        sid = uuid4()
        probes = [
            run(_get(app, SAMPLES)),
            run(_get(app, f"{SAMPLES}/{sid}")),
            run(_post(app, f"{SAMPLES}/{sid}/sanitize", {"passed": True})),
            run(_post(app, f"{SAMPLES}/{sid}/admit", ALL_ADMIT)),
            run(_post(app, f"{SAMPLES}/{sid}/promote", ALL_PROMOTE)),
            run(_get(app, LEARNED)),
            run(_post(app, ASK, {"key": "x"})),
            run(_post(app, SAMPLES, {"knowledge_key": "k", "knowledge_value": {}})),
            run(_post(app, f"{SAMPLES}/{sid}/evaluate", {"output": {}})),
        ]
        for response in probes:
            assert response.status_code == 403, response.status_code


class TestHttpEntry:
    """R159 — the lifecycle's HTTP entry closes the R158 recorded producer
    gap: capture (execution-born OR external) and evaluate ride routes."""

    def test_external_capture_enters_pending_pipeline(self) -> None:
        world = World()
        app = _app(world)
        created = run(
            _post(
                app,
                SAMPLES,
                {"knowledge_key": "ext.rule", "knowledge_value": {"answer": 1}},
            )
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["eligibility"] == "pending"
        assert body["sanitization_state"] == "pending"
        assert body["verification_level"] == "RAW"
        report = run(_get(app, f"{SAMPLES}/{body['id']}"))
        assert report.json()["source_kind"] == "external"
        # never trusted on entry: GOLD path still gated
        assert run(_get(app, LEARNED)).json()["keys"] == []

    def test_execution_born_capture_requires_tenant_visible_execution(
        self,
    ) -> None:
        world = World()
        app = _app(world)
        # Unknown / foreign execution id => 404 (anti-enumeration).
        missing = run(
            _post(
                app,
                SAMPLES,
                {
                    "knowledge_key": "k",
                    "knowledge_value": {},
                    "source_execution_id": str(uuid4()),
                },
            )
        )
        assert missing.status_code == 404
        # A REAL execution through the platform's execute path => captured.
        world.usage.configure_tenant(
            world.principal.tenant_id, plan="pro", task_units_limit=100.0
        )
        transport = httpx.ASGITransport(app=app)

        async def execute() -> str:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t"
            ) as c:
                r = await c.post("/v1/execute", json={"ask": "hello"})
            assert r.status_code == 200, r.text
            execution_id: str = r.json()["execution_id"]
            return execution_id

        execution_id = run(execute())
        created = run(
            _post(
                app,
                SAMPLES,
                {
                    "knowledge_key": "exec.k",
                    "knowledge_value": {"answer": "x"},
                    "source_execution_id": execution_id,
                },
            )
        )
        assert created.status_code == 201, created.text
        assert created.json()["source_execution_id"] == execution_id
        report = run(_get(app, f"{SAMPLES}/{created.json()['id']}"))
        assert report.json()["source_kind"] == "execution"

    def test_evaluate_binds_level_through_existing_grader(self) -> None:
        world = World()
        app = _app(world)
        sample_id = _capture(app, world, "eval.k")
        evaluated = run(
            _post(app, f"{SAMPLES}/{sample_id}/evaluate", {"output": {"a": 1}})
        )
        assert evaluated.status_code == 200, evaluated.text
        assert evaluated.json()["evaluated"] is True
        assert evaluated.json()["sample"]["verification_level"] == "VALIDATED"
        unknown = run(_post(app, f"{SAMPLES}/{uuid4()}/evaluate", {"output": {}}))
        assert unknown.status_code == 404

    def test_absent_memory_seam_means_absent_routes_and_inert_catalog(
        self,
    ) -> None:
        world = World()
        app = _app(world, with_memory=False)
        assert run(_get(app, SAMPLES)).status_code == 404
        assert app.state.learning_lifecycle_service is None
        catalog = {
            c.id: c.state.value for c in app.state.capability_catalog
        }
        assert catalog["learning.lifecycle"] == "inert"

    def test_composed_seam_reports_available_in_catalog(self) -> None:
        world = World()
        app = _app(world)
        catalog = {c.id: c.state.value for c in app.state.capability_catalog}
        assert catalog["learning.lifecycle"] == "available"
