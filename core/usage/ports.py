"""Usage accounting port — reserve BEFORE execution, settle AFTER (41 §43/§44).

Port + in-memory fake pattern (same posture as core/storage, core/secrets,
core/runtime): Core defines the seam; the durable billing/persistence
binding is an infrastructure concern for a later phase. No real payments
integration in the MVP (41 §43 scope table: "units estimate/reserve/settle").

Lifecycle contract (03 §7 UsageLedger, applied uniformly):

1. ``reserve(tenant_id, execution_id, units)`` — hold units against the
   tenant's task-unit budget (21 §5 plan limits) BEFORE any provider work.
   Insufficient budget or missing entitlement raises BEFORE execution
   starts — a denied request must never reach a provider.
2. Exactly ONE resolution per reservation:
   - ``settle(...)``  — execution succeeded; finalize from ACTUAL usage.
   - ``refund(...)``  — nothing consumed; release the full hold.
   - ``fail(...)``    — execution failed; record failed settlement with
     whatever units policy says failed work costs (may be 0).
3. Double resolution raises :class:`ReservationAlreadyResolved` — ledger
   entries are append-once accounting facts, never silently rewritten.

Settled units MAY exceed the reservation (estimates are estimates); the
overage is charged to the budget honestly rather than clamped — hiding real
consumption would corrupt the 10 §8 usage summary.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.contracts.base import JsonObject
from core.contracts.usage import UsageLedger, UsageSummary


class UsageAccountingPort(Protocol):
    """Task-unit reservation/settlement seam (03 §7; 10 §8; 21 §5)."""

    def reserve(self, tenant_id: UUID, execution_id: UUID, units: float) -> UsageLedger:
        """Hold ``units`` for ``execution_id`` against the tenant budget.

        Raises ``EntitlementNotConfigured`` (deny-by-default) or
        ``BudgetExceeded`` BEFORE any provider work can start.
        """
        ...

    def settle(
        self,
        execution_id: UUID,
        units_settled: float,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        """Finalize the reservation from actual usage (status=settled)."""
        ...

    def refund(self, execution_id: UUID) -> UsageLedger:
        """Release the full hold with zero consumption (status=refunded)."""
        ...

    def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        """Resolve a failed execution's reservation (status=failed)."""
        ...

    def get(self, execution_id: UUID) -> UsageLedger:
        """Return the ledger entry for ``execution_id`` (raises if absent)."""
        ...

    def summary(self, tenant_id: UUID) -> UsageSummary:
        """The tenant's 10 §8 usage view: plan, task_units, modality_limits."""
        ...
