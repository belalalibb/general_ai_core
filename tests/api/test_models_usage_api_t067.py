"""GET /v1/models + GET /v1/usage — FINAL Phase 18 slice 1 (T-IMPL-067).

Contract authority: 10 §6 (models rows: id/name/tier/modalities/
capabilities/availability), 10 §8 (usage: plan/task_units/modality_limits),
41 §21 (Phase 18 supporting endpoints), 20 §4 (absent seam ⇒ no route),
20 §6 (usage is principal-tenant-scoped), 03 §4 (availability is a
per-binding fact — projection recorded in core/contracts/model_listing.py).

Exit mapping (41 §21 supporting list):

- GET /v1/models      -> TestModelsEndpoint (this file)
- GET /v1/usage       -> TestUsageEndpoint (this file)
- GET /v1/skills      -> pre-existing (T-IMPL-028)
- GET /v1/executions  -> pre-existing (T-IMPL-023)
- POST /v1/execute    -> pre-existing (T-IMPL-023)
- POST /v1/webhooks / Async / Streaming -> NOT this slice (recorded in
  apps/api/app.py header — contracts exist, delivery/runtime gated).

Hermetic: in-memory registries/accounting only, ASGI transport, no sockets.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api.app import Principal, create_app
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.model_listing import derive_model_availability
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.usage.memory import InMemoryUsageAccounting

T = TypeVar("T")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- builders --------------------------------------------------------------------


def make_model(
    key: str,
    *,
    status: ModelStatus = ModelStatus.ACTIVE,
    tier: ModelTier = ModelTier.MEDIUM,
    capabilities: list[str] | None = None,
) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=f"Display {key}",
        tier=tier,
        modalities=["text"],
        capabilities=capabilities if capabilities is not None else ["reasoning"],
        status=status,
    )


def make_binding(
    provider_id: Any, model_id: Any, availability: BindingAvailability
) -> ProviderModelBinding:
    return ProviderModelBinding(
        provider_id=provider_id,
        model_id=model_id,
        provider_model_name="vendor/model",
        availability=availability,
    )


class World:
    """Minimal API world for the two read endpoints — no execution needed.

    ``create_app`` requires a router + execution service; the listing
    endpoints never call them, so inert instances suffice (the pre-existing
    execute-path suites already cover those services).
    """

    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4())
        self.usage: InMemoryUsageAccounting | None = None
        self.provider = Provider(
            id=uuid4(),
            provider_key="prov_a",
            display_name="prov_a",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )

    def app(
        self,
        *,
        with_models: bool = True,
        with_usage: bool = False,
    ) -> FastAPI:
        from core.execution.service import ExecutionService
        from core.routing.router import SimpleScoringRouter

        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        service = ExecutionService(
            adapters={},
            credential_refs={},
            bindings=self.bindings,
        )
        return create_app(
            router=router,
            execution_service=service,
            principal=self.principal,
            models=self.models if with_models else None,
            bindings=self.bindings if with_models else None,
            usage=self.usage if with_usage else None,
        )


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


# --- availability projection (recorded derivation) --------------------------------


class TestAvailabilityProjection:
    def test_any_available_binding_wins(self) -> None:
        pid, mid = uuid4(), uuid4()
        bindings = [
            make_binding(pid, mid, BindingAvailability.UNAVAILABLE),
            make_binding(uuid4(), mid, BindingAvailability.AVAILABLE),
        ]
        assert derive_model_availability(bindings) is BindingAvailability.AVAILABLE

    def test_degraded_beats_unavailable(self) -> None:
        mid = uuid4()
        bindings = [
            make_binding(uuid4(), mid, BindingAvailability.UNAVAILABLE),
            make_binding(uuid4(), mid, BindingAvailability.DEGRADED),
        ]
        assert derive_model_availability(bindings) is BindingAvailability.DEGRADED

    def test_all_unavailable_is_unavailable(self) -> None:
        mid = uuid4()
        bindings = [make_binding(uuid4(), mid, BindingAvailability.UNAVAILABLE)]
        assert derive_model_availability(bindings) is BindingAvailability.UNAVAILABLE

    def test_no_bindings_is_unavailable_deny_by_default(self) -> None:
        assert derive_model_availability([]) is BindingAvailability.UNAVAILABLE


# --- GET /v1/models (10 §6) --------------------------------------------------------


class TestModelsEndpoint:
    def test_row_shape_is_the_documented_10_6_shape(self) -> None:
        world = World()
        model = make_model("example-max", tier=ModelTier.MAX)
        world.models.register(model)
        world.bindings.register(
            make_binding(world.provider.id, model.id, BindingAvailability.AVAILABLE)
        )
        response = run(_get(world.app(), "/v1/models"))
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"models"}
        (row,) = body["models"]
        assert row == {
            "id": str(model.id),
            "name": "example-max",
            "tier": "max",
            "modalities": ["text"],
            "capabilities": ["reasoning"],
            "availability": "available",
        }

    def test_lists_active_models_only(self) -> None:
        world = World()
        active = make_model("model-a")
        disabled = make_model("model-b", status=ModelStatus.DISABLED)
        world.models.register(active)
        world.models.register(disabled)
        world.bindings.register(
            make_binding(world.provider.id, active.id, BindingAvailability.AVAILABLE)
        )
        body = run(_get(world.app(), "/v1/models")).json()
        assert [row["name"] for row in body["models"]] == ["model-a"]

    def test_model_without_bindings_listed_unavailable(self) -> None:
        world = World()
        world.models.register(make_model("model-orphan"))
        body = run(_get(world.app(), "/v1/models")).json()
        (row,) = body["models"]
        assert row["availability"] == "unavailable"

    def test_rows_are_key_ordered_deterministic(self) -> None:
        world = World()
        for key in ("model-c", "model-a", "model-b"):
            world.models.register(make_model(key))
        body = run(_get(world.app(), "/v1/models")).json()
        assert [row["name"] for row in body["models"]] == [
            "model-a",
            "model-b",
            "model-c",
        ]

    def test_empty_registry_yields_empty_array_not_error(self) -> None:
        world = World()
        response = run(_get(world.app(), "/v1/models"))
        assert response.status_code == 200
        assert response.json() == {"models": []}

    def test_absent_seam_no_route_exists(self) -> None:
        world = World()
        response = run(_get(world.app(with_models=False), "/v1/models"))
        assert response.status_code == 404


# --- GET /v1/usage (10 §8) ----------------------------------------------------------


class TestUsageEndpoint:
    def test_documented_10_8_shape(self) -> None:
        world = World()
        world.usage = InMemoryUsageAccounting()
        world.usage.configure_tenant(
            world.principal.tenant_id,
            plan="pro",
            task_units_limit=100.0,
            modality_limits={"image_generation": {"limit": 20, "used": 4}},
        )
        response = run(_get(world.app(with_usage=True), "/v1/usage"))
        assert response.status_code == 200
        body = response.json()
        assert body["plan"] == "pro"
        assert body["task_units"] == {"limit": 100.0, "used": 0.0, "remaining": 100.0}
        assert body["modality_limits"] == {"image_generation": {"limit": 20, "used": 4}}

    def test_reflects_reservations_and_settlements(self) -> None:
        world = World()
        world.usage = InMemoryUsageAccounting()
        world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=10.0)
        execution_id = uuid4()
        world.usage.reserve(world.principal.tenant_id, execution_id, 3.0)
        app = world.app(with_usage=True)
        body = run(_get(app, "/v1/usage")).json()
        assert body["task_units"]["used"] == 3.0
        assert body["task_units"]["remaining"] == 7.0
        world.usage.settle(execution_id, 2.0)
        body = run(_get(app, "/v1/usage")).json()
        assert body["task_units"]["used"] == 2.0
        assert body["task_units"]["remaining"] == 8.0

    def test_unconfigured_tenant_denies_entitlement_exceeded(self) -> None:
        world = World()
        world.usage = InMemoryUsageAccounting()  # no configure_tenant call
        response = run(_get(world.app(with_usage=True), "/v1/usage"))
        assert response.status_code == 403
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert body["error"]["code"] == "entitlement_exceeded"

    def test_scoped_to_principal_tenant_never_another(self) -> None:
        world = World()
        world.usage = InMemoryUsageAccounting()
        other_tenant = uuid4()
        world.usage.configure_tenant(other_tenant, plan="max", task_units_limit=999.0)
        # The caller's own tenant has NO budget: the other tenant's data
        # must never leak through this surface (20 §6).
        response = run(_get(world.app(with_usage=True), "/v1/usage"))
        assert response.status_code == 403

    def test_absent_seam_no_route_exists(self) -> None:
        world = World()
        response = run(_get(world.app(with_usage=False), "/v1/usage"))
        assert response.status_code == 404


# --- module guard -----------------------------------------------------------------


def test_listing_contract_module_does_no_io() -> None:
    import inspect

    import core.contracts.model_listing as mod

    source = inspect.getsource(mod)
    for banned in ("httpx", "requests", "urllib", "socket", "subprocess", "open("):
        assert banned not in source
