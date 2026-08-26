"""In-memory usage accounting (hermetic fake for the UsageAccountingPort).

Satisfies :class:`~core.usage.ports.UsageAccountingPort` against
process-local state — the MVP binding (41 §43: no payments integration)
and the test double. Durable billing swaps in at the composition root
without touching callers.

Budget semantics (10 §8 ``used``/``remaining``; recorded once):

- ``used`` = all resolved consumption (settled + failed-settlement units)
  PLUS active (unresolved) holds — a reservation consumes budget the moment
  it is granted, so parallel requests cannot jointly overdraw the limit.
- ``remaining`` = ``limit - used``, floored at 0 for the summary view
  (settled overage can push raw ``used`` past ``limit``; the summary never
  reports negative remaining).
- Refund returns the FULL hold; settle replaces the hold with ACTUAL units,
  even when actual > reserved (honest accounting, module docstring of
  :mod:`core.usage.ports`).

Deny-by-default: tenants get a budget ONLY via :meth:`configure_tenant`
(the 21 §5 plan seam). Reserving for an unconfigured tenant raises
:class:`EntitlementNotConfigured` — never a silent default allowance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from core.contracts.base import JsonObject
from core.contracts.usage import (
    TaskUnitBudget,
    UsageLedger,
    UsageLedgerStatus,
    UsageSummary,
)
from core.usage.errors import (
    BudgetExceeded,
    EntitlementNotConfigured,
    ReservationAlreadyResolved,
    ReservationNotFound,
)


@dataclass
class _TenantBudget:
    """Mutable per-tenant accounting state (21 §5 plan limits)."""

    plan: str
    limit: float
    consumed: float = 0.0  # resolved consumption (settled + failed units)
    held: float = 0.0  # active, unresolved reservations
    modality_limits: JsonObject = field(default_factory=dict)

    @property
    def used(self) -> float:
        return self.consumed + self.held

    @property
    def remaining(self) -> float:
        return self.limit - self.used


class InMemoryUsageAccounting:
    """Process-local task-unit ledger (03 §7 records, keyed by execution)."""

    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory
        self._budgets: dict[UUID, _TenantBudget] = {}
        self._ledger: dict[UUID, UsageLedger] = {}  # execution_id -> entry

    # --- entitlement configuration (the 21 §5 plan seam) ----------------------

    def configure_tenant(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        task_units_limit: float,
        modality_limits: JsonObject | None = None,
    ) -> None:
        """Grant/replace the tenant's plan budget (admin control plane seam).

        Plan changes keep accounting history (consumed/held survive) —
        upgrading a plan must not erase what the tenant already spent.
        """
        if task_units_limit < 0:
            msg = "task_units_limit must be >= 0"
            raise ValueError(msg)
        budget = _TenantBudget(
            plan=plan,
            limit=task_units_limit,
            modality_limits=dict(modality_limits) if modality_limits else {},
        )
        existing = self._budgets.get(tenant_id)
        if existing is not None:
            budget.consumed = existing.consumed
            budget.held = existing.held
        self._budgets[tenant_id] = budget

    # --- port implementation ---------------------------------------------------

    def reserve(
        self, tenant_id: UUID, execution_id: UUID, units: float
    ) -> UsageLedger:
        if units < 0:
            msg = "reservation units must be >= 0"
            raise ValueError(msg)
        budget = self._budgets.get(tenant_id)
        if budget is None:
            raise EntitlementNotConfigured(tenant_id)
        existing = self._ledger.get(execution_id)
        if existing is not None:
            raise ReservationAlreadyResolved(execution_id, existing.status.value)
        if units > budget.remaining:
            raise BudgetExceeded(
                tenant_id, requested=units, remaining=max(budget.remaining, 0.0)
            )
        budget.held += units
        entry = UsageLedger(
            id=self._id_factory(),
            tenant_id=tenant_id,
            execution_id=execution_id,
            units_reserved=units,
            units_settled=0,
            status=UsageLedgerStatus.RESERVED,
        )
        self._ledger[execution_id] = entry
        return entry

    def settle(
        self,
        execution_id: UUID,
        units_settled: float,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return self._resolve(
            execution_id,
            units_settled,
            UsageLedgerStatus.SETTLED,
            modality_costs=modality_costs,
        )

    def refund(self, execution_id: UUID) -> UsageLedger:
        return self._resolve(execution_id, 0.0, UsageLedgerStatus.REFUNDED)

    def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return self._resolve(
            execution_id,
            units_settled,
            UsageLedgerStatus.FAILED,
            modality_costs=modality_costs,
        )

    def get(self, execution_id: UUID) -> UsageLedger:
        entry = self._ledger.get(execution_id)
        if entry is None:
            raise ReservationNotFound(execution_id)
        return entry

    def summary(self, tenant_id: UUID) -> UsageSummary:
        budget = self._budgets.get(tenant_id)
        if budget is None:
            raise EntitlementNotConfigured(tenant_id)
        return UsageSummary(
            plan=budget.plan,
            task_units=TaskUnitBudget(
                limit=budget.limit,
                used=budget.used,
                remaining=max(budget.remaining, 0.0),
            ),
            modality_limits=dict(budget.modality_limits),
        )

    # --- internals ----------------------------------------------------------------

    def _resolve(
        self,
        execution_id: UUID,
        units_settled: float,
        status: UsageLedgerStatus,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        if units_settled < 0:
            msg = "units_settled must be >= 0"
            raise ValueError(msg)
        entry = self._ledger.get(execution_id)
        if entry is None:
            raise ReservationNotFound(execution_id)
        if entry.status is not UsageLedgerStatus.RESERVED:
            raise ReservationAlreadyResolved(execution_id, entry.status.value)
        budget = self._budgets[entry.tenant_id]
        # Release the hold, book the actual consumption (may exceed the
        # reservation — honest accounting, never clamped).
        budget.held -= entry.units_reserved
        budget.consumed += units_settled
        resolved = entry.model_copy(
            update={
                "units_settled": units_settled,
                "status": status,
                "modality_costs": dict(modality_costs) if modality_costs else {},
            }
        )
        self._ledger[execution_id] = resolved
        return resolved
