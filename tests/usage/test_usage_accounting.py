"""Usage accounting tests (T-IMPL-024; 03 §7; 10 §8; 21 §5; 41 §43/§44).

Covers the UsageLedger contract shape, the reserve→settle/refund/fail
lifecycle, deny-by-default entitlements, budget enforcement (including
concurrent-hold semantics), exactly-once resolution, honest overage
accounting, and the 10 §8 summary view. Hermetic: in-memory only.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.contracts.usage import (
    TaskUnitBudget,
    UsageLedger,
    UsageLedgerStatus,
    UsageSummary,
)
from core.usage import (
    BudgetExceeded,
    EntitlementNotConfigured,
    InMemoryUsageAccounting,
    ReservationAlreadyResolved,
    ReservationNotFound,
    UsageAccountingPort,
    UsageError,
)

TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest.fixture()
def usage() -> InMemoryUsageAccounting:
    svc = InMemoryUsageAccounting()
    svc.configure_tenant(TENANT_A, plan="pro", task_units_limit=100.0)
    return svc


# --- contract shape (03 §7 verbatim) --------------------------------------------


class TestUsageLedgerContract:
    def test_status_closed_set_verbatim(self) -> None:
        """03 §7: reserved|settled|refunded|failed — exactly these four."""
        assert {s.value for s in UsageLedgerStatus} == {
            "reserved",
            "settled",
            "refunded",
            "failed",
        }

    def test_ledger_fields_verbatim(self) -> None:
        """03 §7 field set carried exactly — no additions, renames, drops."""
        assert set(UsageLedger.model_fields) == {
            "id",
            "tenant_id",
            "execution_id",
            "units_reserved",
            "units_settled",
            "modality_costs",
            "status",
        }

    def test_negative_units_rejected_by_contract(self) -> None:
        with pytest.raises(ValueError):
            UsageLedger(
                id=uuid4(),
                tenant_id=TENANT_A,
                execution_id=uuid4(),
                units_reserved=-1,
                status=UsageLedgerStatus.RESERVED,
            )

    def test_summary_shape_10_s8(self) -> None:
        """GET /v1/usage: plan + task_units{limit,used,remaining} + modality_limits."""
        s = UsageSummary(
            plan="pro",
            task_units=TaskUnitBudget(limit=100, used=40, remaining=60),
            modality_limits={"image_generations": 500},
        )
        dumped = s.model_dump()
        assert dumped["task_units"] == {"limit": 100, "used": 40, "remaining": 60}
        assert dumped["modality_limits"]["image_generations"] == 500


# --- port + lifecycle --------------------------------------------------------------


class TestReserveSettleLifecycle:
    def test_satisfies_port_protocol(self, usage: InMemoryUsageAccounting) -> None:
        port: UsageAccountingPort = usage
        assert isinstance(port, InMemoryUsageAccounting)

    def test_reserve_creates_reserved_entry(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        entry = usage.reserve(TENANT_A, execution_id, 10.0)
        assert entry.status is UsageLedgerStatus.RESERVED
        assert entry.units_reserved == 10.0
        assert entry.units_settled == 0
        assert entry.tenant_id == TENANT_A
        assert entry.execution_id == execution_id
        assert usage.get(execution_id) == entry

    def test_settle_finalizes_from_actual_usage(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        settled = usage.settle(
            execution_id, 7.5, modality_costs={"text_tokens": 1500}
        )
        assert settled.status is UsageLedgerStatus.SETTLED
        assert settled.units_settled == 7.5
        assert settled.modality_costs == {"text_tokens": 1500}
        # Budget reflects actual, not reserved: 100 - 7.5
        assert usage.summary(TENANT_A).task_units.used == 7.5

    def test_refund_releases_full_hold(self, usage: InMemoryUsageAccounting) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        refunded = usage.refund(execution_id)
        assert refunded.status is UsageLedgerStatus.REFUNDED
        assert refunded.units_settled == 0
        assert usage.summary(TENANT_A).task_units.used == 0

    def test_fail_records_failed_settlement(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        failed = usage.fail(execution_id, 2.0)
        assert failed.status is UsageLedgerStatus.FAILED
        assert failed.units_settled == 2.0
        # Failed-settlement units are still consumption (never lost).
        assert usage.summary(TENANT_A).task_units.used == 2.0

    def test_fail_defaults_to_zero_units(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        assert usage.fail(execution_id).units_settled == 0
        assert usage.summary(TENANT_A).task_units.used == 0

    def test_settled_overage_charged_honestly(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        """Actual > reserved is charged, never clamped (ports module rule)."""
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 5.0)
        settled = usage.settle(execution_id, 8.0)
        assert settled.units_settled == 8.0
        assert usage.summary(TENANT_A).task_units.used == 8.0


class TestExactlyOnceResolution:
    def test_double_settle_raises(self, usage: InMemoryUsageAccounting) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        usage.settle(execution_id, 10.0)
        with pytest.raises(ReservationAlreadyResolved):
            usage.settle(execution_id, 10.0)

    def test_refund_after_settle_raises(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        usage.settle(execution_id, 10.0)
        with pytest.raises(ReservationAlreadyResolved):
            usage.refund(execution_id)

    def test_duplicate_reserve_for_same_execution_raises(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        with pytest.raises(ReservationAlreadyResolved):
            usage.reserve(TENANT_A, execution_id, 10.0)

    def test_resolving_unknown_reservation_raises(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        with pytest.raises(ReservationNotFound):
            usage.settle(uuid4(), 1.0)
        with pytest.raises(ReservationNotFound):
            usage.get(uuid4())

    def test_double_settle_does_not_double_charge(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 10.0)
        usage.settle(execution_id, 10.0)
        with pytest.raises(ReservationAlreadyResolved):
            usage.settle(execution_id, 10.0)
        assert usage.summary(TENANT_A).task_units.used == 10.0


# --- entitlement enforcement (deny-by-default; 21 §5; 10 §9) -----------------------


class TestBudgetEnforcement:
    def test_unconfigured_tenant_denied(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        """Deny-by-default: no plan configured -> no implicit allowance."""
        with pytest.raises(EntitlementNotConfigured):
            usage.reserve(TENANT_B, uuid4(), 1.0)
        with pytest.raises(EntitlementNotConfigured):
            usage.summary(TENANT_B)

    def test_reservation_beyond_remaining_denied(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        with pytest.raises(BudgetExceeded) as exc:
            usage.reserve(TENANT_A, uuid4(), 100.1)
        assert exc.value.requested == 100.1
        assert exc.value.remaining == 100.0

    def test_active_holds_count_against_budget(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        """Parallel reservations cannot jointly overdraw the limit."""
        usage.reserve(TENANT_A, uuid4(), 60.0)
        with pytest.raises(BudgetExceeded):
            usage.reserve(TENANT_A, uuid4(), 60.0)

    def test_refund_restores_budget(self, usage: InMemoryUsageAccounting) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 60.0)
        usage.refund(execution_id)
        # Full budget back: a 100-unit reservation now fits.
        usage.reserve(TENANT_A, uuid4(), 100.0)

    def test_exact_remaining_is_allowed(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        usage.reserve(TENANT_A, uuid4(), 100.0)  # exactly the limit

    def test_errors_are_usage_errors(self) -> None:
        assert issubclass(BudgetExceeded, UsageError)
        assert issubclass(EntitlementNotConfigured, UsageError)
        assert issubclass(ReservationNotFound, UsageError)
        assert issubclass(ReservationAlreadyResolved, UsageError)

    def test_negative_reserve_rejected(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        with pytest.raises(ValueError):
            usage.reserve(TENANT_A, uuid4(), -1.0)

    def test_negative_settle_rejected(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 5.0)
        with pytest.raises(ValueError):
            usage.settle(execution_id, -1.0)


# --- tenant isolation + summary (10 §8) --------------------------------------------


class TestSummaryAndIsolation:
    def test_summary_reports_plan_and_budget(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        usage.configure_tenant(
            TENANT_B,
            plan="free",
            task_units_limit=10.0,
            modality_limits={"image_generations": 5},
        )
        s = usage.summary(TENANT_B)
        assert s.plan == "free"
        assert s.task_units == TaskUnitBudget(limit=10.0, used=0.0, remaining=10.0)
        assert s.modality_limits == {"image_generations": 5}

    def test_tenants_do_not_share_budgets(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        usage.configure_tenant(TENANT_B, plan="free", task_units_limit=10.0)
        usage.reserve(TENANT_A, uuid4(), 90.0)
        # Tenant B unaffected by tenant A's consumption.
        assert usage.summary(TENANT_B).task_units.remaining == 10.0

    def test_remaining_floors_at_zero_on_overage(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 100.0)
        usage.settle(execution_id, 120.0)  # honest overage
        s = usage.summary(TENANT_A)
        assert s.task_units.used == 120.0
        assert s.task_units.remaining == 0.0  # never negative in the view

    def test_plan_change_keeps_history(
        self, usage: InMemoryUsageAccounting
    ) -> None:
        execution_id = uuid4()
        usage.reserve(TENANT_A, execution_id, 40.0)
        usage.settle(execution_id, 40.0)
        usage.configure_tenant(TENANT_A, plan="enterprise", task_units_limit=1000.0)
        s = usage.summary(TENANT_A)
        assert s.plan == "enterprise"
        assert s.task_units.used == 40.0
        assert s.task_units.remaining == 960.0

    def test_negative_limit_rejected(self, usage: InMemoryUsageAccounting) -> None:
        with pytest.raises(ValueError):
            usage.configure_tenant(TENANT_B, plan="bad", task_units_limit=-1.0)
