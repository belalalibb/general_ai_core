"""ProviderOnboardingService — 31 §19 checklist walker (runtime subset).

Hermetic; a configurable fake adapter drives every gate. Pins:

- happy path passes steps 3/5/6/4/11/13/12 in order, registers the provider
  DISABLED (step 13) with its models/bindings, and PREPARES the step-14
  enable draft without enabling anything itself;
- each gate refuses loudly AT its step: template manifest (3), bad
  credential (5), unhealthy provider (6), zero declared operations (4),
  duplicate provider (11), unknown modality (12);
- a duplicate model key under the DEFAULT prefix rolls the WHOLE onboarding back;
  an EXPLICIT prefix resolving to an existing logical Model binds to it (R190)
  (no half-registered provider — parallel-state ban);
- the disabled registration is NOT routable until admin enables it, and
  the prepared draft publishes through the REAL AdminConfigService making
  it routable (step 14: enable via Admin/Config only);
- the service only ever sees the opaque credential_ref (20 §5).

Async driven by asyncio.run (ADR-0001; no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.admin import AdminConfigService
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import AdminAction, ConfigLifecycleState
from core.contracts.domain import AuthType, ProviderStatus
from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.providers import (
    BindingRegistry,
    ModelRegistry,
    OnboardingRefused,
    ProviderOnboardingService,
    ProviderRegistry,
)
from core.routing import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _manifest(**overrides: object) -> ProviderManifest:
    data: dict[str, object] = {
        "id": "cand",
        "name": "Candidate Provider",
        "version": "1.0.0",
        "status": "active",
        "auth": {"types": ["api_key"], "supports_refresh": False},
        "account_pool": {"supported": False},
        "capabilities": {"chat": True},
        "operations": ["generate_text"],
        "models": {"discovery": "dynamic"},
        "rate_limits": {"strategy": "provider_defined"},
        "health": {"checks": ["ping"]},
        "errors": {"mapping": "error_map.json"},
    }
    data.update(overrides)
    return ProviderManifest.model_validate(data)


class FakeAdapter:
    """Configurable ProviderAdapterPort fake for gate-by-gate testing."""

    def __init__(
        self,
        *,
        manifest: ProviderManifest | None = None,
        credential_ok: bool = True,
        healthy: bool = True,
        models: list[dict[str, object]] | None = None,
    ) -> None:
        self._manifest = manifest if manifest is not None else _manifest()
        self._credential_ok = credential_ok
        self._healthy = healthy
        self._models = (
            models
            if models is not None
            else [{"provider_model_name": "cand-1", "modalities": ["text"]}]
        )
        self.seen_credential_refs: list[str] = []

    def get_manifest(self) -> ProviderManifest:
        return self._manifest

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        self.seen_credential_refs.append(credential_ref)
        status = "active" if self._credential_ok else "invalid"
        return CredentialHealth.model_validate({"credential_ref": credential_ref, "status": status})

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return [DiscoveredModel.model_validate(m) for m in self._models]

    async def get_capabilities(self) -> ProviderCapabilities:
        return self._manifest.capabilities

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        return ProviderGenerateResponse(
            request_id=request.request_id, succeeded=True, output={"text": "ok"}
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        state = "HEALTHY" if self._healthy else "UNAVAILABLE"
        return ProviderHealth.model_validate({"provider_id": "cand", "state": state})

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.PROVIDER_INTERNAL,
            retryable=False,
            safe_message="fake",
        )


class World:
    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.service = ProviderOnboardingService(
            providers=self.providers,
            models=self.models,
            bindings=self.bindings,
        )

    def onboard(self, adapter: FakeAdapter, key: str = "cand"):
        return run(
            self.service.onboard(
                adapter=adapter,
                provider_key=key,
                display_name="Candidate",
                auth_types=[AuthType.API_KEY],
                credential_ref="secret-ref://cand",
            )
        )


class TestHappyPath:
    def test_steps_pass_in_checklist_order(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter())
        assert report.steps_passed == (
            "step-3-real-manifest",
            "step-5-credential-validation",
            "step-6-health-check",
            "step-4-declared-operations",
            "step-11-register-provider",
            "step-13-provider-kept-disabled",
            "step-12-register-bindings",
        )

    def test_provider_registered_disabled_with_models_and_bindings(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter())
        entry = world.providers.get("cand")
        assert entry.provider.status is ProviderStatus.DISABLED
        assert report.registered_model_keys == ("cand/cand-1",)
        model = world.models.get("cand/cand-1")
        binding = world.bindings.get(entry.provider.id, model.id)
        assert binding.provider_model_name == "cand-1"

    def test_disabled_provider_is_not_routable(self) -> None:
        world = World()
        world.onboard(FakeAdapter())
        assert world.providers.get("cand").is_routable is False

    def test_unverified_steps_reported_honestly(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter())
        assert any("step-9-contract-tests" in u for u in report.unverified)
        assert any("step-10-security-checks" in u for u in report.unverified)

    def test_only_opaque_credential_ref_reaches_the_adapter(self) -> None:
        world = World()
        adapter = FakeAdapter()
        world.onboard(adapter)
        assert adapter.seen_credential_refs == ["secret-ref://cand"]

    def test_no_discovered_models_registers_provider_without_bindings(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter(models=[]))
        assert report.registered_model_keys == ()
        assert "step-12-register-bindings" not in report.steps_passed
        assert world.providers.get("cand").provider.status is ProviderStatus.DISABLED


class TestGates:
    def test_template_manifest_refused_at_step_3(self) -> None:
        world = World()
        adapter = FakeAdapter(manifest=_manifest(is_template=True))
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(adapter)
        assert exc.value.step == "step-3-real-manifest"

    def test_non_functional_manifest_refused_at_step_3(self) -> None:
        world = World()
        adapter = FakeAdapter(manifest=_manifest(is_functional=False))
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(adapter)
        assert exc.value.step == "step-3-real-manifest"

    def test_invalid_credential_refused_at_step_5(self) -> None:
        world = World()
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(FakeAdapter(credential_ok=False))
        assert exc.value.step == "step-5-credential-validation"
        # Nothing was registered.
        assert world.providers.all_keys() == []

    def test_unhealthy_provider_refused_at_step_6(self) -> None:
        world = World()
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(FakeAdapter(healthy=False))
        assert exc.value.step == "step-6-health-check"

    def test_zero_operations_refused_at_step_4(self) -> None:
        world = World()
        adapter = FakeAdapter(manifest=_manifest(operations=[]))
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(adapter)
        assert exc.value.step == "step-4-declared-operations"

    def test_duplicate_provider_refused_at_step_11(self) -> None:
        world = World()
        world.onboard(FakeAdapter())
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(FakeAdapter())
        assert exc.value.step == "step-11-register-provider"

    def test_unknown_modality_refused_never_guessed(self) -> None:
        world = World()
        adapter = FakeAdapter(models=[{"provider_model_name": "x", "modalities": ["telepathy"]}])
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(adapter)
        assert exc.value.step == "step-12-register-bindings"
        assert "telepathy" in exc.value.reason
        # Refused BEFORE any registration happened.
        assert world.providers.all_keys() == []

    def test_explicit_prefix_binds_second_provider_to_existing_model_r190(self) -> None:
        """R190 (P-R189-01, operator YES) — BEFORE: this exact scenario was
        refused at step 12 (duplicate model key, full rollback; see
        evidence/r190/before_pins_now_fail_7a846a46.txt for the old pin).
        AFTER: an EXPLICIT prefix that resolves to an existing logical Model
        binds the new provider to that Model — one Model, two bindings."""
        world = World()
        world.onboard(FakeAdapter(), key="first")
        adapter = FakeAdapter(models=[{"provider_model_name": "cand-1", "modalities": ["text"]}])
        report = run(
            world.service.onboard(
                adapter=adapter,
                provider_key="second",
                display_name="Second",
                auth_types=[AuthType.API_KEY],
                credential_ref="secret-ref://second",
                model_key_prefix="first",  # explicit: resolves to first/cand-1
            )
        )
        assert report.registered_model_keys == ("first/cand-1",)
        model = world.models.get("first/cand-1")
        assert [m.model_key for m in world.models.all_models()] == ["first/cand-1"]
        bound = {b.provider_id for b in world.bindings.bindings_for_model(model.id)}
        assert bound == {
            world.providers.get("first").provider.id,
            world.providers.get("second").provider.id,
        }

    def test_default_prefix_collision_is_still_refused_and_rolled_back(self) -> None:
        """Pre-R190 rule preserved: WITHOUT an explicit prefix the default
        prefix is the provider key, so a collision is foreign state and the
        whole onboarding is refused at step 12 with full rollback."""
        world = World()
        # Seed "third/cand-1" under another owner via an explicit prefix.
        run(
            world.service.onboard(
                adapter=FakeAdapter(),
                provider_key="seed",
                display_name="Seed",
                auth_types=[AuthType.API_KEY],
                credential_ref="secret-ref://seed",
                model_key_prefix="third",
            )
        )
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(FakeAdapter(), key="third")
        assert exc.value.step == "step-12-register-bindings"
        from core.providers.errors import ProviderNotRegistered

        with pytest.raises(ProviderNotRegistered):
            world.providers.get("third")
        # Seed provider and its model untouched.
        model = world.models.get("third/cand-1")
        assert {b.provider_id for b in world.bindings.bindings_for_model(model.id)} == {
            world.providers.get("seed").provider.id
        }


class TestStep14AdminEnable:
    def test_prepared_draft_publishes_through_real_admin_service(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter())
        # Compose the REAL admin service over the SAME registries.
        router = SimpleScoringRouter(world.providers, world.models, world.bindings)
        admin = AdminConfigService(
            providers=world.providers,
            models=world.models,
            usage=InMemoryUsageAccounting(),
            routing=router,
            audit_log=InMemoryAuditLog(),
            bindings=world.bindings,
        )
        tenant, actor = uuid4(), uuid4()
        change = admin.draft(
            tenant_id=tenant,
            actor_id=actor,
            action=AdminAction.ENABLE_PROVIDER,
            payload=report.enable_draft_payload,
        )
        validated = admin.validate(tenant, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED
        admin.preview(tenant, change.id)
        admin.publish(tenant, change.id)
        entry = world.providers.get("cand")
        assert entry.provider.status is ProviderStatus.ACTIVE
        assert entry.is_routable is True
