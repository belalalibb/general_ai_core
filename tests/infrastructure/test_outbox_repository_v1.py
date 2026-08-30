"""Durable outbox repository — hermetic + live gates (Vision V2 chunk 1).

Two layers, same posture as the V1 repository suites:

1. Hermetic (always run): row↔record conversion fidelity, SQL compiles
   for the postgresql dialect, non-numeric id refusal BEFORE any I/O,
   surface pin — no server needed.
2. Live (env-gated, skip-when-absent per 41 §49): append/pending/
   mark_dispatched semantics against REAL PostgreSQL — oldest-first
   order, settle-once loudness, payload fidelity, and the EXISTING
   ``OutboxRelay`` (core/runtime/outbox.py) draining the durable outbox
   onto the EXISTING ``InMemoryQueue`` — the 40 §4.2 chain proven over
   the real staging table with zero core changes.

Run the live layer with:

    DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/db \\
    python3 -m pytest tests/infrastructure/test_outbox_repository_v1.py -v
"""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.dialects import postgresql

from core.runtime.errors import RecordNotPending
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import OutboxRecord, OutboxRelay
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import PostgresOutbox
from infrastructure.db.repositories.outbox import _row_to_record
from infrastructure.db.tables import metadata, outbox_records

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


class _Row:
    """Bare attribute carrier standing in for a SQLAlchemy Row."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def _exploding_factory() -> Any:
    class _Boom:
        def __call__(self) -> Any:
            raise AssertionError("session factory must not be touched before validation")

    return _Boom()


class TestHermetic:
    def test_row_to_record_conversion_fidelity(self) -> None:
        row = _Row(
            id=42,
            stream="executions.requests",
            payload={"execution_id": "abc", "tenant_id": "t1"},
            idempotency_key="exec-abc",
        )
        record = _row_to_record(row)
        assert record == OutboxRecord(
            record_id="42",
            stream="executions.requests",
            payload={"execution_id": "abc", "tenant_id": "t1"},
            idempotency_key="exec-abc",
        )
        # BIGINT identity renders as an OPAQUE string id (port contract).
        assert isinstance(record.record_id, str)

    def test_statements_compile_for_postgresql(self) -> None:
        dialect = postgresql.dialect()
        insert = (
            outbox_records.insert()
            .values(stream="s", payload={}, idempotency_key="k")
            .returning(outbox_records.c.id)
        )
        assert "INSERT INTO outbox_records" in str(insert.compile(dialect=dialect))

    @pytest.mark.asyncio()
    async def test_non_numeric_record_id_refused_before_io(self) -> None:
        # mark_dispatched validates the opaque id BEFORE opening a session:
        # a malformed id can never be pending (ids are identity values).
        outbox = PostgresOutbox(_exploding_factory())
        with pytest.raises(RecordNotPending):
            await outbox.mark_dispatched("not-a-number")

    def test_surface_is_exactly_the_port_plus_transaction_seam(self) -> None:
        # OutboxPort {append, pending, mark_dispatched} + the recorded
        # same-transaction seam (append_in_session) — nothing else.
        surface = {n for n in dir(PostgresOutbox) if not n.startswith("_")}
        assert surface == {
            "append",
            "append_in_session",
            "mark_dispatched",
            "pending",
        }


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(outbox_records))
    await eng.dispose()


@pytest_asyncio.fixture()
async def outbox(engine: Any) -> PostgresOutbox:
    async with engine.begin() as conn:
        await conn.execute(delete(outbox_records))
    return PostgresOutbox(create_session_factory(engine))


@requires_live_postgres
class TestLivePostgres:
    @pytest.mark.asyncio()
    async def test_append_pending_dispatch_round_trip(
        self, outbox: PostgresOutbox
    ) -> None:
        rid_1 = await outbox.append(
            "executions.requests", {"execution_id": "e1"}, "k1"
        )
        rid_2 = await outbox.append(
            "executions.requests", {"execution_id": "e2"}, "k2"
        )
        # Oldest first, payload verbatim.
        got = await outbox.pending(max_records=10)
        assert [r.record_id for r in got] == [rid_1, rid_2]
        assert got[0].payload == {"execution_id": "e1"}
        assert got[0].idempotency_key == "k1"
        # Settle the oldest; only the second remains pending.
        await outbox.mark_dispatched(rid_1)
        remaining = await outbox.pending(max_records=10)
        assert [r.record_id for r in remaining] == [rid_2]

    @pytest.mark.asyncio()
    async def test_mark_dispatched_is_settle_once_and_loud(
        self, outbox: PostgresOutbox
    ) -> None:
        rid = await outbox.append("s", {"a": "1"}, "k")
        await outbox.mark_dispatched(rid)
        with pytest.raises(RecordNotPending):
            await outbox.mark_dispatched(rid)  # already settled
        with pytest.raises(RecordNotPending):
            await outbox.mark_dispatched("999999999")  # unknown id

    @pytest.mark.asyncio()
    async def test_pending_respects_max_records(
        self, outbox: PostgresOutbox
    ) -> None:
        for n in range(3):
            await outbox.append("s", {"n": str(n)}, f"k{n}")
        got = await outbox.pending(max_records=2)
        assert len(got) == 2
        assert [r.payload["n"] for r in got] == ["0", "1"]

    @pytest.mark.asyncio()
    async def test_existing_relay_drains_durable_outbox_onto_queue(
        self, outbox: PostgresOutbox
    ) -> None:
        # The 40 §4.2 chain over the REAL staging table: the EXISTING
        # OutboxRelay (unchanged core) publishes durable records onto the
        # EXISTING queue, marking each dispatched after publish.
        queue = InMemoryQueue()
        relay = OutboxRelay(outbox, queue)
        await outbox.append("executions.requests", {"execution_id": "e1"}, "k1")
        await outbox.append("executions.requests", {"execution_id": "e2"}, "k2")
        assert await relay.relay_once(max_records=10) == 2
        assert await outbox.pending(max_records=10) == ()
        # Both messages actually arrived on the bus, in order.
        delivered = await queue.consume(
            "executions.requests", "workers", "w1", max_messages=10
        )
        assert [m.payload["execution_id"] for m in delivered] == ["e1", "e2"]
        assert [m.idempotency_key for m in delivered] == ["k1", "k2"]
