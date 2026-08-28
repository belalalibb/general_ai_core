"""Worker runtime — consume → deduplicate → process → settle (41 §13, 40 §4).

Design decisions (recorded, per the standing derivation rule):

- 41 §13 names "Worker runtime" as a build item without an interface.
  Derived shape: a caller-driven loop body (``run_once`` for new messages,
  ``recover_once`` for stale-claimed ones) over the existing ``QueuePort``
  — the hosting process owns cadence and concurrency; Core owns semantics.
- Idempotency (40 §4.3): deduplication is the CONSUMER's duty (recorded in
  ports.py). The worker checks an ``IdempotencyPort`` BEFORE the handler
  and records AFTER success. Real binding = a PostgreSQL unique constraint
  (durable truth, 40 §4.1); the in-memory store keeps gates hermetic.
  A duplicate is acked WITHOUT re-running the handler — the 41 §13
  "duplicate request" exit behaviour.
- Error-aware retry (40 §4.6): the handler signals a permanent failure by
  raising :class:`PermanentTaskError` → immediate dead-letter (retrying a
  request-indicting failure cannot succeed). Any other exception is
  transient: the message is LEFT PENDING so ``claim_stale`` re-delivers it
  after the idle threshold — unless ``delivery_count`` has reached
  ``max_deliveries``, which dead-letters instead (40 §4.7 no infinite
  retry). ``QueuePort`` has no nack, so "leave pending + stale claim" IS
  the retry mechanism; this mirrors Redis Streams XAUTOCLAIM semantics
  pinned by ADR-0003.
- Worker crash / stale worker (41 §13 exit tests): a crashed worker simply
  never acks; ``recover_once`` on a healthy worker claims the stale
  pending messages and processes them. No heartbeat registry is invented —
  staleness is defined by pending idle time, which is what the port
  already models.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from core.runtime.ports import QueueMessage, QueuePort


class PermanentTaskError(Exception):
    """Handler signal: this message can never succeed — dead-letter it."""


class IdempotencyPort(Protocol):
    """Processed-key registry (40 §4.3) — durable binding is PostgreSQL."""

    async def seen(self, key: str) -> bool:
        """Return True if ``key`` was already processed successfully."""
        ...

    async def record(self, key: str) -> None:
        """Mark ``key`` as processed (idempotent)."""
        ...


class InMemoryIdempotencyStore:
    """Process-memory implementation of ``IdempotencyPort`` (hermetic gates)."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def seen(self, key: str) -> bool:
        return key in self._keys

    async def record(self, key: str) -> None:
        self._keys.add(key)


@dataclass
class WorkerReport:
    """Settlement accounting for one worker pass."""

    processed: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    left_pending: list[str] = field(default_factory=list)
    dead_lettered: list[str] = field(default_factory=list)


class Worker:
    """One consumer's loop body over a stream/group (41 §13 worker runtime)."""

    def __init__(
        self,
        queue: QueuePort,
        idempotency: IdempotencyPort,
        *,
        stream: str,
        group: str,
        consumer: str,
        handler: Callable[[QueueMessage], Awaitable[None]],
        max_deliveries: int = 3,
    ) -> None:
        if max_deliveries < 1:
            raise ValueError("max_deliveries must be >= 1 (40 §4.7)")
        self._queue = queue
        self._idempotency = idempotency
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._handler = handler
        self._max_deliveries = max_deliveries

    async def run_once(self, max_messages: int = 1) -> WorkerReport:
        """Consume NEW messages and process each; returns the accounting."""
        messages = await self._queue.consume(
            self._stream, self._group, self._consumer, max_messages
        )
        return await self._process(messages)

    async def recover_once(
        self, idle_ms: int, max_messages: int = 1
    ) -> WorkerReport:
        """Claim messages stuck pending past ``idle_ms`` and process them.

        Crash recovery (41 §13 worker crash / stale worker): the dead
        worker never acked, so its deliveries are claimable here.
        """
        messages = await self._queue.claim_stale(
            self._stream, self._group, self._consumer, idle_ms, max_messages
        )
        return await self._process(messages)

    async def _process(self, messages: tuple[QueueMessage, ...]) -> WorkerReport:
        report = WorkerReport()
        for message in messages:
            if await self._idempotency.seen(message.idempotency_key):
                # Duplicate request (41 §13): settle without re-running.
                await self._queue.ack(self._stream, self._group, message.message_id)
                report.duplicates.append(message.message_id)
                continue
            try:
                await self._handler(message)
            except PermanentTaskError:
                await self._queue.dead_letter(
                    self._stream, self._group, message.message_id
                )
                report.dead_lettered.append(message.message_id)
            except Exception:  # noqa: BLE001 — boundary containment (30 §14)
                if message.delivery_count >= self._max_deliveries:
                    # 40 §4.7 — no infinite retry.
                    await self._queue.dead_letter(
                        self._stream, self._group, message.message_id
                    )
                    report.dead_lettered.append(message.message_id)
                else:
                    # Transient: leave pending; claim_stale is the retry path.
                    report.left_pending.append(message.message_id)
            else:
                await self._idempotency.record(message.idempotency_key)
                await self._queue.ack(self._stream, self._group, message.message_id)
                report.processed.append(message.message_id)
        return report
