"""REGISTER_PROVIDER / REGISTER_MODEL admin actions (21 §4 'add' verbs).

Hermetic — in-memory registries only. Pins:

- both actions ride the FULL 21 §3 lifecycle (draft→validate→preview→publish)
  and land in the SAME registries routing reads;
- validation is deny-by-default: malformed contracts, duplicates, unknown
  binding providers and an absent binding seam are all REJECTED with reasons;
- publish makes a routable candidate ONLY when status/manifest allow it
  (31 §10 posture unchanged — registration alone routes nothing);
- rollback REMOVES the registered rows again (21 §8: restore reality);
- payloads carry no credential material by construction (contract shapes).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.admin import AdminConfigService
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    ACTION_AREA,
    AdminAction,
    AdminArea,
    ConfigLifecycleState,
)
from core.contracts.base import JsonObject
from core.contracts.domain import ModelStatus
from core.contracts.provider import ProviderOperation
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.providers.errors import (
    BindingNotFound,
    ModelNotRegistered,
    ProviderNotRegistered,
)
from core.routing import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting

TENANT = uuid4()
ACTOR = uuid4()


def _manifest_payload(provider_key: str) -> JsonObject:
    return {
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


def _provider_payload(provider_key: str, status: str = "active") -> JsonObject:
    return {
        "id": str(uuid4()),
        "provider_key": provider_key,
        "display_name": provider_key,
        "status": status,
        "auth_types": ["api_key"],
        "supports_account_pool": False,
    }


def _model_payload(model_key: str, status: str = "active") -> JsonObject:
    return {
        "id": str(uuid4()),
        "model_key": model_key,
        "display_name": model_key,
        "tier": "medium",
        "modalities": ["text"],
        "capabilities": ["chat"],
        "status": status,
    }


class World:
    def __init__(self, *, with_bindings: bool = True) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.usage = InMemoryUsageAccounting()
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.audit = InMemoryAuditLog()
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
            bindings=self.bindings if with_bindings else None,
        )

    def draft(self, action: AdminAction, payload: JsonObject):
        return self.admin.draft(
            tenant_id=TENANT, actor_id=ACTOR, action=action, payload=payload
        )

    def publish(self, action: AdminAction, payload: JsonObject):
        change = self.draft(action, payload)
        validated = self.admin.validate(TENANT, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED, (
            validated.validation_result
        )
        self.admin.preview(TENANT, change.id)
        return self.admin.publish(TENANT, change.id)


class TestContract:
    def test_actions_map_to_their_areas(self) -> None:
        assert ACTION_AREA[AdminAction.REGISTER_PROVIDER] is AdminArea.PROVIDERS
        assert ACTION_AREA[AdminAction.REGISTER_MODEL] is AdminArea.MODELS

    def test_every_action_still_has_exactly_one_area(self) -> None:
        assert set(ACTION_AREA) == set(AdminAction)


class TestRegisterProvider:
    def test_full_lifecycle_registers_into_the_live_registry(self) -> None:
        world = World()
        payload = {
            "provider": _provider_payload("acme"),
            "manifest": _manifest_payload("acme"),
        }
        published = world.publish(AdminAction.REGISTER_PROVIDER, payload)
        assert published.state is ConfigLifecycleState.PUBLISHED
        entry = world.providers.get("acme")
        assert entry.provider.provider_key == "acme"
        assert entry.is_routable is True

    def test_registration_of_disabled_provider_routes_nothing(self) -> None:
        world = World()
        payload = {
            "provider": _provider_payload("dormant", status="disabled"),
            "manifest": _manifest_payload("dormant"),
        }
        world.publish(AdminAction.REGISTER_PROVIDER, payload)
        assert world.providers.get("dormant").is_routable is False

    def test_duplicate_provider_rejected_at_validation(self) -> None:
        world = World()
        payload = {
            "provider": _provider_payload("acme"),
            "manifest": _manifest_payload("acme"),
        }
        world.publish(AdminAction.REGISTER_PROVIDER, payload)
        change = world.draft(AdminAction.REGISTER_PROVIDER, payload)
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "already registered" in (rejected.validation_result or "")

    def test_malformed_provider_contract_rejected(self) -> None:
        world = World()
        change = world.draft(
            AdminAction.REGISTER_PROVIDER,
            {"provider": {"provider_key": "x"}, "manifest": _manifest_payload("x")},
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "not a valid Provider contract" in (rejected.validation_result or "")

    def test_missing_manifest_rejected(self) -> None:
        world = World()
        change = world.draft(
            AdminAction.REGISTER_PROVIDER, {"provider": _provider_payload("x")}
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "manifest" in (rejected.validation_result or "")

    def test_rollback_removes_the_registration(self) -> None:
        world = World()
        payload = {
            "provider": _provider_payload("acme"),
            "manifest": _manifest_payload("acme"),
        }
        published = world.publish(AdminAction.REGISTER_PROVIDER, payload)
        world.admin.rollback(TENANT, published.id)
        with pytest.raises(ProviderNotRegistered):
            world.providers.get("acme")


class TestRegisterModel:
    def _registered_provider(self, world: World) -> None:
        world.publish(
            AdminAction.REGISTER_PROVIDER,
            {
                "provider": _provider_payload("acme"),
                "manifest": _manifest_payload("acme"),
            },
        )

    def test_full_lifecycle_registers_model_and_bindings(self) -> None:
        world = World()
        self._registered_provider(world)
        payload = {
            "model": _model_payload("acme-chat-1"),
            "bindings": [{"provider_key": "acme", "provider_model_name": "chat-1"}],
        }
        world.publish(AdminAction.REGISTER_MODEL, payload)
        model = world.models.get("acme-chat-1")
        assert model.status is ModelStatus.ACTIVE
        provider = world.providers.get("acme").provider
        binding = world.bindings.get(provider.id, model.id)
        assert binding.provider_model_name == "chat-1"

    def test_registered_model_becomes_routable_end_to_end(self) -> None:
        from core.contracts.routing import RoutingRequest

        world = World()
        self._registered_provider(world)
        world.publish(
            AdminAction.REGISTER_MODEL,
            {
                "model": _model_payload("acme-chat-1"),
                "bindings": [
                    {"provider_key": "acme", "provider_model_name": "chat-1"}
                ],
            },
        )
        decision = world.router.route(
            RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
        )
        model = world.models.get("acme-chat-1")
        assert decision.selected.model_id == model.id

    def test_unknown_binding_provider_rejected(self) -> None:
        world = World()
        change = world.draft(
            AdminAction.REGISTER_MODEL,
            {
                "model": _model_payload("m1"),
                "bindings": [{"provider_key": "ghost", "provider_model_name": "x"}],
            },
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "unregistered provider" in (rejected.validation_result or "")

    def test_bindings_without_seam_rejected(self) -> None:
        world = World(with_bindings=False)
        self._registered_provider(world)
        change = world.draft(
            AdminAction.REGISTER_MODEL,
            {
                "model": _model_payload("m1"),
                "bindings": [{"provider_key": "acme", "provider_model_name": "x"}],
            },
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "seam is not bound" in (rejected.validation_result or "")

    def test_duplicate_model_rejected(self) -> None:
        world = World()
        self._registered_provider(world)
        payload = {"model": _model_payload("m1")}
        world.publish(AdminAction.REGISTER_MODEL, payload)
        change = world.draft(AdminAction.REGISTER_MODEL, payload)
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "already registered" in (rejected.validation_result or "")

    def test_rollback_removes_model_and_bindings(self) -> None:
        world = World()
        self._registered_provider(world)
        published = world.publish(
            AdminAction.REGISTER_MODEL,
            {
                "model": _model_payload("m1"),
                "bindings": [{"provider_key": "acme", "provider_model_name": "x"}],
            },
        )
        model = world.models.get("m1")
        provider = world.providers.get("acme").provider
        world.admin.rollback(TENANT, published.id)
        with pytest.raises(ModelNotRegistered):
            world.models.get("m1")
        with pytest.raises(BindingNotFound):
            world.bindings.get(provider.id, model.id)

    def test_invalid_availability_rejected(self) -> None:
        world = World()
        self._registered_provider(world)
        change = world.draft(
            AdminAction.REGISTER_MODEL,
            {
                "model": _model_payload("m1"),
                "bindings": [
                    {
                        "provider_key": "acme",
                        "provider_model_name": "x",
                        "availability": "sometimes",
                    }
                ],
            },
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "BindingAvailability" in (rejected.validation_result or "")


class TestRegistryRemove:
    def test_provider_remove_unknown_raises(self) -> None:
        with pytest.raises(ProviderNotRegistered):
            ProviderRegistry().remove("ghost")

    def test_model_remove_unknown_raises(self) -> None:
        with pytest.raises(ModelNotRegistered):
            ModelRegistry().remove("ghost")

    def test_binding_remove_unknown_raises(self) -> None:
        with pytest.raises(BindingNotFound):
            BindingRegistry().remove(uuid4(), uuid4())


class TestAudit:
    def test_publish_and_rollback_are_audited(self) -> None:
        world = World()
        payload = {
            "provider": _provider_payload("acme"),
            "manifest": _manifest_payload("acme"),
        }
        published = world.publish(AdminAction.REGISTER_PROVIDER, payload)
        world.admin.rollback(TENANT, published.id)
        events = world.audit.events_for_tenant(TENANT)
        whats = [e.admin_change.what for e in events if e.admin_change is not None]
        assert any("register_provider: acme" in w for w in whats)
        assert any("rollback register_provider: acme" in w for w in whats)
