"""Provider onboarding orchestration (31 §19 steps 3–14, machine-run subset).

WHAT THIS IS
------------
One coordinator that walks a candidate provider through the 31 §19
checklist steps that are RUNTIME-checkable, in order, refusing loudly at
the first failed step (no silent skips):

    step 3   manifest is real (not template; functional; real declaration)
    step 5   credential handled as an opaque ref only (validate_credential)
    step 6   health check works
    step 4   declared operations only (>=1 operation declared)
    step 11  register provider in the Provider Registry (status=DISABLED)
    step 12  register model/provider bindings from discover_models
    step 13  keep provider disabled until verification passes
    step 14  enable via Admin/Config only (returned as a PREPARED admin
             draft payload — this service NEVER enables anything itself)

WHAT THIS IS NOT (honest scope, 41 §49)
---------------------------------------
- Steps 1–2 and 7–10 (docs, error-map authorship, contract-test suites,
  security review) are HUMAN/CI work: this service verifies their
  runtime-observable artifacts only (manifest declarations) and reports
  what it could not verify in ``unverified``.
- No secret material ever passes through here: the adapter resolves the
  credential_ref itself (20 §5); this service sees the opaque ref only.

Composition-agnostic: registries and the adapter are injected; no I/O
besides the adapter's own methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from core.contracts.base import JsonObject
from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    CredentialStatus,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    DiscoveredModel,
    HealthScope,
    ProviderHealthState,
    ProviderManifest,
)
from core.providers.errors import DuplicateRegistration, ProviderNotRegistered
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry


class OnboardingRefused(Exception):
    """A 31 §19 step failed — onboarding stops AT that step, loudly."""

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"onboarding refused at {step}: {reason}")


#: Modality strings the domain enum knows; anything else is refused, never
#: guessed (30 §4.3 forbidden assumptions).
_KNOWN_MODALITIES = {m.value for m in Modality}


@dataclass(frozen=True)
class OnboardingReport:
    """What happened, step by step — evidence, not vibes (41 §49)."""

    provider_id: UUID
    provider_key: str
    steps_passed: tuple[str, ...]
    unverified: tuple[str, ...]
    discovered_models: tuple[str, ...]
    registered_model_keys: tuple[str, ...]
    #: The PREPARED step-14 admin draft payload (action=enable_provider).
    #: Publishing it through AdminConfigService is the ONLY enable path.
    enable_draft_payload: JsonObject = field(default_factory=dict)


#: 31 §19 steps this service can NOT verify at runtime — reported verbatim.
_UNVERIFIED_STEPS: tuple[str, ...] = (
    "step-1-provider-type-identified (human)",
    "step-2-capabilities-documented (human)",
    "step-7-error-normalization-authored (verified only via manifest.errors)",
    "step-8-rate-limit-behavior (verified only via manifest.rate_limits)",
    "step-9-contract-tests (CI evidence, not runtime)",
    "step-10-security-checks (CI evidence, not runtime)",
)


class ProviderOnboardingService:
    """Walk 31 §19 for one candidate provider over the LIVE registries."""

    def __init__(
        self,
        *,
        providers: ProviderRegistry,
        models: ModelRegistry,
        bindings: BindingRegistry,
    ) -> None:
        self._providers = providers
        self._models = models
        self._bindings = bindings

    async def onboard(
        self,
        *,
        adapter: ProviderAdapterPort,
        provider_key: str,
        display_name: str,
        auth_types: list[AuthType],
        credential_ref: str,
        model_tier: ModelTier = ModelTier.MEDIUM,
        model_key_prefix: str | None = None,
    ) -> OnboardingReport:
        """Run the checklist; return the report or raise OnboardingRefused.

        ``credential_ref`` is the opaque secret-manager reference (20 §5) —
        never the key itself. ``model_key_prefix`` defaults to provider_key,
        producing model keys ``{prefix}/{provider_model_name}``.
        """
        steps: list[str] = []

        # --- step 3: manifest is real, not template (31 §22) -----------------
        manifest = adapter.get_manifest()
        problem = self._manifest_problem(manifest)
        if problem is not None:
            raise OnboardingRefused("step-3-real-manifest", problem)
        steps.append("step-3-real-manifest")

        # --- duplicate guard BEFORE any provider I/O --------------------------
        try:
            self._providers.get(provider_key)
        except ProviderNotRegistered:
            pass
        else:
            raise OnboardingRefused(
                "step-11-register-provider",
                f"provider already registered: {provider_key}",
            )

        # --- step 5: credential handling (opaque ref -> ACTIVE) ---------------
        credential = await adapter.validate_credential(credential_ref)
        if credential.status is not CredentialStatus.ACTIVE:
            raise OnboardingRefused(
                "step-5-credential-validation",
                f"credential status is {credential.status.value} "
                f"(ref={credential.credential_ref})",
            )
        steps.append("step-5-credential-validation")

        # --- step 6: health check works ---------------------------------------
        health = await adapter.health_check(HealthScope.PROVIDER)
        if health.state is not ProviderHealthState.HEALTHY:
            raise OnboardingRefused(
                "step-6-health-check",
                f"provider health is {health.state.value}",
            )
        steps.append("step-6-health-check")

        # --- step 4 (observable half): >=1 declared operation ------------------
        if not manifest.operations:
            raise OnboardingRefused(
                "step-4-declared-operations",
                "manifest declares no operations (30 §5: undeclared = ineligible)",
            )
        steps.append("step-4-declared-operations")

        # --- step 12 input: discover + normalize BEFORE registering anything ---
        discovered = await adapter.discover_models()
        normalized = self._normalize_discovered(discovered)

        # --- step 11: register provider, status=DISABLED (step 13) ------------
        provider = Provider(
            id=uuid4(),
            provider_key=provider_key,
            display_name=display_name,
            status=ProviderStatus.DISABLED,  # step 13: disabled until enabled
            auth_types=auth_types,
            supports_account_pool=manifest.account_pool.supported,
        )
        self._providers.register(provider, manifest)
        steps.append("step-11-register-provider")
        steps.append("step-13-provider-kept-disabled")

        # --- step 12: register models + bindings ------------------------------
        prefix = model_key_prefix if model_key_prefix is not None else provider_key
        registered_keys: list[str] = []
        try:
            for dm, modalities in normalized:
                model_key = f"{prefix}/{dm.provider_model_name}"
                model = Model(
                    id=uuid4(),
                    model_key=model_key,
                    display_name=dm.provider_model_name,
                    tier=model_tier,
                    modalities=modalities,
                    # Per-model capability facts are not invented (30 §4.3);
                    # capability eligibility stays a manifest question.
                    capabilities=[],
                    status=ModelStatus.ACTIVE,
                )
                self._models.register(model)
                self._bindings.register(
                    ProviderModelBinding(
                        provider_id=provider.id,
                        model_id=model.id,
                        provider_model_name=dm.provider_model_name,
                        availability=BindingAvailability.AVAILABLE,
                    )
                )
                registered_keys.append(model_key)
        except DuplicateRegistration:
            # Roll the WHOLE onboarding back — a half-registered provider
            # would be parallel state (P2). Remove in reverse order.
            for key in registered_keys:
                model = self._models.get(key)
                self._bindings.remove(provider.id, model.id)
                self._models.remove(key)
            self._providers.remove(provider_key)
            raise OnboardingRefused(
                "step-12-register-bindings",
                "duplicate model key during binding registration — "
                "onboarding rolled back completely",
            ) from None
        if registered_keys:
            steps.append("step-12-register-bindings")

        # --- step 14: PREPARE the admin enable draft (never publish it) --------
        enable_payload: JsonObject = {"provider_key": provider_key}

        return OnboardingReport(
            provider_id=provider.id,
            provider_key=provider_key,
            steps_passed=tuple(steps),
            unverified=_UNVERIFIED_STEPS,
            discovered_models=tuple(d.provider_model_name for d in discovered),
            registered_model_keys=tuple(registered_keys),
            enable_draft_payload=enable_payload,
        )

    # --- internals -------------------------------------------------------------

    @staticmethod
    def _manifest_problem(manifest: ProviderManifest) -> str | None:
        """31 §22: 'manifest is real, not template'."""
        if manifest.is_template:
            return "manifest declares is_template=true (31 §10)"
        if not manifest.is_functional:
            return "manifest declares is_functional=false (31 §10)"
        if manifest.real_provider_required:
            return "manifest declares real_provider_required=true (31 §10)"
        if not manifest.auth.types:
            return "real manifest must declare at least one auth type (30 §7)"
        return None

    @staticmethod
    def _normalize_discovered(
        discovered: list[DiscoveredModel],
    ) -> list[tuple[DiscoveredModel, list[Modality]]]:
        """Map provider-declared modalities onto the domain enum.

        Unknown modality strings are refused (never guessed); a model
        declaring NO modalities defaults to text — the only safe minimum
        (03 §4 requires >=1 modality).
        """
        normalized: list[tuple[DiscoveredModel, list[Modality]]] = []
        for dm in discovered:
            unknown = [m for m in dm.modalities if m not in _KNOWN_MODALITIES]
            if unknown:
                raise OnboardingRefused(
                    "step-12-register-bindings",
                    f"model '{dm.provider_model_name}' declares unknown "
                    f"modalities {unknown} (30 §4.3: never guessed)",
                )
            modalities = (
                [Modality(m) for m in dm.modalities]
                if dm.modalities
                else [Modality.TEXT]
            )
            normalized.append((dm, modalities))
        return normalized
