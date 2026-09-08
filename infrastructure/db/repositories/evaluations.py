"""PostgreSQL evaluation repository — rows of the EXISTING ``evaluations``
table (migration 0010) behind the ``EvaluationStorePort`` shape (R177-FIX-11).

Design decisions (recorded at the binding):

- NO NEW SCHEMA: the ``evaluations`` table shipped with migration 0010 and
  already carries every 03 §7 field the contract holds (id / tenant_id /
  execution_id / level / score / confidence / evidence_ref / graders). The
  planned ``0019`` migration is SUPERSEDED by reusing that table — a second
  evaluation table would duplicate schema authority (nothing invented).
- APPEND-ONLY (22 §6 / 22 §12 "evidence integrity", 21 §4 unbreakable):
  ``record`` is a plain INSERT — a primary-key collision surfaces as the
  named :class:`DuplicateEvaluation`; there is deliberately NO upsert, NO
  update and NO delete path in this module.
- ROWS NEVER CARRY TRUST: reconstruction goes through
  ``EvaluationRecord.model_validate`` so every stored row is re-checked
  against the contract (closed ``level`` set, [0,1] bounds, RAW-carries-no-
  judgment, above-RAW-needs-graders). A row that violates the contract
  raises instead of producing an object that lies.
- TENANT ISOLATION IS STRUCTURAL (20 §6): every read filters ``tenant_id``
  in SQL; absent and foreign answer the identical :class:`EvaluationNotFound`,
  and ``list_for_execution`` returns an EMPTY tuple for an unknown or
  foreign execution — byte-identical to the in-memory binding.
- ORDERING (honest limitation, recorded): the 0010 schema has no
  recording-sequence column, so ``list_for_execution`` orders by ``id`` —
  a stable, deterministic order that is NOT insertion order. The port
  docstring's "recording order" is therefore satisfied only by the
  in-memory binding today; adding a sequence column is a future migration
  (would be ``0019``) and is NOT done here to stay within the FIX-11 scope
  (durability of the artefact, not ordering semantics).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.evaluation import EvaluationRecord
from core.evaluation.errors import DuplicateEvaluation, EvaluationNotFound
from infrastructure.db.tables import evaluations

__all__ = ["PostgresEvaluationRepository"]


def _record_values(record: EvaluationRecord) -> dict[str, Any]:
    """Contract → row values; key set == ``evaluations`` table columns."""
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "execution_id": record.execution_id,
        "level": record.level.value,
        "score": record.score,
        "confidence": record.confidence,
        "evidence_ref": record.evidence_ref,
        "graders": [grader.model_dump(mode="json", exclude_none=True) for grader in record.graders],
    }


def _row_to_record(row: Any) -> EvaluationRecord:
    """Row → contract THROUGH validation (never around it)."""
    return EvaluationRecord.model_validate(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "execution_id": row.execution_id,
            "level": row.level,
            "score": row.score,
            "confidence": row.confidence,
            "evidence_ref": row.evidence_ref,
            "graders": tuple(row.graders or ()),
        }
    )


class PostgresEvaluationRepository:
    """Append-only evaluation persistence over asyncpg sessions.

    The session FACTORY is injected (never constructed here) — engine,
    credentials and pooling belong to the composition root, mirroring
    every other repository binding.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def record(self, evaluation: EvaluationRecord) -> None:
        """INSERT one record; a duplicate id is refused loudly, never rewritten."""
        stmt = evaluations.insert().values(_record_values(evaluation))
        async with self._sessions() as session:
            try:
                async with session.begin():
                    await session.execute(stmt)
            except IntegrityError as exc:
                if "evaluations_pkey" in str(exc.orig):
                    raise DuplicateEvaluation(evaluation.id) from exc
                raise

    async def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        """Tenant-scoped read; foreign == absent (20 §6)."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(evaluations).where(
                        evaluations.c.tenant_id == tenant_id,
                        evaluations.c.id == evaluation_id,
                    )
                )
            ).one_or_none()
        if row is None:
            raise EvaluationNotFound(evaluation_id)
        return _row_to_record(row)

    async def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        """All records of one execution within the tenant (see ORDERING note)."""
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(evaluations)
                    .where(
                        evaluations.c.tenant_id == tenant_id,
                        evaluations.c.execution_id == execution_id,
                    )
                    .order_by(evaluations.c.id)
                )
            ).all()
        return tuple(_row_to_record(row) for row in rows)
