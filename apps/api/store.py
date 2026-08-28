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
"""

from __future__ import annotations

from uuid import UUID

from core.execution.service import ExecutionReport


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

    def __len__(self) -> int:
        return len(self._reports)
