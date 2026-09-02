"""V7 chunk 3 — Test Scenarios → Regression Center (saved, replayable).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Test Scenarios (saved, replayable) →
Regression Center pack" plus "Agent gains the corresponding tools":

- CLOSED CHECK SET: scenario checks are EXACTLY the platform's own
  deterministic checks (core/evaluation/policy.MVP_DETERMINISTIC_CHECKS,
  P1 — zero new grader machinery); an unknown name is a loud refusal at
  construction, over HTTP (422), and through the agent tool.
- REAL REPLAY: replaying a scenario runs a REAL budget-bounded execution
  as the admitted caller, labeled machine-checkably (SCENARIO_LABEL_KEY
  in the stored node's input_ref) and resolvable on the SAME poll
  surface a user reads. No entitlement ⇒ honest replayed:False.
- HONEST VERDICTS (P6): grades follow stored truth; the regression pack
  reports one ``regression_pass`` (the SAME signal name the learning
  gates consume) and an EMPTY pack honestly fails.
- GATES: non-admin 403 unauthorized on all four routes; absent, foreign
  and malformed scenario ids answer identically (404, 20 §6); absent
  admin surface ⇒ routes absent (20 §4).
- ONE STORE, TWO CONSUMERS: the agent's tools dispatch through
  app.state.scenario_service — registered only when composed; absent
  field ⇒ absent tools.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.admin_agent.contracts import ToolClass
from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api.scenarios import (
    SCENARIO_LABEL_KEY,
    Scenario,
    ScenarioService,
    UnknownCheckName,
)
from apps.api.store import InMemoryExecutionStore
from core.contracts.base import utc_now
from core.execution.service import ExecutionService
from tests.api.test_admin_api import World, _no_sleep

#: The closed set, sorted — exactly the platform's own deterministic checks.
ALL_CHECKS = ["error_free_output", "output_present"]


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


def _grant(world: World, limit: float = 100.0) -> None:
    world.usage.configure_tenant(world.principal.tenant_id, plan="test", task_units_limit=limit)


async def _save(app: FastAPI, name: str = "smoke", ask: str = "say hello") -> str:
    response = await _post(app, "/v1/admin/scenarios", {"name": name, "ask": ask})
    assert response.status_code == 201, response.text
    scenario_id = response.json()["scenario_id"]
    assert isinstance(scenario_id, str)
    return scenario_id


# --- module closure ----------------------------------------------------------------


class TestScenarioModule:
    def test_unknown_check_name_refused_at_construction(self) -> None:
        with pytest.raises(UnknownCheckName, match="closed"):
            Scenario(
                id=uuid4(),
                tenant_id=uuid4(),
                name="bad",
                ask="ask",
                checks=("output_present", "not_a_check"),
                created_at=utc_now(),
            )

    def test_service_save_refuses_unknown_checks(self) -> None:
        world = World()
        service = ScenarioService(
            router=world.router,
            execution_service=ExecutionService(
                adapters={world.provider.id: world.adapter},
                credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
                bindings=world.bindings,
                max_retries_per_candidate=0,
                usage=world.usage,
                sleeper=_no_sleep,
            ),
            execution_store=InMemoryExecutionStore(),
        )
        with pytest.raises(UnknownCheckName):
            service.save(
                world.principal.tenant_id,
                name="bad",
                ask="ask",
                checks=("model_graded_quality",),
            )
        # A refused save stores NOTHING — refusal is not partial data.
        assert service.list(world.principal.tenant_id) == []


# --- HTTP surface ------------------------------------------------------------------


class TestScenarioRoutes:
    def test_save_and_list_are_tenant_scoped(self) -> None:
        world = World()
        app = world.app()
        assert run(_get(app, "/v1/admin/scenarios")).json() == {"scenarios": []}
        scenario_id = run(_save(app, name="alpha", ask="ask alpha"))
        rows = run(_get(app, "/v1/admin/scenarios")).json()["scenarios"]
        assert [r["scenario_id"] for r in rows] == [scenario_id]
        assert rows[0]["name"] == "alpha"
        assert rows[0]["ask"] == "ask alpha"
        # Default checks = the FULL closed set, sorted.
        assert rows[0]["checks"] == ALL_CHECKS
        # A DIFFERENT tenant's app sees nothing (tenant scoping is real
        # only when the store is shared — here each app has its own
        # service, so assert the service-level scoping directly).
        service = app.state.scenario_service
        assert service.list(uuid4()) == []

    def test_unknown_check_name_is_a_422(self) -> None:
        world = World()
        response = run(
            _post(
                world.app(),
                "/v1/admin/scenarios",
                {"name": "bad", "ask": "ask", "checks": ["not_a_check"]},
            )
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"] == {"field": "checks"}

    def test_empty_checks_list_is_a_422(self) -> None:
        world = World()
        response = run(
            _post(
                world.app(),
                "/v1/admin/scenarios",
                {"name": "bad", "ask": "ask", "checks": []},
            )
        )
        assert response.status_code == 422

    def test_replay_runs_a_real_labeled_execution(self) -> None:
        # Explicit store so the label is assertable in the SAME store the
        # poll surface reads (no new persistence mechanism).
        from apps.api import create_app

        world = World()
        _grant(world)
        store = InMemoryExecutionStore()
        service = ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
            usage=world.usage,
            sleeper=_no_sleep,
        )
        app = create_app(
            router=world.router,
            execution_service=service,
            store=store,
            principal=world.principal,
            admin=world.surface(),
        )
        scenario_id = run(_save(app))
        response = run(_post(app, f"/v1/admin/scenarios/{scenario_id}/replay"))
        assert response.status_code == 200
        body = response.json()
        assert body["scenario_id"] == scenario_id
        assert body["replayed"] is True
        assert body["execution_status"] == "succeeded"
        assert body["passed"] is True
        assert {row["name"] for row in body["checks"]} == set(ALL_CHECKS)
        assert all(row["passed"] for row in body["checks"])
        execution_id = body["execution_id"]
        # Evidence resolves on the SAME poll surface a user reads.
        poll = run(_get(app, f"/v1/executions/{execution_id}"))
        assert poll.status_code == 200
        assert poll.json()["status"] == "succeeded"
        # The scenario label is machine-checkable in the stored node.
        report = store.get(world.principal.tenant_id, UUID(execution_id))
        assert len(report.nodes) == 1
        input_ref = report.nodes[0].node.input_ref
        assert isinstance(input_ref, dict)
        context = input_ref["context"]
        assert isinstance(context, dict)
        metadata = context["metadata"]
        assert isinstance(metadata, dict)
        assert metadata[SCENARIO_LABEL_KEY] == {"scenario_id": scenario_id}

    def test_no_entitlement_replay_is_honest(self) -> None:
        world = World()  # no budget configured
        app = world.app()
        scenario_id = run(_save(app))
        body = run(_post(app, f"/v1/admin/scenarios/{scenario_id}/replay")).json()
        assert body["replayed"] is False
        assert "entitlement" in body["error"]

    def test_empty_regression_pack_honestly_fails(self) -> None:
        world = World()
        body = run(_post(world.app(), "/v1/admin/scenarios/regression-pack")).json()
        assert body == {
            "scenario_count": 0,
            "regression_pass": False,
            "results": [],
        }

    def test_regression_pack_passes_when_every_scenario_passes(self) -> None:
        world = World()
        _grant(world)
        app = world.app()
        first = run(_save(app, name="first", ask="ask one"))
        second = run(_save(app, name="second", ask="ask two"))
        body = run(_post(app, "/v1/admin/scenarios/regression-pack")).json()
        assert body["scenario_count"] == 2
        assert body["regression_pass"] is True
        assert [r["scenario_id"] for r in body["results"]] == [first, second]
        assert all(r["replayed"] and r["passed"] for r in body["results"])

    def test_regression_pack_fails_when_a_replay_cannot_run(self) -> None:
        world = World()  # no entitlement — replays honestly fail
        app = world.app()
        run(_save(app))
        body = run(_post(app, "/v1/admin/scenarios/regression-pack")).json()
        assert body["scenario_count"] == 1
        assert body["regression_pass"] is False

    def test_unknown_scenario_ids_answer_identically(self) -> None:
        world = World()
        app = world.app()
        run(_save(app))  # a real scenario exists; these ids still 404
        foreign_app = World().app()
        real_id = run(_save(foreign_app))  # exists in ANOTHER service
        for scenario_id in (str(uuid4()), real_id, "not-a-uuid"):
            response = run(_post(app, f"/v1/admin/scenarios/{scenario_id}/replay"))
            assert response.status_code == 404, scenario_id
            body = response.json()
            assert set(body.keys()) == {"error"}
            assert body["error"]["code"] == "validation_error"

    def test_non_admin_denied_on_all_four_routes(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        responses = [
            run(_get(app, "/v1/admin/scenarios")),
            run(_post(app, "/v1/admin/scenarios", {"name": "x", "ask": "y"})),
            run(_post(app, f"/v1/admin/scenarios/{uuid4()}/replay")),
            run(_post(app, "/v1/admin/scenarios/regression-pack")),
        ]
        for response in responses:
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "unauthorized"

    def test_absent_admin_surface_means_no_routes(self) -> None:
        world = World()
        app = world.app(with_admin=False)
        assert run(_get(app, "/v1/admin/scenarios")).status_code == 404
        assert run(_post(app, "/v1/admin/scenarios", {"name": "x", "ask": "y"})).status_code == 404
        assert run(_post(app, f"/v1/admin/scenarios/{uuid4()}/replay")).status_code == 404
        assert run(_post(app, "/v1/admin/scenarios/regression-pack")).status_code == 404


# --- agent tools -------------------------------------------------------------------


def _agent_surface(world: World, scenarios: ScenarioService | None) -> AgentToolSurface:
    service = ExecutionService(
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
        execution_service=service,
        execution_store=InMemoryExecutionStore(),
        admin=world.surface(),
        usage=world.usage,
        audit=world.audit,
        scenarios=scenarios,
    )


class TestAgentScenarioTools:
    def test_tools_registered_with_correct_classes(self) -> None:
        # Recorded design decision: a scenario is TEST data, not platform
        # config — save/replay/pack are R1 (run_test_execution's risk
        # class), NOT R2; list is a pure R0 read.
        world = World()
        service = world.app().state.scenario_service
        registry = build_registry(_agent_surface(world, service))
        list_spec = registry.get("list_scenarios")
        save_spec = registry.get("save_scenario")
        replay_spec = registry.get("replay_scenario")
        pack_spec = registry.get("run_regression_pack")
        assert list_spec is not None and list_spec.tool_class is ToolClass.R0_READ
        assert save_spec is not None
        assert save_spec.tool_class is ToolClass.R1_EXECUTE_TEST
        assert save_spec.allowed_args == frozenset({"name", "ask", "checks"})
        assert replay_spec is not None
        assert replay_spec.tool_class is ToolClass.R1_EXECUTE_TEST
        assert replay_spec.allowed_args == frozenset({"scenario_id"})
        assert pack_spec is not None
        assert pack_spec.tool_class is ToolClass.R1_EXECUTE_TEST
        assert pack_spec.allowed_args == frozenset()

    def test_agent_save_then_route_list_sees_it(self) -> None:
        # ONE store, TWO consumers: a scenario the agent saves is exactly
        # what the admin route lists.
        world = World()
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.scenario_service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(
            dispatcher.dispatch(
                world.principal,
                "save_scenario",
                {"name": "agent-made", "ask": "say hi"},
            )
        )
        assert record.ok, record.refusal
        assert record.result is not None
        assert record.result["checks"] == ALL_CHECKS  # default = full set
        route_rows = run(_get(app, "/v1/admin/scenarios")).json()["scenarios"]
        assert [r["scenario_id"] for r in route_rows] == [record.result["scenario_id"]]

    def test_agent_save_refusals_are_honest_content(self) -> None:
        world = World()
        service = world.app().state.scenario_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        cases: list[tuple[dict[str, object], str]] = [
            ({"name": "", "ask": "x"}, "required"),
            ({"name": "x", "ask": ""}, "required"),
            ({"name": "x", "ask": "y", "checks": []}, "non-empty"),
            ({"name": "x", "ask": "y", "checks": "output_present"}, "non-empty"),
            ({"name": "x", "ask": "y", "checks": ["nope"]}, "closed"),
        ]
        for args, needle in cases:
            record = run(dispatcher.dispatch(world.principal, "save_scenario", args))
            assert record.ok, record.refusal  # honest error CONTENT
            assert record.result is not None
            error = record.result["error"]
            assert isinstance(error, str) and needle in error, args
        # No refused save left data behind.
        assert service.list(world.principal.tenant_id) == []

    def test_agent_replay_and_pack_run_real_executions(self) -> None:
        world = World()
        _grant(world)
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.scenario_service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        scenario_id = run(_save(app))
        record = run(
            dispatcher.dispatch(world.principal, "replay_scenario", {"scenario_id": scenario_id})
        )
        assert record.ok, record.refusal
        assert record.result is not None
        assert record.result["replayed"] is True
        assert record.result["passed"] is True
        pack = run(dispatcher.dispatch(world.principal, "run_regression_pack", {}))
        assert pack.ok, pack.refusal
        assert pack.result is not None
        assert pack.result["scenario_count"] == 1
        assert pack.result["regression_pass"] is True

    def test_agent_unknown_scenario_id_anti_enumeration(self) -> None:
        world = World()
        service = world.app().state.scenario_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        for scenario_id in (str(uuid4()), "not-a-uuid"):
            record = run(
                dispatcher.dispatch(
                    world.principal,
                    "replay_scenario",
                    {"scenario_id": scenario_id},
                )
            )
            assert record.ok
            assert record.result == {"error": "unknown scenario id"}

    def test_absent_scenarios_field_means_absent_tools(self) -> None:
        world = World()
        registry = build_registry(_agent_surface(world, None))
        for name in (
            "list_scenarios",
            "save_scenario",
            "replay_scenario",
            "run_regression_pack",
        ):
            assert name not in registry.names()

    def test_non_admin_dispatch_refused(self) -> None:
        world = World()
        service = world.app().state.scenario_service
        registry = build_registry(_agent_surface(world, service))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        non_admin = dataclasses.replace(world.principal, is_admin=False)
        for name, args in (
            ("list_scenarios", {}),
            ("save_scenario", {"name": "x", "ask": "y"}),
            ("replay_scenario", {"scenario_id": str(uuid4())}),
            ("run_regression_pack", {}),
        ):
            record = run(dispatcher.dispatch(non_admin, name, dict(args)))
            assert not record.ok, name
            assert record.refusal == "admin access required"
