"""S3 — bounded fan-out for PARALLEL_COMPARE (multi_model.py).

Measures the REAL peak of concurrently in-flight provider calls with a
compare set larger than the bound, and pins that every other semantic
(all branches run, policy-order results, allow_partial, failure handling)
is unchanged. Hermetic; asyncio.run (ADR-0001).
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
from core.contracts.model_policy import ExplicitModelsPolicy
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderManifest,
    ProviderOperation,
)
from core.execution.multi_model import DEFAULT_MAX_PARALLEL, MultiModelExecutor
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from tests.execution.test_multi_model import _manifest

TENANT = uuid4()
USER = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(_: float) -> None:
    return None


class _Gauge:
    """Counts in-flight generate() calls across every adapter."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0
        self.calls = 0


class _SlowAdapter:
    """Succeeds after yielding to the loop so overlapping calls are visible."""

    def __init__(self, gauge: _Gauge, *, fail: bool = False) -> None:
        self._gauge = gauge
        self._fail = fail
        self.manifest: ProviderManifest | None = None

    def get_manifest(self) -> ProviderManifest:
        assert self.manifest is not None
        return self.manifest

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(self, account_id: UUID | None = None) -> list[Any]:
        return []

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(chat=True)

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self._gauge.calls += 1
        self._gauge.in_flight += 1
        self._gauge.peak = max(self._gauge.peak, self._gauge.in_flight)
        try:
            for _ in range(3):
                await asyncio.sleep(0)
            if self._fail:
                return ProviderGenerateResponse(
                    request_id=request.request_id,
                    succeeded=False,
                    error=self.normalize_error(None),
                    latency_ms=1,
                )
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=True,
                output={"text": f"ok:{request.provider_model_name}"},
                usage={"units": 1},
                latency_ms=1,
            )
        finally:
            self._gauge.in_flight -= 1

    async def health_check(self, scope: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
            retryable=False,
            safe_message="scripted",
        )


class World:
    def __init__(
        self,
        n_models: int,
        *,
        max_parallel: int | None = None,
        fail_idx: set[int] | None = None,
    ) -> None:
        self.gauge = _Gauge()
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        adapters: dict[UUID, Any] = {}
        refs: dict[UUID, str] = {}
        self.model_ids: list[str] = []
        for i in range(n_models):
            key = f"prov_{i}"
            adapter = _SlowAdapter(self.gauge, fail=i in (fail_idx or set()))
            adapter.manifest = _manifest(key)
            provider = Provider(
                id=uuid4(),
                provider_key=key,
                display_name=key,
                status=ProviderStatus.ACTIVE,
                auth_types=["api_key"],
                supports_account_pool=False,
            )
            self.providers.register(provider, adapter.manifest)
            model = Model(
                id=uuid4(),
                model_key=f"model-{i}",
                display_name=f"model-{i}",
                tier=ModelTier.MEDIUM,
                modalities=["text"],
                capabilities=[],
                status=ModelStatus.ACTIVE,
            )
            self.models.register(model)
            self.bindings.register(
                ProviderModelBinding(
                    provider_id=provider.id,
                    model_id=model.id,
                    provider_model_name=f"vendor/{model.model_key}",
                    availability=BindingAvailability.AVAILABLE,
                )
            )
            adapters[provider.id] = adapter
            refs[provider.id] = f"secret-ref://{key}"
            self.model_ids.append(model.model_key)
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        execution = ExecutionService(
            adapters=adapters,
            credential_refs=refs,
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
        )
        kwargs: dict[str, Any] = {"router": router, "execution": execution}
        if max_parallel is not None:
            kwargs["max_parallel"] = max_parallel
        self.executor = MultiModelExecutor(**kwargs)

    def compare(self, **extra: object):
        policy = ExplicitModelsPolicy.model_validate(
            {
                "type": "explicit_models",
                "selection_strategy": "parallel_compare",
                "models": [{"model_id": m} for m in self.model_ids],
                **extra,
            }
        )
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


class TestBoundedFanout:
    def test_peak_in_flight_never_exceeds_bound(self) -> None:
        world = World(6, max_parallel=2)
        report = world.compare()
        assert world.gauge.calls == 6  # every branch still executed
        assert world.gauge.peak == 2  # bound reached, never exceeded
        assert len(report.branches) == 6

    def test_default_bound_applies(self) -> None:
        world = World(DEFAULT_MAX_PARALLEL + 3)
        world.compare()
        assert world.gauge.peak == DEFAULT_MAX_PARALLEL
        assert world.gauge.calls == DEFAULT_MAX_PARALLEL + 3

    def test_results_stay_in_policy_order(self) -> None:
        world = World(5, max_parallel=2)
        report = world.compare()
        assert [b.model_id for b in report.branches] == world.model_ids
        for branch in report.branches:
            assert branch.report is not None
            final = branch.report.final_output
            assert final is not None
            # The branch report belongs to ITS model (no cross-wiring under the bound).
            assert branch.model_id in str(final.get("text"))

    def test_partial_failure_semantics_unchanged(self) -> None:
        world = World(4, max_parallel=1, fail_idx={1})
        report = world.compare(allow_partial=True)
        assert world.gauge.peak == 1  # fully serialized
        statuses = [b.succeeded for b in report.branches]
        assert statuses == [True, False, True, True]
        assert report.winner is not None

    def test_invalid_bound_refused(self) -> None:
        with pytest.raises(ValueError):
            World(1, max_parallel=0)
