"""In-memory execution record store for the MVP API slice (T-IMPL-023).

Scope decision (recorded in PROJECT_EXECUTION_STATE.md): the durable
persistence binding for Execution records is an infrastructure concern
already covered by ports/ADR-0002; this slice needs only enough state to
serve GET /v1/executions/{id} for executions created by THIS process.
The store is deliberately tiny and dependency-free so the composition
root can swap in a repository-backed implementation without touching
route handlers.

Tenant isolation (T-IMPL-033 hardening fix, 20 §6): every read is
tenant-scoped. A lookup for an execution owned by ANOTHER tenant raises
the SAME :class:`ExecutionNotFound` as a truly absent id — foreign
existence must not leak (anti-enumeration: 404/NotFound, never 403).
The tenant key comes from the stored ``Execution.tenant_id`` fact itself,
never from caller-supplied storage-time parameters.

Phase AA-1 (seam EXE-1): ``list`` — the tenant-scoped, filterable list
read the executions surface needs. Structural tenant scoping: foreign
rows are simply absent from the result (never an error to enumerate,
20 §6). Newest-first order; ``limit`` keeps the newest N. The method is
apps-level protocol growth per the T-IMPL-072 injectable pattern — a
repository-backed binding implements the same shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from core.contracts.execute import ExecutionStatus
from core.execution.service import ExecutionReport


class ExecutionStorePort(Protocol):
    """Structural surface every ExecutionStore binding satisfies (P-A.1).

    Exactly the shape ``InMemoryExecutionStore`` has always exposed —
    extracted as a Protocol so the composition root can swap in the
    repository-backed ``DurableExecutionStore`` WITHOUT touching route
    handlers or the worker (the swap this module's docstring promised).
    ``InMemoryExecutionStore`` itself is unchanged and satisfies this
    structurally (P2 — widen the annotation, never rewrite call sites).
    """

    def put(self, report: ExecutionReport) -> None: ...

    def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionReport: ...

    def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[ExecutionReport, ...]: ...


class ExecutionNotFound(KeyError):
    """No execution record exists for the requested id IN THIS TENANT.

    Deliberately identical for "absent" and "exists in a foreign tenant"
    (20 §6 anti-enumeration): existence must not leak across tenants.
    """

    def __init__(self, execution_id: UUID) -> None:
        super().__init__(str(execution_id))
        self.execution_id = execution_id


class InMemoryExecutionStore:
    """Process-local execution report store (03 §5 records, keyed by id).

    Reads REQUIRE the caller's tenant id; cross-tenant reads are
    indistinguishable from missing records (20 §6).
    """

    def __init__(self) -> None:
        self._reports: dict[UUID, ExecutionReport] = {}

    def put(self, report: ExecutionReport) -> None:
        self._reports[report.execution.id] = report

    def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionReport:
        report = self._reports.get(execution_id)
        if report is None or report.execution.tenant_id != tenant_id:
            raise ExecutionNotFound(execution_id)
        return report

    def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[ExecutionReport, ...]:
        """Tenant-scoped, filterable list (AA-1 seam EXE-1), newest-first.

        Foreign-tenant rows are structurally ABSENT (20 §6) — an empty
        result is honest for "no rows" and "all rows foreign" alike.
        ``limit`` keeps the newest N of the filtered result.
        """
        rows = [
            report
            for report in self._reports.values()
            if report.execution.tenant_id == tenant_id
            and (status is None or report.execution.status is status)
            and (initiated_by is None or report.execution.user_id == initiated_by)
            and (created_after is None or report.execution.created_at > created_after)
            and (created_before is None or report.execution.created_at < created_before)
        ]
        rows.sort(key=lambda r: r.execution.created_at, reverse=True)
        if limit is not None:
            rows = rows[:limit]
        return tuple(rows)

    def __len__(self) -> int:
        return len(self._reports)
