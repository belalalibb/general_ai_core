"""Scheduler — Vision V6 chunk 1 gates (worker that enqueues on time policy).

Deterministic throughout: injected clock / ``tick(now=...)``; the REAL
InMemoryOutbox verifies staging; one end-to-end test drives a staged
occurrence through the EXISTING relay/queue/worker chain to prove the
scheduler is a pure producer over the V2 machinery (P2).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from core.events import ScheduleEntry, Scheduler
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import InMemoryOutbox, OutboxRelay
from core.runtime.ports import QueueMessage
from core.runtime.worker import InMemoryIdempotencyStore, Worker

T0 = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


def _entry(
    entry_id: str = "nightly",
    interval: float = 60.0,
    next_due: datetime = T0,
    stream: str = "executions.requests",
) -> ScheduleEntry:
    return ScheduleEntry(
        entry_id=entry_id,
        stream=stream,
        payload={"kind": "scheduled", "entry": entry_id},
        interval_seconds=interval,
        next_due=next_due,
    )


class TestEntryValidation:
    def test_zero_or_negative_interval_refused(self) -> None:
        for interval in (0.0, -5.0):
            with pytest.raises(ValueError, match="interval_seconds"):
                _entry(interval=interval)

    def test_empty_entry_id_refused(self) -> None:
        with pytest.raises(ValueError, match="entry_id"):
            _entry(entry_id="")

    def test_duplicate_registration_refused(self) -> None:
        scheduler = Scheduler(InMemoryOutbox())
        scheduler.add(_entry())
        with pytest.raises(ValueError, match="already exists"):
            scheduler.add(_entry())

    def test_remove_unknown_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown schedule entry"):
            Scheduler(InMemoryOutbox()).remove("ghost")


class TestTick:
    def test_due_entry_stages_exactly_one_record(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox)
            scheduler.add(_entry())
            staged = await scheduler.tick(now=T0)
            assert len(staged) == 1
            (record,) = await outbox.pending(10)
            assert record.stream == "executions.requests"
            assert record.payload == {"kind": "scheduled", "entry": "nightly"}
            assert record.idempotency_key == f"schedule:nightly:{T0.isoformat()}"

        asyncio.run(run())

    def test_not_due_entry_stages_nothing(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox)
            scheduler.add(_entry(next_due=T0 + timedelta(seconds=1)))
            assert await scheduler.tick(now=T0) == ()
            assert await outbox.pending(10) == ()

        asyncio.run(run())

    def test_next_due_advances_one_interval(self) -> None:
        async def run() -> None:
            scheduler = Scheduler(InMemoryOutbox())
            scheduler.add(_entry(interval=60.0, next_due=T0))
            await scheduler.tick(now=T0)
            (entry,) = scheduler.entries()
            assert entry.next_due == T0 + timedelta(seconds=60)
            # Second tick at the same moment: nothing due.
            assert await scheduler.tick(now=T0) == ()

        asyncio.run(run())

    def test_catch_up_skips_missed_windows_stages_once(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox)
            scheduler.add(_entry(interval=60.0, next_due=T0))
            # The scheduler was down for 10 intervals.
            late = T0 + timedelta(seconds=600)
            staged = await scheduler.tick(now=late)
            assert len(staged) == 1  # ONE occurrence, never a burst
            (entry,) = scheduler.entries()
            assert entry.next_due == T0 + timedelta(seconds=660)
            assert entry.next_due > late

        asyncio.run(run())

    def test_occurrence_idempotency_key_is_deterministic(self) -> None:
        # Two scheduler instances racing the same tick produce records
        # with the SAME key — the Worker collapses them (40 §4.3).
        async def run() -> None:
            keys = []
            for _ in range(2):
                outbox = InMemoryOutbox()
                scheduler = Scheduler(outbox)
                scheduler.add(_entry())
                await scheduler.tick(now=T0)
                (record,) = await outbox.pending(10)
                keys.append(record.idempotency_key)
            assert keys[0] == keys[1]

        asyncio.run(run())

    def test_multiple_entries_independent_schedules(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox)
            scheduler.add(_entry(entry_id="a", next_due=T0))
            scheduler.add(_entry(entry_id="b", next_due=T0 + timedelta(seconds=30)))
            assert len(await scheduler.tick(now=T0)) == 1  # only "a"
            assert (
                len(await scheduler.tick(now=T0 + timedelta(seconds=30))) == 1
            )  # only "b"

        asyncio.run(run())

    def test_injected_clock_is_used_when_now_omitted(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox, clock=lambda: T0)
            scheduler.add(_entry())
            assert len(await scheduler.tick()) == 1

        asyncio.run(run())

    def test_removed_entry_never_fires(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            scheduler = Scheduler(outbox)
            scheduler.add(_entry())
            scheduler.remove("nightly")
            assert await scheduler.tick(now=T0) == ()
            assert scheduler.entries() == ()

        asyncio.run(run())


class TestSchedulerOverTheChain:
    def test_scheduled_occurrence_flows_to_a_worker_exactly_once(self) -> None:
        """Scheduler → outbox → relay → queue → Worker; duplicate tick
        staging (two racing schedulers) collapses at the Worker."""

        async def run() -> None:
            outbox = InMemoryOutbox()
            queue = InMemoryQueue()
            relay = OutboxRelay(outbox, queue)
            handled: list[QueueMessage] = []

            async def handler(message: QueueMessage) -> None:
                handled.append(message)

            worker = Worker(
                queue,
                InMemoryIdempotencyStore(),
                stream="executions.requests",
                group="g",
                consumer="c",
                handler=handler,
            )
            # Two racing schedulers stage the SAME occurrence.
            for _ in range(2):
                scheduler = Scheduler(outbox)
                scheduler.add(_entry())
                await scheduler.tick(now=T0)
            assert await relay.relay_once(10) == 2
            report = await worker.run_once(10)
            assert len(report.processed) == 1
            assert len(report.duplicates) == 1
            assert len(handled) == 1  # exactly once, end to end
            assert handled[0].payload["entry"] == "nightly"

        asyncio.run(run())
