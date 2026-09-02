"""Gap 2 — admin changes survive restart (write-through + startup replay).

Hermetic pins over the OPTIONAL AdminPersistencePort seam and the
composition-layer read side (replay_admin_status_overrides):

- ENABLE/DISABLE provider/model publish writes the UPDATED entity through
  the seam AFTER the in-memory mutation (status included);
- rollback writes the RESTORED entity through the same seam (durability
  follows reality in both directions);
- REGISTER_PROVIDER/REGISTER_MODEL publish persists entity+bindings in
  FK-safe order (model before bindings); rollback deletes in the reverse
  order (bindings before model) and removes the provider row;
- a REFUSED change never reaches the seam (validation failure ⇒ zero
  persistence calls);
- a durable failure re-raises verbatim (loud — no silent split);
- unbound seam ⇒ prior behavior exactly (publish/rollback still work);
- replay applies DURABLE status over composed defaults by NATURAL key,
  skips durable-only rows (never invents providers), and leaves matching
  statuses untouched.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from apps.composition.provider_onboarding import replay_admin_status_overrides
from core.admin import AdminConfigService
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import AdminAction, ConfigLifecycleState
from core.contracts.base import JsonObject
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import ProviderManifest
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting

TENANT = uuid4()
ACTOR = uuid4()


# --- fixtures (shapes reused from tests/admin/test_admin_config_service) ----


def _manifest(provider_key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": provider_key,
            "name": provider_key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(key: str, status: ModelStatus = ModelStatus.ACTIVE) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=status,
    )


class RecordingPersistence:
    """AdminPersistencePort spy — records every call in ORDER."""

    def __init__(self, world: _World | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        # Optional back-reference lets ordering pins read the registry
        # state AT CALL TIME (proves write-through runs after apply).
        self._world = world
        self.provider_status_at_call: list[ProviderStatus] = []

    def persist_provider(self, provider: Provider) -> None:
        if self._world is not None:
            entry = self._world.providers.get(provider.provider_key)
            self.provider_status_at_call.append(entry.provider.status)
        self.calls.append(("persist_provider", provider))

    def persist_model(self, model: Model) -> None:
        self.calls.append(("persist_model", model))

    def persist_binding(self, binding: ProviderModelBinding) -> None:
        self.calls.append(("persist_binding", binding))

    def delete_provider(self, provider_id: UUID) -> None:
        self.calls.append(("delete_provider", provider_id))

    def delete_model(self, model_id: UUID) -> None:
        self.calls.append(("delete_model", model_id))

    def delete_binding(self, provider_id: UUID, model_id: UUID) -> None:
        self.calls.append(("delete_binding", (provider_id, model_id)))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class ExplodingPersistence(RecordingPersistence):
    """Raises on the first persist call — durable-failure honesty pin."""

    def persist_provider(self, provider: Provider) -> None:
        raise RuntimeError("catalog write failed")


class _World:
    def __init__(self, persistence: RecordingPersistence | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.usage = InMemoryUsageAccounting()
        self.audit = InMemoryAuditLog()
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.persistence = persistence
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
            bindings=self.bindings,
            persistence=persistence,
        )

    def seed(self) -> tuple[Provider, Model]:
        provider = _provider("prov_a")
        self.providers.register(provider, _manifest("prov_a"))
        model = _model("model-a")
        self.models.register(model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name=model.model_key,
                availability=BindingAvailability.AVAILABLE,
            )
        )
        return provider, model

    def publish(self, action: AdminAction, payload: JsonObject):
        change = self.admin.draft(tenant_id=TENANT, actor_id=ACTOR, action=action, payload=payload)
        validated = self.admin.validate(TENANT, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED, validated.validation_result
        self.admin.preview(TENANT, change.id)
        return self.admin.publish(TENANT, change.id)


def _world_with_spy() -> tuple[_World, RecordingPersistence]:
    spy = RecordingPersistence()
    world = _World(persistence=spy)
    spy._world = world  # ordering pins read registry state at call time
    return world, spy


# --- write-through: status flips ---------------------------------------------------


class TestStatusWriteThrough:
    def test_disable_provider_persists_the_disabled_entity(self) -> None:
        world, spy = _world_with_spy()
        provider, _ = world.seed()
        world.publish(AdminAction.DISABLE_PROVIDER, {"provider_key": provider.provider_key})
        assert spy.names() == ["persist_provider"]
        persisted = spy.calls[0][1]
        assert isinstance(persisted, Provider)
        assert persisted.status is ProviderStatus.DISABLED
        assert persisted.provider_key == provider.provider_key
        # Write-through ran AFTER the in-memory replace (registry already
        # showed the new status when the seam was called).
        assert spy.provider_status_at_call == [ProviderStatus.DISABLED]

    def test_disable_model_persists_the_disabled_entity(self) -> None:
        world, spy = _world_with_spy()
        _, model = world.seed()
        world.publish(AdminAction.DISABLE_MODEL, {"model_key": model.model_key})
        assert spy.names() == ["persist_model"]
        persisted = spy.calls[0][1]
        assert isinstance(persisted, Model)
        assert persisted.status is ModelStatus.DISABLED

    def test_rollback_persists_the_restored_status_too(self) -> None:
        world, spy = _world_with_spy()
        provider, _ = world.seed()
        published = world.publish(
            AdminAction.DISABLE_PROVIDER, {"provider_key": provider.provider_key}
        )
        world.admin.rollback(TENANT, published.id)
        assert spy.names() == ["persist_provider", "persist_provider"]
        restored = spy.calls[1][1]
        assert isinstance(restored, Provider)
        assert restored.status is ProviderStatus.ACTIVE

    def test_refused_change_never_reaches_the_seam(self) -> None:
        world, spy = _world_with_spy()
        world.seed()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_PROVIDER,
            payload={"provider_key": "ghost"},
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert spy.calls == []

    def test_durable_failure_reraises_verbatim(self) -> None:
        spy = ExplodingPersistence()
        world = _World(persistence=spy)
        provider, _ = world.seed()
        with pytest.raises(RuntimeError, match="catalog write failed"):
            world.publish(
                AdminAction.DISABLE_PROVIDER,
                {"provider_key": provider.provider_key},
            )

    def test_unbound_seam_keeps_prior_behavior(self) -> None:
        world = _World(persistence=None)
        provider, _ = world.seed()
        published = world.publish(
            AdminAction.DISABLE_PROVIDER, {"provider_key": provider.provider_key}
        )
        assert world.providers.get(provider.provider_key).provider.status is ProviderStatus.DISABLED
        world.admin.rollback(TENANT, published.id)
        assert world.providers.get(provider.provider_key).provider.status is ProviderStatus.ACTIVE


# --- write-through: register verbs -------------------------------------------------


def _register_provider_payload(key: str) -> JsonObject:
    return {
        "provider": {
            "id": str(uuid4()),
            "provider_key": key,
            "display_name": key,
            "status": "active",
            "auth_types": ["api_key"],
            "supports_account_pool": False,
        },
        "manifest": _manifest(key).model_dump(mode="json"),
    }


class TestRegisterWriteThrough:
    def test_register_provider_persists_the_entity_row(self) -> None:
        world, spy = _world_with_spy()
        world.publish(AdminAction.REGISTER_PROVIDER, _register_provider_payload("acme"))
        assert spy.names() == ["persist_provider"]
        persisted = spy.calls[0][1]
        assert isinstance(persisted, Provider)
        assert persisted.provider_key == "acme"

    def test_register_model_persists_model_then_bindings(self) -> None:
        world, spy = _world_with_spy()
        provider, _ = world.seed()
        model_id = uuid4()
        world.publish(
            AdminAction.REGISTER_MODEL,
            {
                "model": {
                    "id": str(model_id),
                    "model_key": "model-b",
                    "display_name": "model-b",
                    "tier": "medium",
                    "modalities": ["text"],
                    "capabilities": ["chat"],
                    "status": "active",
                },
                "bindings": [
                    {
                        "provider_key": provider.provider_key,
                        "provider_model_name": "model-b",
                    }
                ],
            },
        )
        # FK-safe order: the model row exists before any binding row.
        assert spy.names() == ["persist_model", "persist_binding"]
        binding = spy.calls[1][1]
        assert isinstance(binding, ProviderModelBinding)
        assert binding.provider_id == provider.id
        assert binding.model_id == model_id

    def test_register_rollback_deletes_bindings_before_model(self) -> None:
        world, spy = _world_with_spy()
        provider, _ = world.seed()
        model_id = uuid4()
        published = world.publish(
            AdminAction.REGISTER_MODEL,
            {
                "model": {
                    "id": str(model_id),
                    "model_key": "model-b",
                    "display_name": "model-b",
                    "tier": "medium",
                    "modalities": ["text"],
                    "capabilities": ["chat"],
                    "status": "active",
                },
                "bindings": [
                    {
                        "provider_key": provider.provider_key,
                        "provider_model_name": "model-b",
                    }
                ],
            },
        )
        spy.calls.clear()
        world.admin.rollback(TENANT, published.id)
        assert spy.names() == ["delete_binding", "delete_model"]
        assert spy.calls[0][1] == (provider.id, model_id)
        assert spy.calls[1][1] == model_id

    def test_register_provider_rollback_deletes_the_row(self) -> None:
        world, spy = _world_with_spy()
        payload = _register_provider_payload("acme")
        published = world.publish(AdminAction.REGISTER_PROVIDER, payload)
        spy.calls.clear()
        world.admin.rollback(TENANT, published.id)
        assert spy.names() == ["delete_provider"]
        provider_dict = payload["provider"]
        assert isinstance(provider_dict, dict)
        assert spy.calls[0][1] == UUID(str(provider_dict["id"]))


# --- read side: startup replay -----------------------------------------------------


class _Bridge:
    """Minimal AsyncBridge stand-in: run one coroutine to completion."""

    def run(self, coro):
        return asyncio.run(coro)


class _FakeCatalog:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    async def load_all(self) -> list:
        return list(self._rows)


def _fake_database(providers: list[Provider], models: list[Model]) -> SimpleNamespace:
    return SimpleNamespace(
        provider_catalog=_FakeCatalog(providers),
        model_catalog=_FakeCatalog(models),
    )


class TestStartupReplay:
    def test_durable_disabled_status_overrides_composed_default(self) -> None:
        registry = ProviderRegistry()
        composed = _provider("prov_a")  # per-boot id, composed ACTIVE
        registry.register(composed, _manifest("prov_a"))
        durable = _provider("prov_a", status=ProviderStatus.DISABLED)
        overridden = replay_admin_status_overrides(
            database=_fake_database([durable], []),
            bridge=_Bridge(),
            providers=registry,
            models=ModelRegistry(),
        )
        assert overridden == ["prov_a"]
        assert registry.get("prov_a").provider.status is ProviderStatus.DISABLED
        # Natural-key match: the in-memory id (adapter map key) is KEPT.
        assert registry.get("prov_a").provider.id == composed.id

    def test_durable_model_status_replays_by_model_key(self) -> None:
        models = ModelRegistry()
        models.register(_model("model-a"))
        durable = _model("model-a", status=ModelStatus.DISABLED)
        overridden = replay_admin_status_overrides(
            database=_fake_database([], [durable]),
            bridge=_Bridge(),
            providers=ProviderRegistry(),
            models=models,
        )
        assert overridden == ["model-a"]
        assert models.get("model-a").status is ModelStatus.DISABLED

    def test_durable_only_rows_are_skipped_never_invented(self) -> None:
        registry = ProviderRegistry()
        overridden = replay_admin_status_overrides(
            database=_fake_database([_provider("ghost")], [_model("ghost-m")]),
            bridge=_Bridge(),
            providers=registry,
            models=ModelRegistry(),
        )
        assert overridden == []
        assert registry.all_keys() == []

    def test_matching_status_is_left_untouched(self) -> None:
        registry = ProviderRegistry()
        registry.register(_provider("prov_a"), _manifest("prov_a"))
        overridden = replay_admin_status_overrides(
            database=_fake_database([_provider("prov_a")], []),
            bridge=_Bridge(),
            providers=registry,
            models=ModelRegistry(),
        )
        assert overridden == []
