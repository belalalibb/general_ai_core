"""In-memory execution record store for the MVP API slice (T-IMPL-023).

Scope decision (recorded in PROJECT_EXECUTION_STATE.md): the durable
persistence binding for Execution records is an infrastructure concern
already covered by ports/ADR-0002; this slice needs only enough state to
serve GET /v1/executions/{id} for executions created by THIS process.
The store is deliberately tiny and dependency-free so the composition
root can swap in a repository-backed implementation without touching
route handlers.
"""

from __future__ import annotations

from uuid import UUID

from core.execution.service import ExecutionReport


class ExecutionNotFound(KeyError):
    """No execution record exists for the requested id."""

    def __init__(self, execution_id: UUID) -> None:
        super().__init__(str(execution_id))
        self.execution_id = execution_id


class InMemoryExecutionStore:
    """Process-local execution report store (03 §5 records, keyed by id)."""

    def __init__(self) -> None:
        self._reports: dict[UUID, ExecutionReport] = {}

    def put(self, report: ExecutionReport) -> None:
        self._reports[report.execution.id] = report

    def get(self, execution_id: UUID) -> ExecutionReport:
        try:
            return self._reports[execution_id]
        except KeyError:
            raise ExecutionNotFound(execution_id) from None

    def __len__(self) -> int:
        return len(self._reports)
