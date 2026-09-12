"""R179 rulings Q1 (DEC-B / F-R179-04) — durable audit + usage bindings.

Same posture as tests/composition/test_durable_memory_r179.py (4.5): FAKE async
repositories drive the adapters over a REAL AsyncBridge; port parity is checked
structurally; the runtime binds the durable stores ONLY in the ``DATABASE_URL``
branch and keeps the in-memory classes otherwise.

USAGE is bound behind the SAME adapter shape, but its live behaviour is a
MEASUREMENT (tests_live/r179): ``usage_ledger.execution_id`` is a NOT NULL FK to
``executions.id`` while ``ExecutionService`` reserves BEFORE the execution row
exists and ``core/tools/executor.py`` reserves under a call id that never has a
row. The hermetic tests here only prove the adapter forwards verbatim and that
repository refusals cross the bridge unchanged — they do not claim the live
path works (see F-R179-06 once measured).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.composition.audit_usage import (
    DurableAuditLog,
    DurableUsageAccounting,
    build_durable_audit_usage,
)
from apps.composition.bridge import AsyncBridge
from core.audit.errors import InvalidAuditEvent
from core.audit.memory import InMemoryAuditLog
from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject
from core.contracts.usage import TaskUnitBudget, UsageLedger, UsageLedgerStatus, UsageSummary
from core.usage.errors import EntitlementNotConfigured, ReservationNotFound
from core.usage.memory import InMemoryUsageAccounting
from core.usage.ports import UsageAccountingPort

RUNTIME_PY = Path(__file__).resolve().parents[2] / "apps" / "composition" / "runtime.py"
TENANT = uuid4()
OTHER = uuid4()


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def append(self, event: AuditEvent) -> AuditEvent:
        if event.event_type is AuditEventType.LOGIN and event.admin_change is not None:
            raise InvalidAuditEvent("login must not carry an AdminChangeRecord")
        self.events.append(event)
        return event

    async def read(
        self, tenant_id: UUID, event_type: AuditEventType | None = None, limit: int | None = None
    ) -> tuple[AuditEvent, ...]:
        rows = [
            e
            for e in self.events
            if e.tenant_id == tenant_id and (event_type is None or e.event_type is event_type)
        ]
        if limit is not None:
            rows = rows[-limit:]
        return tuple(rows)

    async def count(self, tenant_id: UUID) -> int:
        return sum(1 for e in self.events if e.tenant_id == tenant_id)


class FakeUsageRepository:
    def __init__(self) -> None:
        self.ledgers: dict[UUID, UsageLedger] = {}
        self.plans: dict[UUID, tuple[str, float]] = {}
        self.calls: list[tuple[Any, ...]] = []

    async def configure_tenant(
        self, tenant_id: UUID, *, plan: str, task_units_limit: float, modality_limits: Any = None
    ) -> None:
        self.calls.append(("configure_tenant", tenant_id, plan, task_units_limit, modality_limits))
        self.plans[tenant_id] = (plan, task_units_limit)

    async def reserve(self, tenant_id: UUID, execution_id: UUID, units: float) -> UsageLedger:
        if tenant_id not in self.plans:
            raise EntitlementNotConfigured(tenant_id)
        ledger = UsageLedger(
            id=uuid4(),
            tenant_id=tenant_id,
            execution_id=execution_id,
            units_reserved=units,
            status=UsageLedgerStatus.RESERVED,
        )
        self.ledgers[execution_id] = ledger
        return ledger

    async def settle(
        self, execution_id: UUID, units_settled: float, *, modality_costs: JsonObject | None = None
    ) -> UsageLedger:
        self.calls.append(("settle", execution_id, units_settled, modality_costs))
        ledger = self.ledgers[execution_id].model_copy(
            update={"units_settled": units_settled, "status": UsageLedgerStatus.SETTLED}
        )
        self.ledgers[execution_id] = ledger
        return ledger

    async def refund(self, execution_id: UUID) -> UsageLedger:
        ledger = self.ledgers[execution_id].model_copy(
            update={"status": UsageLedgerStatus.REFUNDED}
        )
        self.ledgers[execution_id] = ledger
        return ledger

    async def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        self.calls.append(("fail", execution_id, units_settled, modality_costs))
        ledger = self.ledgers[execution_id].model_copy(
            update={"units_settled": units_settled, "status": UsageLedgerStatus.FAILED}
        )
        self.ledgers[execution_id] = ledger
        return ledger

    async def get(self, execution_id: UUID) -> UsageLedger:
        if execution_id not in self.ledgers:
            raise ReservationNotFound(execution_id)
        return self.ledgers[execution_id]

    async def summary(self, tenant_id: UUID) -> UsageSummary:
        if tenant_id not in self.plans:
            raise EntitlementNotConfigured(tenant_id)
        plan, limit = self.plans[tenant_id]
        used = sum(
            (lg.units_reserved if lg.status is UsageLedgerStatus.RESERVED else lg.units_settled)
            for lg in self.ledgers.values()
            if lg.tenant_id == tenant_id
        )
        return UsageSummary(
            plan=plan, task_units=TaskUnitBudget(limit=limit, used=used, remaining=limit - used)
        )


@pytest.fixture
def bridge() -> Iterator[AsyncBridge]:
    b = AsyncBridge()
    try:
        yield b
    finally:
        b.close()


def _event(tenant: UUID = TENANT, kind: AuditEventType = AuditEventType.LOGIN) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        tenant_id=tenant,
        event_type=kind,
        actor_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


class TestDurableAuditLog:
    def test_append_read_count_round_trip_tenant_scoped(self, bridge: AsyncBridge) -> None:
        repo = FakeAuditRepository()
        log = DurableAuditLog(repository=repo, bridge=bridge)  # type: ignore[arg-type]
        e1 = log.append(_event())
        e2 = log.append(_event())
        log.append(_event(OTHER))
        assert log.read(TENANT) == (e1, e2)
        assert log.read(TENANT, limit=1) == (e2,)
        assert log.read(TENANT, event_type=AuditEventType.LOGIN) == (e1, e2)
        assert log.count(TENANT) == 2 and log.count(OTHER) == 1

    def test_named_refusal_crosses_unchanged(self, bridge: AsyncBridge) -> None:
        from core.contracts.audit import AdminChangeRecord

        log = DurableAuditLog(repository=FakeAuditRepository(), bridge=bridge)  # type: ignore[arg-type]
        bad = _event().model_copy(
            update={
                "admin_change": AdminChangeRecord.model_construct(
                    change_id=uuid4(), area="models", action="enable_model", before={}, after={}
                )
            }
        )
        with pytest.raises(InvalidAuditEvent):
            log.append(bad)


class TestDurableUsageAccounting:
    def test_forwards_every_port_method_and_configure_tenant(self, bridge: AsyncBridge) -> None:
        repo = FakeUsageRepository()
        usage = DurableUsageAccounting(repository=repo, bridge=bridge)  # type: ignore[arg-type]
        usage.configure_tenant(TENANT, plan="local-default", task_units_limit=100.0)
        execution = uuid4()
        reserved = usage.reserve(TENANT, execution, 5.0)
        assert reserved.status is UsageLedgerStatus.RESERVED
        assert usage.summary(TENANT).task_units.used == 5.0
        settled = usage.settle(execution, 2.0, modality_costs={"text": 2})
        assert settled.status is UsageLedgerStatus.SETTLED
        assert usage.get(execution) == settled
        assert usage.summary(TENANT).task_units.used == 2.0
        other = uuid4()
        usage.reserve(TENANT, other, 1.0)
        assert usage.fail(other, 0.5).status is UsageLedgerStatus.FAILED
        third = uuid4()
        usage.reserve(TENANT, third, 1.0)
        assert usage.refund(third).status is UsageLedgerStatus.REFUNDED
        assert ("settle", execution, 2.0, {"text": 2}) in repo.calls

    def test_refusals_cross_unchanged(self, bridge: AsyncBridge) -> None:
        usage = DurableUsageAccounting(repository=FakeUsageRepository(), bridge=bridge)  # type: ignore[arg-type]
        with pytest.raises(EntitlementNotConfigured):
            usage.reserve(OTHER, uuid4(), 1.0)
        with pytest.raises(ReservationNotFound):
            usage.get(uuid4())


class TestPortParityAndBuilder:
    def test_both_bindings_satisfy_the_ports(self, bridge: AsyncBridge) -> None:
        durable_audit: AuditLogPort = DurableAuditLog(
            repository=FakeAuditRepository(), bridge=bridge
        )  # type: ignore[arg-type]
        durable_usage: UsageAccountingPort = DurableUsageAccounting(
            repository=FakeUsageRepository(),
            bridge=bridge,  # type: ignore[arg-type]
        )
        for port, impls in (
            (AuditLogPort, (durable_audit, InMemoryAuditLog())),
            (UsageAccountingPort, (durable_usage, InMemoryUsageAccounting())),
        ):
            for name in (n for n in vars(port) if not n.startswith("_")):
                for impl in impls:
                    assert callable(getattr(impl, name)), (type(impl).__name__, name)
        # The admin plan seam (UsageConfigurationPort) is served by BOTH usage bindings.
        assert callable(durable_usage.configure_tenant)  # type: ignore[attr-defined]

    def test_builder_wires_bindings_over_the_shared_bridge(self, bridge: AsyncBridge) -> None:
        class Bindings:
            audit = FakeAuditRepository()
            usage = FakeUsageRepository()

        audit, usage = build_durable_audit_usage(Bindings(), bridge)  # type: ignore[arg-type]
        assert audit.repository is Bindings.audit and usage.repository is Bindings.usage
        assert audit.bridge is bridge and usage.bridge is bridge


class TestRuntimeBinding:
    def test_runtime_binds_durable_audit_and_usage_only_in_the_database_branch(self) -> None:
        source = RUNTIME_PY.read_text(encoding="utf-8")
        assert (
            "from apps.composition.audit_usage import UsageBinding, build_durable_audit_usage"
            in (source)
        )
        # The binding is born inside the FIRST `if settings is not None:` block
        # (the durable connections are built before the execution service that
        # consumes usage), and the in-memory classes are the ONLY else-branch.
        bind_at = source.index("audit, usage = build_durable_audit_usage(bindings, bridge)")
        durable_branch = source.index("if settings is not None:\n        bridge = AsyncBridge()")
        else_branch = source.index(
            "    else:\n        # In-memory profile: process-local audit + usage, unchanged."
        )
        assert durable_branch < bind_at < else_branch
        # Exactly one place constructs each in-memory class (no second path).
        assert source.count("InMemoryUsageAccounting()") == 1
        assert source.count("InMemoryAuditLog()") == 1

    def test_frozen_agent_tool_surface_uses_only_summary_on_usage(self) -> None:
        """F-R179-07: apps/admin_agent/tools.py (frozen) annotates the concrete
        InMemoryUsageAccounting but only ever calls ``.summary`` — both bindings
        satisfy that structurally; the annotation waits for the Q5 thaw."""
        import re

        source = (RUNTIME_PY.parent.parent / "admin_agent" / "tools.py").read_text(encoding="utf-8")
        uses = set(re.findall(r"surface\.usage\.(\w+)", source))
        assert uses == {"summary"}, uses

    def test_in_memory_profile_is_unchanged(self) -> None:
        from apps.composition.runtime import build_runtime_profile

        profile = build_runtime_profile(environ={})
        assert profile.durable is False and profile.bindings is None
        assert isinstance(profile.usage, InMemoryUsageAccounting)
