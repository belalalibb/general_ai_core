"""Core-side provider/model/binding registries + health aggregation.

T-IMPL-019 (MVP Phase 4 slice 2, 41 §43). Spec anchors:

- 30 §4.2: "the registry trusts ONLY this declaration" — eligibility is
  computed from the provider's manifest, never inferred.
- 30 §5: a provider without the requested operation "is ineligible for that
  task" — never emulated.
- 30 §7 + 20 §4: unknown capability => DENY (deny-by-default).
- 30 §11: provider health is SEPARATE from account health; "one account
  failed" must never be conflated with "the whole provider is down".
- 31 §10 registry behavior with templates (verbatim rules):
    template_disabled providers are excluded from routing
    is_functional=false providers are excluded from execution
    real_provider_required=true providers cannot pass health checks
  The registry may still LOAD templates (for schema validation, docs, and
  scaffolding tests) — loading is allowed, eligibility is not.
- 03 §4: Model / Provider / ProviderModelBinding entities; Model != Provider
  != Account (architecture invariant).

Everything here is in-memory and hermetic: real persistence binds these
registries through infrastructure/ (ADR-0002) in a later task; the Router
consumes eligibility answers, it never re-derives them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from core.contracts.domain import (
    Model,
    ModelStatus,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    AccountHealthCheckState,
    ProviderHealth,
    ProviderHealthState,
    ProviderManifest,
    ProviderOperation,
)
from core.providers.errors import (
    BindingNotFound,
    DuplicateRegistration,
    ModelNotRegistered,
    ProviderNotEligible,
    ProviderNotRegistered,
)

#: Manifest status word that marks a scaffold template (31 §7/§10).
TEMPLATE_DISABLED_STATUS = "template_disabled"


class RegisteredProvider:
    """One provider registration: domain record + its manifest declaration.

    Immutable pairing — replacing either part is a re-registration, so the
    registry can never hold a record that drifted from its declaration.
    """

    __slots__ = ("manifest", "provider")

    def __init__(self, provider: Provider, manifest: ProviderManifest) -> None:
        self.provider = provider
        self.manifest = manifest

    @property
    def is_template(self) -> bool:
        """True if ANY 31 §7 template marker is present (defense in depth)."""
        return (
            self.manifest.is_template
            or self.manifest.status == TEMPLATE_DISABLED_STATUS
            or self.manifest.real_provider_required
        )

    @property
    def is_executable(self) -> bool:
        """31 §10: is_functional=false providers are excluded from execution."""
        return self.manifest.is_functional and not self.is_template

    @property
    def is_routable(self) -> bool:
        """Routing eligibility: active domain status AND executable manifest.

        31 §10: template_disabled providers are excluded from routing.
        03 §4: disabled/maintenance providers are not routing candidates.
        """
        return self.provider.status is ProviderStatus.ACTIVE and self.is_executable


class ProviderRegistry:
    """In-memory provider registry (30 §4.2, 31 §10).

    Keys are the domain ``provider_key``; identity duplicates are rejected
    rather than silently replaced (explicit re-registration API instead).
    """

    def __init__(self) -> None:
        self._by_key: dict[str, RegisteredProvider] = {}
        self._by_id: dict[UUID, RegisteredProvider] = {}

    # -- registration -----------------------------------------------------------

    def register(self, provider: Provider, manifest: ProviderManifest) -> None:
        """Register a provider with its manifest declaration.

        Templates ARE loadable (31 §10 allows loading for schema validation,
        docs, and scaffolding tests) — they are excluded at eligibility time,
        not at load time.
        """
        if provider.provider_key in self._by_key or provider.id in self._by_id:
            msg = f"provider already registered: {provider.provider_key}"
            raise DuplicateRegistration(msg)
        entry = RegisteredProvider(provider, manifest)
        self._by_key[provider.provider_key] = entry
        self._by_id[provider.id] = entry

    def replace(self, provider: Provider, manifest: ProviderManifest) -> None:
        """Explicit re-registration (admin update path)."""
        existing = self._by_key.get(provider.provider_key)
        if existing is not None:
            del self._by_id[existing.provider.id]
        entry = RegisteredProvider(provider, manifest)
        self._by_key[provider.provider_key] = entry
        self._by_id[provider.id] = entry

    def remove(self, provider_key: str) -> None:
        """Remove a registration (admin rollback of REGISTER_PROVIDER).

        Rollback must restore reality (21 §8): rolling back a published
        registration means the row is GONE again, never merely disabled.
        Unknown key raises — removal of nothing would fake a rollback.
        """
        entry = self._by_key.get(provider_key)
        if entry is None:
            raise ProviderNotRegistered(provider_key)
        del self._by_key[provider_key]
        del self._by_id[entry.provider.id]

    # -- lookup -----------------------------------------------------------------

    def get(self, provider_key: str) -> RegisteredProvider:
        entry = self._by_key.get(provider_key)
        if entry is None:
            raise ProviderNotRegistered(provider_key)
        return entry

    def get_by_id(self, provider_id: UUID) -> RegisteredProvider:
        entry = self._by_id.get(provider_id)
        if entry is None:
            raise ProviderNotRegistered(str(provider_id))
        return entry

    def all_keys(self) -> list[str]:
        """Every loaded provider key, INCLUDING templates (loading is legal)."""
        return sorted(self._by_key)

    # -- eligibility (the registry's real job) -----------------------------------

    def supports_operation(
        self, provider_key: str, operation: ProviderOperation
    ) -> bool:
        """Manifest-declared operation check (30 §5). Unknown => False."""
        entry = self.get(provider_key)
        return operation in entry.manifest.operations

    def supports_capability(self, provider_key: str, capability: str) -> bool:
        """Deny-by-default capability check (30 §7, 20 §4).

        A capability key the manifest schema does not know is DENIED, never
        guessed. ``getattr`` default False covers exactly that case.
        """
        entry = self.get(provider_key)
        declared: object = getattr(entry.manifest.capabilities, capability, False)
        return declared is True

    def ensure_eligible(
        self, provider_key: str, operation: ProviderOperation
    ) -> RegisteredProvider:
        """Gate used by execution paths: raise unless fully eligible.

        Order of checks is deliberate: existence -> template/functional
        exclusion (31 §10) -> domain status -> declared operation (30 §5).
        """
        entry = self.get(provider_key)
        if entry.is_template:
            msg = f"provider is a scaffold template (31 §10): {provider_key}"
            raise ProviderNotEligible(msg)
        if not entry.manifest.is_functional:
            msg = f"provider is not functional (31 §10): {provider_key}"
            raise ProviderNotEligible(msg)
        if entry.provider.status is not ProviderStatus.ACTIVE:
            msg = f"provider status is {entry.provider.status}: {provider_key}"
            raise ProviderNotEligible(msg)
        if operation not in entry.manifest.operations:
            msg = f"operation {operation} not declared by {provider_key}"
            raise ProviderNotEligible(msg)
        return entry

    def routing_candidates(
        self, operation: ProviderOperation | None = None
    ) -> list[RegisteredProvider]:
        """Providers the Router may consider (31 §10 exclusions applied).

        Optionally narrowed to those declaring ``operation`` (30 §5).
        """
        candidates = [e for e in self._by_key.values() if e.is_routable]
        if operation is not None:
            candidates = [c for c in candidates if operation in c.manifest.operations]
        return sorted(candidates, key=lambda e: e.provider.provider_key)


class ModelRegistry:
    """In-memory model registry (03 §4). Model records are Router contracts."""

    def __init__(self) -> None:
        self._by_key: dict[str, Model] = {}
        self._by_id: dict[UUID, Model] = {}

    def register(self, model: Model) -> None:
        if model.model_key in self._by_key or model.id in self._by_id:
            msg = f"model already registered: {model.model_key}"
            raise DuplicateRegistration(msg)
        self._by_key[model.model_key] = model
        self._by_id[model.id] = model

    def replace(self, model: Model) -> None:
        """Explicit re-registration (admin update path, 21 §4 Models row).

        Mirrors ``ProviderRegistry.replace``: the admin control plane
        publishes model status changes (enable/disable) by replacing the
        stored frozen record — routing sees the change immediately through
        ``active_models()``; there is no parallel admin copy.
        """
        existing = self._by_key.get(model.model_key)
        if existing is not None:
            del self._by_id[existing.id]
        self._by_key[model.model_key] = model
        self._by_id[model.id] = model

    def remove(self, model_key: str) -> None:
        """Remove a registration (admin rollback of REGISTER_MODEL).

        Same 21 §8 posture as :meth:`ProviderRegistry.remove`.
        """
        model = self._by_key.get(model_key)
        if model is None:
            raise ModelNotRegistered(model_key)
        del self._by_key[model_key]
        del self._by_id[model.id]

    def get(self, model_key: str) -> Model:
        model = self._by_key.get(model_key)
        if model is None:
            raise ModelNotRegistered(model_key)
        return model

    def get_by_id(self, model_id: UUID) -> Model:
        model = self._by_id.get(model_id)
        if model is None:
            raise ModelNotRegistered(str(model_id))
        return model

    def all_models(self) -> list[Model]:
        """Every registered model, INCLUDING non-ACTIVE (admin read view, 21 §5).

        The admin control plane must SEE disabled models to re-enable them
        (21 §4 Models row); routing keeps using ``active_models`` — this
        read surface changes no eligibility rule.
        """
        return sorted(self._by_key.values(), key=lambda m: m.model_key)

    def active_models(self) -> list[Model]:
        """Routing pool: only ACTIVE models (03 §4 status)."""
        return sorted(
            (m for m in self._by_key.values() if m.status is ModelStatus.ACTIVE),
            key=lambda m: m.model_key,
        )

    def models_with_capability(self, capability: str) -> list[Model]:
        """Declared-capability filter (11 §5): undeclared => ineligible."""
        return [m for m in self.active_models() if capability in m.capabilities]

    def models_in_tier(self, tier: str) -> list[Model]:
        """Tier-registry query (41 §9 'Tier Registry'; FINAL Phase 6,
        T-IMPL-055).

        Compares against ``tier.value`` with an OPEN string parameter — the
        same semantics as the Router's TierModelPolicy hard filter (10 §13.2:
        allowed tiers are admin-configurable, so policy tier strings stay
        open; the domain enum's ``custom`` bucket carries admin-defined
        tiers). ACTIVE models only; unknown tier => empty list, never a
        guess (11 §5).
        """
        return [m for m in self.active_models() if m.tier.value == tier]

    def models_with_modality(self, modality: str) -> list[Model]:
        """Modality-registry query (41 §9 'Modality Registry'; FINAL Phase 6,
        T-IMPL-055).

        Declared-modality filter with the same semantics as the Router's
        model-level exclusion (11 §5): a modality the model did not declare
        makes it ineligible — undeclared/unknown => excluded, never guessed.
        Compares against ``Modality.value`` strings so callers do not need
        the enum type.
        """
        return [
            m
            for m in self.active_models()
            if modality in {mod.value for mod in m.modalities}
        ]


class BindingRegistry:
    """In-memory provider<->model binding registry (03 §4).

    The same model may be bound to multiple providers; availability is a
    per-binding fact — never inferred from provider or model records.
    """

    def __init__(self) -> None:
        self._bindings: dict[tuple[UUID, UUID], ProviderModelBinding] = {}

    def register(self, binding: ProviderModelBinding) -> None:
        key = (binding.provider_id, binding.model_id)
        if key in self._bindings:
            msg = f"binding already registered: {key}"
            raise DuplicateRegistration(msg)
        self._bindings[key] = binding

    def remove(self, provider_id: UUID, model_id: UUID) -> None:
        """Remove a binding (admin rollback of REGISTER_MODEL bindings)."""
        key = (provider_id, model_id)
        if key not in self._bindings:
            raise BindingNotFound(f"{key}")
        del self._bindings[key]

    def get(self, provider_id: UUID, model_id: UUID) -> ProviderModelBinding:
        binding = self._bindings.get((provider_id, model_id))
        if binding is None:
            raise BindingNotFound(f"({provider_id}, {model_id})")
        return binding

    def bindings_for_model(self, model_id: UUID) -> list[ProviderModelBinding]:
        return [b for b in self._bindings.values() if b.model_id == model_id]

    def bindings_for_provider(self, provider_id: UUID) -> list[ProviderModelBinding]:
        return [b for b in self._bindings.values() if b.provider_id == provider_id]


def aggregate_provider_health(
    entry: RegisteredProvider,
    account_states: dict[str, AccountHealthCheckState] | None = None,
    *,
    provider_signal: ProviderHealthState | None = None,
    checked_at: datetime | None = None,
) -> ProviderHealth:
    """Aggregate provider-wide health (30 §11, 31 §10).

    Rules, in precedence order:

    1. Templates / real_provider_required=true CANNOT pass health checks
       (31 §10) => UNAVAILABLE, always.
    2. An explicit provider-level signal (an outage/suspension observed at
       the PROVIDER scope) wins over account arithmetic.
    3. Account states only ever DEGRADE, never kill: some non-READY accounts
       => DEGRADED; even ALL accounts failing yields DEGRADED, because "one
       account failed" (or all of them) is account-scope evidence, not
       provider-scope evidence (30 §11).
    4. No accounts + no adverse signal => HEALTHY (account pools are
       optional, 30 §10.1 — absence of accounts is not evidence of anything).
    """
    accounts = dict(account_states or {})
    stamp = checked_at if checked_at is not None else datetime.now(tz=UTC)
    provider_id = entry.manifest.id

    if entry.is_template or not entry.manifest.is_functional:
        return ProviderHealth(
            provider_id=provider_id,
            state=ProviderHealthState.UNAVAILABLE,
            accounts=accounts,
            checked_at=stamp,
            detail="template/non-functional provider cannot pass health checks",
        )

    if provider_signal is not None and provider_signal is not ProviderHealthState.HEALTHY:
        return ProviderHealth(
            provider_id=provider_id,
            state=provider_signal,
            accounts=accounts,
            checked_at=stamp,
            detail="explicit provider-scope signal",
        )

    unhealthy = [
        key
        for key, state in accounts.items()
        if state is not AccountHealthCheckState.READY
    ]
    if unhealthy:
        return ProviderHealth(
            provider_id=provider_id,
            state=ProviderHealthState.DEGRADED,
            accounts=accounts,
            checked_at=stamp,
            detail=f"{len(unhealthy)}/{len(accounts)} accounts not READY",
        )

    return ProviderHealth(
        provider_id=provider_id,
        state=ProviderHealthState.HEALTHY,
        accounts=accounts,
        checked_at=stamp,
        detail=None,
    )
