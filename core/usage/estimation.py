"""Task-unit estimation — FINAL Phase 16 (41 §19, T-IMPL-065).

Spec anchors:

- 41 §19 Units (verbatim): ``Simple = 1 / Medium = 2 / Complex = 3`` and
  "Values are configuration-driven." — the table below is DATA, injectable,
  shipped with exactly the three verbatim values as the default.
- 41 §19 Flow: ``Estimate → Reserve → Execute → Settle``. Reserve/Execute/
  Settle pre-exist (T-IMPL-024 UsageAccountingPort + ExecutionService);
  THIS module is the missing Estimate step.
- 41 §19: "Cost Snapshot: fixed at Task start." — the estimate is computed
  BEFORE execution and rendered in the documented 11 §10 snapshot shape
  (``{"estimated_units": 2}``); the ExecutionService's fixed-cost mode
  (same task) freezes it as the user's price.
- 11 §3: ``TaskAnalysis.complexity`` is the input — an OPEN bounded string
  by contract (doc 11 declares no closed set).

Recorded derivations (nothing invented silently):

- The estimator maps ``TaskAnalysis.complexity`` against the injected unit
  table by EXACT string match. Doc 11's example value is lowercase
  ("medium") and the 41 §19 words Simple/Medium/Complex are normalized to
  the same lowercase keys the TaskAnalysis examples use — one recorded
  normalization at the DATA layer, none at lookup time.
- A complexity ABSENT from the table is REFUSED loudly
  (:class:`~core.usage.errors.UnknownComplexity`) — deny-by-default:
  inventing a price for an unpriced complexity would fabricate billing
  policy (same posture as EntitlementNotConfigured).
- ``CostEstimate.as_snapshot()`` renders the 11 §10 documented shape
  verbatim (``{"estimated_units": N}``) — the fixed-at-start snapshot
  fragment; the execution record's ``cost_snapshot`` carries it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from core.contracts.base import JsonObject
from core.contracts.routing import TaskAnalysis
from core.usage.errors import UnknownComplexity

#: The 41 §19 unit table, verbatim values, as configuration DATA
#: (keys lowercase per the doc 11 TaskAnalysis example style).
DEFAULT_TASK_UNIT_VALUES: Mapping[str, float] = MappingProxyType(
    {
        "simple": 1.0,
        "medium": 2.0,
        "complex": 3.0,
    }
)


@dataclass(frozen=True)
class CostEstimate:
    """One Estimate-step outcome: the complexity priced, fixed at task start."""

    complexity: str
    estimated_units: float

    def as_snapshot(self) -> JsonObject:
        """The 11 §10 documented cost-snapshot fragment, verbatim shape."""
        return {"estimated_units": self.estimated_units}


class TaskUnitEstimator:
    """The 41 §19 Estimate step: TaskAnalysis complexity -> task units.

    ``unit_values`` is injectable configuration (41 §19 "Values are
    configuration-driven"); the default is the verbatim three-row table.
    An empty table prices nothing — every estimate refuses (deny-by-
    default survives misconfiguration).
    """

    def __init__(
        self, unit_values: Mapping[str, float] = DEFAULT_TASK_UNIT_VALUES
    ) -> None:
        for key, value in unit_values.items():
            if value < 0:
                msg = f"unit value for {key!r} must be >= 0, got {value}"
                raise ValueError(msg)
        self._unit_values = dict(unit_values)

    def estimate(self, task: TaskAnalysis) -> CostEstimate:
        """Price one task by its analyzed complexity; unknown REFUSES."""
        complexity = task.complexity
        if complexity not in self._unit_values:
            raise UnknownComplexity(complexity, known=sorted(self._unit_values))
        return CostEstimate(
            complexity=complexity,
            estimated_units=self._unit_values[complexity],
        )
