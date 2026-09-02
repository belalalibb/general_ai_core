"""Transactional Outbox — 40 §4.2: DB Transaction → Outbox → Publisher → Message Bus.

Design decisions (recorded, per the standing derivation rule):

- 40 §4.2 defines the CHAIN, not an interface. Derived minimal port:
  ``append`` (called inside the state-changing transaction), ``pending``
  (relay pull, oldest first), ``mark_dispatched`` (after successful
  publish). The real binding writes the outbox row in the SAME PostgreSQL
  transaction as the state change; the in-memory fake approximates the
  atomicity for hermetic gates (40 §5.1 — durable truth is PostgreSQL).
- Relay crash window: if the relay publishes to the bus but dies before
  ``mark_dispatched``, the record is re-published on the next pass. That
  is the documented at-least-once posture (ports.py header); the consumer
  deduplicates via ``idempotency_key`` (40 §4.3). The relay therefore
  publishes-then-marks — never the reverse (marking first could LOSE a
  message on crash, which 40 §4.2 exists to prevent).
- Records carry the same flat ``Mapping[str, str]`` payload constraint as
  ``QueuePort`` so the relay is a pure pass-through.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from core.runtime.errors import RecordNotPending
from core.runtime.ports import QueuePort


@dataclass(frozen=True)
class OutboxRecord:
    """One staged message awaiting relay to the bus (40 §4.2)."""

    record_id: str
    stream: str
    payload: Mapping[str, str]
    idempotency_key: str


class OutboxPort(Protocol):
    """Staging table for messages written inside the state transaction."""

    async def append(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        """Stage a message; returns the outbox record id."""
        ...

    async def pending(self, max_records: int = 1) -> tuple[OutboxRecord, ...]:
        """Return up to ``max_records`` undispatched records, oldest first."""
        ...

    async def mark_dispatched(self, record_id: str) -> None:
        """Settle a record after successful publish.

        Raises :class:`~core.runtime.errors.RecordNotPending` if the record
        is unknown or already dispatched.
        """
        ...


class InMemoryOutbox:
    """Process-memory implementation of ``OutboxPort`` (hermetic gates)."""

    def __init__(self) -> None:
        self._seq = itertools.count(1)
        # record_id -> record; insertion order == append order (oldest first)
        self._pending: dict[str, OutboxRecord] = {}
        self._dispatched: list[OutboxRecord] = []

    async def append(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        record_id = f"outbox-{next(self._seq)}"
        self._pending[record_id] = OutboxRecord(
            record_id=record_id,
            stream=stream,
            payload=dict(payload),
            idempotency_key=idempotency_key,
        )
        return record_id

    async def pending(self, max_records: int = 1) -> tuple[OutboxRecord, ...]:
        return tuple(list(self._pending.values())[:max_records])

    async def mark_dispatched(self, record_id: str) -> None:
        record = self._pending.pop(record_id, None)
        if record is None:
            raise RecordNotPending(f"outbox record {record_id!r} is not pending")
        self._dispatched.append(record)


class OutboxRelay:
    """The Publisher step of 40 §4.2 — drains the outbox onto the bus.

    Single-pass, caller-driven (``relay_once``): the hosting worker/process
    owns the loop cadence. Publish-then-mark ordering is deliberate — see
    module docstring for the crash-window derivation.
    """

    def __init__(self, outbox: OutboxPort, queue: QueuePort) -> None:
        self._outbox = outbox
        self._queue = queue

    async def relay_once(self, max_records: int = 1) -> int:
        """Publish up to ``max_records`` pending records; returns the count."""
        relayed = 0
        for record in await self._outbox.pending(max_records):
            await self._queue.publish(record.stream, record.payload, record.idempotency_key)
            await self._outbox.mark_dispatched(record.record_id)
            relayed += 1
        return relayed
