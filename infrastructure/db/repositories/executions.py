"""PostgreSQL execution repository — Execution/ExecutionNode bindings.

Design decisions (recorded, per the standing derivation rule):

- WHAT IS DURABLE: the 03 §5 domain entities (``Execution`` +
  ``ExecutionNode``) — exactly what the schema maps (tables.py). The
  richer process-level ``ExecutionReport`` (attempt trails, provider
  responses) is deliberately NOT persisted here: attempts/responses are
  explainability data of one process run; the durable truth is the
  entity pair (40 §2.1 tables map contracts, they never redefine truth).
- SURFACE SHAPE mirrors the proven in-memory store protocol
  (apps/api/store.py — put/get/list with the same tenant-scoping and
  filter semantics) so a repository-backed binding can serve the same
  seams; methods are async because the engine is asyncpg (ADR-0001/0002).
- TENANT ISOLATION IS STRUCTURAL (20 §6): ``get`` filters by
  ``tenant_id`` IN SQL — a foreign row is never fetched, and the refusal
  is byte-identical to "absent" (:class:`ExecutionNotFound`); ``list``
  simply omits foreign rows.
- IDEMPOTENCY (10 §10): the ``uq_executions_idempotency_key`` unique
  constraint is the durable authority; its violation surfaces as the
  named :class:`DuplicateIdempotencyKey`, never a bare IntegrityError.
- ``input_ref``/``output_ref`` are ``BoundedStr | JsonObject`` per 03 §5
  "string/json"; a bare JSON string is valid JSONB so ONE column carries
  both shapes (recorded in tables.py) — the round-trip preserves the
  original shape because JSONB returns str for strings, dict for objects.
- UPSERT posture: ``put`` persists a finished record; re-putting the SAME
  execution id updates the row (status transitions written by later
  phases — e.g. async queued→running→terminal — ride the same method).
  Nodes are replaced wholesale on re-put: the entity set is the truth of
  the run, not an append log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.execute import ExecutionStatus
from core.contracts.execution import Execution, ExecutionNode
from infrastructure.db.repositories.errors import (
    DuplicateIdempotencyKey,
    ExecutionNotFound,
)
from infrastructure.db.tables import execution_nodes, executions

_IDEMPOTENCY_CONSTRAINT = "uq_executions_idempotency_key"


@dataclass(frozen=True)
class ExecutionRecord:
    """One durable execution: the root entity plus its node entities."""

    execution: Execution
    nodes: tuple[ExecutionNode, ...]


def _execution_values(execution: Execution) -> dict[str, Any]:
    return {
        "id": execution.id,
        "tenant_id": execution.tenant_id,
        "user_id": execution.user_id,
        "conversation_id": execution.conversation_id,
        "request_hash": execution.request_hash,
        "idempotency_key": execution.idempotency_key,
        "status": execution.status.value,
        "strategy": execution.strategy.value,
        "cost_snapshot": execution.cost_snapshot,
        "created_at": execution.created_at,
        "completed_at": execution.completed_at,
    }


def _node_values(node: ExecutionNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "execution_id": node.execution_id,
        "node_key": node.node_key,
        "type": node.type.value,
        "status": node.status.value,
        "input_ref": node.input_ref,
        "output_ref": node.output_ref,
        "retry_count": node.retry_count,
        "error": node.error,
    }


def _row_to_execution(row: Any) -> Execution:
    return Execution(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        conversation_id=row.conversation_id,
        request_hash=row.request_hash,
        idempotency_key=row.idempotency_key,
        status=row.status,
        strategy=row.strategy,
        cost_snapshot=row.cost_snapshot,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _row_to_node(row: Any) -> ExecutionNode:
    return ExecutionNode(
        id=row.id,
        execution_id=row.execution_id,
        node_key=row.node_key,
        type=row.type,
        status=row.status,
        input_ref=row.input_ref,
        output_ref=row.output_ref,
        retry_count=row.retry_count,
        error=row.error,
    )


class PostgresExecutionRepository:
    """Durable Execution/ExecutionNode persistence over asyncpg sessions.

    The session FACTORY is injected (never constructed here) — engine,
    credentials, and pooling belong to the composition root, mirroring
    the boto3-client-injection posture of the S3 binding.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def put(
        self, execution: Execution, nodes: tuple[ExecutionNode, ...] = ()
    ) -> None:
        """Persist (or update) one execution and its full node set.

        Node entities must belong to the execution (guarded loudly — a
        cross-wired node is a programming error, not tenant input).
        """
        for node in nodes:
            if node.execution_id != execution.id:
                msg = (
                    "node does not belong to this execution: "
                    f"{node.id} -> {node.execution_id} != {execution.id}"
                )
                raise ValueError(msg)
        stmt = pg_insert(executions).values(_execution_values(execution))
        stmt = stmt.on_conflict_do_update(
            index_elements=[executions.c.id],
            set_={
                "status": stmt.excluded.status,
                "cost_snapshot": stmt.excluded.cost_snapshot,
                "completed_at": stmt.excluded.completed_at,
            },
        )
        async with self._sessions() as session:
            try:
                async with session.begin():
                    await session.execute(stmt)
                    await session.execute(
                        delete(execution_nodes).where(
                            execution_nodes.c.execution_id == execution.id
                        )
                    )
                    if nodes:
                        await session.execute(
                            execution_nodes.insert(),
                            [_node_values(node) for node in nodes],
                        )
            except IntegrityError as exc:
                if _IDEMPOTENCY_CONSTRAINT in str(exc.orig):
                    raise DuplicateIdempotencyKey(
                        execution.tenant_id, execution.idempotency_key or ""
                    ) from exc
                raise

    async def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionRecord:
        """Tenant-scoped read; foreign == absent (20 §6)."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(executions).where(
                        executions.c.id == execution_id,
                        executions.c.tenant_id == tenant_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise ExecutionNotFound(execution_id)
            node_rows = (
                await session.execute(
                    select(execution_nodes)
                    .where(execution_nodes.c.execution_id == execution_id)
                    .order_by(execution_nodes.c.node_key)
                )
            ).all()
        return ExecutionRecord(
            execution=_row_to_execution(row),
            nodes=tuple(_row_to_node(r) for r in node_rows),
        )

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[Execution, ...]:
        """Tenant-scoped, filterable list — newest first (EXE-1 semantics).

        Returns root entities only (a list is not a bulk-exfil surface —
        the recorded EXE-1 posture); node detail rides ``get``.
        Filter semantics mirror the in-memory store exactly: strict
        after/before comparisons, ``limit`` keeps the newest N.
        """
        stmt = select(executions).where(executions.c.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(executions.c.status == status.value)
        if initiated_by is not None:
            stmt = stmt.where(executions.c.user_id == initiated_by)
        if created_after is not None:
            stmt = stmt.where(executions.c.created_at > created_after)
        if created_before is not None:
            stmt = stmt.where(executions.c.created_at < created_before)
        stmt = stmt.order_by(executions.c.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_row_to_execution(row) for row in rows)
