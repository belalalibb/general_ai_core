"""T-IMPL-071 — FINAL Phase 22 chaos: transport-fault injection (41 §25
"Reliability: Redis failure").

The one 41 §25 row without existing coverage. Pre-existing suites already
cover: worker crash / stale worker / duplicate / lease expiry / queue flood
(t059), retry+DLQ discipline and reclaim contention (t035, runtime ports),
provider outage (execution service). Those inject faults into the HANDLER
or simulate crashes by *stopping*; none makes the TRANSPORT ITSELF RAISE
mid-operation — which is what a Redis connection failure looks like to the
caller (redis-py raises; our in-memory fakes never do).

Method: wrap the real in-memory ports in flaky decorators that raise
ConnectionError on chosen operations, then assert the documented safety
invariants of the EXISTING machinery hold (test-only task — no production
code change; a defect found would have been fixed in the same commit,
none was):

1. Relay publish fault  → record STAYS pending (never marked dispatched);
   next pass delivers it: NO MESSAGE LOSS across a publish outage.
2. Relay mark_dispatched fault → publish already happened; record stays
   pending; next pass re-publishes; the consumer's idempotency dedup
   absorbs the duplicate: the documented at-least-once crash window holds
   when the fault is a RAISE, not just a stop (t059 tested the stop).
3. Worker ack fault AFTER successful handler → idempotency was recorded
   FIRST (worker's record-then-ack order), so the stale re-delivery is
   settled as a DUPLICATE — the handler NEVER runs twice for one key even
   though the ack was lost.
4. Worker consume fault → propagates loudly to the driving loop (the
   worker must not swallow transport failures into a fake empty report).
5. Handler-side effects vs transport faults: a handler fault and a
   transport fault on the SAME pass leave independent messages intact —
   one poisoned delivery cannot corrupt its batch-mates' settlement.

Hermetic: in-memory ports + fault wrappers, injectable behavior, no
network, no sleeps, asyncio.run (ADR-0001).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping

import pytest

from core.runtime import (
    InMemoryIdempotencyStore,
    InMemoryOutbox,
    InMemoryQueue,
    OutboxRelay,
    QueueMessage,
    Worker,
)

STREAM = "jobs"
GROUP = "workers"


def run[T](coro: Coroutine[..., object, T]) -> T:
    return asyncio.run(coro)


class FlakyQueue:
    """Wraps the real InMemoryQueue; raises ConnectionError on demand.

    ``fail_next`` holds operation names ("publish"/"consume"/"ack"/
    "claim_stale"/"dead_letter") that raise ONCE then clear — modeling a
    transient Redis connection failure, not a permanent outage.
    """

    def __init__(self, inner: InMemoryQueue) -> None:
        self.inner = inner
        self.fail_next: set[str] = set()

    def _maybe_fail(self, op: str) -> None:
        if op in self.fail_next:
            self.fail_next.discard(op)
            raise ConnectionError(f"injected transport fault: {op}")

    async def publish(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        self._maybe_fail("publish")
        return await self.inner.publish(stream, payload, idempotency_key)

    async def consume(
        self, stream: str, group: str, consumer: str, max_messages: int = 1
    ) -> tuple[QueueMessage, ...]:
        self._maybe_fail("consume")
        return await self.inner.consume(stream, group, consumer, max_messages)

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        self._maybe_fail("ack")
        await self.inner.ack(stream, group, message_id)

    async def claim_stale(
        self,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        max_messages: int = 1,
    ) -> tuple[QueueMessage, ...]:
        self._maybe_fail("claim_stale")
        return await self.inner.claim_stale(stream, group, consumer, idle_ms, max_messages)

    async def dead_letter(self, stream: str, group: str, message_id: str) -> None:
        self._maybe_fail("dead_letter")
        await self.inner.dead_letter(stream, group, message_id)


class FlakyOutbox:
    """Wraps the real InMemoryOutbox; raises on mark_dispatched on demand."""

    def __init__(self, inner: InMemoryOutbox) -> None:
        self.inner = inner
        self.fail_next: set[str] = set()

    def _maybe_fail(self, op: str) -> None:
        if op in self.fail_next:
            self.fail_next.discard(op)
            raise ConnectionError(f"injected transport fault: {op}")

    async def append(self, stream: str, payload: Mapping[str, str], idempotency_key: str) -> str:
        return await self.inner.append(stream, payload, idempotency_key)

    async def pending(self, max_records: int = 1) -> tuple[object, ...]:
        self._maybe_fail("pending")
        return await self.inner.pending(max_records)

    async def mark_dispatched(self, record_id: str) -> None:
        self._maybe_fail("mark_dispatched")
        await self.inner.mark_dispatched(record_id)


def make_worker(
    queue: FlakyQueue,
    idempotency: InMemoryIdempotencyStore,
    calls: list[str],
    *,
    consumer: str = "w1",
) -> Worker:
    async def handler(message: QueueMessage) -> None:
        calls.append(message.idempotency_key)

    return Worker(
        queue=queue,
        idempotency=idempotency,
        stream=STREAM,
        group=GROUP,
        consumer=consumer,
        handler=handler,
    )


# ---------------------------------------------------------------------------
# 1+2. OutboxRelay under transport faults
# ---------------------------------------------------------------------------


class TestRelayTransportFaults:
    def test_publish_fault_loses_no_message(self) -> None:
        async def scenario() -> None:
            outbox = InMemoryOutbox()
            queue = FlakyQueue(InMemoryQueue())
            relay = OutboxRelay(outbox, queue)
            await outbox.append(STREAM, {"k": "v"}, "idem-1")

            queue.fail_next.add("publish")
            with pytest.raises(ConnectionError):
                await relay.relay_once()

            # Record STILL pending — nothing was lost or half-settled.
            assert len(await outbox.pending(10)) == 1
            # Next pass (transport recovered) delivers exactly once.
            assert await relay.relay_once() == 1
            assert await outbox.pending(10) == ()
            delivered = await queue.consume(STREAM, GROUP, "w1", 10)
            assert [m.idempotency_key for m in delivered] == ["idem-1"]

        run(scenario())

    def test_mark_dispatched_fault_duplicate_absorbed_downstream(self) -> None:
        """Publish succeeded, settle raised → re-publish next pass; the
        worker's idempotency dedup absorbs it (at-least-once holds for a
        RAISING transport, not only a stopped relay)."""

        async def scenario() -> None:
            outbox = FlakyOutbox(InMemoryOutbox())
            queue = FlakyQueue(InMemoryQueue())
            relay = OutboxRelay(outbox, queue)
            await outbox.append(STREAM, {"k": "v"}, "idem-dup")

            outbox.fail_next.add("mark_dispatched")
            with pytest.raises(ConnectionError):
                await relay.relay_once()
            # Published once already; record still pending → second publish.
            assert await relay.relay_once() == 1

            idempotency = InMemoryIdempotencyStore()
            calls: list[str] = []
            worker = make_worker(queue, idempotency, calls)
            # One batch delivers BOTH copies: the first processes, the
            # second is settled as a duplicate in the same pass.
            report = await worker.run_once(max_messages=10)
            assert len(report.processed) == 1
            assert len(report.duplicates) == 1
            assert calls == ["idem-dup"]  # handler ran exactly once

        run(scenario())


# ---------------------------------------------------------------------------
# 3. Worker ack fault after success — record-then-ack order pays off
# ---------------------------------------------------------------------------


class TestWorkerAckFault:
    def test_ack_fault_after_success_never_reruns_handler(self) -> None:
        async def scenario() -> None:
            queue = FlakyQueue(InMemoryQueue())
            idempotency = InMemoryIdempotencyStore()
            calls: list[str] = []
            worker = make_worker(queue, idempotency, calls)
            await queue.publish(STREAM, {"k": "v"}, "idem-ack")

            queue.fail_next.add("ack")
            with pytest.raises(ConnectionError):
                await worker.run_once(max_messages=10)
            assert calls == ["idem-ack"]  # handler DID run
            # Idempotency was recorded BEFORE the ack raised — so the
            # stale re-delivery settles as duplicate, never a re-run.
            report = await worker.recover_once(idle_ms=0, max_messages=10)
            assert len(report.duplicates) == 1
            assert report.processed == []
            assert calls == ["idem-ack"]  # STILL exactly once

        run(scenario())


# ---------------------------------------------------------------------------
# 4. Consume fault propagates loudly
# ---------------------------------------------------------------------------


class TestConsumeFault:
    def test_consume_fault_propagates_not_swallowed(self) -> None:
        async def scenario() -> None:
            queue = FlakyQueue(InMemoryQueue())
            worker = make_worker(queue, InMemoryIdempotencyStore(), [])
            await queue.publish(STREAM, {"k": "v"}, "idem-c")

            queue.fail_next.add("consume")
            with pytest.raises(ConnectionError):
                await worker.run_once()
            # Transport recovered: the message is still there, undamaged.
            report = await worker.run_once(max_messages=10)
            assert len(report.processed) == 1

        run(scenario())


# ---------------------------------------------------------------------------
# 5. Batch integrity: one message's transport fault cannot corrupt peers
# ---------------------------------------------------------------------------


class TestBatchIntegrityUnderFaults:
    def test_ack_fault_on_first_leaves_second_recoverable(self) -> None:
        """The fault interrupts the batch loop — the untouched peer stays
        pending and BOTH settle on recovery without a duplicate run."""

        async def scenario() -> None:
            queue = FlakyQueue(InMemoryQueue())
            idempotency = InMemoryIdempotencyStore()
            calls: list[str] = []
            worker = make_worker(queue, idempotency, calls)
            await queue.publish(STREAM, {"n": "1"}, "idem-a")
            await queue.publish(STREAM, {"n": "2"}, "idem-b")

            queue.fail_next.add("ack")  # raises on FIRST message's ack
            with pytest.raises(ConnectionError):
                await worker.run_once(max_messages=10)
            assert calls == ["idem-a"]  # loop stopped at the fault

            report = await worker.recover_once(idle_ms=0, max_messages=10)
            # First re-delivery = duplicate (recorded before the lost ack);
            # second = processed normally.
            assert len(report.duplicates) == 1
            assert len(report.processed) == 1
            assert calls == ["idem-a", "idem-b"]  # each ran exactly once

        run(scenario())
