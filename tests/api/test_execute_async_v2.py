"""Async execute path (Vision V2; 10 §4/§5/§10) — hermetic API gates.

Same harness posture as test_execute_api.py: httpx ASGI transport, fake
adapters, asyncio.run. What is verified is the FLIP:

- outbox seam ABSENT ⇒ async=true keeps the original loud rejection
  (already pinned by test_execute_api.py — the behavior is UNCHANGED).
- outbox seam PRESENT ⇒ async=true returns 202 ExecuteAsyncAccepted
  (queued + poll URL — the 10 §4 contract shape, no contract changes),
  stages EXACTLY ONE durable message carrying the verbatim request, and
  calls NO provider (the worker owns execution).
- GET /v1/executions/{id} answers "queued" from the ack onward (10 §5).
- Idempotency-Key replay of an in-flight async execution returns the
  SAME 202 ack and does NOT enqueue again (10 §10 over 10 §4).
- sync requests through an outbox-bearing app stay sync (the flip is
  opt-in PER REQUEST via execution_policy.async).
- admission still precedes enqueue: an unknown role fails 422 with an
  EMPTY outbox (a message for an inadmissible request must never exist).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
from fastapi import FastAPI

from core.runtime.outbox import InMemoryOutbox
from tests.api.test_execute_api import World


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _app_with_outbox(world: World, outbox: InMemoryOutbox) -> FastAPI:
    from apps.api import create_app
    from core.execution.service import ExecutionService
    from core.routing.router import SimpleScoringRouter

    router = SimpleScoringRouter(world.providers, world.models, world.bindings)

    async def _no_sleep(seconds: float) -> None:
        return None

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
        outbox=outbox,
    )


async def _post(
    app: FastAPI, body: dict[str, Any], headers: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/v1/execute", json=body, headers=headers or {})


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


def test_async_returns_202_accepted_with_poll_url() -> None:
    world = World()
    outbox = InMemoryOutbox()
    app = _app_with_outbox(world, outbox)
    response = run(_post(app, {"ask": "hi", "execution_policy": {"async": True}}))
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["poll_url"] == f"/v1/executions/{payload['execution_id']}"
    # No provider was ever called — the worker owns execution.
    assert world.adapter.requests == []


def test_async_stages_exactly_one_durable_message() -> None:
    world = World()
    outbox = InMemoryOutbox()
    app = _app_with_outbox(world, outbox)
    response = run(_post(app, {"ask": "durable?", "execution_policy": {"async": True}}))
    execution_id = response.json()["execution_id"]
    staged = run(outbox.pending(max_records=10))
    assert len(staged) == 1
    record = staged[0]
    assert record.stream == "executions.requests"
    assert record.idempotency_key == f"execute:{execution_id}"
    assert record.payload["execution_id"] == execution_id
    assert record.payload["tenant_id"] == str(world.principal.tenant_id)
    assert record.payload["user_id"] == str(world.principal.user_id)
    # The verbatim contract request rides the message — the worker
    # re-validates and re-routes from THIS, not from a stale decision.
    assert '"ask":"durable?"' in record.payload["request"].replace(" ", "")
    assert "request_hash" in record.payload


def test_status_endpoint_answers_queued_from_the_ack_onward() -> None:
    world = World()
    app = _app_with_outbox(world, InMemoryOutbox())
    accepted = run(_post(app, {"ask": "hi", "execution_policy": {"async": True}}))
    poll_url = accepted.json()["poll_url"]
    status = run(_get(app, poll_url))
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "queued"
    assert body["execution_id"] == accepted.json()["execution_id"]
    # Queued: no result, no error — the 10 §5 shape before the worker runs.
    assert "result" not in body and "error" not in body


def test_idempotent_replay_of_in_flight_async_returns_same_ack_no_second_enqueue() -> None:
    world = World()
    outbox = InMemoryOutbox()
    app = _app_with_outbox(world, outbox)
    body = {"ask": "hi", "execution_policy": {"async": True}}
    headers = {"Idempotency-Key": "abc-123"}
    first = run(_post(app, body, headers))
    second = run(_post(app, body, headers))
    assert second.status_code == 202
    assert second.json()["execution_id"] == first.json()["execution_id"]
    # ONE staged message — the replay must never enqueue twice (10 §10).
    assert len(run(outbox.pending(max_records=10))) == 1


def test_sync_requests_stay_sync_with_outbox_bound() -> None:
    # The flip is per-request: an outbox-bearing app still serves plain
    # sync requests exactly as before (200 + result, nothing staged).
    world = World()
    outbox = InMemoryOutbox()
    app = _app_with_outbox(world, outbox)
    response = run(_post(app, {"ask": "hi"}))
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert run(outbox.pending(max_records=10)) == ()


def test_admission_precedes_enqueue_unknown_role_stages_nothing() -> None:
    # A request that fails admission must leave ZERO durable residue —
    # the queue only ever carries admitted work (20 §4 posture).
    world = World()
    outbox = InMemoryOutbox()
    app = _app_with_outbox(world, outbox)
    body = {
        "ask": "hi",
        "role": {"name": "no-such-role"},
        "execution_policy": {"async": True},
    }
    response = run(_post(app, body))
    assert response.status_code == 422
    assert run(outbox.pending(max_records=10)) == ()
