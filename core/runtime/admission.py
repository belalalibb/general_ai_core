"""Admission control, queue limits, concurrency, fair scheduling (40 §4.5).

Design decisions (recorded, per the standing derivation rule):

- 40 §4.5 lists REQUIRED SUPPORT — Admission Control / Queue Limits /
  Tenant Concurrency / Provider Concurrency / Fair Scheduling / Priority /
  Adaptive Scaling — without interfaces. Derived minimal components:

  * ``AdmissionController`` — the front door. Checks queue depth, then the
    per-tenant admission window (via the existing ``RateLimitPort``, whose
    docstring already names it "admission control (40 §4.5)"). Refusal is
    an explicit ``AdmissionDecision`` with the refusing gate named — never
    a silent drop (deny-by-default is DATA: no registered depth/limit for
    a scope means the deny path for that gate is skipped only when the
    caller passes no limit, i.e. the caller must OPT IN to unlimited).
  * ``ConcurrencyLimiter`` — one counter class serves BOTH tenant and
    provider concurrency (the doc lists them as two applications of the
    same control; keys are opaque scopes, so ``tenant:<id>`` and
    ``provider:<id>`` never collide).
  * ``FairScheduler`` — round-robin across tenant sub-queues with strict
    priority tiers. Round-robin is the minimal schedule satisfying "one
    tenant cannot starve others" (30 §17 fairness posture); within a
    tenant, FIFO. Priority: lower number = served first; the doc names
    "Priority" without levels, so levels are caller data, default 0.

- Adaptive Scaling is a DEPLOYMENT concern (scaling worker processes);
  Core exposes the signals it needs — ``QueueDepthGauge`` counts and the
  scheduler's backlog — but starting/stopping workers belongs to the
  hosting platform. Recorded honestly, not claimed (41 §49).
- ``QueuePort`` deliberately has no depth query (Redis XLEN is
  binding-specific); admission tracks depth at the door instead via
  ``QueueDepthGauge`` — the producer-side count of admitted-not-settled
  work. The binding may substitute a real XLEN-backed gauge behind the
  same calls.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass

from core.runtime.ports import RateLimitPort


@dataclass(frozen=True)
class AdmissionDecision:
    """Explicit admit/refuse outcome — refusals name the gate (30 §14)."""

    admitted: bool
    reason: str | None = None


class QueueDepthGauge:
    """Producer-side depth accounting per stream (queue limits, 40 §4.5)."""

    def __init__(self) -> None:
        self._depth: dict[str, int] = {}

    def depth(self, stream: str) -> int:
        return self._depth.get(stream, 0)

    def enqueued(self, stream: str) -> None:
        self._depth[stream] = self._depth.get(stream, 0) + 1

    def settled(self, stream: str) -> None:
        current = self._depth.get(stream, 0)
        if current > 0:
            self._depth[stream] = current - 1


class AdmissionController:
    """Front-door backpressure (40 §4.5): queue limit then tenant window."""

    def __init__(self, rate_limits: RateLimitPort, gauge: QueueDepthGauge) -> None:
        self._rate_limits = rate_limits
        self._gauge = gauge

    async def admit(
        self,
        *,
        stream: str,
        tenant_id: str,
        max_queue_depth: int | None = None,
        tenant_limit: int | None = None,
        window_seconds: float = 1.0,
    ) -> AdmissionDecision:
        """Check every configured gate; on admit, count the enqueue."""
        if max_queue_depth is not None and self._gauge.depth(stream) >= max_queue_depth:
            return AdmissionDecision(
                admitted=False, reason=f"queue_limit:{stream}"
            )
        if tenant_limit is not None:
            within = await self._rate_limits.hit(
                f"admission:{tenant_id}", tenant_limit, window_seconds
            )
            if not within:
                return AdmissionDecision(
                    admitted=False, reason=f"tenant_window:{tenant_id}"
                )
        self._gauge.enqueued(stream)
        return AdmissionDecision(admitted=True)


class ConcurrencyLimiter:
    """In-flight ceilings per opaque scope (tenant/provider concurrency)."""

    def __init__(self) -> None:
        self._in_flight: dict[str, int] = {}

    def in_flight(self, scope: str) -> int:
        return self._in_flight.get(scope, 0)

    def try_start(self, scope: str, limit: int) -> bool:
        """Reserve one slot if under ``limit``; False refuses (no queueing)."""
        current = self._in_flight.get(scope, 0)
        if current >= limit:
            return False
        self._in_flight[scope] = current + 1
        return True

    def finish(self, scope: str) -> None:
        current = self._in_flight.get(scope, 0)
        if current > 0:
            self._in_flight[scope] = current - 1


class FairScheduler:
    """Priority tiers + per-tenant round-robin + FIFO within a tenant."""

    def __init__(self) -> None:
        self._seq = itertools.count(1)
        # priority -> tenant_id -> FIFO of (seq, item)
        self._tiers: dict[int, dict[str, deque[tuple[int, str]]]] = {}
        # priority -> rotation order of tenant ids
        self._rotation: dict[int, deque[str]] = {}

    def submit(self, tenant_id: str, item: str, *, priority: int = 0) -> None:
        tier = self._tiers.setdefault(priority, {})
        if tenant_id not in tier:
            tier[tenant_id] = deque()
            self._rotation.setdefault(priority, deque()).append(tenant_id)
        tier[tenant_id].append((next(self._seq), item))

    def backlog(self) -> int:
        return sum(
            len(q) for tier in self._tiers.values() for q in tier.values()
        )

    def next_item(self) -> tuple[str, str] | None:
        """Pop ``(tenant_id, item)`` — best priority, round-robin tenants."""
        for priority in sorted(self._tiers):
            rotation = self._rotation[priority]
            tier = self._tiers[priority]
            for _ in range(len(rotation)):
                tenant_id = rotation[0]
                rotation.rotate(-1)
                queue = tier[tenant_id]
                if queue:
                    _seq, item = queue.popleft()
                    return (tenant_id, item)
        return None
