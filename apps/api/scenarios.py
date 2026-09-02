"""Test Scenarios → Regression Center — Vision V7 chunk 3 (frozen clause).

The frozen definition: "Test Scenarios (saved, replayable) → Regression
Center pack". Recorded derivations:

- A SAVED SCENARIO is a named request shape (ask + named checks) — data,
  tenant-scoped, in-memory first (repository binding later through the
  V1 patterns; NO new persistence mechanism in this chunk).
- REPLAY runs the REAL execute path (ExecutionService.execute_single —
  the same substrate the agent's R1 tool and the exercise probes ride,
  P1) as the calling principal, labeled machine-checkably in the stored
  node's input_ref (SCENARIO_LABEL_KEY), billed to the caller's tenant.
- CHECKS are a CLOSED set of names bound to the platform's OWN
  deterministic checks (core/evaluation/policy.MVP_DETERMINISTIC_CHECKS
  — reused verbatim, zero new grader machinery; R049 boundary (c) keeps
  model-based grading out of this surface). An unknown check name is a
  construction-time refusal, never silent data.
- A REGRESSION PACK replays EVERY saved scenario of the tenant and
  reports per-scenario verdicts + one overall ``regression_pass`` —
  the SAME signal name core/learning/gates.py consumes (data alignment,
  not a wiring claim: feeding gates stays composition territory).
- VERDICTS follow stored truth (P6): a failed execution grades its
  checks over an EMPTY output — never a fabricated pass; the stored
  execution id rides every verdict as machine-checkable evidence.
- ANTI-ENUMERATION (20 §6): absent and foreign-tenant scenario ids are
  the same answer.
- CONSUMERS (P3): admin routes and the agent's tools both dispatch
  through THIS service — one store, two consumers, zero parallel state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject, utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.evaluation.policy import MVP_DETERMINISTIC_CHECKS, DeterministicCheck
from core.execution.service import ExecutionService
from core.routing.errors import FallbackNotConfigured, NoEligibleCandidates
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.api.store import ExecutionStorePort

#: The metadata key that labels scenario-replay executions — same
#: machine-checkable posture as the R1 and exercise labels.
SCENARIO_LABEL_KEY = "test_scenario"

#: The CLOSED check-name set — exactly the platform's own deterministic
#: checks (P1). Extending means extending core policy first, never here.
SCENARIO_CHECKS: dict[str, DeterministicCheck] = {
    check.name: check for check in MVP_DETERMINISTIC_CHECKS
}


class UnknownCheckName(ValueError):
    """A scenario referenced a check outside the closed set."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown check name {name!r}; the scenario check set is closed")


class ScenarioNotFound(KeyError):
    """Absent and foreign-tenant ids are the same answer (20 §6)."""


class ScenarioSaveRequest(ContractModel):
    """POST /v1/admin/scenarios body — app-layer contract (closed shape).

    Tenant comes from the authenticated principal; clients never claim
    identity fields. ``checks`` defaults to the FULL closed set — a
    scenario with no checks would be a replay that proves nothing.
    """

    name: BoundedStr
    ask: BoundedStr
    checks: list[str] = Field(default_factory=lambda: sorted(SCENARIO_CHECKS), min_length=1)


@dataclass(frozen=True)
class Scenario:
    """One saved, replayable scenario — pure data."""

    id: UUID
    tenant_id: UUID
    name: str
    ask: str
    checks: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        unknown = [c for c in self.checks if c not in SCENARIO_CHECKS]
        if unknown:
            raise UnknownCheckName(unknown[0])


def scenario_json(scenario: Scenario) -> JsonObject:
    """The row shape both consumers render."""
    return {
        "scenario_id": str(scenario.id),
        "name": scenario.name,
        "ask": scenario.ask,
        "checks": list(scenario.checks),
        "created_at": scenario.created_at.isoformat(),
    }


