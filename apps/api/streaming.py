"""SSE progress at the API surface (Vision V6 chunk 2; 10 §11 events).

Frozen clause: "SSE progress at the API surface". Recorded design:

- The surface is ``GET /v1/executions/{execution_id}/events`` — a
  ``text/event-stream`` response that emits the EXISTING 10 §11
  StreamEvent contracts (closed 6-type vocabulary, discriminated union
  in core/contracts/execute.py — never redefined) DERIVED from the
  stored ExecutionReport (P6: events are projections of stored truth,
  never fabricated narration).
- PROGRESS, not token deltas: ``delta`` events require streaming
  provider adapters, which do not exist — a delta stream synthesized
  from a terminal result would be fabricated capability (41 §49).
  Consequently ``execution_policy.stream=true`` on POST /v1/execute
  KEEPS its recorded loud rejection — inline result streaming is a
  different (absent) capability; this endpoint reports lifecycle
  progress for executions the caller already started (typically async
  V2 runs being processed by the worker).
- For a QUEUED/RUNNING execution the stream polls the store (injectable
  sleeper — deterministic tests) and emits node events INCREMENTALLY as
  they appear, closing with ``final`` or ``error`` once terminal, or an
  ``error`` event naming the timeout if the budget elapses (bounded —
  never an infinite hold, 40 §4.5 posture).
- Event derivation is PURE (:func:`derive_events`) and identical for
  terminal and in-flight reports: execution_started → (node_started,
  node_completed)* → final|error. A node currently RUNNING contributes
  only its node_started half; the completion event joins the stream
  when the stored trail shows a terminal node state.
- Tenant scoping identical to GET /v1/executions/{id}: the store's
  tenant-scoped read; unknown and foreign ids are the same 404 BEFORE
  any stream starts (20 §6).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from core.contracts.execute import (
    ErrorEvent,
    ExecutionStartedEvent,
    ExecutionStatus,
    FinalEvent,
    NodeCompletedEvent,
    NodeStartedEvent,
)
from core.execution.service import ExecutionReport

# One event as it rides the wire (SSE data frame).
SseEvent = (
    ExecutionStartedEvent
    | NodeStartedEvent
    | NodeCompletedEvent
    | FinalEvent
    | ErrorEvent
)

Sleeper = Callable[[float], Awaitable[None]]

_TERMINAL_NODE_STATES = frozenset({"succeeded", "failed", "skipped", "cancelled"})
_TERMINAL_EXECUTION_STATES = frozenset(
    {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)


def sse_frame(event: SseEvent) -> str:
    """Serialize one 10 §11 event as an SSE data frame (verbatim JSON)."""
    return f"data: {json.dumps(event.model_dump(mode='json'), sort_keys=True)}\n\n"


def is_terminal(report: ExecutionReport) -> bool:
    return report.execution.status in _TERMINAL_EXECUTION_STATES


def derive_events(report: ExecutionReport) -> list[SseEvent]:
    """Project the stored report onto the 10 §11 event sequence (pure).

    Deterministic: same report ⇒ same list. The terminal tail (final /
    error) appears ONLY when the execution itself is terminal.
    """
    events: list[SseEvent] = [
        ExecutionStartedEvent(
            type="execution_started", execution_id=str(report.execution.id)
        )
    ]
    for entry in report.nodes:
        events.append(
            NodeStartedEvent(type="node_started", node=entry.node.node_key)
        )
        if entry.node.status.value in _TERMINAL_NODE_STATES:
            events.append(
                NodeCompletedEvent(type="node_completed", node=entry.node.node_key)
            )
    status = report.execution.status
    if status is ExecutionStatus.SUCCEEDED:
        events.append(FinalEvent(type="final", result=report.final_output or {}))
    elif status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        last_error = None
        for entry in reversed(report.nodes):
            if entry.node.error is not None:
                last_error = entry.node.error
                break
        events.append(
            ErrorEvent(
                type="error",
                error=last_error
                or {"status": status.value, "execution_id": str(report.execution.id)},
            )
        )
    return events


async def event_stream(
    load: Callable[[], ExecutionReport],
    *,
    poll_interval_seconds: float = 0.5,
    timeout_seconds: float = 60.0,
    sleeper: Sleeper | None = None,
) -> AsyncIterator[str]:
    """Async generator of SSE frames until the execution is terminal.

    ``load`` re-reads the STORED report (tenant scoping already applied
    by the caller's closure). Already-emitted events are never repeated:
    each pass emits only the derived-sequence suffix beyond what was
    sent (the derivation is append-only for a progressing execution —
    nodes only gain terminal states and the tail only appears at the
    end). Bounded by ``timeout_seconds``: on expiry an ``error`` event
    names the timeout and the stream closes (never an infinite hold).
    """
    sleep = sleeper if sleeper is not None else asyncio.sleep
    emitted = 0
    waited = 0.0
    while True:
        report = load()
        events = derive_events(report)
        for event in events[emitted:]:
            yield sse_frame(event)
        emitted = len(events)
        if is_terminal(report):
            return
        if waited >= timeout_seconds:
            yield sse_frame(
                ErrorEvent(
                    type="error",
                    error={
                        "reason": "stream_timeout",
                        "detail": (
                            "execution did not reach a terminal state within "
                            f"{timeout_seconds} seconds; poll GET /v1/executions/{{id}}"
                        ),
                    },
                )
            )
            return
        await sleep(poll_interval_seconds)
        waited += poll_interval_seconds
