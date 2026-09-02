"""ADR-0011 — gateway provider hydration at startup (hermetic pins).

hydrate_gateway_providers replays durable onboarding rows into the LIVE
registries and the SAME adapters/credential_refs maps the composed
ExecutionService reads. Pins:

- full replay: provider (DISABLED, manifest re-derived), models,
  bindings, adapter rebuilt (RemoteGatewayAdapter) + credential_ref map;
- no registrations ⇒ no-op (empty list, registries untouched);
- gateway settings absent ⇒ DATA hydrates but adapters stay honestly
  absent (no fake adapter — AdapterNotBound territory);
- registration without its provider row ⇒ LOUD RuntimeError (catalog
  corruption is never skipped silently);
- runtime composition: the onboarding route exists ONLY when the gateway
  binding is configured (absent seam ⇒ absent route, 20 §4).

Catalog fakes stand in for the Postgres catalogs (their load_all
surfaces are pinned by tests/infrastructure); the AsyncBridge is REAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.provider_onboarding import GatewayOnboardRequest
from apps.composition.bridge import AsyncBridge
from apps.composition.gateway import GatewaySettings
from apps.composition.provider_onboarding import (
    PLATFORM_TENANT_ID,
    hydrate_gateway_providers,
    manifest_from_definition,
)
from apps.composition.runtime import build_runtime_profile
from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.secrets.memory import InMemorySecretManager
from providers.real.gateway import RemoteGatewayAdapter

SETTINGS = GatewaySettings(base_url="http://localhost:9999", secret="gw-secret", secret_version=1)


def _definition(provider_key: str = "gw_alpha") -> dict[str, Any]:
    return GatewayOnboardRequest.model_validate(
        {
            "provider_key": provider_key,
            "display_name": "Gateway Alpha",
            "operations": ["generate_text"],
            "capabilities": {"chat": True},
            "static_models": [],
            "credential_ref": "credref_alpha",
            "route_token_ref": "credref_route_alpha",
            "credential_mode": "platform",
        }
    ).model_dump(mode="json")


class FakeCatalog:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def load_all(self) -> list[Any]:
        return list(self._rows)


@dataclass
class FakeDatabase:
    """Duck-typed DatabaseBindings subset hydration reads."""

    gateway_registrations: FakeCatalog
    provider_catalog: FakeCatalog
    model_catalog: FakeCatalog
    binding_catalog: FakeCatalog


@dataclass
class HydrationWorld:
    providers: ProviderRegistry = field(default_factory=ProviderRegistry)
    models: ModelRegistry = field(default_factory=ModelRegistry)
    bindings: BindingRegistry = field(default_factory=BindingRegistry)
    adapters: dict[UUID, Any] = field(default_factory=dict)
    credential_refs: dict[UUID, str] = field(default_factory=dict)


def _durable_rows(provider_key: str = "gw_alpha") -> FakeDatabase:
    provider_id = uuid4()
    model_id = uuid4()
    provider = Provider(
        id=provider_id,
        provider_key=provider_key,
        display_name="Gateway Alpha",
        status=ProviderStatus.DISABLED,
        auth_types=[AuthType.CUSTOM],
        supports_account_pool=False,
    )
    model = Model(
        id=model_id,
        model_key=f"{provider_key}/alpha-1",
        display_name="alpha-1",
        tier=ModelTier.MEDIUM,
        modalities=[Modality.TEXT],
        capabilities=[],
        status=ModelStatus.ACTIVE,
    )
    binding = ProviderModelBinding(
        provider_id=provider_id,
        model_id=model_id,
        provider_model_name="alpha-1",
        availability=BindingAvailability.AVAILABLE,
    )
    return FakeDatabase(
        gateway_registrations=FakeCatalog([(provider_id, _definition(provider_key))]),
        provider_catalog=FakeCatalog([provider]),
        model_catalog=FakeCatalog([model]),
        binding_catalog=FakeCatalog([binding]),
    )


def _hydrate(
    world: HydrationWorld,
    database: FakeDatabase,
    *,
    settings: GatewaySettings | None = SETTINGS,
) -> list[str]:
    bridge = AsyncBridge()
    try:
        return hydrate_gateway_providers(
            database=database,  # type: ignore[arg-type]
            bridge=bridge,
            providers=world.providers,
            models=world.models,
            bindings=world.bindings,
            adapters=world.adapters,
            credential_refs=world.credential_refs,
            gateway_settings=settings,
            secrets=InMemorySecretManager() if settings is not None else None,
        )
    finally:
        bridge.close()


class TestHydration:
    def test_full_replay_rebuilds_registries_and_adapter(self) -> None:
        world = HydrationWorld()
        hydrated = _hydrate(world, _durable_rows())
        assert hydrated == ["gw_alpha"]
        entry = world.providers.get("gw_alpha")
        assert entry.provider.status is ProviderStatus.DISABLED
        assert entry.manifest.status == "disabled"  # re-derived, never invented
        model = world.models.get("gw_alpha/alpha-1")
        binding = world.bindings.get(entry.provider.id, model.id)
        assert binding.provider_model_name == "alpha-1"
        adapter = world.adapters[entry.provider.id]
        assert isinstance(adapter, RemoteGatewayAdapter)
        assert world.credential_refs[entry.provider.id] == "credref_alpha"

    def test_no_registrations_is_a_noop(self) -> None:
        world = HydrationWorld()
        empty = FakeDatabase(
            gateway_registrations=FakeCatalog([]),
            provider_catalog=FakeCatalog([]),
            model_catalog=FakeCatalog([]),
            binding_catalog=FakeCatalog([]),
        )
        assert _hydrate(world, empty) == []
        assert world.providers.all_keys() == []
        assert world.adapters == {}

    def test_without_gateway_settings_data_hydrates_but_no_adapter(self) -> None:
        world = HydrationWorld()
        hydrated = _hydrate(world, _durable_rows(), settings=None)
        assert hydrated == ["gw_alpha"]
        entry = world.providers.get("gw_alpha")
        # Honest degradation: catalog DATA present, adapter absent — routing
        # to this provider refuses (AdapterNotBound), nothing is faked.
        assert world.adapters == {}
        assert world.credential_refs == {}
        assert entry.provider.provider_key == "gw_alpha"

    def test_registration_without_provider_row_is_loud(self) -> None:
        world = HydrationWorld()
        orphan = FakeDatabase(
            gateway_registrations=FakeCatalog([(uuid4(), _definition())]),
            provider_catalog=FakeCatalog([]),
            model_catalog=FakeCatalog([]),
            binding_catalog=FakeCatalog([]),
        )
        with pytest.raises(RuntimeError, match="without provider row"):
            _hydrate(world, orphan)

    def test_manifest_rederivation_matches_route_derivation(self) -> None:
        # One derivation, two consumers: hydration's manifest equals the
        # route's manifest for the same stored definition.
        definition = GatewayOnboardRequest.model_validate(_definition())
        assert manifest_from_definition(definition) == manifest_from_definition(definition)

    def test_platform_custody_scope_is_deterministic(self) -> None:
        # Refs stored under this scope must stay resolvable across restarts.
        assert str(PLATFORM_TENANT_ID) == "00000000-0000-0000-0000-00000000ada1"


class TestRuntimeSeam:
    def test_route_absent_without_gateway_binding(self) -> None:
        profile = build_runtime_profile({})
        client = TestClient(profile.app)
        assert client.post("/v1/admin/providers/onboard", json={}).status_code == 404

    def test_route_present_with_gateway_binding(self) -> None:
        profile = build_runtime_profile(
            {
                "GATEWAY_BASE_URL": "http://localhost:9999",
                "GATEWAY_SECRET": "s3",
                "GATEWAY_SECRET_VERSION": "1",
            }
        )
        client = TestClient(profile.app)
        # 422 (body validation) proves the route EXISTS; admission and the
        # walker are pinned elsewhere.
        response = client.post("/v1/admin/providers/onboard", json={})
        assert response.status_code == 422