@dataclass
class ScenarioService:
    """Tenant-scoped scenario store + replay over the REAL execute path.

    Composed with the SAME router/execution service/store create_app
    composes for user traffic — a replay is a real execution, not a
    simulation (P1; the honesty posture of the exercise probes).
    """

    router: SimpleScoringRouter
    execution_service: ExecutionService
    execution_store: ExecutionStorePort
    _scenarios: dict[UUID, dict[UUID, Scenario]] = field(default_factory=dict)

    # --- store (data only) --------------------------------------------------

    def save(self, tenant_id: UUID, *, name: str, ask: str, checks: tuple[str, ...]) -> Scenario:
        """Save a scenario; unknown check names refuse loudly (closed set)."""
        scenario = Scenario(
            id=uuid4(),
            tenant_id=tenant_id,
            name=name[:256],
            ask=ask[:4096],
            checks=checks,
            created_at=utc_now(),
        )
        self._scenarios.setdefault(tenant_id, {})[scenario.id] = scenario
        return scenario

    def list(self, tenant_id: UUID) -> list[Scenario]:
        rows = self._scenarios.get(tenant_id, {})
        return sorted(rows.values(), key=lambda s: (s.created_at, str(s.id)))

    def get(self, tenant_id: UUID, scenario_id: UUID) -> Scenario:
        scenario = self._scenarios.get(tenant_id, {}).get(scenario_id)
        if scenario is None:
            raise ScenarioNotFound(scenario_id)
        return scenario

    # --- replay (real executions, honest verdicts) --------------------------

    async def replay(self, tenant_id: UUID, user_id: UUID, scenario_id: UUID) -> JsonObject:
        """Replay ONE scenario as the caller — verdict follows stored truth."""
        scenario = self.get(tenant_id, scenario_id)
        payload: JsonObject = {
            "ask": scenario.ask,
            "context": {"metadata": {SCENARIO_LABEL_KEY: {"scenario_id": str(scenario.id)}}},
        }
        try:
            decision = self.router.route(RoutingRequest(operation=ProviderOperation.GENERATE_TEXT))
        except (
            NoEligibleCandidates,
            FallbackNotConfigured,
            UnsupportedPolicyType,
        ) as exc:
            return {
                "scenario_id": str(scenario.id),
                "replayed": False,
                "error": f"routing failed: {type(exc).__name__}",
            }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            report = await self.execution_service.execute_single(
                tenant_id=tenant_id,
                user_id=user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=request_hash,
            )
        except BudgetExceeded as exc:
            return {
                "scenario_id": str(scenario.id),
                "replayed": False,
                "error": "budget exceeded",
                "requested": exc.requested,
                "remaining": exc.remaining,
            }
        except EntitlementNotConfigured:
            return {
                "scenario_id": str(scenario.id),
                "replayed": False,
                "error": "no entitlement configured for this tenant",
            }
        self.execution_store.put(report)
        # Verdicts over STORED truth: a non-succeeded execution grades its
        # checks against an EMPTY output — failure is honest data (P6).
        output: JsonObject = report.final_output or {}
        check_rows: list[JsonObject] = []
        all_passed = report.execution.status is ExecutionStatus.SUCCEEDED
        for check_name in scenario.checks:
            check = SCENARIO_CHECKS[check_name]
            passed = check.predicate(output)
            check_rows.append({"name": check_name, "passed": passed})
            all_passed = all_passed and passed
        return {
            "scenario_id": str(scenario.id),
            "replayed": True,
            "execution_id": str(report.execution.id),
            "execution_status": report.execution.status.value,
            "passed": all_passed,
            "checks": check_rows,
        }

    async def regression_pack(self, tenant_id: UUID, user_id: UUID) -> JsonObject:
        """Replay EVERY saved scenario — the Regression Center pack.

        ``regression_pass`` is true only when every scenario replayed AND
        passed; an empty scenario set is honestly reported (a pack with
        nothing in it proves nothing — regression_pass stays false).
        """
        scenarios = self.list(tenant_id)
        results: list[JsonObject] = []
        for scenario in scenarios:
            results.append(await self.replay(tenant_id, user_id, scenario.id))
        regression_pass = bool(results) and all(
            r.get("replayed") is True and r.get("passed") is True for r in results
        )
        return {
            "scenario_count": len(results),
            "regression_pass": regression_pass,
            "results": results,
        }
