"""In-memory evaluation store (MVP Phase 7 binding, 41 §46).

Satisfies :class:`~core.evaluation.ports.EvaluationStorePort` against
process memory — the same skeleton discipline as ``InMemoryObjectStorage``
/ the Phase 6 stores: durable persistence arrives later behind the same
port.

Isolation mechanics (20 §6): physical keying by ``(tenant_id, id)``; a
foreign tenant's record can never be addressed, and probing it raises the
same NotFound as a truly absent record. ``list_for_execution`` returns an
empty tuple for foreign executions — indistinguishable from "never
evaluated".

Append-only (recorded on the port): no update/delete surface exists;
duplicate ids are rejected loudly, never overwritten.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.evaluation import EvaluationRecord
from core.evaluation.errors import DuplicateEvaluation, EvaluationNotFound


class InMemoryEvaluationStore:
    """Hermetic, tenant-scoped, append-only evaluation record store."""

    def __init__(self) -> None:
        self._records: dict[tuple[UUID, UUID], EvaluationRecord] = {}
        # Insertion order per (tenant, execution) — recording order is
        # part of the port contract for list_for_execution.
        self._by_execution: dict[tuple[UUID, UUID], list[UUID]] = {}

    def record(self, evaluation: EvaluationRecord) -> EvaluationRecord:
        key = (evaluation.tenant_id, evaluation.id)
        if key in self._records:
            raise DuplicateEvaluation(evaluation.id)
        self._records[key] = evaluation
        exec_key = (evaluation.tenant_id, evaluation.execution_id)
        self._by_execution.setdefault(exec_key, []).append(evaluation.id)
        return evaluation

    def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        try:
            return self._records[(tenant_id, evaluation_id)]
        except KeyError:
            raise EvaluationNotFound(evaluation_id) from None

    def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        ids = self._by_execution.get((tenant_id, execution_id), [])
        return tuple(self._records[(tenant_id, rid)] for rid in ids)
