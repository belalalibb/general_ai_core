"""Runtime coordination port semantics (T-IMPL-016; 40 §4, ADR-0003).

Hermetic — exercises the in-memory fakes that implement the same ports as
``infrastructure/redis``. Async ports are driven with ``asyncio.run`` (no
pytest-asyncio dependency; ADR-0001 dev toolchain unchanged).

A fake monotonic clock makes TTL/idle expiry deterministic (no sleeping).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from core.runtime import (
    InMemoryCache,
    InMemoryLeaseManager,
    InMemoryQueue,
    InMemoryRateLimiter,
    LeaseNotHeld,
    MessageNotPending,
    UnknownStream,
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------- queue


def test_publish_consume_ack_roundtrip() -> None:
    async def scenario() -> None:
        q = InMemoryQueue()
        mid = await q.publish("jobs", {"kind": "run"}, idempotency_key="idem-1")
        (msg,) = await q.consume("jobs", "workers", "w1")
        assert msg.message_id == mid
        assert msg.payload == {"kind": "run"}
        assert msg.idempotency_key == "idem-1"
        assert msg.delivery_count == 1
        await q.ack("jobs", "workers", mid)
        # acked → nothing new, nothing pending
        assert await q.consume("jobs", "workers", "w1") == ()
        with pytest.raises(MessageNotPending):
            await q.ack("jobs", "workers", mid)

    run(scenario())


def test_at_least_once_unacked_message_is_claimable_by_another_consumer() -> None:
    """Crash recovery (40 §4.7): w1 dies mid-flight; w2 claims after idle."""

    async def scenario() -> None:
        clock = FakeClock()
        q = InMemoryQueue(clock=clock)
        await q.publish("jobs", {"kind": "run"}, idempotency_key="idem-1")
        (msg,) = await q.consume("jobs", "workers", "w1")
        # not yet idle long enough
        assert await q.claim_stale("jobs", "workers", "w2", idle_ms=5000) == ()
        clock.advance(6.0)
        (claimed,) = await q.claim_stale("jobs", "workers", "w2", idle_ms=5000)
        assert claimed.message_id == msg.message_id
        assert claimed.delivery_count == 2  # retry taxonomy input (40 §4.6)
        assert claimed.idempotency_key == "idem-1"  # dedup key survives redelivery
        await q.ack("jobs", "workers", claimed.message_id)

    run(scenario())


def test_dead_letter_moves_to_dlq_and_acks_original() -> None:
    async def scenario() -> None:
        q = InMemoryQueue()
        mid = await q.publish("jobs", {"kind": "bad"}, idempotency_key="idem-x")
        await q.consume("jobs", "workers", "w1")
        await q.dead_letter("jobs", "workers", mid)
        # original no longer pending
        with pytest.raises(MessageNotPending):
            await q.ack("jobs", "workers", mid)
        # DLQ carries payload + idempotency key (40 §4.7: no infinite retry)
        (dead,) = await q.consume("jobs.dlq", "recovery", "r1")
        assert dead.payload == {"kind": "bad"}
        assert dead.idempotency_key == "idem-x"

    run(scenario())


def test_consumer_groups_are_independent() -> None:
    """Two groups each receive every message (fan-out, 40 §4.1)."""

    async def scenario() -> None:
        q = InMemoryQueue()
        await q.publish("events", {"n": "1"}, idempotency_key="i1")
        (a,) = await q.consume("events", "group-a", "a1")
        (b,) = await q.consume("events", "group-b", "b1")
        assert a.payload == b.payload == {"n": "1"}
        await q.ack("events", "group-a", a.message_id)
        # group-a's ack does not affect group-b's pending entry
        await q.ack("events", "group-b", b.message_id)

    run(scenario())


def test_queue_operations_on_unknown_group_raise() -> None:
    async def scenario() -> None:
        q = InMemoryQueue()
        await q.publish("jobs", {"k": "v"}, idempotency_key="i")
        with pytest.raises(UnknownStream):
            await q.ack("jobs", "nope", "1-0")
        with pytest.raises(UnknownStream):
            await q.claim_stale("jobs", "nope", "w1", idle_ms=0)

    run(scenario())


# ---------------------------------------------------------------- lease


def test_lease_exclusive_and_fencing_tokens_strictly_increase() -> None:
    """40 §4.4: one holder at a time; successors get larger tokens."""

    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        first = await lm.acquire("provider-account:acme", "worker-1", ttl_seconds=30)
        assert first is not None
        # held → competitor refused
        assert await lm.acquire("provider-account:acme", "worker-2", ttl_seconds=30) is None
        await lm.release(first)
        second = await lm.acquire("provider-account:acme", "worker-2", ttl_seconds=30)
        assert second is not None
        assert second.fencing_token > first.fencing_token

    run(scenario())


def test_expired_lease_is_lost_and_stale_release_raises() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        lease = await lm.acquire("cred:key-7", "w1", ttl_seconds=10)
        assert lease is not None
        clock.advance(11.0)  # TTL elapsed
        taken = await lm.acquire("cred:key-7", "w2", ttl_seconds=10)
        assert taken is not None
        assert taken.fencing_token > lease.fencing_token
        # the zombie's handle is now fenced out
        with pytest.raises(LeaseNotHeld):
            await lm.release(lease)
        with pytest.raises(LeaseNotHeld):
            await lm.renew(lease, ttl_seconds=10)

    run(scenario())


def test_renew_extends_ttl_without_changing_token() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        lease = await lm.acquire("cred:key-9", "w1", ttl_seconds=10)
        assert lease is not None
        clock.advance(8.0)
        renewed = await lm.renew(lease, ttl_seconds=10)
        assert renewed.fencing_token == lease.fencing_token
        clock.advance(8.0)  # original would have expired; renewal keeps it
        assert await lm.acquire("cred:key-9", "w2", ttl_seconds=10) is None

    run(scenario())


# ---------------------------------------------------------------- cache


def test_cache_ttl_and_tenant_isolation() -> None:
    """Miss is a normal outcome; tenants never see each other (20 §6)."""

    async def scenario() -> None:
        clock = FakeClock()
        cache = InMemoryCache(clock=clock)
        await cache.set("tenant-a", "k", "va", ttl_seconds=60)
        assert await cache.get("tenant-a", "k") == "va"
        assert await cache.get("tenant-b", "k") is None  # isolation
        clock.advance(61.0)
        assert await cache.get("tenant-a", "k") is None  # expired = miss
        await cache.delete("tenant-a", "k")  # idempotent on absent key

    run(scenario())


# ------------------------------------------------------------ rate limit


def test_rate_limit_window_admits_then_refuses_then_resets() -> None:
    """Admission control (40 §4.5): limit within window, reset after."""

    async def scenario() -> None:
        clock = FakeClock()
        rl = InMemoryRateLimiter(clock=clock)
        assert await rl.hit("tenant-a:runs", limit=2, window_seconds=10)
        assert await rl.hit("tenant-a:runs", limit=2, window_seconds=10)
        assert not await rl.hit("tenant-a:runs", limit=2, window_seconds=10)
        # independent scope unaffected
        assert await rl.hit("tenant-b:runs", limit=2, window_seconds=10)
        clock.advance(10.0)  # next window
        assert await rl.hit("tenant-a:runs", limit=2, window_seconds=10)

    run(scenario())
