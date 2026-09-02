"""T-IMPL-059 — Async fabric: outbox, worker runtime, admission (41 §13).

Exit-test mapping (41 §13, honest per 41 §49):

- duplicate request → test_duplicate_request_is_settled_without_rerunning_handler
  (+ test_relay_crash_window_duplicate_is_absorbed_by_worker_dedup)
- worker crash → test_worker_crash_leaves_pending_and_peer_recovers
- lease expiry → tests/runtime/test_runtime_ports.py::
  test_expired_lease_is_lost_and_stale_release_raises (pre-existing)
- stale worker → test_stale_worker_delivery_is_reclaimed_and_completed
- retry → test_transient_failure_retries_via_stale_claim_then_succeeds
- DLQ → test_permanent_failure_dead_letters_immediately
  + test_retry_exhaustion_dead_letters (and pre-existing DLQ port tests)
- queue flood → test_queue_flood_refused_at_depth_limit
  + test_tenant_window_flood_refused

All hermetic: in-memory ports, injectable clocks, zero network, zero AI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

import pytest

from core.runtime import (
    AdmissionController,
    ConcurrencyLimiter,
    FairScheduler,
    InMemoryIdempotencyStore,
    InMemoryOutbox,
    InMemoryQueue,
    InMemoryRateLimiter,
    OutboxRelay,
    PermanentTaskError,
    QueueDepthGauge,
    QueueMessage,
    RecordNotPending,
    Worker,
)

STREAM = "jobs"
GROUP = "workers"


def run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


class _Clock:
    """Deterministic monotonic clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Handler:
    """Recording handler with scriptable failures."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_transient_ids: set[str] = set()
        self.fail_permanent_ids: set[str] = set()
        self.always_transient = False

    async def __call__(self, message: QueueMessage) -> None:
        self.calls.append(message.message_id)
        if message.message_id in self.fail_permanent_ids:
            raise PermanentTaskError(message.message_id)
        if self.always_transient or message.message_id in self.fail_transient_ids:
            raise RuntimeError(f"transient:{message.message_id}")


def _fabric(
    clock: _Clock | None = None, *, max_deliveries: int = 3, consumer: str = "w1"
) -> tuple[InMemoryQueue, InMemoryIdempotencyStore, _Handler, Worker]:
    queue = InMemoryQueue(clock=clock or _Clock())
    idem = InMemoryIdempotencyStore()
    handler = _Handler()
    worker = Worker(
        queue,
        idem,
        stream=STREAM,
        group=GROUP,
        consumer=consumer,
        handler=handler,
        max_deliveries=max_deliveries,
    )
    return queue, idem, handler, worker


# ---------------------------------------------------------------- outbox


def test_outbox_append_pending_dispatch_roundtrip() -> None:
    async def scenario() -> None:
        outbox = InMemoryOutbox()
        first = await outbox.append(STREAM, {"k": "1"}, "idem-1")
        second = await outbox.append(STREAM, {"k": "2"}, "idem-2")
        pending = await outbox.pending(max_records=10)
        assert [r.record_id for r in pending] == [first, second]  # oldest first
        await outbox.mark_dispatched(first)
        remaining = await outbox.pending(max_records=10)
        assert [r.record_id for r in remaining] == [second]

    run(scenario())


def test_outbox_mark_dispatched_twice_raises() -> None:
    async def scenario() -> None:
        outbox = InMemoryOutbox()
        record_id = await outbox.append(STREAM, {"k": "1"}, "idem-1")
        await outbox.mark_dispatched(record_id)
        with pytest.raises(RecordNotPending):
            await outbox.mark_dispatched(record_id)

    run(scenario())


def test_relay_publishes_pending_records_to_the_bus_in_order() -> None:
    async def scenario() -> None:
        outbox = InMemoryOutbox()
        queue = InMemoryQueue(clock=_Clock())
        relay = OutboxRelay(outbox, queue)
        await outbox.append(STREAM, {"k": "1"}, "idem-1")
        await outbox.append(STREAM, {"k": "2"}, "idem-2")
        assert await relay.relay_once(max_records=10) == 2
        assert await relay.relay_once(max_records=10) == 0  # drained
        delivered = await queue.consume(STREAM, GROUP, "w1", max_messages=10)
        assert [m.payload["k"] for m in delivered] == ["1", "2"]
        assert [m.idempotency_key for m in delivered] == ["idem-1", "idem-2"]

    run(scenario())


def test_relay_crash_window_duplicate_is_absorbed_by_worker_dedup() -> None:
    """41 §13 duplicate request — the documented at-least-once crash window.

    Relay publishes then crashes before mark_dispatched; next pass
    re-publishes. The consumer's idempotency check (40 §4.3) absorbs it.
    """

    async def scenario() -> None:
        outbox = InMemoryOutbox()
        queue, idem, handler, worker = _fabric()
        await outbox.append(STREAM, {"k": "1"}, "idem-1")
        # Crash window: publish succeeded, mark_dispatched never ran.
        (record,) = await outbox.pending()
        await queue.publish(record.stream, record.payload, record.idempotency_key)
        # Recovery pass relays the still-pending record → duplicate on bus.
        relay = OutboxRelay(outbox, queue)
        assert await relay.relay_once(max_records=10) == 1
        report = await worker.run_once(max_messages=10)
        assert len(report.processed) == 1
        assert len(report.duplicates) == 1
        assert len(handler.calls) == 1  # handler ran exactly once

    run(scenario())


# ---------------------------------------------------------------- worker


def test_worker_processes_acks_and_records_idempotency() -> None:
    async def scenario() -> None:
        queue, idem, handler, worker = _fabric()
        await queue.publish(STREAM, {"k": "1"}, "idem-1")
        report = await worker.run_once()
        assert report.processed and handler.calls == report.processed
        assert await idem.seen("idem-1")
        # Fully settled: nothing left to consume or claim.
        follow_up = await worker.run_once()
        assert not (
            follow_up.processed
            or follow_up.duplicates
            or follow_up.left_pending
            or follow_up.dead_lettered
        )

    run(scenario())


def test_duplicate_request_is_settled_without_rerunning_handler() -> None:
    """41 §13 exit test: duplicate request."""

    async def scenario() -> None:
        queue, _idem, handler, worker = _fabric()
        await queue.publish(STREAM, {"k": "1"}, "idem-same")
        await queue.publish(STREAM, {"k": "1-again"}, "idem-same")
        report = await worker.run_once(max_messages=10)
        assert len(report.processed) == 1
        assert len(report.duplicates) == 1
        assert len(handler.calls) == 1
        # Duplicate was still acked — not stuck pending forever.
        stale = await queue.claim_stale(STREAM, GROUP, "w2", idle_ms=0, max_messages=10)
        assert stale == ()

    run(scenario())


def test_worker_crash_leaves_pending_and_peer_recovers() -> None:
    """41 §13 exit test: worker crash — never acks; peer claims + completes."""

    async def scenario() -> None:
        clock = _Clock()
        queue = InMemoryQueue(clock=clock)
        idem = InMemoryIdempotencyStore()
        # Crashed worker: consumes, then dies before processing/ack.
        await queue.publish(STREAM, {"k": "1"}, "idem-1")
        crashed = await queue.consume(STREAM, GROUP, "dead-worker")
        assert len(crashed) == 1
        clock.now += 60.0  # pending grows stale
        handler = _Handler()
        survivor = Worker(
            queue,
            idem,
            stream=STREAM,
            group=GROUP,
            consumer="survivor",
            handler=handler,
        )
        report = await survivor.recover_once(idle_ms=30_000, max_messages=10)
        assert len(report.processed) == 1
        assert handler.calls == report.processed
        assert await idem.seen("idem-1")

    run(scenario())


def test_stale_worker_delivery_is_reclaimed_and_completed() -> None:
    """41 §13 exit test: stale worker — idle threshold gates the takeover."""

    async def scenario() -> None:
        clock = _Clock()
        queue = InMemoryQueue(clock=clock)
        idem = InMemoryIdempotencyStore()
        await queue.publish(STREAM, {"k": "1"}, "idem-1")
        await queue.consume(STREAM, GROUP, "slow-worker")
        handler = _Handler()
        peer = Worker(
            queue,
            idem,
            stream=STREAM,
            group=GROUP,
            consumer="peer",
            handler=handler,
        )
        # Not yet stale: takeover refused by the idle threshold.
        clock.now += 1.0
        early = await peer.recover_once(idle_ms=30_000, max_messages=10)
        assert not early.processed and not handler.calls
        # Now stale: reclaimed and completed.
        clock.now += 60.0
        late = await peer.recover_once(idle_ms=30_000, max_messages=10)
        assert len(late.processed) == 1 and len(handler.calls) == 1

    run(scenario())


def test_transient_failure_retries_via_stale_claim_then_succeeds() -> None:
    """41 §13 exit test: retry — transient failure left pending, retried."""

    async def scenario() -> None:
        clock = _Clock()
        queue = InMemoryQueue(clock=clock)
        idem = InMemoryIdempotencyStore()
        handler = _Handler()
        worker = Worker(
            queue,
            idem,
            stream=STREAM,
            group=GROUP,
            consumer="w1",
            handler=handler,
        )
        message_id = await queue.publish(STREAM, {"k": "1"}, "idem-1")
        handler.fail_transient_ids.add(message_id)
        first = await worker.run_once()
        assert first.left_pending == [message_id]
        assert not await idem.seen("idem-1")
        # Retry path: heal the fault, stale-claim redelivers with count=2.
        handler.fail_transient_ids.clear()
        clock.now += 60.0
        second = await worker.recover_once(idle_ms=30_000)
        assert second.processed == [message_id]
        assert handler.calls == [message_id, message_id]
        assert await idem.seen("idem-1")

    run(scenario())


def test_permanent_failure_dead_letters_immediately() -> None:
    """41 §13 exit test: DLQ — request-indicting failure never retries."""

    async def scenario() -> None:
        queue, idem, handler, worker = _fabric()
        message_id = await queue.publish(STREAM, {"k": "bad"}, "idem-bad")
        handler.fail_permanent_ids.add(message_id)
        report = await worker.run_once()
        assert report.dead_lettered == [message_id]
        assert not await idem.seen("idem-bad")
        dlq = await queue.consume(f"{STREAM}.dlq", "auditors", "a1", max_messages=10)
        assert [m.idempotency_key for m in dlq] == ["idem-bad"]

    run(scenario())


def test_retry_exhaustion_dead_letters() -> None:
    """40 §4.7 — no infinite retry: max_deliveries bound routes to the DLQ."""

    async def scenario() -> None:
        clock = _Clock()
        queue = InMemoryQueue(clock=clock)
        idem = InMemoryIdempotencyStore()
        handler = _Handler()
        handler.always_transient = True
        worker = Worker(
            queue,
            idem,
            stream=STREAM,
            group=GROUP,
            consumer="w1",
            handler=handler,
            max_deliveries=2,
        )
        message_id = await queue.publish(STREAM, {"k": "1"}, "idem-1")
        first = await worker.run_once()  # delivery 1 → transient, left pending
        assert first.left_pending == [message_id]
        clock.now += 60.0
        second = await worker.recover_once(idle_ms=30_000)  # delivery 2 = cap
        assert second.dead_lettered == [message_id]
        dlq = await queue.consume(f"{STREAM}.dlq", "auditors", "a1", max_messages=10)
        assert len(dlq) == 1

    run(scenario())


def test_worker_rejects_nonpositive_max_deliveries() -> None:
    queue = InMemoryQueue(clock=_Clock())

    async def noop(_message: QueueMessage) -> None:
        return None

    with pytest.raises(ValueError):
        Worker(
            queue,
            InMemoryIdempotencyStore(),
            stream=STREAM,
            group=GROUP,
            consumer="w1",
            handler=noop,
            max_deliveries=0,
        )


# ------------------------------------------------------------- admission


def test_queue_flood_refused_at_depth_limit() -> None:
    """41 §13 exit test: queue flood — depth limit refuses loudly."""

    async def scenario() -> None:
        controller = AdmissionController(InMemoryRateLimiter(_Clock()), QueueDepthGauge())
        admitted = 0
        refused = None
        for _ in range(10):
            decision = await controller.admit(stream=STREAM, tenant_id="t1", max_queue_depth=3)
            if decision.admitted:
                admitted += 1
            else:
                refused = decision
                break
        assert admitted == 3
        assert refused is not None and refused.reason == f"queue_limit:{STREAM}"

    run(scenario())


def test_settled_work_reopens_queue_capacity() -> None:
    async def scenario() -> None:
        gauge = QueueDepthGauge()
        controller = AdmissionController(InMemoryRateLimiter(_Clock()), gauge)
        for _ in range(2):
            assert (
                await controller.admit(stream=STREAM, tenant_id="t1", max_queue_depth=2)
            ).admitted
        blocked = await controller.admit(stream=STREAM, tenant_id="t1", max_queue_depth=2)
        assert not blocked.admitted
        gauge.settled(STREAM)  # one job finished
        reopened = await controller.admit(stream=STREAM, tenant_id="t1", max_queue_depth=2)
        assert reopened.admitted

    run(scenario())


def test_tenant_window_flood_refused() -> None:
    """41 §13 queue flood, tenant axis — per-tenant window (40 §4.5)."""

    async def scenario() -> None:
        clock = _Clock()
        controller = AdmissionController(InMemoryRateLimiter(clock), QueueDepthGauge())

        async def admit(tenant: str) -> bool:
            decision = await controller.admit(
                stream=STREAM, tenant_id=tenant, tenant_limit=2, window_seconds=1.0
            )
            return decision.admitted

        assert await admit("t1") and await admit("t1")
        third = await controller.admit(
            stream=STREAM, tenant_id="t1", tenant_limit=2, window_seconds=1.0
        )
        assert not third.admitted and third.reason == "tenant_window:t1"
        # Another tenant is unaffected; the window resets with time.
        assert await admit("t2")
        clock.now += 1.5
        assert await admit("t1")

    run(scenario())


def test_concurrency_limiter_serves_tenant_and_provider_scopes() -> None:
    limiter = ConcurrencyLimiter()
    assert limiter.try_start("tenant:t1", limit=1)
    assert not limiter.try_start("tenant:t1", limit=1)
    assert limiter.try_start("provider:openai", limit=1)  # scopes independent
    limiter.finish("tenant:t1")
    assert limiter.try_start("tenant:t1", limit=1)
    limiter.finish("never-started")  # idempotent floor at zero
    assert limiter.in_flight("never-started") == 0


def test_fair_scheduler_round_robins_tenants_and_fifo_within() -> None:
    scheduler = FairScheduler()
    scheduler.submit("t1", "a1")
    scheduler.submit("t1", "a2")
    scheduler.submit("t2", "b1")
    order = [scheduler.next_item() for _ in range(3)]
    assert order == [("t1", "a1"), ("t2", "b1"), ("t1", "a2")]
    assert scheduler.next_item() is None
    assert scheduler.backlog() == 0


def test_fair_scheduler_flooding_tenant_cannot_starve_others() -> None:
    scheduler = FairScheduler()
    for i in range(100):
        scheduler.submit("flooder", f"f{i}")
    scheduler.submit("victim", "v1")
    served = [scheduler.next_item() for _ in range(4)]
    tenants = [item[0] for item in served if item is not None]
    assert "victim" in tenants[:2]  # served within one rotation, not after 100


def test_fair_scheduler_priority_tiers_preempt_rotation() -> None:
    scheduler = FairScheduler()
    scheduler.submit("t1", "low", priority=5)
    scheduler.submit("t2", "high", priority=0)
    scheduler.submit("t3", "mid", priority=2)
    order = [scheduler.next_item() for _ in range(3)]
    assert [item[1] for item in order if item is not None] == ["high", "mid", "low"]


# --------------------------------------------------- fabric end-to-end


def test_end_to_end_admit_stage_relay_work_settle() -> None:
    """Full 40 §4.2 chain: admission → outbox → relay → bus → worker → settle."""

    async def scenario() -> None:
        clock = _Clock()
        gauge = QueueDepthGauge()
        controller = AdmissionController(InMemoryRateLimiter(clock), gauge)
        outbox = InMemoryOutbox()
        queue = InMemoryQueue(clock=clock)
        relay = OutboxRelay(outbox, queue)
        idem = InMemoryIdempotencyStore()
        handler = _Handler()
        worker = Worker(
            queue,
            idem,
            stream=STREAM,
            group=GROUP,
            consumer="w1",
            handler=handler,
        )
        decision = await controller.admit(
            stream=STREAM, tenant_id="t1", max_queue_depth=10, tenant_limit=10
        )
        assert decision.admitted
        await outbox.append(STREAM, {"job": "x"}, "idem-x")
        assert await relay.relay_once() == 1
        report = await worker.run_once()
        assert len(report.processed) == 1
        gauge.settled(STREAM)
        assert gauge.depth(STREAM) == 0
        assert await idem.seen("idem-x")

    run(scenario())


def test_fabric_is_fully_testable_without_network_or_ai() -> None:
    """41 §13 posture: every fabric module is pure Core, zero I/O imports."""
    import core.runtime.admission as admission
    import core.runtime.outbox as outbox
    import core.runtime.worker as worker

    for module in (admission, outbox, worker):
        source = open(module.__file__).read()  # noqa: SIM115
        for banned in ("httpx", "redis", "asyncpg", "sqlalchemy", "socket"):
            assert banned not in source, f"{module.__name__} imports {banned}"
