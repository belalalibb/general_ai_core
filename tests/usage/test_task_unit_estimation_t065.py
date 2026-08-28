"""T-IMPL-065 tests (partial slice 1): 41 §19 Estimate step + billing rules.

Exit mapping (41 §19, FINAL Phase 16 — Reserve/Execute/Settle pre-exist,
T-IMPL-024, verified by the 29 pre-existing usage tests + execution
suite, never redone):

- Units "Simple = 1 / Medium = 2 / Complex = 3", configuration-driven ->
  TestTaskUnitEstimator (verbatim default table; injectable; unknown
  complexity REFUSED — deny-by-default pricing).
- Flow "Estimate → Reserve → ..." -> the estimator is the Estimate step
  over TaskAnalysis.complexity (11 §3).
- "Cost Snapshot: fixed at Task start." -> TestFixedCostSnapshot
  (estimated_units computed before provider work, carried verbatim in
  the 11 §10 documented snapshot key, identical on success and failure).
- "Internal retry/failover never multiplies the user's cost." ->
  test_retry_does_not_multiply_cost (a stage succeeding after a retry
  reserves and settles exactly what a first-attempt success costs).

Hermetic: fake adapters only (41 §49).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from core.contracts.routing import TaskAnalysis
from core.usage import (
    DEFAULT_TASK_UNIT_VALUES,
    TaskUnitEstimator,
    UnknownComplexity,
    UsageError,
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def make_task(complexity: str) -> TaskAnalysis:
    return TaskAnalysis.model_validate(
        {
            "task_type": "code_review",
            "complexity": complexity,
            "capabilities_required": [],
            "risk_level": "low",
        }
    )


class TestTaskUnitEstimator:
    def test_default_table_is_the_verbatim_41s19_values(self) -> None:
        assert dict(DEFAULT_TASK_UNIT_VALUES) == {
            "simple": 1.0,
            "medium": 2.0,
            "complex": 3.0,
        }

    @pytest.mark.parametrize(
        ("complexity", "units"), [("simple", 1.0), ("medium", 2.0), ("complex", 3.0)]
    )
    def test_estimate_prices_by_complexity(
        self, complexity: str, units: float
    ) -> None:
        estimate = TaskUnitEstimator().estimate(make_task(complexity))
        assert estimate.estimated_units == units
        assert estimate.complexity == complexity

    def test_unknown_complexity_refused_naming_known(self) -> None:
        with pytest.raises(UnknownComplexity) as exc:
            TaskUnitEstimator().estimate(make_task("herculean"))
        assert exc.value.complexity == "herculean"
        assert exc.value.known == ["complex", "medium", "simple"]

    def test_unknown_complexity_is_a_usage_error(self) -> None:
        assert issubclass(UnknownComplexity, UsageError)

    def test_table_is_injectable_configuration(self) -> None:
        estimator = TaskUnitEstimator({"trivial": 0.5})
        assert estimator.estimate(make_task("trivial")).estimated_units == 0.5
        with pytest.raises(UnknownComplexity):
            estimator.estimate(make_task("simple"))

    def test_empty_table_prices_nothing(self) -> None:
        with pytest.raises(UnknownComplexity):
            TaskUnitEstimator({}).estimate(make_task("simple"))

    def test_negative_unit_value_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            TaskUnitEstimator({"simple": -1.0})

    def test_snapshot_fragment_is_the_documented_11s10_shape(self) -> None:
        estimate = TaskUnitEstimator().estimate(make_task("medium"))
        assert estimate.as_snapshot() == {"estimated_units": 2.0}


class TestFixedCostSnapshot:
    """41 §19: snapshot fixed at start; retry never multiplies cost.

    Reuses the execution test world (fake adapters, scripted outcomes).
    """

    def _world(self) -> Any:
        from tests.execution.test_execution_service import World

        return World()

    def _run_single(
        self, world: Any, provider_script: list[object], **service_kwargs: Any
    ) -> Any:
        from uuid import uuid4

        from core.contracts.provider import ProviderOperation

        provider_id, adapter = world.add_provider(provider_script)
        service = world.service(**service_kwargs)
        report = run(
            service.execute_single(
                tenant_id=uuid4(),
                user_id=uuid4(),
                decision=world.decision(world.candidate(provider_id)),
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"prompt": "x"},
                request_hash="h",
            )
        )
        return report, adapter

    def test_snapshot_carries_estimated_units_fixed_at_start(self) -> None:
        report, _ = self._run_single(self._world(), [{"text": "ok"}])
        assert report.execution.cost_snapshot["estimated_units"] == 1.0

    def test_estimate_is_fixed_even_when_execution_fails(self) -> None:
        from core.contracts.provider import ProviderErrorCategory
        from tests.execution.test_execution_service import _error

        report, _ = self._run_single(
            self._world(), [_error(ProviderErrorCategory.BAD_REQUEST)]
        )
        assert report.execution.cost_snapshot["estimated_units"] == 1.0

    def test_retry_does_not_multiply_cost(self) -> None:
        """Two attempts, one stage: reserved/settled = first-attempt price."""
        from uuid import uuid4

        from core.contracts.provider import ProviderErrorCategory
        from core.contracts.usage import UsageLedgerStatus
        from core.usage import InMemoryUsageAccounting
        from tests.execution.test_execution_service import _error

        world = self._world()
        usage = InMemoryUsageAccounting()
        provider_id, adapter = world.add_provider(
            [
                _error(ProviderErrorCategory.RETRYABLE_SERVER_ERROR, retryable=True),
                {"text": "recovered"},
            ]
        )
        service = world.service(usage=usage)
        tenant_id = uuid4()
        usage.configure_tenant(tenant_id, plan="pro", task_units_limit=10)

        from core.contracts.provider import ProviderOperation

        report = run(
            service.execute_single(
                tenant_id=tenant_id,
                user_id=uuid4(),
                decision=world.decision(world.candidate(provider_id)),
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"prompt": "x"},
                request_hash="h",
            )
        )
        assert len(adapter.requests) == 2  # the retry really happened
        settlement = report.execution.cost_snapshot["settlement"]
        assert settlement == {
            "status": UsageLedgerStatus.SETTLED.value,
            "units_reserved": 1.0,  # not 2.0
            "units_settled": 1.0,  # not 2.0
        }
        assert report.execution.cost_snapshot["estimated_units"] == 1.0
