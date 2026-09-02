"""In-memory runtime coordination fakes (MVP Phase 3, 41 §42 / ADR-0003).

Hermetic implementations of the runtime ports — the gates run against
these; ``infrastructure/redis/`` provides the real bindings behind the
same ports (ADR-0003 decision: hermetic gates keep fakes).

Determinism: every class takes an injectable ``clock`` (monotonic seconds)
so TTL expiry is testable without sleeping.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Mapping

from core.runtime.errors import LeaseNotHeld, MessageNotPending, UnknownStream
from core.runtime.ports import Lease, QueueMessage


class InMemoryQueue:
    """Process-memory implementation of ``QueuePort``.

    Models Redis Streams semantics: per-(stream, group) pending entries,
    delivery counts, stale-claim, and a ``<stream>.dlq`` stream.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._seq = itertools.count(1)
        # stream -> ordered list of (message_id, payload, idempotency_key)
        self._streams: dict[str, list[tuple[str, dict[str, str], str]]] = {}
        # (stream, group) -> next undelivered index into the stream list
        self._cursors: dict[tuple[str, str], int] = {}
        # (stream, group) -> message_id -> (consumer, delivered_at, delivery_count)
        self._pending: dict[tuple[str, str], dict[str, tuple[str, float, int]]] = {}

    async def publish(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        message_id = f"{next(self._seq)}-0"
        self._streams.setdefault(stream, []).append((message_id, dict(payload), idempotency_key))
        return message_id

    async def consume(
        self, stream: str, group: str, consumer: str, max_messages: int = 1
    ) -> tuple[QueueMessage, ...]:
        entries = self._streams.setdefault(stream, [])
        key = (stream, group)
        cursor = self._cursors.setdefault(key, 0)  # group starts at stream head
        pending = self._pending.setdefault(key, {})
        out: list[QueueMessage] = []
        while cursor < len(entries) and len(out) < max_messages:
            message_id, payload, idem = entries[cursor]
            cursor += 1
            pending[message_id] = (consumer, self._clock(), 1)
            out.append(
                QueueMessage(
                    message_id=message_id,
                    stream=stream,
                    payload=payload,
                    idempotency_key=idem,
                    delivery_count=1,
                )
            )
        self._cursors[key] = cursor
        return tuple(out)

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        pending = self._require_group(stream, group)
        if message_id not in pending:
            raise MessageNotPending(f"{message_id} not pending in {stream}/{group}")
        del pending[message_id]

    async def claim_stale(
        self,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        max_messages: int = 1,
    ) -> tuple[QueueMessage, ...]:
        pending = self._require_group(stream, group)
        by_id = {mid: (p, i) for mid, p, i in self._streams.get(stream, [])}
        now = self._clock()
        out: list[QueueMessage] = []
        for message_id in sorted(pending, key=lambda m: int(m.split("-")[0])):
            if len(out) >= max_messages:
                break
            _owner, delivered_at, count = pending[message_id]
            if (now - delivered_at) * 1000.0 < idle_ms:
                continue
            pending[message_id] = (consumer, now, count + 1)
            payload, idem = by_id[message_id]
            out.append(
                QueueMessage(
                    message_id=message_id,
                    stream=stream,
                    payload=payload,
                    idempotency_key=idem,
                    delivery_count=count + 1,
                )
            )
        return tuple(out)

    async def dead_letter(self, stream: str, group: str, message_id: str) -> None:
        pending = self._require_group(stream, group)
        if message_id not in pending:
            raise MessageNotPending(f"{message_id} not pending in {stream}/{group}")
        by_id = {mid: (p, i) for mid, p, i in self._streams.get(stream, [])}
        payload, idem = by_id[message_id]
        await self.publish(f"{stream}.dlq", payload, idem)
        del pending[message_id]

    def _require_group(self, stream: str, group: str) -> dict[str, tuple[str, float, int]]:
        key = (stream, group)
        if key not in self._pending:
            raise UnknownStream(f"no consumer group {group!r} on stream {stream!r}")
        return self._pending[key]


class InMemoryLeaseManager:
    """Process-memory implementation of ``LeasePort`` (fencing, 40 §4.4)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._token = itertools.count(1)
        # resource -> (owner, fencing_token, expires_at)
        self._held: dict[str, tuple[str, int, float]] = {}

    async def acquire(self, resource: str, owner: str, ttl_seconds: float) -> Lease | None:
        now = self._clock()
        current = self._held.get(resource)
        if current is not None and current[2] > now and current[0] != owner:
            return None  # held by another live owner
        token = next(self._token)  # strictly increasing across holders
        self._held[resource] = (owner, token, now + ttl_seconds)
        return Lease(resource=resource, owner=owner, fencing_token=token, ttl_seconds=ttl_seconds)

    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease:
        self._require_holder(lease)
        self._held[lease.resource] = (
            lease.owner,
            lease.fencing_token,
            self._clock() + ttl_seconds,
        )
        return Lease(
            resource=lease.resource,
            owner=lease.owner,
            fencing_token=lease.fencing_token,
            ttl_seconds=ttl_seconds,
        )

    async def release(self, lease: Lease) -> None:
        self._require_holder(lease)
        del self._held[lease.resource]

    def _require_holder(self, lease: Lease) -> None:
        current = self._held.get(lease.resource)
        if (
            current is None
            or current[2] <= self._clock()
            or current[0] != lease.owner
            or current[1] != lease.fencing_token
        ):
            raise LeaseNotHeld(f"{lease.owner!r} does not hold {lease.resource!r}")


class InMemoryCache:
    """Process-memory implementation of ``CachePort`` (tenant-scoped TTL)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[tuple[str, str], tuple[str, float]] = {}

    async def get(self, tenant_id: str, key: str) -> str | None:
        entry = self._entries.get((tenant_id, key))
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= self._clock():
            del self._entries[(tenant_id, key)]
            return None
        return value

    async def set(self, tenant_id: str, key: str, value: str, ttl_seconds: float) -> None:
        self._entries[(tenant_id, key)] = (value, self._clock() + ttl_seconds)

    async def delete(self, tenant_id: str, key: str) -> None:
        self._entries.pop((tenant_id, key), None)


class InMemoryRateLimiter:
    """Process-memory implementation of ``RateLimitPort`` (fixed window)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # (scope, window_index) -> count; stale windows pruned lazily
        self._windows: dict[tuple[str, int], int] = {}

    async def hit(self, scope: str, limit: int, window_seconds: float) -> bool:
        window = int(self._clock() // window_seconds)
        key = (scope, window)
        # prune older windows for this scope
        for stale in [k for k in self._windows if k[0] == scope and k[1] < window]:
            del self._windows[stale]
        count = self._windows.get(key, 0) + 1
        self._windows[key] = count
        return count <= limit
