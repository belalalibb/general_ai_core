"""FINAL Phase 8 router-engine components (T-IMPL-057; 41 §11, doc 11).

Hermetic — in-memory registries, pools, and lease manager only; no network,
no adapters, no AI. Covers the three 41 §11 additions:

- BootstrapRouter (11 §9): policy-pinned, deterministic, recursion-guarded
  selection of the router-analysis model; the 11 §11 required
  "router model bootstrap" test lives here.
- StrategyPlanner (11 §2 "Execution Strategy Selection"): explicit request
  wins (11 §13); unknown strategy rejected loudly; auto maps needs_agent =>
  agent (the ONLY documented signal), else single.
- ResourceSelector (11 §2 "Provider/Account Selection"): fills account_id
  from the Phase 7 AccountPoolManager for pooled providers; pool-less
  providers complete without an account (30 §10.1); walks ranked candidates;
  fails clearly when exhausted. NO lease is taken (Router decides, never
  executes — 41 §11).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.contracts.domain import (
    AccountHealthState,
    AccountLifecycleState,
    Credential,
    CredentialPolicy,
    CredentialStatus,
    Model,
    ModelStatus,
    ModelTier,
    OwnerType,
    Provider,
    ProviderAccount,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.execution import ExecutionStrategy
from core.contracts.model_policy import (
    AgentNodeMappingPolicy,
    ExplicitModelPolicy,
    TierModelPolicy,
)
from core.contracts.provider import ProviderManifest
from core.contracts.routing import RoutingDecision, RoutingRequest, TaskAnalysis
from core.providers import (
    AccountPoolManager,
    BindingRegistry,
    ModelRegistry,
    NoEligibleAccount,
    ProviderRegistry,
)
from core.routing import (
    BootstrapNotConfigured,
    BootstrapRouter,
    NoEligibleCandidates,
    ResourceSelector,
    SimpleScoringRouter,
    StrategyPlanner,
    UnknownStrategy,
)
from core.runtime.memory import InMemoryLeaseManager

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


def _provider(key: str) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=ProviderStatus.ACTIVE,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(key: str, tier: ModelTier = ModelTier.MEDIUM) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=tier,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=ModelStatus.ACTIVE,
    )


class _World:
    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.leases = InMemoryLeaseManager()
        self.accounts = AccountPoolManager(self.providers, self.leases)

    def add_provider(self, key: str, **manifest_overrides: object) -> Provider:
        provider = _provider(key)
        self.providers.register(provider, _manifest(key, **manifest_overrides))
        return provider

    def add_model(self, key: str, tier: ModelTier = ModelTier.MEDIUM) -> Model:
        model = _model(key, tier)
        self.models.register(model)
        return model

    def bind(self, provider: Provider, model: Model) -> None:
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name=model.model_key,
                availability="available",
            )
        )

    def add_account(self, provider: Provider) -> ProviderAccount:
        credential = Credential(
            id=uuid4(),
            owner_type=OwnerType.PLATFORM,
            provider_id=provider.id,
            credential_ref=f"vault://cred/{uuid4()}",
            status=CredentialStatus.ACTIVE,
        )
        account = ProviderAccount(
            id=uuid4(),
            provider_id=provider.id,
            credential_id=credential.id,
            owner_type=OwnerType.PLATFORM,
            lifecycle_state=AccountLifecycleState.READY,
            health_state=AccountHealthState.HEALTHY,
        )
        self.accounts.pool_for(provider.id).register(account, credential)
        return account

    def router(self) -> SimpleScoringRouter:
        return SimpleScoringRouter(self.providers, self.models, self.bindings)

    def route(self) -> RoutingDecision:
        request = RoutingRequest.model_validate({"operation": "generate_text"})
        return self.router().route(request)


def _routed_world() -> tuple[_World, Provider, Model]:
    world = _World()
    provider = world.add_provider("prov_a")
    model = world.add_model("model-a")
    world.bind(provider, model)
    return world, provider, model


# --- BootstrapRouter (11 §9) ---------------------------------------------------------


def test_router_model_bootstrap_selects_via_pinned_policy() -> None:
    # The 11 §11 required test: "router model bootstrap".
    world, _, model = _routed_world()
    bootstrap = BootstrapRouter(
        world.router(),
        policy=ExplicitModelPolicy(type="explicit_model", model_id="model-a"),
    )
    decision = bootstrap.select_analysis_model()
    assert decision.selected.model_id == model.id


def test_bootstrap_unconfigured_fails_clearly_never_guesses() -> None:
    world, _, _ = _routed_world()
    bootstrap = BootstrapRouter(world.router())
    assert not bootstrap.is_configured
    with pytest.raises(BootstrapNotConfigured, match="never guesses"):
        bootstrap.select_analysis_model()


def test_bootstrap_rejects_multi_model_policies_at_configuration() -> None:
    # "Simple": only the 11 §4 single-selection modes are admitted.
    world, _, _ = _routed_world()
    with pytest.raises(BootstrapNotConfigured, match="single-selection"):
        BootstrapRouter(
            world.router(),
            policy=AgentNodeMappingPolicy(type="agent_node_mapping"),
        )


def test_bootstrap_is_deterministic() -> None:
    world, _, _ = _routed_world()
    world_model_b = world.add_model("model-b")
    world.bind(world.providers.get("prov_a").provider, world_model_b)
    bootstrap = BootstrapRouter(world.router(), policy=TierModelPolicy(type="tier", tier="medium"))
    first = bootstrap.select_analysis_model()
    second = bootstrap.select_analysis_model()
    assert first.selected.model_id == second.selected.model_id
    assert [c.model_id for c in first.ranked] == [c.model_id for c in second.ranked]


def test_bootstrap_applies_the_same_hard_filters() -> None:
    # "Safe": 11 §5 filters hold on the bootstrap path too.
    world = _World()
    world.add_provider("prov_a")
    world.add_model("model-a")  # deliberately unbound => ineligible
    bootstrap = BootstrapRouter(
        world.router(),
        policy=ExplicitModelPolicy(type="explicit_model", model_id="model-a", allow_fallback=False),
    )
    with pytest.raises(NoEligibleCandidates):
        bootstrap.select_analysis_model()


def test_bootstrap_request_never_carries_task_analysis() -> None:
    # Recursion guard: the internal request has no task_analysis field set.
    world, _, _ = _routed_world()
    captured: list[object] = []

    router = world.router()
    original = router.route

    def spy(request):  # type: ignore[no-untyped-def]
        captured.append(request)
        return original(request)

    router.route = spy  # type: ignore[method-assign]
    BootstrapRouter(
        router, policy=ExplicitModelPolicy(type="explicit_model", model_id="model-a")
    ).select_analysis_model()
    assert len(captured) == 1
    assert captured[0].task_analysis is None  # type: ignore[attr-defined]


# --- StrategyPlanner (11 §2) ----------------------------------------------------------


def test_explicit_strategy_request_wins() -> None:
    # 11 §13: explicit user choice outranks Router preference.
    planner = StrategyPlanner()
    analysis = TaskAnalysis(
        task_type="code_review",
        complexity="medium",
        risk_level="medium",
        needs_agent=True,
    )
    assert (
        planner.plan(requested_strategy="debate", task_analysis=analysis)
        is ExecutionStrategy.DEBATE
    )


def test_every_closed_set_member_is_honored_verbatim() -> None:
    planner = StrategyPlanner()
    for member in ExecutionStrategy:
        assert planner.plan(requested_strategy=member.value) is member


def test_unknown_strategy_rejected_never_coerced() -> None:
    planner = StrategyPlanner()
    with pytest.raises(UnknownStrategy, match="closed set"):
        planner.plan(requested_strategy="swarm")


def test_auto_maps_needs_agent_to_agent() -> None:
    # 11 §3 needs_agent is the only documented analysis→strategy signal.
    planner = StrategyPlanner()
    analysis = TaskAnalysis(task_type="ops", complexity="high", risk_level="high", needs_agent=True)
    assert planner.plan(task_analysis=analysis) is ExecutionStrategy.AGENT
    assert (
        planner.plan(requested_strategy="auto", task_analysis=analysis) is ExecutionStrategy.AGENT
    )


def test_auto_defaults_to_single() -> None:
    planner = StrategyPlanner()
    assert planner.plan() is ExecutionStrategy.SINGLE
    no_agent = TaskAnalysis(task_type="chat", complexity="low", risk_level="low", needs_agent=False)
    assert planner.plan(task_analysis=no_agent) is ExecutionStrategy.SINGLE
    unset = TaskAnalysis(task_type="chat", complexity="low", risk_level="low")
    assert planner.plan(task_analysis=unset) is ExecutionStrategy.SINGLE


# --- ResourceSelector (11 §2 Provider/Account Selection) -------------------------------


def test_poolless_provider_completes_without_account() -> None:
    # 30 §10.1: pools are optional — account_id stays None, selection valid.
    world, _, model = _routed_world()
    decision = world.route()
    selector = ResourceSelector(world.providers, world.accounts)
    completed = selector.select(decision)
    assert completed.model_id == model.id
    assert completed.account_id is None


def test_pooled_provider_gets_account_id_filled() -> None:
    world = _World()
    provider = world.add_provider("prov_a", account_pool={"supported": True})
    model = world.add_model("model-a")
    world.bind(provider, model)
    account = world.add_account(provider)

    decision = world.route()
    completed = ResourceSelector(world.providers, world.accounts).select(decision)
    assert completed.account_id == account.id


def test_pooled_provider_without_eligible_account_fails_clearly() -> None:
    # 11 §14 step 7: no eligible route => fail clearly.
    world = _World()
    provider = world.add_provider("prov_a", account_pool={"supported": True})
    model = world.add_model("model-a")
    world.bind(provider, model)  # pool declared but EMPTY

    decision = world.route()
    selector = ResourceSelector(world.providers, world.accounts)
    with pytest.raises(NoEligibleAccount, match="resource-completed"):
        selector.select(decision)


def test_exhausted_pooled_candidate_falls_through_to_next() -> None:
    # Ranked walk: pooled provider with empty pool is skipped; the pool-less
    # provider serving the same model completes the selection.
    world = _World()
    pooled = world.add_provider("prov_pooled", account_pool={"supported": True})
    poolless = world.add_provider("prov_free")
    model = world.add_model("model-a")
    world.bind(pooled, model)
    world.bind(poolless, model)

    decision = world.route()
    assert len(decision.ranked) == 2
    completed = ResourceSelector(world.providers, world.accounts).select(decision)
    assert completed.provider_id == poolless.id
    assert completed.account_id is None


def test_credential_policy_flows_through_to_pool_eligibility() -> None:
    world = _World()
    provider = world.add_provider("prov_a", account_pool={"supported": True})
    model = world.add_model("model-a")
    world.bind(provider, model)
    world.add_account(provider)  # platform-owned

    decision = world.route()
    selector = ResourceSelector(world.providers, world.accounts)
    with pytest.raises(NoEligibleAccount):
        selector.select(decision, policy=CredentialPolicy.USER_ONLY)
    completed = selector.select(decision, policy=CredentialPolicy.PLATFORM_ONLY)
    assert completed.account_id is not None


def test_selection_takes_no_lease() -> None:
    # Router decides; execution leases (41 §11 DOES/DOES-NOT).
    world = _World()
    provider = world.add_provider("prov_a", account_pool={"supported": True})
    model = world.add_model("model-a")
    world.bind(provider, model)
    account = world.add_account(provider)

    decision = world.route()
    ResourceSelector(world.providers, world.accounts).select(decision)
    # The account's lease resource must still be free: acquiring it now works.
    import asyncio

    from core.providers import lease_resource_for

    lease = asyncio.run(world.leases.acquire(lease_resource_for(account.id), "exec-1", 30.0))
    assert lease is not None


def test_selection_does_not_mutate_the_decision() -> None:
    world = _World()
    provider = world.add_provider("prov_a", account_pool={"supported": True})
    model = world.add_model("model-a")
    world.bind(provider, model)
    world.add_account(provider)

    decision = world.route()
    before = decision.model_dump()
    ResourceSelector(world.providers, world.accounts).select(decision)
    assert decision.model_dump() == before
