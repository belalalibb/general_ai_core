"""Gap 1a/1b — onboarding executability + durability seams (hermetic pins).

The remediation seams added to ProviderOnboardingService are OPTIONAL and
prior behavior is unchanged (test_onboarding_service.py keeps pinning
that); THIS module pins the new behavior when they are bound:

- adapters/credential_refs maps (the SAME maps ExecutionService reads)
  are populated on success and emptied again on rollback;
- persistence write-through happens AFTER in-memory success, in
  provider→model→binding order, and NEVER on a refused onboarding;
- step 5: an adapter whose validate_credential raises NotImplementedError
  (e.g. GatewayCredentialCheckUnsupported) is honestly UNVERIFIED — the
  walk continues; a definite non-ACTIVE answer still refuses.

Async driven by asyncio.run (ADR-0001; no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import pytest

from core.contracts.domain import (
    AuthType,
    Model,
    Provider,
    ProviderModelBinding,
)
from core.providers import (
    BindingRegistry,
    ModelRegistry,
    OnboardingRefused,
    ProviderOnboardingService,
    ProviderRegistry,
)
from core.providers.ports import ProviderAdapterPort
from tests.providers.test_onboarding_service import FakeAdapter


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class RecordingPersistence:
    """OnboardingPersistencePort fake — records call order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def persist_provider(self, provider: Provider) -> None:
        self.calls.append(("provider", provider.provider_key))

    def persist_model(self, model: Model) -> None:
        self.calls.append(("model", model.model_key))

    def persist_binding(self, binding: ProviderModelBinding) -> None:
        self.calls.append(("binding", binding.provider_model_name))


class NoCheckSurfaceAdapter(FakeAdapter):
    """validate_credential has NO wire surface (gateway v1 posture)."""

    async def validate_credential(self, credential_ref: str):  # type: ignore[override]
        raise NotImplementedError("no credential-validation wire surface in v1")


class SeamWorld:
    def __init__(self, *, persistence: RecordingPersistence | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapters: dict[UUID, ProviderAdapterPort] = {}
        self.credential_refs: dict[UUID, str] = {}
        self.persistence = persistence
        self.service = ProviderOnboardingService(
            providers=self.providers,
            models=self.models,
            bindings=self.bindings,
            adapters=self.adapters,
            credential_refs=self.credential_refs,
            persistence=persistence,
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


class TestExecutabilitySeam:
    def test_success_populates_the_execution_service_maps(self) -> None:
        world = SeamWorld()
        adapter = FakeAdapter()
        report = world.onboard(adapter)
        assert world.adapters[report.provider_id] is adapter
        assert world.credential_refs[report.provider_id] == "secret-ref://cand"

    def test_rollback_empties_the_maps_again(self) -> None:
        world = SeamWorld()
        # Two discovered models with the SAME name ⇒ duplicate model key
        # mid-registration ⇒ full rollback.
        adapter = FakeAdapter(
            models=[
                {"provider_model_name": "dup", "modalities": ["text"]},
                {"provider_model_name": "dup", "modalities": ["text"]},
            ]
        )
        with pytest.raises(OnboardingRefused) as excinfo:
            world.onboard(adapter)
        assert excinfo.value.step == "step-12-register-bindings"
        assert world.adapters == {}
        assert world.credential_refs == {}

    def test_refusal_before_registration_touches_no_map(self) -> None:
        world = SeamWorld()
        with pytest.raises(OnboardingRefused):
            world.onboard(FakeAdapter(credential_ok=False))
        assert world.adapters == {}
        assert world.credential_refs == {}


class TestDurabilitySeam:
    def test_write_through_after_success_in_order(self) -> None:
        persistence = RecordingPersistence()
        world = SeamWorld(persistence=persistence)
        report = world.onboard(FakeAdapter())
        assert persistence.calls == [
            ("provider", "cand"),
            ("model", "cand/cand-1"),
            ("binding", "cand-1"),
        ]
        assert "step-durable-persistence" in report.steps_passed

    def test_refused_onboarding_never_persists_a_row(self) -> None:
        persistence = RecordingPersistence()
        world = SeamWorld(persistence=persistence)
        with pytest.raises(OnboardingRefused):
            world.onboard(FakeAdapter(healthy=False))
        assert persistence.calls == []

    def test_rolled_back_onboarding_never_persists_a_row(self) -> None:
        persistence = RecordingPersistence()
        world = SeamWorld(persistence=persistence)
        with pytest.raises(OnboardingRefused):
            world.onboard(
                FakeAdapter(
                    models=[
                        {"provider_model_name": "dup", "modalities": ["text"]},
                        {"provider_model_name": "dup", "modalities": ["text"]},
                    ]
                )
            )
        assert persistence.calls == []


class TestStep5NoCheckSurface:
    def test_not_implemented_is_unverified_not_failed(self) -> None:
        world = SeamWorld()
        report = world.onboard(NoCheckSurfaceAdapter())
        assert "step-5-credential-validation" not in report.steps_passed
        assert any(
            u.startswith("step-5-credential-validation (adapter has no check")
            for u in report.unverified
        )
        # The walk CONTINUED — the provider registered (disabled).
        assert "step-11-register-provider" in report.steps_passed
        assert world.providers.get("cand").is_routable is False

    def test_definite_invalid_still_refuses_loudly(self) -> None:
        world = SeamWorld()
        with pytest.raises(OnboardingRefused) as excinfo:
            world.onboard(FakeAdapter(credential_ok=False))
        assert excinfo.value.step == "step-5-credential-validation"
