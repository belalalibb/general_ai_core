"""MultiModelExecutor — 10 §13.4 strategies + 10 §13.5 node resolution.

Hermetic: two providers/models with scripted fake adapters. Pins:

- fallback_chain: order honored; first success stops the chain (later
  models NEVER called); routing refusals skip to the next model; all-fail
  returns the last executed report; all-refused raises CompareRefused;
- parallel_compare: every branch executes; winner = first succeeded in
  policy order (no judge); judge_policy routes a judge whose payload
  carries the candidates and whose output IS the final report; judge
  failure degrades to the deterministic winner (documented rule);
  allow_partial=False refuses on refused branch or failed branch;
  allow_partial=True proceeds;
- unsupported strategies + nested judge refuse loudly (never degrade);
- resolve_node_policy follows 10 §13.5 order (node > default > None).

Async driven by asyncio.run (ADR-0001; no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
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
    ExplicitModelsPolicy,
    TierModelPolicy,
)
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
    ProviderOperation,
)
from core.execution.multi_model import (
    JUDGE_CANDIDATES_KEY,
    CompareRefused,
    InvalidJudgePolicy,
    MultiModelExecutor,
    UnsupportedStrategy,
    resolve_node_policy,
)
from core.execution.service import ExecutionService
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import SimpleScoringRouter

TENANT = uuid4()
USER = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


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


def _model(key: str, tier: ModelTier = ModelTier.MEDIUM) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=tier,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )


_FAIL = ProviderError(
    category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
    retryable=False,
    safe_message="scripted failure",
)


class ScriptedAdapter:
    """Pops one scripted step per generate call; records requests."""

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        raise NotImplementedError  # pragma: no cover - unused

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"ok": True}
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=step,
                latency_ms=1,
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=1,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return _FAIL


class World:
    """Two providers (a, b), each serving its own model (model-a, model-b)."""

    def __init__(
        self,
        *,
        script_a: list[object] | None = None,
        script_b: list[object] | None = None,
    ) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapter_a = ScriptedAdapter(script_a)
        self.adapter_b = ScriptedAdapter(script_b)

        self.provider_a = self._provider("prov_a")
        self.provider_b = self._provider("prov_b")
        self.model_a = _model("model-a")
        self.model_b = _model("model-b", tier=ModelTier.MAX)
        self.models.register(self.model_a)
        self.models.register(self.model_b)
        self._bind(self.provider_a, self.model_a)
        self._bind(self.provider_b, self.model_b)

        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.execution = ExecutionService(
            adapters={
                self.provider_a.id: self.adapter_a,
                self.provider_b.id: self.adapter_b,
            },
            credential_refs={
                self.provider_a.id: "secret-ref://a",
                self.provider_b.id: "secret-ref://b",
            },
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
        )
        self.executor = MultiModelExecutor(
            router=self.router, execution=self.execution
        )

    def _provider(self, key: str) -> Provider:
        provider = Provider(
            id=uuid4(),
            provider_key=key,
            display_name=key,
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(provider, _manifest(key))
        return provider

    def _bind(self, provider: Provider, model: Model) -> None:
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name=f"vendor/{model.model_key}",
                availability=BindingAvailability.AVAILABLE,
            )
        )

    def execute(self, policy: ExplicitModelsPolicy):
        return run(
            self.executor.execute(
                tenant_id=TENANT,
                user_id=USER,
                policy=policy,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"ask": "hi"},
                request_hash="h",
            )
        )


def _policy(**kwargs: object) -> ExplicitModelsPolicy:
    base: dict[str, object] = {
        "type": "explicit_models",
        "models": [{"model_id": "model-a"}, {"model_id": "model-b"}],
    }
    base.update(kwargs)
    return ExplicitModelsPolicy.model_validate(base)


class TestFallbackChain:
    def test_first_success_stops_the_chain(self) -> None:
        world = World(script_a=[{"text": "from-a"}])
        report = world.execute(_policy(selection_strategy="fallback_chain"))
        assert report.winner is not None
        assert report.winner.model_id == "model-a"
        assert report.final_report.final_output == {"text": "from-a"}
        # model-b was NEVER called.
        assert world.adapter_b.requests == []

    def test_default_strategy_is_fallback_chain(self) -> None:
        world = World(script_a=[{"text": "from-a"}])
        report = world.execute(_policy())
        assert report.strategy.value == "fallback_chain"

    def test_failure_moves_to_next_model(self) -> None:
        world = World(script_a=[_FAIL], script_b=[{"text": "from-b"}])
        report = world.execute(_policy(selection_strategy="fallback_chain"))
        assert report.winner is not None
        assert report.winner.model_id == "model-b"
        assert report.final_report.final_output == {"text": "from-b"}
        assert len(report.branches) == 2
        assert report.branches[0].succeeded is False

    def test_routing_refusal_skips_to_next_model(self) -> None:
        world = World(script_b=[{"text": "from-b"}])
        policy = ExplicitModelsPolicy.model_validate(
            {
                "type": "explicit_models",
                "models": [{"model_id": "ghost"}, {"model_id": "model-b"}],
                "selection_strategy": "fallback_chain",
            }
        )
        report = world.execute(policy)
        assert report.winner is not None
        assert report.winner.model_id == "model-b"
        assert report.branches[0].routing_refusal is not None

    def test_all_failed_returns_last_executed_report(self) -> None:
        world = World(script_a=[_FAIL], script_b=[_FAIL])
        report = world.execute(_policy(selection_strategy="fallback_chain"))
        assert report.winner is None
        assert report.final_report.final_output is None
        assert len(report.branches) == 2

    def test_all_refused_raises_compare_refused(self) -> None:
        world = World()
        policy = ExplicitModelsPolicy.model_validate(
            {
                "type": "explicit_models",
                "models": [{"model_id": "ghost1"}, {"model_id": "ghost2"}],
                "selection_strategy": "fallback_chain",
            }
        )
        with pytest.raises(CompareRefused):
            world.execute(policy)


class TestParallelCompare:
    def test_all_branches_execute_and_first_success_wins(self) -> None:
        world = World(script_a=[{"text": "A"}], script_b=[{"text": "B"}])
        report = world.execute(
            _policy(selection_strategy="parallel_compare", allow_partial=True)
        )
        assert report.winner is not None
        assert report.winner.model_id == "model-a"  # policy order
        assert report.final_report.final_output == {"text": "A"}
        # BOTH adapters were called (unlike fallback_chain).
        assert len(world.adapter_a.requests) == 1
        assert len(world.adapter_b.requests) == 1

    def test_failed_first_branch_second_wins_with_allow_partial(self) -> None:
        world = World(script_a=[_FAIL], script_b=[{"text": "B"}])
        report = world.execute(
            _policy(selection_strategy="parallel_compare", allow_partial=True)
        )
        assert report.winner is not None
        assert report.winner.model_id == "model-b"

    def test_branch_failure_without_allow_partial_refuses(self) -> None:
        world = World(script_a=[_FAIL], script_b=[{"text": "B"}])
        with pytest.raises(CompareRefused):
            world.execute(_policy(selection_strategy="parallel_compare"))

    def test_routing_refusal_without_allow_partial_refuses(self) -> None:
        world = World()
        policy = ExplicitModelsPolicy.model_validate(
            {
                "type": "explicit_models",
                "models": [{"model_id": "ghost"}, {"model_id": "model-b"}],
                "selection_strategy": "parallel_compare",
            }
        )
        with pytest.raises(CompareRefused):
            world.execute(policy)

    def test_all_branches_failed_returns_last_failed_report(self) -> None:
        world = World(script_a=[_FAIL], script_b=[_FAIL])
        report = world.execute(
            _policy(selection_strategy="parallel_compare", allow_partial=True)
        )
        assert report.winner is None
        assert report.final_report.final_output is None


class TestJudgedCompare:
    def test_judge_output_is_the_final_report(self) -> None:
        # Judge routes via tier=max -> model-b/prov_b; its SECOND scripted
        # step is the judge answer (first step consumed by the branch run).
        world = World(
            script_a=[{"text": "A"}],
            script_b=[{"text": "B"}, {"text": "JUDGED"}],
        )
        report = world.execute(
            _policy(
                selection_strategy="parallel_compare",
                allow_partial=True,
                judge_policy={"type": "tier", "tier": "max"},
            )
        )
        assert report.judge is not None
        assert report.final_report.final_output == {"text": "JUDGED"}
        assert report.winner is None  # judge supersedes branch picks

    def test_judge_payload_carries_all_succeeded_candidates(self) -> None:
        world = World(
            script_a=[{"text": "A"}],
            script_b=[{"text": "B"}, {"text": "JUDGED"}],
        )
        world.execute(
            _policy(
                selection_strategy="parallel_compare",
                allow_partial=True,
                judge_policy={"type": "tier", "tier": "max"},
            )
        )
        judge_request = world.adapter_b.requests[-1]
        candidates = judge_request.payload[JUDGE_CANDIDATES_KEY]
        assert [c["model_id"] for c in candidates] == ["model-a", "model-b"]
        assert candidates[0]["output"] == {"text": "A"}

    def test_judge_failure_degrades_to_deterministic_winner(self) -> None:
        world = World(
            script_a=[{"text": "A"}],
            script_b=[{"text": "B"}, _FAIL],  # judge step fails
        )
        report = world.execute(
            _policy(
                selection_strategy="parallel_compare",
                allow_partial=True,
                judge_policy={"type": "tier", "tier": "max"},
            )
        )
        assert report.judge is None
        assert report.winner is not None
        assert report.final_report.final_output == {"text": "A"}


class TestRefusals:
    def test_unsupported_strategy_refused(self) -> None:
        world = World()
        with pytest.raises(UnsupportedStrategy):
            world.execute(_policy(selection_strategy="best_of_n"))

    def test_debate_refused(self) -> None:
        world = World()
        with pytest.raises(UnsupportedStrategy):
            world.execute(_policy(selection_strategy="debate"))

    def test_nested_explicit_models_judge_refused(self) -> None:
        world = World()
        with pytest.raises(InvalidJudgePolicy):
            world.execute(
                _policy(
                    selection_strategy="parallel_compare",
                    judge_policy={
                        "type": "explicit_models",
                        "models": [{"model_id": "model-a"}],
                    },
                )
            )


class TestResolveNodePolicy:
    def test_node_policy_wins_over_default(self) -> None:
        mapping = AgentNodeMappingPolicy.model_validate(
            {
                "type": "agent_node_mapping",
                "default_model_policy": {"type": "auto"},
                "node_model_policies": {
                    "single": {"type": "tier", "tier": "max"}
                },
            }
        )
        resolved = resolve_node_policy(mapping, "single")
        assert isinstance(resolved, TierModelPolicy)
        assert resolved.tier == "max"

    def test_default_used_when_node_absent(self) -> None:
        mapping = AgentNodeMappingPolicy.model_validate(
            {
                "type": "agent_node_mapping",
                "default_model_policy": {"type": "auto"},
            }
        )
        resolved = resolve_node_policy(mapping, "single")
        assert isinstance(resolved, AutoModelPolicy)

    def test_none_when_mapping_is_silent(self) -> None:
        mapping = AgentNodeMappingPolicy.model_validate(
            {"type": "agent_node_mapping"}
        )
        assert resolve_node_policy(mapping, "single") is None
