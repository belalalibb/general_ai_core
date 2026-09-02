"""V7 chunk 1 — Capability Catalog (honest closed-set Available/Inert/Unavailable).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Capability Catalog (honest closed-set
Available/Inert/Unavailable)" plus "Agent gains the corresponding tools":

- MODULE CLOSURE: unknown capability ids are a construction-time
  ValueError; ``catalog_json`` refuses duplicates AND incomplete
  derivations (an omitted row would be a hidden claim).
- HONEST DERIVATION: states in GET /v1/admin/capabilities flip with the
  ACTUAL create_app seams — a minimal composition reports the optional
  surfaces INERT; a fuller composition reports them AVAILABLE; the
  recorded UNAVAILABLE row (token streaming) never changes.
- ADMIN GATE (deny-by-default): non-admin principals get the same 403
  ``unauthorized`` every /v1/admin/* route returns; no admin surface ⇒
  the route does not exist at all (20 §4).
- ONE DERIVATION, TWO CONSUMERS: ``app.state.capability_catalog`` is the
  SAME tuple the route rendered; the agent's R0 ``list_capabilities``
  tool renders the identical payload; absent surface field ⇒ absent tool
  (nothing to probe).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api.capabilities import (
    CAPABILITY_IDS,
    Capability,
    CapabilityState,
    catalog_json,
)
from tests.api.test_admin_api import World


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


def _states(body: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["state"] for row in body["capabilities"]}


def _full_catalog(state: CapabilityState = CapabilityState.INERT) -> tuple[Capability, ...]:
    return tuple(
        Capability(id=cap_id, state=state, evidence="test") for cap_id in sorted(CAPABILITY_IDS)
    )


# --- module closure: closed sets both ways ----------------------------------------


class TestCatalogModule:
    def test_unknown_capability_id_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="closed"):
            Capability(
                id="not.a.capability",
                state=CapabilityState.AVAILABLE,
                evidence="x",
            )

    def test_duplicate_ids_refused_by_serializer(self) -> None:
        entries = _full_catalog() + (
            Capability(
                id="execute.sync",
                state=CapabilityState.AVAILABLE,
                evidence="dup",
            ),
        )
        with pytest.raises(ValueError, match="duplicate"):
            catalog_json(entries)

    def test_incomplete_derivation_refused_by_serializer(self) -> None:
        partial = _full_catalog()[:-1]
        with pytest.raises(ValueError, match="incomplete"):
            catalog_json(partial)

    def test_serialized_shape_sorted_process_scoped(self) -> None:
        payload = catalog_json(_full_catalog())
        assert payload["scope"] == "process"
        rows = payload["capabilities"]
        assert isinstance(rows, list)
        ids = [row["id"] for row in rows]
        assert ids == sorted(CAPABILITY_IDS)
        for row in rows:
            assert set(row.keys()) == {"id", "state", "evidence"}
            assert row["state"] in {"available", "inert", "unavailable"}
            assert isinstance(row["evidence"], str) and row["evidence"]


# --- HTTP surface: honest derivation + admin gate ----------------------------------


class TestCapabilityRoute:
    def test_minimal_composition_reports_optional_seams_inert(self) -> None:
        world = World()
        response = run(_get(world.app(), "/v1/admin/capabilities"))
        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "process"
        states = _states(body)
        assert set(states) == CAPABILITY_IDS  # exactly the closed set
        # Always-mounted surfaces:
        assert states["execute.sync"] == "available"
        assert states["skills.listing"] == "available"
        assert states["admin.control_plane"] == "available"  # this app has admin
        # Recorded UNAVAILABLE (V6-2): needs work that does not exist.
        assert states["execute.token_streaming"] == "unavailable"
        # Optional seams NOT composed by World.app() — honestly INERT:
        for cap_id in (
            "execute.async",
            "executions.progress_sse",
            "conversations.persistence",
            "context.composition",
            "models.listing",
            "usage.reporting",
            "webhooks.registration",
            "webhooks.delivery_staging",
            "rate_limits.execute",
            "auth.sessions",
            "health.liveness",
        ):
            assert states[cap_id] == "inert", cap_id

    def test_fuller_composition_flips_states_to_available(self) -> None:
        # Same World, richer create_app call — the SAME seam variables that
        # mount routes must flip the corresponding rows to AVAILABLE.
        from apps.api import create_app
        from core.execution.service import ExecutionService
        from core.runtime.outbox import InMemoryOutbox
        from tests.api.test_admin_api import _no_sleep

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
            webhooks=True,
            outbox=InMemoryOutbox(),
            healthz=True,
            sse=True,
        )
        response = run(_get(app, "/v1/admin/capabilities"))
        assert response.status_code == 200
        states = _states(response.json())
        for cap_id in (
            "execute.async",
            "executions.progress_sse",
            "models.listing",
            "usage.reporting",
            "webhooks.registration",
            "webhooks.delivery_staging",
            "health.liveness",
        ):
            assert states[cap_id] == "available", cap_id
        # Still honestly INERT / UNAVAILABLE:
        assert states["conversations.persistence"] == "inert"
        assert states["auth.sessions"] == "inert"
        assert states["execute.token_streaming"] == "unavailable"

    def test_non_admin_denied_same_as_every_admin_route(self) -> None:
        world = World(is_admin=False)
        response = run(_get(world.app(), "/v1/admin/capabilities"))
        assert response.status_code == 403
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert body["error"]["code"] == "unauthorized"

    def test_absent_admin_surface_means_no_route_at_all(self) -> None:
        world = World()
        response = run(_get(world.app(with_admin=False), "/v1/admin/capabilities"))
        assert response.status_code == 404

    def test_app_state_carries_the_same_derivation(self) -> None:
        # One derivation, two consumers: the composition root reads
        # app.state.capability_catalog to hand the agent the SAME tuple.
        world = World()
        app = world.app()
        catalog = app.state.capability_catalog
        assert isinstance(catalog, tuple)
        route_body = run(_get(app, "/v1/admin/capabilities")).json()
        assert catalog_json(catalog) == route_body


# --- agent R0 tool: same payload, deny-by-default registration ---------------------


def _agent_surface(world: World, capabilities: tuple[Capability, ...] | None) -> AgentToolSurface:
    from apps.api.store import InMemoryExecutionStore
    from core.execution.service import ExecutionService
    from tests.api.test_admin_api import _no_sleep

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
        capabilities=capabilities,
    )


class TestAgentCapabilityTool:
    def test_tool_registered_and_returns_route_identical_payload(self) -> None:
        world = World()
        app = world.app()
        catalog = app.state.capability_catalog
        registry = build_registry(_agent_surface(world, catalog))
        assert "list_capabilities" in registry.names()
        from apps.admin_agent.contracts import ToolClass

        spec = registry.get("list_capabilities")
        assert spec is not None
        assert spec.tool_class is ToolClass.R0_READ
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "list_capabilities", {}))
        assert record.ok, record.refusal
        route_body = run(_get(app, "/v1/admin/capabilities")).json()
        assert record.result == route_body

    def test_absent_capabilities_field_means_absent_tool(self) -> None:
        world = World()
        registry = build_registry(_agent_surface(world, None))
        assert "list_capabilities" not in registry.names()
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "list_capabilities", {}))
        assert not record.ok
        assert record.refusal is not None
        assert "not in the registered tool set" in record.refusal

    def test_non_admin_caller_refused_by_dispatcher(self) -> None:
        import dataclasses

        world = World()
        catalog = world.app().state.capability_catalog
        registry = build_registry(_agent_surface(world, catalog))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        non_admin = dataclasses.replace(world.principal, is_admin=False)
        record = run(dispatcher.dispatch(non_admin, "list_capabilities", {}))
        assert not record.ok
        assert record.refusal == "admin access required"

    def test_unknown_arguments_refused(self) -> None:
        world = World()
        catalog = world.app().state.capability_catalog
        registry = build_registry(_agent_surface(world, catalog))
        dispatcher = ToolDispatcher(registry, audit=world.audit)
        record = run(dispatcher.dispatch(world.principal, "list_capabilities", {"surprise": True}))
        assert not record.ok
        assert record.refusal is not None
        assert "unknown arguments" in record.refusal

    def test_incomplete_catalog_fails_at_registry_construction(self) -> None:
        world = World()
        partial = _full_catalog()[:-1]
        with pytest.raises(ValueError, match="incomplete"):
            build_registry(_agent_surface(world, partial))
