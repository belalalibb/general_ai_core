"""API-side rate limiting on POST /v1/execute — 41 §24 "API: rate limits"
(T-IMPL-070, FINAL Phase 21).

Contract authority: 41 §24 API list (rate limits); 20 §3 threat rows
"Unbounded Spend → cost budgets + quotas + backpressure" and "Account
Abuse → leases + rate limits + cooldown"; 10 §9 unified ``rate_limited``
code (429, retryable); 40 §4.5 admission machinery (the EXISTING
RateLimitPort — nothing new invented).

Recorded decisions under test (create_app docstring):

- gate scope is per-tenant ``execute:{tenant_id}``;
- refusal is the unified rate_limited 429 with retryable=true;
- the gate runs FIRST — a 429 leaves ZERO state (no execution stored, no
  idempotency entry, no conversation turn);
- limits are composition-root DATA: default 0 = NOT CONFIGURED ⇒ gate
  absent; rate_limits seam absent ⇒ gate absent.

Hermetic — httpx ASGI transport, injectable-clock InMemoryRateLimiter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
from fastapi import FastAPI

from apps.api.app import create_app
from core.execution.service import ExecutionService
from core.routing import SimpleScoringRouter
from core.runtime.memory import InMemoryRateLimiter
from tests.api.test_execute_api import World, _no_sleep


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class _Clock:
    """Manual clock so window rollover is deterministic (no sleeps)."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def make_app(
    world: World,
    *,
    limiter: InMemoryRateLimiter | None,
    limit: int,
    window: float = 1.0,
) -> FastAPI:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        rate_limits=limiter,
        execute_rate_limit=limit,
        execute_rate_window_seconds=window,
    )


async def _post(app: FastAPI, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/v1/execute", json={"ask": "hello"}, headers=headers or {})


class TestRateLimitGate:
    def test_within_limit_executes_normally(self) -> None:
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(_Clock()), limit=3)
        response = run(_post(app))
        assert response.status_code == 200

    def test_over_limit_returns_unified_429(self) -> None:
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(_Clock()), limit=2)
        assert run(_post(app)).status_code == 200
        assert run(_post(app)).status_code == 200
        third = run(_post(app))
        assert third.status_code == 429
        error = third.json()["error"]
        assert error["code"] == "rate_limited"
        assert error["retryable"] is True
        assert error["details"] == {"scope": "execute"}

    def test_window_rollover_readmits(self) -> None:
        clock = _Clock()
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(clock), limit=1, window=1.0)
        assert run(_post(app)).status_code == 200
        assert run(_post(app)).status_code == 429
        clock.now += 1.0  # next fixed window
        assert run(_post(app)).status_code == 200

    def test_429_leaves_zero_state(self) -> None:
        """A limited request stores NOTHING — no execution, no idempotency
        entry usable for replay (zero-residue posture)."""
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(_Clock()), limit=1)
        assert run(_post(app)).status_code == 200
        stored_after_first = len(world.store)
        denied = run(_post(app, headers={"Idempotency-Key": "k-denied"}))
        assert denied.status_code == 429
        assert len(world.store) == stored_after_first

    def test_gate_precedes_idempotent_replay(self) -> None:
        """The limit applies even to would-be replays — gate runs FIRST."""
        clock = _Clock()
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(clock), limit=1, window=1.0)
        first = run(_post(app, headers={"Idempotency-Key": "k1"}))
        assert first.status_code == 200
        replay_limited = run(_post(app, headers={"Idempotency-Key": "k1"}))
        assert replay_limited.status_code == 429
        clock.now += 1.0
        replay_ok = run(_post(app, headers={"Idempotency-Key": "k1"}))
        assert replay_ok.status_code == 200
        assert replay_ok.json()["execution_id"] == first.json()["execution_id"]


class TestOptInPosture:
    def test_zero_limit_means_not_configured(self) -> None:
        """Composition root must OPT IN: limit=0 ⇒ gate absent."""
        world = World()
        app = make_app(world, limiter=InMemoryRateLimiter(_Clock()), limit=0)
        for _ in range(5):
            assert run(_post(app)).status_code == 200

    def test_absent_seam_means_gate_absent(self) -> None:
        world = World()
        app = make_app(world, limiter=None, limit=100)
        for _ in range(5):
            assert run(_post(app)).status_code == 200

    def test_tenant_scoped_not_global(self) -> None:
        """One tenant exhausting its window must not limit another."""
        limiter = InMemoryRateLimiter(_Clock())
        world_a = World()
        world_b = World()
        app_a = make_app(world_a, limiter=limiter, limit=1)
        app_b = make_app(world_b, limiter=limiter, limit=1)
        assert run(_post(app_a)).status_code == 200
        assert run(_post(app_a)).status_code == 429
        # Different tenant, SAME limiter instance: unaffected.
        assert run(_post(app_b)).status_code == 200
