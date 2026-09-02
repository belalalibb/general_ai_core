"""Async execution worker (Vision V2 chunk 3) — handler + end-to-end chain.

Hermetic throughout (same posture as test_execute_api.py). Two layers:

1. Handler semantics: parse/deny/succeed taxonomy against the recorded
   40 §4.6 mapping — malformed message → PermanentTaskError (dead-letter);
   routing/budget denial → stored FAILED terminal report, message settled;
   success → stored SUCCEEDED report under the PRE-ASSIGNED execution id.
2. The full 40 §4.2 chain over EXISTING core pieces only: API enqueue
   (outbox) → OutboxRelay → InMemoryQueue → core Worker (dedupe via
   IdempotencyPort) → handler → the SAME GET /v1/executions/{id} the sync
   path serves — queued before the worker runs, succeeded after, duplicate
   delivery acked WITHOUT re-execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.worker import ExecutionMessageHandler
from core.execution.service import ExecutionService
from core.routing.router import SimpleScoringRouter
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import InMemoryOutbox, OutboxRelay
from core.runtime.ports import QueueMessage
from core.runtime.worker import (
    InMemoryIdempotencyStore,
    PermanentTaskError,
    Worker,
)
from tests.api.test_execute_api import World

STREAM = "executions.requests"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


def _service_factory(world: World) -> Any:
    """Composition-root bridge: id_factory yields the acked execution id."""

    def factory(execution_id: UUID) -> ExecutionService:
        return ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
            usage=world.usage,
            sleeper=_no_sleep,
            id_factory=lambda: execution_id,
        )

    return factory


def _handler(world: World) -> ExecutionMessageHandler:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    return ExecutionMessageHandler(
        router=router,
        service_factory=_service_factory(world),
        store=world.store,
    )


def _message(payload: dict[str, str], *, delivery: int = 1) -> QueueMessage:
    return QueueMessage(
        message_id="m-1",
        stream=STREAM,
        payload=payload,
        idempotency_key=payload.get("idempotency_key", "k"),
        delivery_count=delivery,
    )


def _valid_payload(world: World, execution_id: UUID | None = None) -> dict[str, str]:
    eid = execution_id or uuid4()
    return {
        "execution_id": str(eid),
        "tenant_id": str(world.principal.tenant_id),
        "user_id": str(world.principal.user_id),
        "request": '{"ask": "hi"}',
        "payload": '{"ask": "hi"}',
        "request_hash": "h" * 64,
    }


# --- layer 1: handler semantics -------------------------------------------------------


def test_success_stores_report_under_the_preassigned_id() -> None:
    world = World()
    execution_id = uuid4()
    handler = _handler(world)
    run(handler(_message(_valid_payload(world, execution_id))))
    report = world.store.get(world.principal.tenant_id, execution_id)
    assert report.execution.id == execution_id
    assert report.execution.status.value == "succeeded"
    # The provider was actually called with the staged payload.
    assert len(world.adapter.requests) == 1


def test_malformed_message_raises_permanent_task_error() -> None:
    world = World()
    handler = _handler(world)
    broken = _valid_payload(world)
    broken["request"] = "{not json"
    with pytest.raises(PermanentTaskError):
        run(handler(_message(broken)))
    missing = _valid_payload(world)
    del missing["tenant_id"]
    with pytest.raises(PermanentTaskError):
        run(handler(_message(missing)))


def test_routing_denial_stores_failed_terminal_report() -> None:
    world = World()
    handler = _handler(world)
    execution_id = uuid4()
    payload = _valid_payload(world, execution_id)
    # An explicit_models policy is unsupported by the router — a denial.
    payload["request"] = (
        '{"ask": "hi", "model_policy": {"type": "explicit_models", "models": [{"model_id": "x"}]}}'
    )
    run(handler(_message(payload)))
    report = world.store.get(world.principal.tenant_id, execution_id)
    assert report.execution.status.value == "failed"
    assert report.execution.cost_snapshot["denied"]["reason"] == "model_unavailable"
    assert world.adapter.requests == []  # denied BEFORE provider work


def test_budget_denial_stores_failed_terminal_report() -> None:
    world = World()
    usage = world.grant_budget(0.0)  # configured, zero budget
    assert usage is not None
    handler = _handler(world)
    execution_id = uuid4()
    run(handler(_message(_valid_payload(world, execution_id))))
    report = world.store.get(world.principal.tenant_id, execution_id)
    assert report.execution.status.value == "failed"
    assert report.execution.cost_snapshot["denied"]["reason"] == "entitlement_exceeded"
    assert world.adapter.requests == []


# --- layer 2: the full 40 §4.2 chain, existing pieces only ----------------------------


def _async_app(world: World, outbox: InMemoryOutbox) -> FastAPI:
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
        outbox=outbox,
    )


def test_end_to_end_async_chain_over_existing_core_pieces() -> None:
    async def scenario() -> None:
        world = World()
        outbox = InMemoryOutbox()
        app = _async_app(world, outbox)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            accepted = await c.post(
                "/v1/execute",
                json={"ask": "hi", "execution_policy": {"async": True}},
            )
            assert accepted.status_code == 202
            poll_url = accepted.json()["poll_url"]

            # Before any worker pass: queued (the placeholder answers).
            before = await c.get(poll_url)
            assert before.json()["status"] == "queued"

            # Relay drains the outbox onto the bus (40 §4.2 publisher).
            queue = InMemoryQueue()
            assert await OutboxRelay(outbox, queue).relay_once(10) == 1

            # The EXISTING core Worker consumes and runs the handler.
            worker = Worker(
                queue,
                InMemoryIdempotencyStore(),
                stream=STREAM,
                group="workers",
                consumer="w1",
                handler=_handler(world),
            )
            report = await worker.run_once()
            assert len(report.processed) == 1

            # The SAME poll URL now answers succeeded with the result.
            after = await c.get(poll_url)
            body = after.json()
            assert body["status"] == "succeeded"
            assert body["execution_id"] == accepted.json()["execution_id"]
            assert body["result"]["type"] == "message"

    run(scenario())


def test_duplicate_delivery_is_acked_without_reexecution() -> None:
    async def scenario() -> None:
        world = World()
        queue = InMemoryQueue()
        payload = _valid_payload(world)
        key = f"execute:{payload['execution_id']}"
        await queue.publish(STREAM, payload, key)
        await queue.publish(STREAM, payload, key)  # duplicate (same key)
        worker = Worker(
            queue,
            InMemoryIdempotencyStore(),
            stream=STREAM,
            group="workers",
            consumer="w1",
            handler=_handler(world),
        )
        report = await worker.run_once(max_messages=2)
        assert len(report.processed) == 1
        assert len(report.duplicates) == 1
        # EXACTLY one provider call — dedupe is the worker's duty (40 §4.3).
        assert len(world.adapter.requests) == 1

    run(scenario())


def test_malformed_message_is_dead_lettered_by_the_worker() -> None:
    async def scenario() -> None:
        world = World()
        queue = InMemoryQueue()
        await queue.publish(STREAM, {"garbage": "yes"}, "k-bad")
        worker = Worker(
            queue,
            InMemoryIdempotencyStore(),
            stream=STREAM,
            group="workers",
            consumer="w1",
            handler=_handler(world),
        )
        report = await worker.run_once()
        assert len(report.dead_lettered) == 1
        assert world.adapter.requests == []

    run(scenario())
