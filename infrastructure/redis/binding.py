"""redis-py asyncio implementations of the core runtime ports (ADR-0003).

Semantics map (port → Redis):

QueuePort
    publish      → XADD  (payload fields + ``_idem`` reserved field)
    consume      → XGROUP CREATE (idempotent, from stream start '0')
                   then XREADGROUP with the '>' new-messages cursor
    ack          → XACK, guarded by an XPENDING existence check so a
                   non-pending ack raises instead of silently no-op'ing
    claim_stale  → XAUTOCLAIM (delivery_count from XPENDING info)
    dead_letter  → XADD to ``<stream>.dlq`` + XACK original — the durable
                   failure record in PostgreSQL is the CALLER's step
                   (Redis is never a source of truth, 40 §5.1)

LeasePort (fencing, 40 §4.4)
    acquire      → INCR fencing counter, then SET key value NX PX ttl;
                   value = "owner:token". Re-entrant same-owner acquire
                   issues a FRESH token (strictly increasing invariant).
    renew        → Lua: value matches owner:token → PEXPIRE, else error
    release      → Lua: value matches owner:token → DEL, else error

CachePort
    get/set/del  → GET / SET PX / DEL on ``cache:{tenant}:{key}``

RateLimitPort
    hit          → Lua: INCR window key, PEXPIRE on first hit, compare limit

Key prefixes keep the namespaces disjoint: ``stream:``, ``lease:``,
``cache:``, ``rl:``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from core.runtime.errors import LeaseNotHeld, MessageNotPending, UnknownStream
from core.runtime.ports import Lease, QueueMessage

_IDEM_FIELD = "_idem"

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RATELIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class RedisQueue:
    """``QueuePort`` on Redis Streams consumer groups."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @staticmethod
    def _key(stream: str) -> str:
        return f"stream:{stream}"

    async def publish(
        self, stream: str, payload: Mapping[str, str], idempotency_key: str
    ) -> str:
        if _IDEM_FIELD in payload:
            raise ValueError(f"payload field {_IDEM_FIELD!r} is reserved")
        fields: dict[str, str] = {**payload, _IDEM_FIELD: idempotency_key}
        message_id = await self._redis.xadd(self._key(stream), fields)  # type: ignore[arg-type]
        return _decode(message_id)

    async def _ensure_group(self, stream: str, group: str) -> None:
        try:
            # id='0' → group consumes from stream start (parity with fake).
            await self._redis.xgroup_create(self._key(stream), group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _to_message(
        self, stream: str, message_id: bytes | str, fields: dict[Any, Any], delivery_count: int
    ) -> QueueMessage:
        decoded = {_decode(k): _decode(v) for k, v in fields.items()}
        idem = decoded.pop(_IDEM_FIELD, "")
        return QueueMessage(
            message_id=_decode(message_id),
            stream=stream,
            payload=decoded,
            idempotency_key=idem,
            delivery_count=delivery_count,
        )

    async def consume(
        self, stream: str, group: str, consumer: str, max_messages: int = 1
    ) -> tuple[QueueMessage, ...]:
        await self._ensure_group(stream, group)
        reply: Any = await self._redis.xreadgroup(
            group, consumer, {self._key(stream): ">"}, count=max_messages
        )
        out: list[QueueMessage] = []
        for _stream_key, entries in reply or []:
            for message_id, fields in entries:
                out.append(self._to_message(stream, message_id, fields, delivery_count=1))
        return tuple(out)

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self._require_pending(stream, group, message_id)
        await self._redis.xack(self._key(stream), group, message_id)

    async def claim_stale(
        self,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        max_messages: int = 1,
    ) -> tuple[QueueMessage, ...]:
        try:
            _cursor, entries, _deleted = await self._redis.xautoclaim(
                self._key(stream),
                group,
                consumer,
                min_idle_time=idle_ms,
                start_id="0-0",
                count=max_messages,
            )
        except ResponseError as exc:
            raise UnknownStream(f"no consumer group {group!r} on stream {stream!r}") from exc
        out: list[QueueMessage] = []
        for message_id, fields in entries:
            info = await self._redis.xpending_range(
                self._key(stream), group, min=message_id, max=message_id, count=1
            )
            delivery_count = int(info[0]["times_delivered"]) if info else 2
            out.append(self._to_message(stream, message_id, fields, delivery_count))
        return tuple(out)

    async def dead_letter(self, stream: str, group: str, message_id: str) -> None:
        await self._require_pending(stream, group, message_id)
        entries = await self._redis.xrange(self._key(stream), min=message_id, max=message_id)
        if entries:
            fields: dict[Any, Any] = entries[0][1] or {}
            decoded = {_decode(k): _decode(v) for k, v in fields.items()}
            idem = decoded.pop(_IDEM_FIELD, "")
            await self.publish(f"{stream}.dlq", decoded, idem)
        await self._redis.xack(self._key(stream), group, message_id)

    async def _require_pending(self, stream: str, group: str, message_id: str) -> None:
        try:
            info = await self._redis.xpending_range(
                self._key(stream), group, min=message_id, max=message_id, count=1
            )
        except ResponseError as exc:
            raise UnknownStream(f"no consumer group {group!r} on stream {stream!r}") from exc
        if not info:
            raise MessageNotPending(f"{message_id} not pending in {stream}/{group}")


class RedisLeaseManager:
    """``LeasePort`` via SET NX PX + fencing counter + Lua release (40 §4.4)."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @staticmethod
    def _key(resource: str) -> str:
        return f"lease:{resource}"

    @staticmethod
    def _value(owner: str, token: int) -> str:
        return f"{owner}:{token}"

    async def acquire(
        self, resource: str, owner: str, ttl_seconds: float
    ) -> Lease | None:
        token = int(await self._redis.incr(f"lease-token:{resource}"))
        px = max(1, int(ttl_seconds * 1000))
        ok = await self._redis.set(
            self._key(resource), self._value(owner, token), nx=True, px=px
        )
        if ok:
            return Lease(
                resource=resource, owner=owner, fencing_token=token, ttl_seconds=ttl_seconds
            )
        # Same-owner re-acquire: replace atomically only if we still hold it.
        current = await self._redis.get(self._key(resource))
        if current is not None and _decode(current).rsplit(":", 1)[0] == owner:
            replaced = await self._redis.set(
                self._key(resource), self._value(owner, token), xx=True, px=px
            )
            if replaced:
                return Lease(
                    resource=resource,
                    owner=owner,
                    fencing_token=token,
                    ttl_seconds=ttl_seconds,
                )
        return None

    async def renew(self, lease: Lease, ttl_seconds: float) -> Lease:
        px = max(1, int(ttl_seconds * 1000))
        value = self._value(lease.owner, lease.fencing_token)
        renewed = await self._redis.eval(
            _RENEW_LUA, 1, self._key(lease.resource), value, str(px)
        )
        if not renewed:
            raise LeaseNotHeld(f"{lease.owner!r} does not hold {lease.resource!r}")
        return Lease(
            resource=lease.resource,
            owner=lease.owner,
            fencing_token=lease.fencing_token,
            ttl_seconds=ttl_seconds,
        )

    async def release(self, lease: Lease) -> None:
        value = self._value(lease.owner, lease.fencing_token)
        deleted = await self._redis.eval(
            _RELEASE_LUA, 1, self._key(lease.resource), value
        )
        if not deleted:
            raise LeaseNotHeld(f"{lease.owner!r} does not hold {lease.resource!r}")


class RedisCache:
    """``CachePort`` — tenant-scoped TTL keys; reconstructible state only."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    @staticmethod
    def _key(tenant_id: str, key: str) -> str:
        return f"cache:{tenant_id}:{key}"

    async def get(self, tenant_id: str, key: str) -> str | None:
        value = await self._redis.get(self._key(tenant_id, key))
        return None if value is None else _decode(value)

    async def set(
        self, tenant_id: str, key: str, value: str, ttl_seconds: float
    ) -> None:
        await self._redis.set(
            self._key(tenant_id, key), value, px=max(1, int(ttl_seconds * 1000))
        )

    async def delete(self, tenant_id: str, key: str) -> None:
        await self._redis.delete(self._key(tenant_id, key))


class RedisRateLimiter:
    """``RateLimitPort`` — fixed-window counter (INCR + PEXPIRE, atomic Lua)."""

    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def hit(self, scope: str, limit: int, window_seconds: float) -> bool:
        window_ms = max(1, int(window_seconds * 1000))
        count = int(
            await self._redis.eval(_RATELIMIT_LUA, 1, f"rl:{scope}", str(window_ms))
        )
        return count <= limit
