"""Evaluation store seam (MVP Phase 7 slice 1, 41 §46).

Port authority:

- docs/ai_orchestration_pack/final_docs_v3/22_EVALUATION_AND_LEARNING.md
  §6 (evaluation record), §7 (user visibility — admin reads scores).
- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §8
  ("Evaluation belongs to Execution/Node").

Same skeleton discipline as MemoryStorePort / UsageAccountingPort: the
Protocol is the seam, the in-memory binding satisfies it hermetically,
and durable persistence arrives later behind the SAME port.

Append-only posture (recorded): evaluation records are EVIDENCE — the
port has record/get/list and deliberately NO update/delete surface.
Re-grading an execution appends a NEW record; history is never rewritten
(22 §12 / 21 §4 "evidence integrity" as an unbreakable invariant).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.contracts.evaluation import EvaluationRecord


class EvaluationStorePort(Protocol):
    """Tenant-scoped, append-only evaluation record seam (22 §6)."""

    def record(self, evaluation: EvaluationRecord) -> EvaluationRecord:
        """Append an evaluation record.

        Raises ``DuplicateEvaluation`` when the id is already recorded —
        records are evidence and are never overwritten.
        """
        ...

    def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        """Fetch by id; raises ``EvaluationNotFound`` (also cross-tenant)."""
        ...

    def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        """All evaluations of one execution, in recording order.

        03 §8: Evaluation belongs to Execution — an execution may
        accumulate multiple records (e.g. re-grading appends). An unknown
        or foreign-tenant execution yields an EMPTY tuple, not an error:
        "no evaluations" and "not your execution" are indistinguishable
        (20 §6 anti-enumeration).
        """
        ...
