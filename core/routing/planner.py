"""Strategy Planner — the 11 §2 "Execution Strategy Selection" stage
(41 §11 "Strategy Planner").

Deterministic mapping from request signals to ONE execution strategy from
the closed set (03 §5 / 12 §2, ``ExecutionStrategy``). The Router DECIDES
the strategy; executing it is the Execution Graph's job (11 "DOES: decide /
DOES NOT: execute").

Recorded derivation decisions (never silent — the docs define the stage and
the signals but NO mapping table):

- EXPLICIT REQUEST WINS: ``execution_policy.strategy`` (10 §6) is the user/
  developer's strategy request. A value naming a member of the closed set is
  honored verbatim (11 §13: explicit user choice outranks Router preference).
  ``"auto"`` (the 10 §6 example value) and absence both mean "Router
  decides". Any OTHER unknown string is REJECTED loudly
  (:class:`UnknownStrategy`) — deny-by-default (11 §5 "Unknown =
  ineligible"), never coerced.
- AUTO MAPPING — the ONLY documented analysis→strategy signal is
  ``needs_agent`` (11 §3): ``needs_agent=True`` => ``agent``. NOTHING else
  in doc 11/12 maps ``task_type``/``complexity``/``risk_level`` to a
  strategy, so NO heuristic is invented: every other auto case maps to
  ``single`` — the minimal, always-valid strategy. Richer auto planning is
  a future policy-driven concern; guessing here would fabricate decisions.
- EXPLICIT_MODELS POLICIES: ``selection_strategy`` (10 §13.4) is a MODEL-
  selection strategy (fallback_chain/parallel_compare/...), a different
  axis from the execution strategy — it is NOT consumed here (recorded to
  prevent conflation; the execution-graph slice maps it to node topology).
- NO ADMIN GATING HERE: 11 §17 strategy eligibility controls (per-plan
  limits) belong to the entitlement filter chain, which is a recorded
  deferred filter (router module docstring) — not silently half-built here.
"""

from __future__ import annotations

from core.contracts.execution import ExecutionStrategy
from core.contracts.routing import TaskAnalysis
from core.routing.errors import UnknownStrategy

#: 10 §6 example value meaning "Router decides" — not a strategy itself.
_AUTO = "auto"

_STRATEGY_VALUES = {member.value for member in ExecutionStrategy}


class StrategyPlanner:
    """Deterministic execution-strategy selection (11 §2 stage; pure)."""

    def plan(
        self,
        *,
        requested_strategy: str | None = None,
        task_analysis: TaskAnalysis | None = None,
    ) -> ExecutionStrategy:
        """Select the execution strategy for a request.

        - ``requested_strategy`` is the raw ``execution_policy.strategy``
          value (10 §6); ``None``/``"auto"`` => Router decides.
        - ``task_analysis`` feeds the auto path (11 §3 ``needs_agent``).
        """
        if requested_strategy is not None and requested_strategy != _AUTO:
            if requested_strategy not in _STRATEGY_VALUES:
                msg = (
                    f"unknown execution strategy {requested_strategy!r} —"
                    " not in the 03 §5 closed set (unknown = rejected,"
                    " never coerced)"
                )
                raise UnknownStrategy(msg)
            return ExecutionStrategy(requested_strategy)
        if task_analysis is not None and task_analysis.needs_agent:
            return ExecutionStrategy.AGENT
        return ExecutionStrategy.SINGLE
