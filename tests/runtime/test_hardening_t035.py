"""T-IMPL-035 — MVP Phase 8 slice 3 (final): queue/retry + load-smoke hardening.

Adversarial tests over the EXISTING core/runtime ports (in-memory bindings)
plus a hermetic concurrency smoke of POST /v1/execute. R054 boundary (b):
fixes for exposed defects in-scope; features out-of-scope.

Gap-focused — tests/runtime/test_runtime_ports.py already covers (and this
module does NOT repeat): publish/consume/ack roundtrip, basic stale-claim
after idle, dead-letter to DLQ + original acked, independent consumer
groups, unknown-group errors, lease exclusivity + token monotonicity,
expired-lease zombie fencing, renew-keeps-token, cache TTL/tenant isolation,
basic window admit/refuse/reset.

What THIS module attacks (40 §4.4-§4.7; 41 §47):

1. Ack-after-claim discipline under contention: after a reclaim, the queue
   acks by (group, message_id) — Redis XACK parity, consumer-agnostic —
   recorded HONESTLY as the port's semantic: mutual exclusion is the
   LEASE's job (fencing tokens), not the queue's. A second ack of the same
   id always raises (no double-settlement).
2. Dead-letter TERMINALITY: a dead-lettered id is unreachable through
   every recovery path (ack, claim_stale, re-dead-letter) and appears in
   the DLQ exactly once with payload + idempotency key intact.
3. Lease fencing beyond the zombie basics: same-owner re-acquire bumps the
   token and fences the OLD handle (a worker restarting cannot resurrect
   its previous incarnation's handle); release with a forged/stale token
   raises; a fenced-out holder cannot extend its way back in.
4. InMemoryRateLimiter fixed-window boundaries: exact-boundary rollover
   (a hit AT t == window edge lands in the NEW window), limit=0 refuses
   always, scope isolation under interleaving, stale windows pruned only
   for the hitting scope, fractional window sizes.
5. Load-smoke: concurrent POST /v1/execute fan-out through httpx-ASGI —
   every request gets a distinct execution id, per-request adapter calls
   never bleed across requests, and the settled usage ledger equals the
   arithmetic sum. HONESTY NOTE (41 §49): in-process ASGI smoke proves
   isolation-under-concurrency of THIS composition; it is NOT a capacity
   or throughput claim and is recorded as such.

Hermetic: fake monotonic clock (no sleeping), asyncio.run (ADR-0001).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import httpx
import pytest

from core.runtime import (
    InMemoryLeaseManager,
    InMemoryQueue,
    InMemoryRateLimiter,
    LeaseNotHeld,
    MessageNotPending,
)
from tests.api.test_execute_api import World, run
from tests.runtime.test_runtime_ports import FakeClock


def gather[T](*coros: Coroutine[Any, Any, T]) -> list[T]:
    async def _all() -> list[T]:
        return list(await asyncio.gather(*coros))

    return asyncio.run(_all())


# --- 1. ack-after-claim discipline under contention -----------------------------------


def test_ack_is_group_scoped_redis_xack_parity_and_never_double_settles() -> None:
    """HONEST SEMANTIC RECORD: after w2 reclaims w1's stale message, an ack
    by (group, id) succeeds regardless of which consumer issues it — Redis
    XACK parity. Worker mutual exclusion is the LEASE port's job (40 §4.4
    fencing), not the queue's. What the queue DOES guarantee: the id can
    settle at most ONCE — the second ack raises."""

    async def scenario() -> None:
        clock = FakeClock()
        q = InMemoryQueue(clock=clock)
        mid = await q.publish("jobs", {"k": "v"}, idempotency_key="i1")
        await q.consume("jobs", "workers", "w1")
        clock.advance(10.0)
        (claimed,) = await q.claim_stale("jobs", "workers", "w2", idle_ms=5000)
        assert claimed.message_id == mid
        await q.ack("jobs", "workers", mid)  # settles once
        with pytest.raises(MessageNotPending):
            await q.ack("jobs", "workers", mid)  # never twice

    run(scenario())


def test_claim_stale_respects_idle_threshold_after_reclaim_too() -> None:
    """A freshly reclaimed message is NOT immediately stale again — the
    idle clock restarts at reclaim time, so a third consumer cannot
    thrash-steal it inside the idle window."""

    async def scenario() -> None:
        clock = FakeClock()
        q = InMemoryQueue(clock=clock)
        await q.publish("jobs", {"k": "v"}, idempotency_key="i1")
        await q.consume("jobs", "workers", "w1")
        clock.advance(10.0)
        (claimed,) = await q.claim_stale("jobs", "workers", "w2", idle_ms=5000)
        assert claimed.delivery_count == 2
        # immediately after reclaim: not stale for w3
        assert await q.claim_stale("jobs", "workers", "w3", idle_ms=5000) == ()
        clock.advance(6.0)
        (reclaimed,) = await q.claim_stale("jobs", "workers", "w3", idle_ms=5000)
        assert reclaimed.delivery_count == 3  # retry taxonomy input grows

    run(scenario())


def test_claim_stale_honors_max_messages_and_oldest_first_order() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        q = InMemoryQueue(clock=clock)
        first = await q.publish("jobs", {"n": "1"}, idempotency_key="i1")
        second = await q.publish("jobs", {"n": "2"}, idempotency_key="i2")
        await q.consume("jobs", "workers", "w1", max_messages=2)
        clock.advance(10.0)
        # idle threshold 5s: both are stale NOW, but max_messages=1 takes
        # only the OLDEST; the reclaim restarts its idle clock, so the next
        # claim (still > 5s idle for `second`, < 5s for `first`) yields the
        # sibling — order and idle discipline hold together.
        (one,) = await q.claim_stale("jobs", "workers", "w2", idle_ms=5000, max_messages=1)
        assert one.message_id == first  # oldest first
        (two,) = await q.claim_stale("jobs", "workers", "w2", idle_ms=5000, max_messages=1)
        assert two.message_id == second

    run(scenario())


# --- 2. dead-letter terminality ---------------------------------------------------------


def test_dead_letter_is_terminal_through_every_recovery_path() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        q = InMemoryQueue(clock=clock)
        mid = await q.publish("jobs", {"k": "bad"}, idempotency_key="ix")
        await q.consume("jobs", "workers", "w1")
        await q.dead_letter("jobs", "workers", mid)
        # unreachable via ack
        with pytest.raises(MessageNotPending):
            await q.ack("jobs", "workers", mid)
        # unreachable via claim_stale even after arbitrary idle time
        clock.advance(3600.0)
        assert await q.claim_stale("jobs", "workers", "w2", idle_ms=0) == ()
        # unreachable via a second dead_letter (no DLQ duplication)
        with pytest.raises(MessageNotPending):
            await q.dead_letter("jobs", "workers", mid)
        # exactly one DLQ copy, payload + idempotency key intact
        dlq = await q.consume("jobs.dlq", "recovery", "r1", max_messages=10)
        assert len(dlq) == 1
        assert dlq[0].payload == {"k": "bad"}
        assert dlq[0].idempotency_key == "ix"

    run(scenario())


def test_dead_letter_of_one_message_leaves_siblings_pending() -> None:
    async def scenario() -> None:
        q = InMemoryQueue()
        bad = await q.publish("jobs", {"n": "bad"}, idempotency_key="ib")
        good = await q.publish("jobs", {"n": "good"}, idempotency_key="ig")
        await q.consume("jobs", "workers", "w1", max_messages=2)
        await q.dead_letter("jobs", "workers", bad)
        await q.ack("jobs", "workers", good)  # sibling still settles normally

    run(scenario())


# --- 3. lease fencing beyond the zombie basics ------------------------------------------


def test_same_owner_reacquire_fences_the_previous_handle() -> None:
    """A restarted worker re-acquiring its own resource gets a NEW token
    and the OLD handle is fenced out — an incarnation cannot be resurrected
    (40 §4.4: the token, not the owner string, is the authority)."""

    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        old = await lm.acquire("res", "w1", ttl_seconds=100)
        assert old is not None
        new = await lm.acquire("res", "w1", ttl_seconds=100)  # same owner, re-entry
        assert new is not None
        assert new.fencing_token > old.fencing_token
        with pytest.raises(LeaseNotHeld):
            await lm.renew(old, ttl_seconds=100)
        with pytest.raises(LeaseNotHeld):
            await lm.release(old)
        # the live handle still works
        await lm.renew(new, ttl_seconds=100)
        await lm.release(new)

    run(scenario())


def test_forged_token_cannot_release_or_renew() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        lease = await lm.acquire("res", "w1", ttl_seconds=100)
        assert lease is not None
        forged = dataclasses.replace(lease, fencing_token=lease.fencing_token + 1)
        with pytest.raises(LeaseNotHeld):
            await lm.release(forged)
        with pytest.raises(LeaseNotHeld):
            await lm.renew(forged, ttl_seconds=100)
        await lm.release(lease)  # real handle unaffected by the attack

    run(scenario())


def test_fenced_holder_cannot_extend_its_way_back_in() -> None:
    """After expiry + takeover, the zombie's renew must fail AND must not
    have extended anything: the new holder's lease survives untouched."""

    async def scenario() -> None:
        clock = FakeClock()
        lm = InMemoryLeaseManager(clock=clock)
        zombie = await lm.acquire("res", "w1", ttl_seconds=10)
        assert zombie is not None
        clock.advance(11.0)
        live = await lm.acquire("res", "w2", ttl_seconds=10)
        assert live is not None
        with pytest.raises(LeaseNotHeld):
            await lm.renew(zombie, ttl_seconds=1000)
        # the failed renew changed nothing: w2 still holds and can renew
        renewed = await lm.renew(live, ttl_seconds=10)
        assert renewed.fencing_token == live.fencing_token

    run(scenario())


