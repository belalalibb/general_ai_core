"""PostgreSQL memory repository — MemoryStorePort binding.

Binds :class:`core.memory.ports.MemoryStorePort` (03 §3 MemoryItem;
13 §3/§7/§8) against the ``memory_items`` table (migration 0007).

Design decisions (recorded):

- SECRET SCREENING (13 §7) is reused from the core module — the SAME
  boundary guard the in-memory binding applies (fix once, benefit
  everywhere): a secret-like key/value refuses loudly BEFORE any I/O.
- LOGICAL-KEY UPSERT: the ``uq_memory_items_logical_key`` unique
  constraint (tenant, user, scope, key — NULLS NOT DISTINCT) is the
  durable authority for the (13 §3) logical key; ON CONFLICT preserves
  the ORIGINAL row id, increments ``evidence_count``, and refreshes
  value/source/confidence/last_seen/expires_at/sensitivity — exactly the
  in-memory ``upsert`` semantics, now race-safe in SQL.
- QUERY semantics mirror the in-memory binding verbatim: tenant-shared
  (user_id NULL) always eligible; user-owned only for that same user
  (13 §7 — never another user's memory); expired excluded unless asked;
  recency order (last_seen desc, 13 §9). Expiry uses the DATABASE clock
  (``now()``) — one authoritative clock for durable truth.
- Anti-enumeration (20 §6): get/delete raise the SAME
  :class:`MemoryItemNotFound` for absent and foreign rows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.memory import MemoryItem, MemoryScope
from core.memory.errors import MemoryItemNotFound
from core.memory.memory import _screen_secret_like
from infrastructure.db.tables import memory_items


def _row_to_item(row: Any) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        scope=row.scope,
        key=row.key,
        value=row.value,
        source=row.source,
        confidence=row.confidence,
        evidence_count=row.evidence_count,
        last_seen=row.last_seen,
        expires_at=row.expires_at,
        sensitivity=row.sensitivity,
    )


class PostgresMemoryRepository:
    """Durable MemoryStorePort binding over asyncpg sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def upsert(self, item: MemoryItem) -> MemoryItem:
        _screen_secret_like(item.key, item.value)
        insert_stmt = pg_insert(memory_items).values(
            id=item.id,
            tenant_id=item.tenant_id,
            user_id=item.user_id,
            scope=item.scope.value,
            key=item.key,
            value=item.value,
            source=item.source,
            confidence=item.confidence,
            evidence_count=item.evidence_count,
            last_seen=item.last_seen,
            expires_at=item.expires_at,
            sensitivity=item.sensitivity.value,
        )
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_memory_items_logical_key",
            set_={
                # Original row id survives (in-memory upsert semantics);
                # evidence accumulates on the DURABLE row's counter.
                "value": insert_stmt.excluded.value,
                "source": insert_stmt.excluded.source,
                "confidence": insert_stmt.excluded.confidence,
                "evidence_count": memory_items.c.evidence_count + 1,
                "last_seen": insert_stmt.excluded.last_seen,
                "expires_at": insert_stmt.excluded.expires_at,
                "sensitivity": insert_stmt.excluded.sensitivity,
            },
        ).returning(memory_items)
        async with self._sessions() as session:
            async with session.begin():
                row = (await session.execute(stmt)).one()
        return _row_to_item(row)

    async def get(self, tenant_id: UUID, memory_id: UUID) -> MemoryItem:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(memory_items).where(
                        memory_items.c.id == memory_id,
                        memory_items.c.tenant_id == tenant_id,
                    )
                )
            ).one_or_none()
        if row is None:
            raise MemoryItemNotFound(memory_id)
        return _row_to_item(row)

    async def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: MemoryScope | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]:
        stmt = select(memory_items).where(memory_items.c.tenant_id == tenant_id)
        # 13 §7: tenant-shared (NULL) always eligible; user-owned only for
        # that same user — never another user's memory.
        if user_id is None:
            stmt = stmt.where(memory_items.c.user_id.is_(None))
        else:
            stmt = stmt.where(
                (memory_items.c.user_id.is_(None))
                | (memory_items.c.user_id == user_id)
            )
        if scope is not None:
            stmt = stmt.where(memory_items.c.scope == scope.value)
        if key is not None:
            stmt = stmt.where(memory_items.c.key == key)
        if min_confidence > 0.0:
            stmt = stmt.where(memory_items.c.confidence >= min_confidence)
        if not include_expired:
            stmt = stmt.where(
                (memory_items.c.expires_at.is_(None))
                | (memory_items.c.expires_at > func.now())
            )
        stmt = stmt.order_by(memory_items.c.last_seen.desc())
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_row_to_item(row) for row in rows)

    async def delete(self, tenant_id: UUID, memory_id: UUID) -> None:
        stmt = (
            delete(memory_items)
            .where(
                memory_items.c.id == memory_id,
                memory_items.c.tenant_id == tenant_id,
            )
            .returning(memory_items.c.id)
        )
        async with self._sessions() as session:
            async with session.begin():
                deleted = (await session.execute(stmt)).one_or_none()
        if deleted is None:
            raise MemoryItemNotFound(memory_id)
