"""Scheduler — a worker that ENQUEUES on time policy (Vision V6, frozen def).

NOT a workflow engine (12 §9: "Do not build an ad-hoc workflow engine
inside Core" — and a real engine is a new dependency = ADR STOP). This
is the minimal reading of the frozen clause "schedule = worker that
enqueues executions on time policy":

- A :class:`ScheduleEntry` names WHAT to stage (stream + flat payload —
  the same ``Mapping[str, str]`` constraint as QueuePort) and WHEN
  (``next_due`` + fixed ``interval_seconds``).
- :meth:`Scheduler.tick` is the loop BODY (caller-driven cadence, same
  posture as ``OutboxRelay.relay_once`` / ``Worker.run_once`` — the
  hosting process owns the loop, Lane C composition territory): every
  DUE entry is staged onto the EXISTING OutboxPort; the EXISTING relay/
  queue/worker chain does the rest. The scheduler never executes
  anything itself (P2 — it is a producer, exactly like the API's async
  path in V2).
- Injected ``clock`` (same seam as ExecutionService); ``tick(now=...)``
  overrides for deterministic tests. No wall-clock reads hide inside.

Recorded decisions:

- Occurrence idempotency: the staged idempotency key is
  ``schedule:{entry_id}:{next_due.isoformat()}`` — deterministic per
  occurrence, so a crash between append and bookkeeping (or two
  scheduler processes racing the same tick) collapses to ONE execution
  at the Worker's dedupe (40 §4.3), not two.
- Catch-up policy: after staging, ``next_due`` advances by WHOLE
  intervals until it is strictly in the future — a scheduler that was
  down for ten intervals stages the ONE overdue occurrence, never a
  burst of ten (missed windows are missed; replaying stale work
  uninvited would be fabricated demand).
- ``interval_seconds > 0`` enforced at entry construction (a zero/
  negative interval is a caller defect, refused loudly).
- Entries live in process memory. Durable schedule DEFINITIONS need a
  table — a justified migration WITH the surface that manages them
  (V7+ territory), not a speculative one here; the chain below the
  scheduler is already durable (PostgresOutbox).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from core.contracts.base import utc_now
from core.runtime.outbox import OutboxPort


@dataclass(frozen=True)
class ScheduleEntry:
    """One recurring staging instruction (what + when)."""

    entry_id: str
    stream: str
    payload: Mapping[str, str]
    interval_seconds: float
    next_due: datetime

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")


class Scheduler:
    """Caller-driven tick loop body that stages due entries on the outbox."""

    def __init__(
        self,
        outbox: OutboxPort,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._outbox = outbox
        self._clock: Callable[[], datetime] = clock if clock is not None else utc_now
        self._entries: dict[str, ScheduleEntry] = {}

    def add(self, entry: ScheduleEntry) -> None:
        """Register an entry; a duplicate id is a caller defect (loud)."""
        if entry.entry_id in self._entries:
            raise ValueError(f"schedule entry already exists: {entry.entry_id}")
        self._entries[entry.entry_id] = entry

    def remove(self, entry_id: str) -> None:
        """Deregister; unknown id is a caller defect (loud)."""
        if self._entries.pop(entry_id, None) is None:
            raise ValueError(f"unknown schedule entry: {entry_id}")

    def entries(self) -> tuple[ScheduleEntry, ...]:
        """Current entries, registration order (introspection, P6)."""
        return tuple(self._entries.values())

    async def tick(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Stage every due entry once; returns staged outbox record ids.

        Idempotent per occurrence (see module header); advances each
        staged entry's ``next_due`` past ``now`` by whole intervals.
        """
        moment = self._clock() if now is None else now
        staged: list[str] = []
        for entry_id, entry in list(self._entries.items()):
            if entry.next_due > moment:
                continue
            record_id = await self._outbox.append(
                entry.stream,
                dict(entry.payload),
                f"schedule:{entry.entry_id}:{entry.next_due.isoformat()}",
            )
            staged.append(record_id)
            step = timedelta(seconds=entry.interval_seconds)
            next_due = entry.next_due + step
            while next_due <= moment:  # catch-up: skip missed windows
                next_due += step
            self._entries[entry_id] = replace(entry, next_due=next_due)
        return tuple(staged)