# --- 4. rate limiter window boundaries ---------------------------------------------------


def test_hit_at_exact_window_boundary_lands_in_the_new_window() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        clock.now = 1000.0  # aligned: 1000 % 10 == 0
        rl = InMemoryRateLimiter(clock=clock)
        assert await rl.hit("s", 1, 10.0) is True
        clock.now = 1009.999  # still inside [1000, 1010)
        assert await rl.hit("s", 1, 10.0) is False
        clock.now = 1010.0  # EXACT boundary => new window
        assert await rl.hit("s", 1, 10.0) is True

    run(scenario())


def test_zero_limit_refuses_every_hit_in_every_window() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        rl = InMemoryRateLimiter(clock=clock)
        assert await rl.hit("s", 0, 10.0) is False
        clock.advance(1000.0)
        assert await rl.hit("s", 0, 10.0) is False

    run(scenario())


def test_scopes_are_isolated_under_interleaving() -> None:
    """Exhausting scope A must never consume scope B's budget, even when
    hits interleave within the same window."""

    async def scenario() -> None:
        clock = FakeClock()
        rl = InMemoryRateLimiter(clock=clock)
        assert await rl.hit("tenant-a", 1, 60.0) is True
        assert await rl.hit("tenant-b", 1, 60.0) is True
        assert await rl.hit("tenant-a", 1, 60.0) is False  # a exhausted
        assert await rl.hit("tenant-b", 1, 60.0) is False  # b exhausted by B, not A
        clock.advance(60.0)
        assert await rl.hit("tenant-a", 1, 60.0) is True  # both reset independently
        assert await rl.hit("tenant-b", 1, 60.0) is True

    run(scenario())


