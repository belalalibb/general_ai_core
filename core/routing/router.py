"""Simple scoring router — MVP Phase 5 slice 1 (41 §44 "router simple scoring").

Spec anchors (11_MODEL_ROUTING_AND_MODEL_CONTROL.md):

- §4  selection modes AUTO / TIER / EXPLICIT_MODEL (this slice's scope; the
  multi-model EXPLICIT_MODELS strategies and AGENT_NODE_MAPPING resolution
  belong to the execution-graph slice and are rejected loudly, never guessed).
- §5  hard eligibility filters; "Unknown = ineligible" (deny-by-default,
  matching 30 §7 / 20 §4).
- §6  configurable scoring formula (weights policy-driven + versioned).
- §7  candidate score shape with human-readable reasons/risks.
- §8/§14 fallback policies; explicit-model default = same_model_different_
  provider first, same_tier only if explicitly allowed; disabled => fail
  clearly.
- §13 priority order: explicit user choice outranks Router preference but
  never availability/eligibility.
- §16 the resolved policy snapshot is recorded on the decision.

Candidate sourcing is EXCLUSIVELY the T-IMPL-019 registries: templates and
non-functional providers are excluded by ``ProviderRegistry.routing_candidates``
by construction (31 §10); only ACTIVE models enter the pool (03 §4); binding
availability is a per-binding fact (never inferred).

Filters this slice does NOT implement (they require services that do not
exist yet and are deferred to their own phases, never faked): tenant/plan
entitlement, rate-limit budget, data-boundary, tool permissions (11 §5).
The eligibility pipeline is ordered so those filters slot in ahead of
scoring without contract changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from core.contracts.domain import BindingAvailability, Model, ProviderModelBinding
from core.contracts.model_policy import (
    AutoModelPolicy,
    ExplicitModelPolicy,
    FallbackScope,
    ModelPolicy,
    TierModelPolicy,
)
from core.contracts.routing import (
    CandidateScore,
    ExclusionRecord,
    RoutingDecision,
    RoutingRequest,
    ScoringWeights,
)
from core.providers.registry import (
    BindingRegistry,
    ModelRegistry,
    ProviderRegistry,
    RegisteredProvider,
)
from core.routing.errors import (
    FallbackNotConfigured,
    NoEligibleCandidates,
    RoutingError,
)

#: Default request-level policy when none is provided (10 §13 posture).
_AUTO_POLICY = AutoModelPolicy(type="auto")


class UnsupportedPolicyType(RoutingError):
    """Policy types outside this slice's scope are rejected, never guessed."""


@dataclass(frozen=True)
class _Candidate:
    """Internal (model, provider, binding) triple that survived filtering."""

    model: Model
    provider: RegisteredProvider
    binding: ProviderModelBinding
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


