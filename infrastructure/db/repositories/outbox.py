"""PostgreSQL transactional outbox — OutboxPort binding (Vision V2).

Binds :class:`core.runtime.outbox.OutboxPort` (40 §4.2) against the
``outbox_records`` table (migration 0015) — the durable binding the port
docstring records ("the real binding writes the outbox row in the SAME
PostgreSQL transaction as the state change").

Design decisions (recorded):

- Record ids are the BIGINT identity values rendered as strings — the
  port's ``record_id: str`` stays opaque to callers; insertion order IS
  the "oldest first" order ``pending`` promises (monotone sequence).
- ``append`` opens its own transaction here because THIS slice's producer
  (the API enqueue path) has no surrounding database transaction to join:
  the durable outbox row IS the state change (the execution placeholder
  lives in the injectable execution store, a separate seam). When a
  future producer writes contract state and the outbox row atomically,
  it passes its OWN session via ``append_in_session`` — the same-
  transaction seam the 40 §4.2 chain names, provided but never faked.
- ``pending`` reads WHERE NOT dispatched ORDER BY id (the partial index's
  exact shape); it takes no lock — the relay is single-drainer by
  deployment posture, and a crashed relay's re-publish is the documented
  at-least-once window consumers deduplicate (outbox module docstring).
- ``mark_dispatched`` updates only rows still pending; an unknown or
  already-dispatched id raises :class:`RecordNotPending` — the port's
  named error, never a silent no-op.
- Payload values are coerced ``str(...)``-free: the port constrains
  ``Mapping[str, str]`` at the type level; this binding stores what it is
  given verbatim (keeping bindings honest — ports.py header).
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.runtime.errors import RecordNotPending
from core.runtime.outbox import OutboxRecord
from infrastructure.db.tables import outbox_records


def _row_to_record(row: object) -> OutboxRecord:
    return OutboxRecord(
        record_id=str(row.id),  # type: ignore[attr-defined]
        stream=row.stream,  # type: ignore[attr-defined]
        payload=dict(row.payload),  # type: ignore[attr-defined]
        idempotency_key=row.idempotency_key,  # type: ignore[attr-defined]
    )


class PostgresOutbox:
    """Durable OutboxPort binding over asyncpg sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def append(
        self, stream: str, payload: Mapping[str, str], idempotency_key: str
    ) -> str:
        """Stage a message in its own transaction; returns the record id."""
        async with self._sessions() as session:
            async with session.begin():
                record_id = await self._insert(
                    session, stream, payload, idempotency_key
                )
        return record_id

    async def append_in_session(
        self,
        session: AsyncSession,
        stream: str,
        payload: Mapping[str, str],
        idempotency_key: str,
    ) -> str:
        """Stage a message INSIDE the caller's open transaction (40 §4.2).

        The same-transaction seam for producers that change contract state
        and stage the message atomically; the caller owns commit/rollback.
        """
        return await self._insert(session, stream, payload, idempotency_key)

    @staticmethod
    async def _insert(
        session: AsyncSession,
        stream: str,
        payload: Mapping[str, str],
        idempotency_key: str,
    ) -> str:
        result = await session.execute(
            outbox_records.insert()
            .values(
                stream=stream,
                payload=dict(payload),
                idempotency_key=idempotency_key,
            )
            .returning(outbox_records.c.id)
        )
        return str(result.scalar_one())

    async def pending(self, max_records: int = 1) -> tuple[OutboxRecord, ...]:
        """Return up to ``max_records`` undispatched records, oldest first."""
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(outbox_records)
                    .where(~outbox_records.c.dispatched)
                    .order_by(outbox_records.c.id)
                    .limit(max_records)
                )
            ).all()
        return tuple(_row_to_record(row) for row in rows)

    async def mark_dispatched(self, record_id: str) -> None:
        """Settle a record after successful publish; loud if not pending."""
        try:
            numeric_id = int(record_id)
        except ValueError:
            raise RecordNotPending(
                f"outbox record {record_id!r} is not pending"
            ) from None
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(
                    update(outbox_records)
                    .where(
                        outbox_records.c.id == numeric_id,
                        ~outbox_records.c.dispatched,
                    )
                    .values(dispatched=True)
                    .returning(outbox_records.c.id)
                )
                if result.scalar_one_or_none() is None:
                    raise RecordNotPending(
                        f"outbox record {record_id!r} is not pending"
                    )
