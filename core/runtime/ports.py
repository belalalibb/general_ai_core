"""Runtime coordination ports (dependency-inversion boundaries; 40 §4).

Design decisions (recorded, mirroring the storage/secrets/audit ports):

- Queue semantics = at-least-once with explicit ack (40 §4.3 idempotency is
  the CONSUMER's duty; the port carries an ``idempotency_key`` field so
  consumers can deduplicate). Claim of stale pending messages and explicit
  dead-lettering implement 40 §4.7 — no infinite retry; the DLQ hand-off to
  a durable PostgreSQL record is the caller's step (Redis holds no truth,
  40 §5.1).
- Lease semantics = fencing tokens (40 §4.4): every successful acquire
  returns a strictly increasing token; release/renew require the owner.
  Leases are ONLY for exclusive resources (provider accounts, credentials,
  exclusive device tools) — never for every job.
- Cache = tenant-scoped keys with TTL; a cache MISS is a normal outcome
  (None), never an error — cached state is always reconstructible.
- Rate limit = fixed-window counter port; the windowing algorithm may be
  refined by the binding (40 §4.5 backpressure) without changing the port.
- All ports are async: bindings do network I/O (ADR-0001 asyncio profile).
  The in-memory fakes are async too so tests exercise the same interface.
- Payloads are ``Mapping[str, str]``: Redis stream entries are flat
  string maps; forcing the constraint into the port keeps bindings honest
  and serialization explicit at the producer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QueueMessage:
    """One delivered stream entry.

    ``delivery_count`` starts at 1 and increases on re-claim — consumers use
    it with the retry taxonomy (40 §4.6) to decide dead-lettering.
    """

    message_id: str
    stream: str
    payload: Mapping[str, str]
    idempotency_key: str
    delivery_count: int


@dataclass(frozen=True)
class Lease:
    """A held lease on an exclusive resource (40 §4.4).

    ``fencing_token`` strictly increases across successive holders of the
    same resource; downstream effectors must reject stale tokens.
    """

    resource: str
    owner: str
    fencing_token: int
    ttl_seconds: float


class QueuePort(Protocol):
    """At-least-once stream queue with consumer groups (40 §4.1, §4.7)."""

    async def publish(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        """Append a message; returns the broker message id."""
        ...

    async def consume(
        self, stream: str, group: str, consumer: str, max_messages: int = 1
    ) -> tuple[QueueMessage, ...]:
        """Deliver up to ``max_messages`` NEW messages to ``consumer``.

        Creates the group at stream start on first use. Delivered messages
        stay pending until ``ack`` — crash-safe at-least-once.
        """
        ...

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        """Acknowledge successful processing.

        Raises :class:`~core.runtime.errors.MessageNotPending` if the
        message is not pending for that group.
        """
        ...

    async def claim_stale(
        self,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        max_messages: int = 1,
    ) -> tuple[QueueMessage, ...]:
        """Re-deliver messages pending longer than ``idle_ms`` to ``consumer``.

        Crash recovery for dead consumers; each re-claim increments the
        message's ``delivery_count``.
        """
        ...

    async def dead_letter(self, stream: str, group: str, message_id: str) -> None:
        """Move a terminally failed pending message to ``<stream>.dlq``.

        Acks the original (40 §4.7 — no infinite retry). Writing the durable
        failure record in PostgreSQL is the caller's responsibility: Redis
        is never a source of truth (40 §5.1).
        """
        ...


class LeasePort(Protocol):
    """Fencing-token leases for exclusive resources ONLY (40 §4.4)."""

    async def acquire(self, resource: str, owner: str, ttl_seconds: float) -> Lease | None:
        """Try to acquire; returns ``None`` if held by another owner."""
        ...

    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease:
        """Extend a held lease (token unchanged).

        Raises :class:`~core.runtime.errors.LeaseNotHeld` if the lease was
        lost (expired and possibly re-acquired by another owner).
        """
        ...

    async def release(self, lease: Lease) -> None:
        """Release if still the owner.

        Raises :class:`~core.runtime.errors.LeaseNotHeld` otherwise — the
        binding must compare owners atomically (Lua in Redis).
        """
        ...


class CachePort(Protocol):
    """Tenant-scoped TTL cache — never a source of truth (40 §5.1)."""

    async def get(self, tenant_id: str, key: str) -> str | None:
        """Return the cached value or ``None`` (miss is a normal outcome)."""
        ...

    async def set(self, tenant_id: str, key: str, value: str, ttl_seconds: float) -> None:
        """Store ``value`` under ``(tenant, key)`` for ``ttl_seconds``."""
        ...

    async def delete(self, tenant_id: str, key: str) -> None:
        """Drop the entry if present (idempotent)."""
        ...


class RateLimitPort(Protocol):
    """Windowed counter for admission control (40 §4.5)."""

    async def hit(self, scope: str, limit: int, window_seconds: float) -> bool:
        """Record one hit against ``scope``; ``True`` if within ``limit``."""
        ...
