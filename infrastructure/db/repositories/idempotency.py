"""PostgreSQL idempotency store — worker IdempotencyPort binding.

Binds :class:`core.runtime.worker.IdempotencyPort` (40 §4.3) against the
``worker_idempotency_keys`` table (migration 0014) — the durable binding
the port docstring records ("Real binding = a PostgreSQL unique
constraint (durable truth, 40 §4.1)").

Design decisions (recorded):

- ``record`` is idempotent BY CONSTRAINT: ``ON CONFLICT DO NOTHING`` on
  the primary key — recording an already-recorded key is a no-op, never
  an error (the port contract: "Mark ``key`` as processed
  (idempotent)"). Two racing workers both succeed; exactly one row
  exists.
- ``seen`` is a bare primary-key point read — no scan, no lock.
- Surface is EXACTLY the port: {seen, record}. No delete/expiry method
  exists; retention policy belongs to a later, justified slice.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.db.tables import worker_idempotency_keys


class PostgresIdempotencyStore:
    """Durable IdempotencyPort binding over asyncpg sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def seen(self, key: str) -> bool:
        """Return True if ``key`` was already processed successfully."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(worker_idempotency_keys.c.key).where(
                        worker_idempotency_keys.c.key == key
                    )
                )
            ).scalar_one_or_none()
        return row is not None

    async def record(self, key: str) -> None:
        """Mark ``key`` as processed (idempotent — duplicate is a no-op)."""
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    pg_insert(worker_idempotency_keys)
                    .values(key=key)
                    .on_conflict_do_nothing(index_elements=["key"])
                )
