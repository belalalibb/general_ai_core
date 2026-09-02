"""Durable async execution chain (Vision V2 chunk 4) — live gate.

Env-gated (skip-when-absent per 41 §49). The 40 §4.2 chain with the
DURABLE bindings in the loop — everything the hermetic e2e proved, now
over real PostgreSQL:

    PostgresOutbox.append (API enqueue seam)
      → OutboxRelay → InMemoryQueue (bus; ADR-0003 binding is Redis —
        the port is identical, and the queue is NOT what this gate proves)
      → core Worker + PostgresIdempotencyStore (durable dedupe)
      → ExecutionMessageHandler → stored terminal report.

Proves the durability claims specifically:

- a staged message survives in outbox_records until dispatched;
- worker dedupe holds ACROSS worker instances because the processed-key
  row is durable (a second worker with the SAME durable store acks a
  duplicate without re-executing — process-memory dedupe cannot do this);
- the terminal report lands under the pre-assigned execution id.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from apps.api.worker import ExecutionMessageHandler
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import OutboxRelay
from core.runtime.worker import Worker
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import PostgresIdempotencyStore, PostgresOutbox
from infrastructure.db.tables import metadata, outbox_records, worker_idempotency_keys
from tests.api.test_execute_api import World
from tests.api.test_execute_worker_v2 import (
    STREAM,
    _handler,
    _valid_payload,
)

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
        await conn.execute(delete(outbox_records))
        await conn.execute(delete(worker_idempotency_keys))
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(outbox_records))
        await conn.execute(delete(worker_idempotency_keys))
    await eng.dispose()


def _worker(
    queue: InMemoryQueue,
    idempotency: PostgresIdempotencyStore,
    handler: ExecutionMessageHandler,
    consumer: str,
) -> Worker:
    return Worker(
        queue,
        idempotency,
        stream=STREAM,
        group="workers",
        consumer=consumer,
        handler=handler,
    )


@requires_live_postgres
class TestDurableAsyncChain:
    @pytest.mark.asyncio()
    async def test_full_chain_over_durable_outbox_and_idempotency(self, engine: Any) -> None:
        factory = create_session_factory(engine)
        outbox = PostgresOutbox(factory)
        idempotency = PostgresIdempotencyStore(factory)
        world = World()
        execution_id = uuid4()
        payload = _valid_payload(world, execution_id)
        key = f"execute:{execution_id}"

        # API enqueue seam: the durable row exists until dispatched.
        await outbox.append(STREAM, payload, key)
        assert len(await outbox.pending(max_records=10)) == 1

        queue = InMemoryQueue()
        assert await OutboxRelay(outbox, queue).relay_once(10) == 1
        assert await outbox.pending(max_records=10) == ()  # settled

        worker = _worker(queue, idempotency, _handler(world), "w1")
        report = await worker.run_once()
        assert len(report.processed) == 1

        stored = world.store.get(world.principal.tenant_id, execution_id)
        assert stored.execution.id == execution_id
        assert stored.execution.status.value == "succeeded"
        # The processed key is durable truth now.
        assert await idempotency.seen(key)

    @pytest.mark.asyncio()
    async def test_dedupe_holds_across_worker_instances(self, engine: Any) -> None:
        # The durable claim process-memory dedupe cannot make: a SECOND
        # worker (fresh instance, same durable store) sees the processed
        # key and acks the duplicate without re-executing.
        factory = create_session_factory(engine)
        idempotency = PostgresIdempotencyStore(factory)
        world = World()
        payload = _valid_payload(world)
        key = f"execute:{payload['execution_id']}"

        queue = InMemoryQueue()
        await queue.publish(STREAM, payload, key)
        first = _worker(queue, idempotency, _handler(world), "w1")
        assert len((await first.run_once()).processed) == 1

        await queue.publish(STREAM, payload, key)  # duplicate delivery
        second = _worker(queue, idempotency, _handler(world), "w2")
        report = await second.run_once()
        assert len(report.duplicates) == 1
        assert report.processed == []
        # EXACTLY one provider call across both workers.
        assert len(world.adapter.requests) == 1
