"""Durable audit + usage bindings — R179 rulings Q1 (DEC-B / F-R179-04).

Measured (4.4, ``evidence/r179/durability_measured.json``): the audit total
and the usage ``used`` counter reset with the process because the runtime
composed ``InMemoryAuditLog`` / ``InMemoryUsageAccounting`` in BOTH profiles
although ``DatabaseBindings.audit`` / ``.usage`` (migration 0002 tables)
have existed since V1. Operator ruling Q1: bind them with the SAME seam
pattern 4.5 proved for memory/conversations.

- **Loop affinity**: every call crosses the AsyncBridge (``bridge.run``);
  the ports are synchronous and are called from the request path, the
  execution service and the tool executor exactly as the in-memory
  bindings are.
- **No translation**: both repositories raise the core-owned refusals
  (``InvalidAuditEvent``; ``EntitlementNotConfigured``, ``BudgetExceeded``,
  ``ReservationNotFound``, ``ReservationAlreadyResolved``) which cross the
  bridge unchanged, so route mappings stay as they are.
- **Admin plan seam**: ``configure_tenant`` (the ``UsageConfigurationPort``
  the admin service and ``BudgetGrantingIdentity`` publish through) is
  forwarded too — plan budgets become durable rows (``plans``/``tenants``).
- **Honest scope**: the usage ledger's ``execution_id`` is a NOT NULL FK to
  ``executions.id``; whether the shipped write ORDER satisfies it is a
  live MEASUREMENT (tests_live/r179), never assumed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject
from core.contracts.usage import UsageLedger, UsageSummary
from infrastructure.db.repositories.audit import PostgresAuditLogRepository
from infrastructure.db.repositories.usage import PostgresUsageRepository

__all__ = [
    "DurableAuditLog",
    "DurableUsageAccounting",
    "UsageBinding",
    "build_durable_audit_usage",
]


class UsageBinding(Protocol):
    """What the runtime needs from a usage binding: the accounting port AND the
    admin plan seam (``configure_tenant``) — satisfied by BOTH
    ``InMemoryUsageAccounting`` and ``DurableUsageAccounting``."""

    def configure_tenant(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        task_units_limit: float,
        modality_limits: JsonObject | None = None,
    ) -> None: ...

    def reserve(self, tenant_id: UUID, execution_id: UUID, units: float) -> UsageLedger: ...

    def settle(
        self,
        execution_id: UUID,
        units_settled: float,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger: ...

    def refund(self, execution_id: UUID) -> UsageLedger: ...

    def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger: ...

    def get(self, execution_id: UUID) -> UsageLedger: ...

    def summary(self, tenant_id: UUID) -> UsageSummary: ...


@dataclass(frozen=True)
class DurableAuditLog:
    """AuditLogPort over the EXISTING Postgres repository (bridged)."""

    repository: PostgresAuditLogRepository
    bridge: AsyncBridge

    def append(self, event: AuditEvent) -> AuditEvent:
        return self.bridge.run(self.repository.append(event))

    def read(
        self,
        tenant_id: UUID,
        event_type: AuditEventType | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        return self.bridge.run(self.repository.read(tenant_id, event_type=event_type, limit=limit))

    def count(self, tenant_id: UUID) -> int:
        return self.bridge.run(self.repository.count(tenant_id))


@dataclass(frozen=True)
class DurableUsageAccounting:
    """UsageAccountingPort + UsageConfigurationPort over the EXISTING repository."""

    repository: PostgresUsageRepository
    bridge: AsyncBridge

    def configure_tenant(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        task_units_limit: float,
        modality_limits: JsonObject | None = None,
    ) -> None:
        self.bridge.run(
            self.repository.configure_tenant(
                tenant_id,
                plan=plan,
                task_units_limit=task_units_limit,
                modality_limits=modality_limits,
            )
        )

    def reserve(self, tenant_id: UUID, execution_id: UUID, units: float) -> UsageLedger:
        return self.bridge.run(self.repository.reserve(tenant_id, execution_id, units))

    def settle(
        self,
        execution_id: UUID,
        units_settled: float,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return self.bridge.run(
            self.repository.settle(execution_id, units_settled, modality_costs=modality_costs)
        )

    def refund(self, execution_id: UUID) -> UsageLedger:
        return self.bridge.run(self.repository.refund(execution_id))

    def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return self.bridge.run(
            self.repository.fail(execution_id, units_settled, modality_costs=modality_costs)
        )

    def get(self, execution_id: UUID) -> UsageLedger:
        return self.bridge.run(self.repository.get(execution_id))

    def summary(self, tenant_id: UUID) -> UsageSummary:
        return self.bridge.run(self.repository.summary(tenant_id))


def build_durable_audit_usage(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> tuple[DurableAuditLog, DurableUsageAccounting]:
    """Adapt the ALREADY-COMPOSED repositories — same builder shape as 4.5."""
    return (
        DurableAuditLog(repository=bindings.audit, bridge=bridge),
        DurableUsageAccounting(repository=bindings.usage, bridge=bridge),
    )