class SimpleScoringRouter:
    """Deterministic, explainable model/provider selection (11 §5-§8, §13-§14).

    The Router consumes registry eligibility answers; it never re-derives
    manifest facts (30 §4.2) and never mutates registries.
    """

    def __init__(
        self,
        providers: ProviderRegistry,
        models: ModelRegistry,
        bindings: BindingRegistry,
        *,
        default_weights: ScoringWeights | None = None,
        admin_fallback_chain: tuple[str, ...] | None = None,
    ) -> None:
        self._providers = providers
        self._models = models
        self._bindings = bindings
        self._default_weights = default_weights or ScoringWeights()
        # 11 §8 admin_defined_chain: ordered model_keys, admin-configured.
        self._admin_fallback_chain = admin_fallback_chain

    # -- public API ---------------------------------------------------------------

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Produce a routing decision, or fail clearly (11 §14)."""
        policy = request.model_policy if request.model_policy is not None else _AUTO_POLICY
        if not isinstance(policy, AutoModelPolicy | TierModelPolicy | ExplicitModelPolicy):
            msg = (
                f"model policy type '{policy.type}' is outside the simple-scoring "
                "slice (explicit_models/agent_node_mapping resolve in the "
                "execution-graph slice)"
            )
            raise UnsupportedPolicyType(msg)

        weights = request.weights if request.weights is not None else self._default_weights
        excluded: list[ExclusionRecord] = []
        candidates = self._eligible_candidates(request, policy, excluded)

        if not candidates:
            msg = "no eligible model/provider candidates (11 §5: unknown = ineligible)"
            raise NoEligibleCandidates(msg, excluded)

        ranked = self._rank(candidates, policy, weights)
        fallback_policy = self._resolve_fallback_scope(policy)
        fallback = self._fallback_candidates(ranked, policy, fallback_policy)

        return RoutingDecision(
            selected=ranked[0],
            ranked=ranked,
            fallback_candidates=fallback,
            excluded=excluded,
            policy_snapshot=policy,
            fallback_policy=fallback_policy,
            weights=weights,
        )

    # -- eligibility (11 §5: hard filters, deny-by-default) ------------------------

    def _eligible_candidates(
        self,
        request: RoutingRequest,
        policy: ModelPolicy,
        excluded: list[ExclusionRecord],
    ) -> list[_Candidate]:
        required_caps = self._required_capabilities(request)
        required_modalities = self._required_modalities(request)

        models = self._candidate_models(policy, excluded)
        providers_by_id = {
            entry.provider.id: entry
            for entry in self._providers.routing_candidates(request.operation)
        }

        candidates: list[_Candidate] = []
        for model in models:
            exclusion = self._model_level_exclusion(
                model, required_caps, required_modalities, request
            )
            if exclusion is not None:
                excluded.append(ExclusionRecord(model_key=model.model_key, reason=exclusion))
                continue
            candidates.extend(
                self._provider_candidates(model, policy, providers_by_id, excluded)
            )
        return candidates

    def _candidate_models(
        self, policy: ModelPolicy, excluded: list[ExclusionRecord]
    ) -> list[Model]:
        """Model pool per policy type. ACTIVE models only (03 §4)."""
        active = self._models.active_models()
        if isinstance(policy, ExplicitModelPolicy):
            # 11 §14 rule 1: validate the model exists — and is active.
            matches = [m for m in active if m.model_key == policy.model_id]
            if not matches:
                excluded.append(
                    ExclusionRecord(
                        model_key=policy.model_id,
                        reason="explicit model not registered or not active",
                    )
                )
            return matches
        if isinstance(policy, TierModelPolicy):
            # 10 §13.2: selection constrained to the tier — hard filter.
            matches = [m for m in active if m.tier.value == policy.tier]
            if not matches:
                excluded.append(
                    ExclusionRecord(
                        model_key=f"tier:{policy.tier}",
                        reason="no active model in requested tier",
                    )
                )
            return matches
        return active

    def _model_level_exclusion(
        self,
        model: Model,
        required_caps: list[str],
        required_modalities: list[str],
        request: RoutingRequest,
    ) -> str | None:
        """Return the exclusion reason, or None if the model passes (11 §5)."""
        # Declared-capability filter (11 §5 + 30 §7): undeclared => ineligible.
        missing_caps = [c for c in required_caps if c not in model.capabilities]
        if missing_caps:
            return f"missing declared capabilities: {', '.join(sorted(missing_caps))}"
        declared_modalities = {m.value for m in model.modalities}
        missing_modalities = [m for m in required_modalities if m not in declared_modalities]
        if missing_modalities:
            return f"missing modalities: {', '.join(sorted(missing_modalities))}"
        if (
            request.context_length_hint is not None
            and model.context_window is not None
            and model.context_window < request.context_length_hint
        ):
            return (
                f"context window {model.context_window} below "
                f"required {request.context_length_hint}"
            )
        return None

    def _provider_candidates(
        self,
        model: Model,
        policy: ModelPolicy,
        providers_by_id: dict[UUID, RegisteredProvider],
        excluded: list[ExclusionRecord],
    ) -> list[_Candidate]:
        """Bind an eligible model to its eligible providers (per-binding facts)."""
        out: list[_Candidate] = []
        bindings = self._bindings.bindings_for_model(model.id)
        if not bindings:
            excluded.append(
                ExclusionRecord(model_key=model.model_key, reason="no provider binding")
            )
            return out

        explicit_provider = (
            policy.provider_id
            if isinstance(policy, ExplicitModelPolicy) and policy.provider_id is not None
            else None
        )

        for binding in bindings:
            entry = providers_by_id.get(binding.provider_id)
            if entry is None:
                # Not among routing candidates: template, non-functional,
                # inactive, or operation undeclared (31 §10 / 30 §5).
                excluded.append(
                    ExclusionRecord(
                        model_key=model.model_key,
                        provider_key=str(binding.provider_id),
                        reason="provider not routable for this operation",
                    )
                )
                continue
            provider_key = entry.provider.provider_key
            # 11 §14 rule 4: explicit provider_id narrows the binding set.
            if explicit_provider is not None and provider_key != explicit_provider:
                excluded.append(
                    ExclusionRecord(
                        model_key=model.model_key,
                        provider_key=provider_key,
                        reason="excluded by explicit provider selection",
                    )
                )
                continue
            if binding.availability is BindingAvailability.UNAVAILABLE:
                excluded.append(
                    ExclusionRecord(
                        model_key=model.model_key,
                        provider_key=provider_key,
                        reason="binding unavailable",
                    )
                )
                continue

            reasons = [
                f"model '{model.model_key}' active in tier '{model.tier.value}'",
                f"provider '{provider_key}' routable for operation",
            ]
            risks: list[str] = []
            if binding.availability is BindingAvailability.DEGRADED:
                # "account healthy or acceptable" (11 §5): degraded is
                # acceptable but must be visible as a risk (11 §7).
                risks.append("binding degraded")
            out.append(
                _Candidate(
                    model=model,
                    provider=entry,
                    binding=binding,
                    reasons=tuple(reasons),
                    risks=tuple(risks),
                )
            )
        return out

    # -- scoring (11 §6-§7) ---------------------------------------------------------

    def _rank(
        self,
        candidates: list[_Candidate],
        policy: ModelPolicy,
        weights: ScoringWeights,
    ) -> list[CandidateScore]:
        scored = [self._score(c, policy, weights) for c in candidates]
        # Deterministic order: score desc, then model/provider key asc.
        keyed = sorted(
            zip(scored, candidates, strict=True),
            key=lambda pair: (
                -pair[0].score,
                pair[1].model.model_key,
                pair[1].provider.provider.provider_key,
            ),
        )
        return [s for s, _ in keyed]

    def _score(
        self, candidate: _Candidate, policy: ModelPolicy, weights: ScoringWeights
    ) -> CandidateScore:
        model = candidate.model
        reasons = list(candidate.reasons)
        risks = list(candidate.risks)

        quality = _component(model.quality_score, "quality", risks)
        reliability = _component(model.reliability_score, "reliability", risks)
        cost = _component(model.cost_score, "cost", risks)
        latency = _component(model.speed_score, "latency", risks)
        # Context fit: hard mismatches were excluded; surviving candidates fit.
        context_fit = 1.0
        policy_preference = self._policy_preference(model, policy, reasons)

        score = (
            weights.quality * quality
            + weights.reliability * reliability
            + weights.cost * cost
            + weights.latency * latency
            + weights.context_fit * context_fit
            + weights.policy_preference * policy_preference
        )
        if candidate.risks:
            reasons.append("selected despite recorded risks")
        return CandidateScore(
            model_id=model.id,
            provider_id=candidate.provider.provider.id,
            account_id=None,
            score=round(score, 6),
            reasons=reasons,
            risks=risks,
        )

    @staticmethod
    def _policy_preference(
        model: Model, policy: ModelPolicy, reasons: list[str]
    ) -> float:
        """Preference component: explicit choice / tier-hint alignment (11 §13)."""
        if isinstance(policy, ExplicitModelPolicy):
            reasons.append("explicit model selection honored")
            return 1.0
        if isinstance(policy, TierModelPolicy):
            reasons.append(f"tier '{policy.tier}' constraint satisfied")
            return 1.0
        if isinstance(policy, AutoModelPolicy) and policy.tier is not None:
            if model.tier.value == policy.tier:
                reasons.append(f"matches auto tier hint '{policy.tier}'")
                return 1.0
            return 0.0
        return 0.0

    # -- fallback (11 §8, §14) --------------------------------------------------------

    @staticmethod
    def _resolve_fallback_scope(policy: ModelPolicy) -> FallbackScope | None:
        allow = getattr(policy, "allow_fallback", None)
        scope = getattr(policy, "fallback_scope", None)
        if allow is False:
            return FallbackScope.NONE
        if scope is not None:
            return scope
        if allow is True and isinstance(policy, ExplicitModelPolicy):
            # 11 §8 explicit-model default: same_model_different_provider first.
            return FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER
        return scope

    def _fallback_candidates(
        self,
        ranked: list[CandidateScore],
        policy: ModelPolicy,
        scope: FallbackScope | None,
    ) -> list[CandidateScore]:
        """Ordered fallback route after the selected candidate (11 §8/§14)."""
        if scope is None or scope is FallbackScope.NONE:
            return []
        rest = ranked[1:]
        if scope is FallbackScope.ADMIN_DEFINED_CHAIN:
            if not self._admin_fallback_chain:
                msg = "fallback_scope=admin_defined_chain but no chain is configured"
                raise FallbackNotConfigured(msg)
            order = {key: i for i, key in enumerate(self._admin_fallback_chain)}
            chain = [
                c
                for c in rest
                if self._models.get_by_id(c.model_id).model_key in order
            ]
            return sorted(
                chain,
                key=lambda c: order[self._models.get_by_id(c.model_id).model_key],
            )
        if scope is FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER:
            selected = ranked[0]
            return [c for c in rest if c.model_id == selected.model_id]
        if scope is FallbackScope.SAME_TIER:
            selected_tier = self._models.get_by_id(ranked[0].model_id).tier
            return [
                c for c in rest if self._models.get_by_id(c.model_id).tier is selected_tier
            ]
        if scope is FallbackScope.LOWER_COST_SAME_CAPABILITY:
            # cost_score is a normalized "cheapness" score: higher = cheaper.
            selected_cost = self._models.get_by_id(ranked[0].model_id).cost_score or 0.0
            return [
                c
                for c in rest
                if (self._models.get_by_id(c.model_id).cost_score or 0.0) >= selected_cost
            ]
        # MAX_ESCALATION: every remaining candidate, best first.
        return list(rest)


def _component(value: float | None, name: str, risks: list[str]) -> float:
    """Score component with unknown-value posture: unknown scores contribute
    0.0 and are surfaced as a risk (never invented — 30 §4.3 spirit)."""
    if value is None:
        risks.append(f"{name} score undeclared")
        return 0.0
    return value
