"""R188 slice C — caller-defined execution strategies over the ONE router/service.

Authority: R188-DEC-01 §C (C1 contract, C2 executor). Proves BEHAVIOUR, not
declaration:

1. CUSTOM strategy executes as requested: a DAG of 4 stages runs in 3 waves;
   the two independent middle stages run CONCURRENTLY (observed overlap with a
   real awaited adapter), each stage is its own stored child execution.
2. Per-stage MODEL POLICY is honoured: stage A explicit model X, stage B explicit
   model Y, stage C AUTO — routed by the ONE router.
3. Review/retest stages receive the upstream output as ``subject``.
4. A failed stage fails the strategy; dependents are SKIPPED (recorded), while
   an independent sibling still completes.
5. AUTO composes a bounded, policy-valid plan (one generate stage; review only
   when asked) — never a hidden methodology.
6. TEMPLATE mode resolves a registered template and refuses an unknown id loudly.
7. Agent <-> provider decoupling: the same stage spec resolves to a DIFFERENT
   provider when the first is cooling (runtime signals inside the ONE router).
8. Contract validation: cycles, unknown deps, review without deps, over-bound
   stage counts are refused at the contract boundary.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNodeStatus, ExecutionStrategy
from core.contracts.execution_strategy import (
    MAX_STAGES,
    ExecutionStrategySpec,
    StageKind,
    StrategyStage,
)
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
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
from core.execution import ExecutionService
from core.execution.strategy import StrategyExecutor, UnknownTemplate, compose_auto_strategy
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.capacity import ResourceSignalBoard
from core.routing.router import SimpleScoringRouter

T0 = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


class RecordingAdapter:
    """Echoes the payload back; optional per-call delay to observe concurrency."""

    def __init__(self, name: str, *, delay: float = 0.0, fail_when: str | None = None) -> None:
        self.name = name
        self.delay = delay
        self.fail_when = fail_when
        self.requests: list[ProviderGenerateRequest] = []
        self.active = 0
        self.max_active = 0

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return []  # pragma: no cover

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            stage = request.payload.get("stage", {})
            if self.fail_when is not None and stage.get("key") == self.fail_when:
                return ProviderGenerateResponse(
                    request_id=request.request_id,
                    succeeded=False,
                    error=ProviderError(
                        category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
                        retryable=False,
                        safe_message="scripted failure",
                    ),
                    latency_ms=1,
                )
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=True,
                output={
                    "provider": self.name,
                    "model": request.provider_model_name,
                    "stage": stage.get("key"),
                    "kind": stage.get("kind"),
                    "subject": request.payload.get("subject"),
                    "previous_output": request.payload.get("previous_output"),
                    "upstream_outputs": request.payload.get("upstream_outputs"),
                },
                usage={"units": 1},
                latency_ms=1,
            )
        finally:
            self.active -= 1

    async def health_check(self, scope: HealthScope) -> ProviderHealth:  # pragma: no cover
        raise NotImplementedError

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="boundary",
        )


def _manifest(key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": key,
            "name": key,
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


def _model(key: str) -> Model:
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
        status=ModelStatus.ACTIVE,
    )


class World:
    """Providers x models matrix; every provider serves every model."""

    def __init__(
        self,
        providers: dict[str, RecordingAdapter],
        model_keys: list[str],
        *,
        templates: dict[str, ExecutionStrategySpec] | None = None,
    ) -> None:
        self.now = T0
        self.board = ResourceSignalBoard(clock=lambda: self.now)
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapters: dict[UUID, RecordingAdapter] = {}
        self.by_key: dict[str, Provider] = {}
        self.model_by_key = {k: _model(k) for k in model_keys}
        for m in self.model_by_key.values():
            self.models.register(m)
        for key, adapter in providers.items():
            provider = Provider(
                id=uuid4(),
                provider_key=key,
                display_name=key,
                status=ProviderStatus.ACTIVE,
                auth_types=[AuthType.API_KEY],
                supports_account_pool=False,
            )
            self.providers.register(provider, _manifest(key))
            for m in self.model_by_key.values():
                self.bindings.register(
                    ProviderModelBinding(
                        provider_id=provider.id,
                        model_id=m.id,
                        provider_model_name=m.model_key,
                        availability=BindingAvailability.AVAILABLE,
                    )
                )
            self.adapters[provider.id] = adapter
            self.by_key[key] = provider
        self.router = SimpleScoringRouter(
            self.providers, self.models, self.bindings, signals=self.board
        )
        self.service = ExecutionService(
            adapters=self.adapters,
            credential_refs={p.id: f"ref-{k}" for k, p in self.by_key.items()},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            clock=lambda: self.now,
            signals=self.board,
        )
        self.executor = StrategyExecutor(
            router=self.router, execution=self.service, templates=templates, clock=lambda: self.now
        )

    def run(self, spec: ExecutionStrategySpec, **kwargs: Any) -> Any:
        return _run(
            self.executor.execute(
                spec=spec,
                tenant_id=uuid4(),
                user_id=uuid4(),
                ask="do the task",
                request_hash="h",
                **kwargs,
            )
        )


def _explicit(model: str) -> ExplicitModelPolicy:
    return ExplicitModelPolicy(type="explicit_model", model_id=model)


DIAMOND = ExecutionStrategySpec(
    mode="custom",
    stages=[
        StrategyStage(key="discover", model_policy=None),
        StrategyStage(
            key="analysis_a",
            role="analyst",
            model_policy=_explicit("model-x"),
            depends_on=["discover"],
        ),
        StrategyStage(
            key="analysis_b",
            role="analyst",
            model_policy=_explicit("model-y"),
            depends_on=["discover"],
        ),
        StrategyStage(
            key="review",
            kind=StageKind.REVIEW,
            role="reviewer",
            depends_on=["analysis_a", "analysis_b"],
        ),
    ],
)


# ------------------------------------------------------------ 1-3. custom DAG runs ---


def test_custom_dag_runs_in_waves_with_concurrency_and_per_stage_models() -> None:
    slow = RecordingAdapter("alpha", delay=0.05)
    w = World({"alpha": slow}, ["model-x", "model-y", "model-z"])
    result = w.run(DIAMOND)

    assert result.succeeded
    assert result.report.execution.strategy is ExecutionStrategy.HYBRID
    assert [n.node.node_key for n in result.report.nodes] == [
        "discover",
        "analysis_a",
        "analysis_b",
        "review",
    ]
    assert all(n.node.status is ExecutionNodeStatus.SUCCEEDED for n in result.report.nodes)
    assert result.report.execution.cost_snapshot["strategy"]["waves"] == [
        ["discover"],
        ["analysis_a", "analysis_b"],
        ["review"],
    ]
    # concurrency observed: the two analyses overlapped inside the adapter
    assert slow.max_active >= 2
    # per-stage model policy honoured by the ONE router
    by_stage = {o.stage.key: o for o in result.outcomes}
    assert by_stage["analysis_a"].output["model"] == "model-x"
    assert by_stage["analysis_b"].output["model"] == "model-y"
    # review received BOTH upstream outputs as subject, keyed by stage
    subject = by_stage["review"].output["subject"]
    assert set(subject) == {"analysis_a", "analysis_b"}
    assert subject["analysis_a"]["model"] == "model-x"
    # each stage is its own stored child execution
    child_ids = result.report.execution.cost_snapshot["child_execution_ids"]
    assert len(child_ids) == 4 and len(set(child_ids)) == 4
    # single-upstream stages get previous_output threaded
    assert by_stage["analysis_a"].output["previous_output"]["stage"] == "discover"


# --------------------------------------------------- 4. failure skips dependents ---


def test_failed_stage_skips_dependents_but_independent_sibling_completes() -> None:
    w = World({"alpha": RecordingAdapter("alpha", fail_when="analysis_a")}, ["model-x", "model-y"])
    result = w.run(DIAMOND)
    assert not result.succeeded
    status = {n.node.node_key: n.node.status for n in result.report.nodes}
    assert status["discover"] is ExecutionNodeStatus.SUCCEEDED
    assert status["analysis_a"] is ExecutionNodeStatus.FAILED
    assert status["analysis_b"] is ExecutionNodeStatus.SUCCEEDED  # independent sibling ran
    assert status["review"] is ExecutionNodeStatus.SKIPPED
    review_node = next(n.node for n in result.report.nodes if n.node.node_key == "review")
    assert review_node.error == {"reason": "upstream stage failed"}
    assert result.report.execution.status is ExecutionStatus.FAILED


# ------------------------------------------------------------- 5. AUTO composes ---


def test_auto_composes_bounded_policy_valid_plan_without_hidden_methodology() -> None:
    plain = compose_auto_strategy(model_policy=None, auto_review=False)
    assert [s.key for s in plain.stages] == ["generate"]
    reviewed = compose_auto_strategy(model_policy=_explicit("model-x"), auto_review=True)
    assert [s.key for s in reviewed.stages] == ["generate", "review"]
    assert reviewed.stages[0].model_policy == _explicit("model-x")
    assert reviewed.stages[1].depends_on == ["generate"]

    w = World({"alpha": RecordingAdapter("alpha")}, ["model-x"])
    result = w.run(ExecutionStrategySpec(mode="auto"))
    assert result.succeeded
    assert [n.node.node_key for n in result.report.nodes] == ["generate"]
    assert result.report.execution.cost_snapshot["strategy"]["mode"] == "custom"


# --------------------------------------------------------------- 6. templates ---


def test_template_mode_resolves_registered_template_and_refuses_unknown() -> None:
    w = World(
        {"alpha": RecordingAdapter("alpha")},
        ["model-x", "model-y"],
        templates={"diamond": DIAMOND},
    )
    result = w.run(ExecutionStrategySpec(mode="template", template_id="diamond"))
    assert result.succeeded and len(result.report.nodes) == 4
    with pytest.raises(UnknownTemplate):
        w.run(ExecutionStrategySpec(mode="template", template_id="nope"))


# ----------------------------------------------- 7. agent <-> provider decoupling ---


def test_same_stage_spec_moves_to_another_provider_when_first_is_cooling() -> None:
    a, b = RecordingAdapter("alpha"), RecordingAdapter("beta")
    w = World({"alpha": a, "beta": b}, ["model-x"])
    spec = ExecutionStrategySpec(
        mode="custom", stages=[StrategyStage(key="s", model_policy=_explicit("model-x"))]
    )
    first = w.run(spec)
    first_provider = first.outcomes[0].output["provider"]
    other = "beta" if first_provider == "alpha" else "alpha"
    w.board.record_error(
        provider_id=w.by_key[first_provider].id,
        model_id=w.model_by_key["model-x"].id,
        error=ProviderError(
            category=ProviderErrorCategory.RATE_LIMITED,
            retryable=True,
            retry_after_ms=60_000,
            safe_message="limited",
        ),
    )
    second = w.run(spec)
    assert second.succeeded
    assert second.outcomes[0].output["provider"] == other
    assert second.outcomes[0].output["model"] == "model-x"  # same model, different provider


# -------------------------------------------------------- 8. contract validation ---


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        (
            [
                StrategyStage(key="a", depends_on=["b"]),
                StrategyStage(key="b", depends_on=["a"]),
            ],
            "cycle",
        ),
        ([StrategyStage(key="a", depends_on=["ghost"])], "unknown stage"),
        ([StrategyStage(key="a"), StrategyStage(key="a")], "duplicate"),
        ([StrategyStage(key="r", kind=StageKind.REVIEW)], "must depend"),
        ([StrategyStage(key=f"s{i}") for i in range(MAX_STAGES + 1)], "exceeds"),
    ],
)
def test_contract_refuses_malformed_strategies(stages: list[StrategyStage], message: str) -> None:
    with pytest.raises(ValidationError) as info:
        ExecutionStrategySpec(mode="custom", stages=stages)
    assert message in str(info.value)


def test_contract_refuses_mode_shape_mismatches() -> None:
    with pytest.raises(ValidationError):
        ExecutionStrategySpec(mode="custom", stages=[])
    with pytest.raises(ValidationError):
        ExecutionStrategySpec(mode="template")
    with pytest.raises(ValidationError):
        ExecutionStrategySpec(mode="auto", stages=[StrategyStage(key="a")])
