"""V7 chunk 2 — Capability Exercise Surface (real probes, real evidence).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Capability Exercise Surface" plus
"Agent gains the corresponding tools":

- MODULE CLOSURE: an exerciser for an id outside CAPABILITY_IDS is a
  construction-time ValueError; ``exercisable()`` lists EXACTLY the
  registered probes (a capability without a real probe is honestly not
  exercisable, 41 §49).
- REAL PROBES: POST /v1/admin/capabilities/execute.sync/exercise runs a
  REAL budget-bounded execution as the admitted caller — the returned
  evidence (execution id + stored status) resolves in the SAME store the
  poll surface reads, and the probe label is machine-checkable in the
  stored node's input_ref. No entitlement ⇒ honest exercised:False.
- SEAM HONESTY: the exercisable list grows with the ACTUAL composition
  (usage/models probes appear only when those seams are composed).
- GATES: non-admin 403 unauthorized; unknown id = recorded 404
  anti-enumeration mapping; absent admin surface ⇒ routes absent.
- ONE REGISTRY, TWO CONSUMERS: the agent's R0 list_exercisable and R1
  exercise_capability tools dispatch through app.state.exercise_surface —
  registered only when composed; absent field ⇒ absent tools.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.admin_agent.contracts import ToolClass
from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api.exercise import EXERCISE_LABEL_KEY, ExerciseSurface
from apps.api.store import InMemoryExecutionStore
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


async def _post(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(path)


def _grant(world: World, limit: float = 100.0) -> None:
    world.usage.configure_tenant(world.principal.tenant_id, plan="test", task_units_limit=limit)


# --- module closure ----------------------------------------------------------------


class TestExerciseModule:
    def test_unknown_capability_id_refused_at_construction(self) -> None:
        async def probe(caller: object) -> dict[str, object]:  # pragma: no cover
            return {}

        with pytest.raises(ValueError, match="closed"):
            ExerciseSurface({"not.a.capability": probe})  # type: ignore[dict-item]

    def test_exercisable_lists_exactly_the_registered_probes(self) -> None:
        surface = ExerciseSurface({})
        assert surface.exercisable() == []
        assert surface.get("execute.sync") is None


# --- HTTP surface ------------------------------------------------------------------


class TestExerciseRoutes:
    def test_minimal_composition_exercisable_set(self) -> None:
        # World.app() composes without usage=/models= seams on create_app —
        # only the always-present probes exist.
        world = World()
        response = run(_get(world.app(), "/v1/admin/capabilities/exercisable"))
        assert response.status_code == 200
        assert response.json() == {"exercisable": ["execute.sync", "skills.listing"]}

    def test_fuller_composition_grows_the_exercisable_set(self) -> None:
        from apps.api import create_app

        world = World()
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
            principal=world.principal,
            admin=world.surface(),
            models=world.models,
            bindings=world.bindings,
            usage=world.usage,
        )
        response = run(_get(app, "/v1/admin/capabilities/exercisable"))
        assert response.json() == {
            "exercisable": [
                "execute.sync",
                "models.listing",
                "skills.listing",
                "usage.reporting",
            ]
        }

    def test_execute_sync_probe_runs_a_real_labeled_execution(self) -> None:
        world = World()
        _grant(world)
        app = world.app()
        response = run(_post(app, "/v1/admin/capabilities/execute.sync/exercise"))
        assert response.status_code == 200
        body = response.json()
        assert body["capability_id"] == "execute.sync"
        result = body["result"]
        assert result["exercised"] is True
        evidence = result["evidence"]
        assert evidence["kind"] == "execution"
        assert evidence["status"] == "succeeded"
        execution_id = evidence["execution_id"]
        # The evidence resolves on the SAME poll surface a user reads.
        poll = run(_get(app, f"/v1/executions/{execution_id}"))
        assert poll.status_code == 200
        assert poll.json()["status"] == "succeeded"

    def test_probe_label_is_machine_checkable_in_the_stored_node(self) -> None:
        # Same store instance create_app composed over — assert the label
        # landed in the node's input_ref (no new persistence mechanism).
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
        response = run(_post(app, "/v1/admin/capabilities/execute.sync/exercise"))
        evidence = response.json()["result"]["evidence"]
        from uuid import UUID

        report = store.get(world.principal.tenant_id, UUID(evidence["execution_id"]))
        assert len(report.nodes) == 1
        input_ref = report.nodes[0].node.input_ref
        assert isinstance(input_ref, dict)
        metadata = input_ref["context"]["metadata"]  # type: ignore[index]
        assert EXERCISE_LABEL_KEY in metadata

    def test_no_entitlement_is_honest_not_fabricated(self) -> None:
        world = World()  # no budget configured
        response = run(_post(world.app(), "/v1/admin/capabilities/execute.sync/exercise"))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["exercised"] is False
        assert "entitlement" in result["error"]

    def test_skills_probe_exercises_the_registry(self) -> None:
        world = World()
        response = run(_post(world.app(), "/v1/admin/capabilities/skills.listing/exercise"))
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["exercised"] is True
        assert result["evidence"]["source"] == "SkillRegistry.list_selectable"

    def test_unknown_id_maps_to_recorded_404(self) -> None:
        world = World()
        for probe_id in ("nope", "execute.async", "auth.sessions"):
            # Unknown AND unregistered ids answer identically (20 §6).
            response = run(_post(world.app(), f"/v1/admin/capabilities/{probe_id}/exercise"))
            assert response.status_code == 404, probe_id
            body = response.json()
            assert set(body.keys()) == {"error"}
            assert body["error"]["code"] == "validation_error"

    def test_non_admin_denied_on_both_routes(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        for response in (
            run(_get(app, "/v1/admin/capabilities/exercisable")),
            run(_post(app, "/v1/admin/capabilities/execute.sync/exercise")),
        ):
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "unauthorized"

    def test_absent_admin_surface_means_no_routes(self) -> None:
        world = World()
        app = world.app(with_admin=False)
        assert run(_get(app, "/v1/admin/capabilities/exercisable")).status_code == 404
        assert run(_post(app, "/v1/admin/capabilities/execute.sync/exercise")).status_code == 404


# --- agent tools -------------------------------------------------------------------


def _agent_surface(world: World, exercise: ExerciseSurface | None) -> AgentToolSurface:
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
        exercise=exercise,
    )


class TestAgentExerciseTools:
    def test_tools_registered_with_correct_classes(self) -> None:
        world = World()
        surface = world.app().state.exercise_surface
        registry = build_registry(_agent_surface(world, surface))
        list_spec = registry.get("list_exercisable")
        exercise_spec = registry.get("exercise_capability")
        assert list_spec is not None and exercise_spec is not None
        assert list_spec.tool_class is ToolClass.R0_READ
        assert exercise_spec.tool_class is ToolClass.R1_EXECUTE_TEST
        assert exercise_spec.allowed_args == frozenset({"capability_id"})

    def test_agent_list_matches_the_route(self) -> None:
        world = World()
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.exercise_surface))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "list_exercisable", {}))
        assert record.ok
        route_body = run(_get(app, "/v1/admin/capabilities/exercisable")).json()
        assert record.result == route_body

    def test_agent_exercise_runs_the_same_probe(self) -> None:
        world = World()
        _grant(world)
        app = world.app()
        registry = build_registry(_agent_surface(world, app.state.exercise_surface))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(
            dispatcher.dispatch(
                world.principal,
                "exercise_capability",
                {"capability_id": "execute.sync"},
            )
        )
        assert record.ok, record.refusal
        assert record.result is not None
        result = record.result["result"]
        assert isinstance(result, dict)
        assert result["exercised"] is True

    def test_agent_unknown_id_anti_enumeration(self) -> None:
        world = World()
        surface = world.app().state.exercise_surface
        registry = build_registry(_agent_surface(world, surface))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        for probe_id in ("nope", "execute.async"):
            record = run(
                dispatcher.dispatch(
                    world.principal,
                    "exercise_capability",
                    {"capability_id": probe_id},
                )
            )
            assert record.ok  # honest error CONTENT, not a dispatch refusal
            assert record.result == {"error": "unknown exercisable capability id"}

    def test_absent_exercise_field_means_absent_tools(self) -> None:
        world = World()
        registry = build_registry(_agent_surface(world, None))
        assert "list_exercisable" not in registry.names()
        assert "exercise_capability" not in registry.names()

    def test_non_admin_dispatch_refused(self) -> None:
        world = World()
        surface = world.app().state.exercise_surface
        registry = build_registry(_agent_surface(world, surface))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        non_admin = dataclasses.replace(world.principal, is_admin=False)
        record = run(
            dispatcher.dispatch(non_admin, "exercise_capability", {"capability_id": "execute.sync"})
        )
        assert not record.ok
        assert record.refusal == "admin access required"