def test_window_rollover_forgets_the_old_count_completely() -> None:
    """Fixed-window semantics: history does not smear into the next window
    (that would be sliding-window behavior — a different, unclaimed port)."""

    async def scenario() -> None:
        clock = FakeClock()
        clock.now = 1000.0
        rl = InMemoryRateLimiter(clock=clock)
        for _ in range(3):
            await rl.hit("s", 3, 10.0)
        assert await rl.hit("s", 3, 10.0) is False  # exhausted
        clock.now = 1010.0
        # fresh window: the full budget is back, not limit-minus-carryover
        results = [await rl.hit("s", 3, 10.0) for _ in range(3)]
        assert results == [True, True, True]
        assert await rl.hit("s", 3, 10.0) is False

    run(scenario())


def test_fractional_window_seconds_behave() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        clock.now = 100.0
        rl = InMemoryRateLimiter(clock=clock)
        assert await rl.hit("s", 1, 0.5) is True
        clock.now = 100.4
        assert await rl.hit("s", 1, 0.5) is False
        clock.now = 100.5  # next 0.5s window
        assert await rl.hit("s", 1, 0.5) is True

    run(scenario())


# --- 5. load-smoke: concurrent /v1/execute (41 §49 honesty note applies) -----------------
#
# HONESTY NOTE (41 §49): this is an IN-PROCESS ASGI concurrency smoke. It
# proves the composed app keeps requests isolated and accounting exact under
# asyncio concurrency. It is NOT a capacity, latency, or throughput claim —
# no such claim is made anywhere.


def test_concurrent_executions_get_distinct_ids_and_exact_accounting() -> None:
    world = World(script=[{"content": f"r{i}"} for i in range(8)])
    accounting = world.grant_budget(100.0)
    app = world.app()

    async def fan_out() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return list(
                await asyncio.gather(
                    *(client.post("/v1/execute", json={"ask": f"q{i}"}) for i in range(8))
                )
            )

    responses = run(fan_out())
    assert [r.status_code for r in responses] == [200] * 8
    ids = {r.json()["execution_id"] for r in responses}
    assert len(ids) == 8  # no id collision / no cross-request bleed
    for execution_id in ids:
        UUID(execution_id)
    # the adapter saw exactly 8 requests, one per API request, asks intact
    asks = sorted(str(req.payload["ask"]) for req in world.adapter.requests)
    assert asks == sorted(f"q{i}" for i in range(8))
    # settled ledger equals the arithmetic sum — nothing leaked, nothing lost
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 100.0 - 8.0


def test_concurrent_mixed_success_and_failure_settle_exactly() -> None:
    from core.contracts.provider import ProviderErrorCategory
    from tests.api.test_execute_api import _provider_error

    # 4 successes + 4 failures interleaved by the scripted adapter.
    script: list[object] = []
    for i in range(4):
        script.append({"content": f"ok{i}"})
        script.append(_provider_error(ProviderErrorCategory.NON_RETRYABLE_ERROR))
    world = World(script=script)
    accounting = world.grant_budget(100.0)
    app = world.app()

    async def fan_out() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return list(
                await asyncio.gather(
                    *(client.post("/v1/execute", json={"ask": f"q{i}"}) for i in range(8))
                )
            )

    responses = run(fan_out())
    successes = [r for r in responses if r.status_code == 200]
    failures = [r for r in responses if r.status_code != 200]
    assert len(successes) == 4
    assert len(failures) == 4
    for failure in failures:
        body = failure.json()
        assert set(body.keys()) == {"error"}  # unified envelope under concurrency
    # only the 4 successes settle units; the 4 failure holds fully release
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 100.0 - 4.0
