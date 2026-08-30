"""PostgreSQL audit-log repository — AuditLogPort binding.

Binds :class:`core.audit.ports.AuditLogPort` (20 §9, 41 §42) against the
``audit_events`` table (migration 0013).

Design decisions (recorded):

- 21 §8 ADMIN-CHANGE INTEGRITY is validated at append time with the SAME
  rule (and the SAME core error) as the in-memory binding — the frozenset
  lives ONLY in core/contracts/audit.py; this binding consumes it (fix
  once, benefit everywhere). Validation happens BEFORE any I/O.
- APPEND-ONLY posture: the repository exposes append + tenant-scoped
  read/count ONLY — no update/delete/truncate method exists (port
  contract; tamper resistance by construction, mirroring the port
  docstring). The schema likewise carries no updated_at.
- AdminChangeRecord round-trips as JSONB via the contract's own
  model_dump/model_validate — no hand-rolled field mapping to drift.
- Read order: chronological ``occurred_at`` with ``id`` tiebreak —
  deterministic review order; the in-memory binding's "insertion order
  for equal timestamps" is process state PostgreSQL does not have; the
  durable deterministic equivalent (recorded) is the id tiebreak.
- ``limit`` keeps the NEWEST N and returns them chronologically (port
  contract) — implemented as desc-limit then reverse.
- 20 §6: reads filter strictly on tenant_id; no cross-tenant or global
  read operation exists.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit.errors import InvalidAuditEvent
from core.contracts.audit import (
    ADMIN_CHANGE_EVENT_TYPES,
    AdminChangeRecord,
    AuditEvent,
    AuditEventType,
)
from infrastructure.db.tables import audit_events


def _row_to_event(row: Any) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        event_type=row.event_type,
        actor_id=row.actor_id,
        occurred_at=row.occurred_at,
        details=row.details,
        admin_change=(
            AdminChangeRecord.model_validate(row.admin_change)
            if row.admin_change is not None
            else None
        ),
    )


class PostgresAuditLogRepository:
    """Durable, append-only AuditLogPort binding over asyncpg sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def append(self, event: AuditEvent) -> AuditEvent:
        # 21 §8 integrity rule — identical to core/audit/memory.py, BEFORE I/O.
        is_admin = event.event_type in ADMIN_CHANGE_EVENT_TYPES
        if is_admin and event.admin_change is None:
            raise InvalidAuditEvent(
                f"{event.event_type} requires an AdminChangeRecord (21 §8)"
            )
        if not is_admin and event.admin_change is not None:
            raise InvalidAuditEvent(
                f"{event.event_type} must not carry an AdminChangeRecord"
            )
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    audit_events.insert().values(
                        id=event.id,
                        tenant_id=event.tenant_id,
                        event_type=event.event_type.value,
                        actor_id=event.actor_id,
                        occurred_at=event.occurred_at,
                        details=event.details,
                        admin_change=(
                            event.admin_change.model_dump()
                            if event.admin_change is not None
                            else None
                        ),
                    )
                )
        return event

    async def read(
        self,
        tenant_id: UUID,
        event_type: AuditEventType | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        stmt = select(audit_events).where(audit_events.c.tenant_id == tenant_id)
        if event_type is not None:
            stmt = stmt.where(audit_events.c.event_type == event_type.value)
        async with self._sessions() as session:
            if limit is not None:
                # Newest N, returned chronologically (port contract).
                newest = (
                    await session.execute(
                        stmt.order_by(
                            audit_events.c.occurred_at.desc(),
                            audit_events.c.id.desc(),
                        ).limit(limit)
                    )
                ).all()
                return tuple(_row_to_event(row) for row in reversed(newest))
            rows = (
                await session.execute(
                    stmt.order_by(audit_events.c.occurred_at, audit_events.c.id)
                )
            ).all()
        return tuple(_row_to_event(row) for row in rows)

    async def count(self, tenant_id: UUID) -> int:
        async with self._sessions() as session:
            result = await session.execute(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.tenant_id == tenant_id)
            )
        return int(result.scalar_one())
