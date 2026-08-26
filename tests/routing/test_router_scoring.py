"""SimpleScoringRouter semantics (T-IMPL-021; 11 §4-§8, §13-§14; 41 §44).

Hermetic — in-memory T-IMPL-019 registries only; no network, no adapters.
Covers the 11 §11 required tests applicable to this slice:

    auto selection
    explicit model selection
    same model provider fallback
    same tier fallback
    provider unavailable
    unknown capability denied

Plus 11 §18 items in scope: explicit model unavailable with fallback
disabled, explicit model same-model different-provider fallback,
provider_id explicit narrowing, policy snapshot preserved. Entitlement /
rate-limit / tool-permission filters are later-phase services (recorded in
the router module docstring), so their tests belong to those slices.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.model_policy import (
    AgentNodeMappingPolicy,
    AutoModelPolicy,
    ExplicitModelPolicy,
    FallbackScope,
    TierModelPolicy,
)
from core.contracts.provider import ProviderManifest, ProviderOperation
from core.contracts.routing import RoutingRequest, ScoringWeights
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import (
    FallbackNotConfigured,
    NoEligibleCandidates,
    SimpleScoringRouter,
    UnsupportedPolicyType,
)

# --- fixtures ----------------------------------------------------------------------


def _manifest(provider_key: str, **overrides: object) -> ProviderManifest:
    payload: dict[str, object] = {
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
    payload.update(overrides)
    return ProviderManifest.model_validate(payload)


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(
    key: str,
    *,
    tier: ModelTier = ModelTier.MEDIUM,
    capabilities: list[str] | None = None,
    quality: float | None = 0.5,
    reliability: float | None = 0.5,
    cost: float | None = 0.5,
    speed: float | None = 0.5,
    context_window: int | None = None,
    status: ModelStatus = ModelStatus.ACTIVE,
) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=tier,
        modalities=["text"],
        capabilities=capabilities if capabilities is not None else ["reasoning"],
        quality_score=quality,
        reliability_score=reliability,
        cost_score=cost,
        speed_score=speed,
        context_window=context_window,
        status=status,
    )


def _binding(
    provider: Provider,
    model: Model,
    availability: BindingAvailability = BindingAvailability.AVAILABLE,
) -> ProviderModelBinding:
    return ProviderModelBinding(
        provider_id=provider.id,
        model_id=model.id,
        provider_model_name=model.model_key,
        availability=availability,
    )


class _World:
    """One in-memory routing world built from the T-IMPL-019 registries."""

    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()

    def add_provider(self, key: str, **manifest_overrides: object) -> Provider:
        provider = _provider(key)
        self.providers.register(provider, _manifest(key, **manifest_overrides))
        return provider

    def add_model(self, model: Model) -> Model:
        self.models.register(model)
        return model

    def bind(
        self,
        provider: Provider,
        model: Model,
        availability: BindingAvailability = BindingAvailability.AVAILABLE,
    ) -> None:
        self.bindings.register(_binding(provider, model, availability))

    def router(self, **kwargs: object) -> SimpleScoringRouter:
        return SimpleScoringRouter(
            self.providers, self.models, self.bindings, **kwargs  # type: ignore[arg-type]
        )


def _request(**overrides: object) -> RoutingRequest:
    payload: dict[str, object] = {"operation": "generate_text"}
    payload.update(overrides)
    return RoutingRequest.model_validate(payload)


def _basic_world() -> tuple[_World, Provider, Model, Model]:
    """Two active models on one provider: strong vs weak scores."""
    world = _World()
    provider = world.add_provider("prov_a")
    strong = world.add_model(
        _model("model-strong", quality=0.9, reliability=0.9, cost=0.9, speed=0.9)
    )
    weak = world.add_model(
        _model("model-weak", quality=0.1, reliability=0.1, cost=0.1, speed=0.1)
    )
    world.bind(provider, strong)
    world.bind(provider, weak)
    return world, provider, strong, weak


# --- auto selection (11 §11) --------------------------------------------------------


def test_auto_selection_picks_highest_scoring_candidate() -> None:
    world, provider, strong, _ = _basic_world()
    decision = world.router().route(_request())
    assert decision.selected.model_id == strong.id
    assert decision.selected.provider_id == provider.id
    assert decision.ranked[0].score > decision.ranked[1].score


def test_auto_selection_is_deterministic_on_ties() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    m1 = world.add_model(_model("model-a"))
    m2 = world.add_model(_model("model-b"))
    world.bind(provider, m1)
    world.bind(provider, m2)
    decision = world.router().route(_request())
    # Equal scores => deterministic tie-break by model_key order.
    assert decision.selected.model_id == m1.id
    again = world.router().route(_request())
    assert again.selected.model_id == decision.selected.model_id


def test_missing_policy_defaults_to_auto_and_is_snapshotted() -> None:
    world, *_ = _basic_world()
    decision = world.router().route(_request())
    assert isinstance(decision.policy_snapshot, AutoModelPolicy)


def test_auto_tier_hint_boosts_matching_tier() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    fast = world.add_model(_model("model-fast", tier=ModelTier.FAST))
    maxm = world.add_model(_model("model-max", tier=ModelTier.MAX))
    world.bind(provider, fast)
    world.bind(provider, maxm)
    policy = AutoModelPolicy(type="auto", tier="max")
    decision = world.router().route(_request(model_policy=policy))
    assert decision.selected.model_id == maxm.id
    assert any("tier hint" in r for r in decision.selected.reasons)


# --- tier policy (10 §13.2) ---------------------------------------------------------


def test_tier_policy_is_a_hard_filter() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    fast = world.add_model(
        _model("model-fast", tier=ModelTier.FAST, quality=0.1, reliability=0.1)
    )
    maxm = world.add_model(
        _model("model-max", tier=ModelTier.MAX, quality=0.9, reliability=0.9)
    )
    world.bind(provider, fast)
    world.bind(provider, maxm)
    policy = TierModelPolicy(type="tier", tier="fast")
    decision = world.router().route(_request(model_policy=policy))
    assert decision.selected.model_id == fast.id
    assert all(c.model_id != maxm.id for c in decision.ranked)


def test_tier_policy_with_no_tier_members_fails_clearly() -> None:
    world, *_ = _basic_world()  # only medium-tier models
    policy = TierModelPolicy(type="tier", tier="max")
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request(model_policy=policy))
    assert any("no active model in requested tier" in e.reason for e in exc.value.excluded)


# --- explicit model (11 §11, §14) ---------------------------------------------------


def test_explicit_model_selection_honored() -> None:
    world, provider, _, weak = _basic_world()
    policy = ExplicitModelPolicy(type="explicit_model", model_id="model-weak")
    decision = world.router().route(_request(model_policy=policy))
    # Explicit user choice outranks Router preference (11 §13).
    assert decision.selected.model_id == weak.id
    assert any("explicit model selection honored" in r for r in decision.selected.reasons)
    assert decision.policy_snapshot == policy


def test_explicit_unknown_model_fails_clearly() -> None:
    world, *_ = _basic_world()
    policy = ExplicitModelPolicy(type="explicit_model", model_id="ghost-model")
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request(model_policy=policy))
    assert any(
        e.model_key == "ghost-model" and "not registered" in e.reason
        for e in exc.value.excluded
    )


def test_explicit_provider_id_narrows_bindings() -> None:
    world = _World()
    prov_a = world.add_provider("prov_a")
    prov_b = world.add_provider("prov_b")
    model = world.add_model(_model("model-x"))
    world.bind(prov_a, model)
    world.bind(prov_b, model)
    policy = ExplicitModelPolicy(
        type="explicit_model", model_id="model-x", provider_id="prov_b"
    )
    decision = world.router().route(_request(model_policy=policy))
    assert decision.selected.provider_id == prov_b.id
    assert all(c.provider_id == prov_b.id for c in decision.ranked)
    assert any(
        e.provider_key == "prov_a" and "explicit provider selection" in e.reason
        for e in decision.excluded
    )


def test_explicit_model_unavailable_with_fallback_disabled_fails_clearly() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    model = world.add_model(_model("model-x"))
    world.bind(provider, model, BindingAvailability.UNAVAILABLE)
    policy = ExplicitModelPolicy(
        type="explicit_model", model_id="model-x", allow_fallback=False
    )
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request(model_policy=policy))
    assert any("binding unavailable" in e.reason for e in exc.value.excluded)


# --- eligibility filters (11 §5) ----------------------------------------------------


def test_unknown_capability_is_denied_with_reason() -> None:
    world, *_ = _basic_world()  # models declare only "reasoning"
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request(required_capabilities=["quantum_magic"]))
    assert all("missing declared capabilities" in e.reason for e in exc.value.excluded)


def test_capability_filter_uses_declared_capabilities_only() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    coder = world.add_model(_model("model-coder", capabilities=["reasoning", "coding"]))
    plain = world.add_model(_model("model-plain", capabilities=["reasoning"]))
    world.bind(provider, coder)
    world.bind(provider, plain)
    decision = world.router().route(_request(required_capabilities=["coding"]))
    assert decision.selected.model_id == coder.id
    assert all(c.model_id != plain.id for c in decision.ranked)


def test_modality_mismatch_excluded() -> None:
    world, *_ = _basic_world()  # text-only models
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request(required_modalities=["video"]))
    assert all("missing modalities" in e.reason for e in exc.value.excluded)


def test_context_window_too_small_is_excluded() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    small = world.add_model(_model("model-small", context_window=4_000))
    large = world.add_model(_model("model-large", context_window=200_000))
    world.bind(provider, small)
    world.bind(provider, large)
    decision = world.router().route(_request(context_length_hint=100_000))
    assert decision.selected.model_id == large.id
    assert any(e.model_key == "model-small" for e in decision.excluded)


def test_inactive_model_never_routes() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    disabled = world.add_model(_model("model-off", status=ModelStatus.DISABLED))
    world.bind(provider, disabled)
    with pytest.raises(NoEligibleCandidates):
        world.router().route(_request())


def test_provider_unavailable_operation_not_declared() -> None:
    # Provider declares only generate_image => ineligible for generate_text.
    world = _World()
    provider = world.add_provider("prov_img", operations=["generate_image"])
    model = world.add_model(_model("model-x"))
    world.bind(provider, model)
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request())
    assert any("not routable" in e.reason for e in exc.value.excluded)


def test_template_provider_never_routes() -> None:
    world = _World()
    template = _provider("template_prov")
    world.providers.register(
        template,
        _manifest(
            "template_prov",
            status="template_disabled",
            is_template=True,
            is_functional=False,
            real_provider_required=True,
        ),
    )
    model = world.add_model(_model("model-x"))
    world.bind(template, model)
    with pytest.raises(NoEligibleCandidates):
        world.router().route(_request())


def test_unavailable_binding_excluded_but_degraded_is_risk() -> None:
    world = _World()
    prov_a = world.add_provider("prov_a")
    prov_b = world.add_provider("prov_b")
    model = world.add_model(_model("model-x"))
    world.bind(prov_a, model, BindingAvailability.UNAVAILABLE)
    world.bind(prov_b, model, BindingAvailability.DEGRADED)
    decision = world.router().route(_request())
    assert decision.selected.provider_id == prov_b.id
    assert "binding degraded" in decision.selected.risks
    assert any(e.reason == "binding unavailable" for e in decision.excluded)


def test_undeclared_scores_contribute_zero_and_surface_as_risk() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    unknown = world.add_model(
        _model("model-mystery", quality=None, reliability=None, cost=None, speed=None)
    )
    world.bind(provider, unknown)
    decision = world.router().route(_request())
    assert "quality score undeclared" in decision.selected.risks
    # Only context_fit (0.10 weight) contributes for a fully-undeclared model.
    assert decision.selected.score == pytest.approx(0.10)


# --- fallback (11 §8, §14) ----------------------------------------------------------


def test_explicit_model_default_fallback_same_model_different_provider() -> None:
    world = _World()
    prov_a = world.add_provider("prov_a")
    prov_b = world.add_provider("prov_b")
    model = world.add_model(_model("model-x"))
    other = world.add_model(_model("model-y"))
    world.bind(prov_a, model)
    world.bind(prov_b, model)
    world.bind(prov_a, other)
    policy = ExplicitModelPolicy(
        type="explicit_model", model_id="model-x", allow_fallback=True
    )
    decision = world.router().route(_request(model_policy=policy))
    assert decision.fallback_policy is FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER
    assert len(decision.fallback_candidates) == 1
    fb = decision.fallback_candidates[0]
    assert fb.model_id == model.id
    assert fb.provider_id != decision.selected.provider_id


def test_fallback_disabled_yields_no_candidates_and_scope_none() -> None:
    world, *_ = _basic_world()
    policy = AutoModelPolicy(type="auto", allow_fallback=False)
    decision = world.router().route(_request(model_policy=policy))
    assert decision.fallback_policy is FallbackScope.NONE
    assert decision.fallback_candidates == []


def test_same_tier_fallback_filters_by_selected_tier() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    best = world.add_model(_model("model-best", tier=ModelTier.MEDIUM, quality=0.9))
    peer = world.add_model(_model("model-peer", tier=ModelTier.MEDIUM, quality=0.5))
    other_tier = world.add_model(_model("model-fastest", tier=ModelTier.FAST, quality=0.7))
    world.bind(provider, best)
    world.bind(provider, peer)
    world.bind(provider, other_tier)
    policy = AutoModelPolicy(
        type="auto", allow_fallback=True, fallback_scope=FallbackScope.SAME_TIER
    )
    decision = world.router().route(_request(model_policy=policy))
    assert decision.selected.model_id == best.id
    fb_ids = [c.model_id for c in decision.fallback_candidates]
    assert peer.id in fb_ids
    assert other_tier.id not in fb_ids


def test_lower_cost_same_capability_fallback() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    # cost_score = cheapness (higher = cheaper).
    expensive = world.add_model(_model("model-pricy", quality=0.95, cost=0.2))
    cheap = world.add_model(_model("model-cheap", quality=0.5, cost=0.9))
    world.bind(provider, expensive)
    world.bind(provider, cheap)
    policy = AutoModelPolicy(
        type="auto",
        allow_fallback=True,
        fallback_scope=FallbackScope.LOWER_COST_SAME_CAPABILITY,
    )
    decision = world.router().route(_request(model_policy=policy))
    assert decision.selected.model_id == expensive.id
    assert [c.model_id for c in decision.fallback_candidates] == [cheap.id]


def test_max_escalation_fallback_returns_all_remaining() -> None:
    world, _, _, weak = _basic_world()
    policy = AutoModelPolicy(
        type="auto", allow_fallback=True, fallback_scope=FallbackScope.MAX_ESCALATION
    )
    decision = world.router().route(_request(model_policy=policy))
    assert [c.model_id for c in decision.fallback_candidates] == [weak.id]


def test_admin_defined_chain_requires_configuration() -> None:
    world, *_ = _basic_world()
    policy = AutoModelPolicy(
        type="auto",
        allow_fallback=True,
        fallback_scope=FallbackScope.ADMIN_DEFINED_CHAIN,
    )
    with pytest.raises(FallbackNotConfigured):
        world.router().route(_request(model_policy=policy))


def test_admin_defined_chain_orders_by_configured_chain() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    best = world.add_model(_model("model-best", quality=0.9))
    b = world.add_model(_model("model-b", quality=0.4))
    c = world.add_model(_model("model-c", quality=0.5))
    for m in (best, b, c):
        world.bind(provider, m)
    router = world.router(admin_fallback_chain=("model-b", "model-c"))
    policy = AutoModelPolicy(
        type="auto",
        allow_fallback=True,
        fallback_scope=FallbackScope.ADMIN_DEFINED_CHAIN,
    )
    decision = router.route(_request(model_policy=policy))
    assert decision.selected.model_id == best.id
    # Chain order (b then c) wins over score order (c then b).
    assert [x.model_id for x in decision.fallback_candidates] == [b.id, c.id]


# --- scoring formula (11 §6) --------------------------------------------------------


def test_default_weights_are_the_documented_initial_values() -> None:
    w = ScoringWeights()
    assert (w.quality, w.reliability, w.cost, w.latency) == (0.35, 0.20, 0.15, 0.15)
    assert (w.context_fit, w.policy_preference) == (0.10, 0.05)


def test_custom_weights_change_ranking_and_are_recorded() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    quality_king = world.add_model(
        _model("model-quality", quality=1.0, cost=0.0, reliability=0.5, speed=0.5)
    )
    cost_king = world.add_model(
        _model("model-cost", quality=0.0, cost=1.0, reliability=0.5, speed=0.5)
    )
    world.bind(provider, quality_king)
    world.bind(provider, cost_king)

    default = world.router().route(_request())
    assert default.selected.model_id == quality_king.id

    cost_first = ScoringWeights(
        version="cost-first-test",
        quality=0.05,
        reliability=0.10,
        cost=0.60,
        latency=0.10,
        context_fit=0.10,
        policy_preference=0.05,
    )
    decision = world.router().route(_request(weights=cost_first))
    assert decision.selected.model_id == cost_king.id
    assert decision.weights.version == "cost-first-test"


def test_score_matches_weighted_component_sum() -> None:
    world = _World()
    provider = world.add_provider("prov_a")
    model = world.add_model(
        _model("model-x", quality=0.8, reliability=0.6, cost=0.4, speed=0.2)
    )
    world.bind(provider, model)
    decision = world.router().route(_request())
    expected = 0.35 * 0.8 + 0.20 * 0.6 + 0.15 * 0.4 + 0.15 * 0.2 + 0.10 * 1.0 + 0.05 * 0.0
    assert decision.selected.score == pytest.approx(expected)


# --- decision explainability + snapshot (11 §7, §16) --------------------------------


def test_decision_carries_reasons_and_exclusions() -> None:
    world = _World()
    prov_a = world.add_provider("prov_a")
    good = world.add_model(_model("model-good", capabilities=["reasoning"]))
    bad = world.add_model(_model("model-bad", capabilities=[]))
    world.bind(prov_a, good)
    world.bind(prov_a, bad)
    decision = world.router().route(_request(required_capabilities=["reasoning"]))
    assert decision.selected.reasons  # human-readable reasons present (11 §7)
    assert any(e.model_key == "model-bad" for e in decision.excluded)


def test_policy_snapshot_is_the_resolved_policy_object() -> None:
    world, *_ = _basic_world()
    policy = TierModelPolicy(type="tier", tier="medium")
    decision = world.router().route(_request(model_policy=policy))
    assert decision.policy_snapshot == policy
    # Snapshot is an immutable contract value (frozen) — cannot drift (11 §16).
    with pytest.raises(Exception, match="frozen"):
        decision.policy_snapshot.tier = "max"  # type: ignore[misc, union-attr]


def test_unbound_model_is_excluded_with_reason() -> None:
    world = _World()
    world.add_provider("prov_a")
    world.add_model(_model("model-orphan"))
    with pytest.raises(NoEligibleCandidates) as exc:
        world.router().route(_request())
    assert any(e.reason == "no provider binding" for e in exc.value.excluded)


# --- out-of-slice policy types are rejected, never guessed --------------------------


def test_agent_node_mapping_policy_rejected_in_this_slice() -> None:
    world, *_ = _basic_world()
    policy = AgentNodeMappingPolicy(type="agent_node_mapping")
    with pytest.raises(UnsupportedPolicyType):
        world.router().route(_request(model_policy=policy))


def test_explicit_models_policy_rejected_in_this_slice() -> None:
    world, *_ = _basic_world()
    request = _request(
        model_policy={
            "type": "explicit_models",
            "models": [{"model_id": "model-strong"}],
        }
    )
    with pytest.raises(UnsupportedPolicyType):
        world.router().route(request)


# --- registry immutability + boundary ------------------------------------------------


def test_router_does_not_mutate_registries() -> None:
    world, provider, strong, weak = _basic_world()
    before_models = [m.model_key for m in world.models.active_models()]
    before_providers = world.providers.all_keys()
    world.router().route(_request())
    assert [m.model_key for m in world.models.active_models()] == before_models
    assert world.providers.all_keys() == before_providers


def test_routing_module_stays_inside_core() -> None:
    """Boundary guard: core.routing must not import apps/providers/infrastructure."""
    import core.routing.errors as errors_mod
    import core.routing.router as router_mod

    for mod in (router_mod, errors_mod):
        source = open(mod.__file__).read()  # noqa: SIM115
        for forbidden in ("import apps", "import providers", "import infrastructure"):
            assert forbidden not in source


def test_operation_enum_used_not_free_strings() -> None:
    request = _request()
    assert isinstance(request.operation, ProviderOperation)


def test_candidate_ids_are_uuids() -> None:
    world, provider, strong, _ = _basic_world()
    decision = world.router().route(_request())
    assert isinstance(decision.selected.model_id, UUID)
    assert isinstance(decision.selected.provider_id, UUID)
