"""Execution repository — hermetic + live-Postgres gates (Vision V1 chunk 1).

Two layers, same posture as the S3 binding (t073 + live smoke):

1. Hermetic (always run): row↔contract conversion fidelity, SQL compiles
   for the postgresql dialect, named-error semantics, node-ownership
   guard — no server needed.
2. Live (env-gated, skip-when-absent per 41 §49): full round-trips
   against a REAL PostgreSQL — put/get/list, tenant anti-enumeration,
   idempotency-constraint surfacing, upsert, node replacement.

Run the live layer with:

    DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/db \\
    python3 -m pytest tests/infrastructure/test_execution_repository_v1.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    DuplicateIdempotencyKey,
    ExecutionNotFound,
    PostgresExecutionRepository,
)
from infrastructure.db.repositories.executions import (
    _execution_values,
    _node_values,
    _row_to_execution,
    _row_to_node,
)
from infrastructure.db.tables import execution_nodes, executions, metadata

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)

TENANT = uuid4()
OTHER_TENANT = uuid4()
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


def make_execution(
    *,
    execution_id: UUID | None = None,
    tenant_id: UUID = TENANT,
    user_id: UUID | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    idempotency_key: str | None = None,
    created_at: datetime = NOW,
) -> Execution:
    return Execution(
        id=execution_id or uuid4(),
        tenant_id=tenant_id,
        user_id=user_id or uuid4(),
        conversation_id=None,
        request_hash="sha256:abc",
        idempotency_key=idempotency_key,
        status=status,
        strategy=ExecutionStrategy.SINGLE,
        cost_snapshot={"estimated_units": 2},
        created_at=created_at,
        completed_at=created_at,
    )


def make_node(
    execution_id: UUID,
    *,
    node_key: str = "n1",
    input_ref: Any = "opaque-ref",
    output_ref: Any = None,
) -> ExecutionNode:
    return ExecutionNode(
        id=uuid4(),
        execution_id=execution_id,
        node_key=node_key,
        type=ExecutionNodeType.MODEL_CALL,
        status=ExecutionNodeStatus.SUCCEEDED,
        input_ref=input_ref,
        output_ref=output_ref,
        retry_count=0,
        error=None,
    )


# --- Hermetic layer -----------------------------------------------------------


class _Row:
    """Minimal row stand-in: attribute access like a SQLAlchemy Row."""

    def __init__(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class TestHermeticConversion:
    def test_execution_round_trips_through_values_and_row(self) -> None:
        execution = make_execution(idempotency_key="key-1")
        restored = _row_to_execution(_Row(_execution_values(execution)))
        assert restored == execution

    def test_node_round_trips_string_and_json_refs(self) -> None:
        execution_id = uuid4()
        for input_ref, output_ref in (
            ("opaque-ref", None),
            ({"inline": "json"}, {"answer": 42}),
            ("ref", {"mixed": True}),
        ):
            node = make_node(execution_id, input_ref=input_ref, output_ref=output_ref)
            restored = _row_to_node(_Row(_node_values(node)))
            assert restored == node
            # 03 §5 string/json: the SHAPE survives, never coerced.
            assert type(restored.input_ref) is type(node.input_ref)

    def test_values_use_enum_values_not_members(self) -> None:
        # Rows store the closed-set VALUE (matches the CHECK constraints).
        values = _execution_values(make_execution())
        assert values["status"] == "succeeded"
        assert values["strategy"] == "single"
        node_values = _node_values(make_node(uuid4()))
        assert node_values["type"] == "model_call"
        assert node_values["status"] == "succeeded"

    def test_statements_compile_for_postgresql(self) -> None:
        # Offline DDL/DML compile — catches metadata drift without a server.
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(executions).values(_execution_values(make_execution()))
        stmt = stmt.on_conflict_do_update(
            index_elements=[executions.c.id],
            set_={"status": stmt.excluded.status},
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT" in compiled
        select_sql = str(
            select(executions)
            .where(executions.c.tenant_id == TENANT)
            .compile(dialect=postgresql.dialect())
        )
        assert "tenant_id" in select_sql

    def test_not_found_error_is_anti_enumeration_shaped(self) -> None:
        execution_id = uuid4()
        error = ExecutionNotFound(execution_id)
        assert str(error) == f"unknown execution id: {execution_id}"
        assert error.execution_id == execution_id

    @pytest.mark.asyncio
    async def test_put_refuses_cross_wired_node_before_any_io(self) -> None:
        # The guard fires BEFORE any session is opened — a factory that
        # explodes on call proves zero I/O happened.
        def exploding_factory() -> AsyncSession:  # pragma: no cover - must not run
            raise AssertionError("session must not be opened for invalid input")

        repo = PostgresExecutionRepository(exploding_factory)  # type: ignore[arg-type]
        execution = make_execution()
        foreign_node = make_node(uuid4())  # belongs to a DIFFERENT execution
        with pytest.raises(ValueError, match="node does not belong"):
            await repo.put(execution, (foreign_node,))


# --- Live layer (env-gated) ---------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng: AsyncEngine = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(execution_nodes))
        await conn.execute(delete(executions))
    await eng.dispose()


PLAN_ID = uuid4()


@pytest_asyncio.fixture()
async def repo(engine: AsyncEngine) -> PostgresExecutionRepository:
    # Seed FK parents (plan -> tenants) required by the schema (columns
    # verified against infrastructure/db/tables.py, not assumed).
    factory = create_session_factory(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO plans (id, name) VALUES (:id, :name)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"id": PLAN_ID, "name": f"plan-{PLAN_ID}"},
        )
        for tenant_id in (TENANT, OTHER_TENANT):
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, name, type, status, plan_id)"
                    " VALUES (:id, :name, 'personal', 'active', :plan_id)"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {"id": tenant_id, "name": f"t-{tenant_id}", "plan_id": PLAN_ID},
            )
    return PostgresExecutionRepository(factory)


async def _seed_user(engine: AsyncEngine, tenant_id: UUID, user_id: UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, preferred_language,"
                " status, created_at, updated_at)"
                " VALUES (:id, :tenant_id, :email, 'en', 'active', :now, :now)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"{user_id}@example.test",
                "now": NOW,
            },
        )


@requires_live_postgres
class TestLivePostgresRoundTrip:
    @pytest.mark.asyncio
    async def test_put_get_round_trip_with_nodes(
        self, engine: AsyncEngine, repo: PostgresExecutionRepository
    ) -> None:
        execution = make_execution()
        await _seed_user(engine, TENANT, execution.user_id)
        nodes = (
            make_node(execution.id, node_key="a", input_ref={"prompt": "hi"}),
            make_node(execution.id, node_key="b", input_ref="ref-string"),
        )
        await repo.put(execution, nodes)
        record = await repo.get(TENANT, execution.id)
        assert record.execution == execution
        assert record.nodes == nodes  # node_key order: a, b
        # string/json shape preserved through real JSONB
        assert isinstance(record.nodes[0].input_ref, dict)
        assert isinstance(record.nodes[1].input_ref, str)

    @pytest.mark.asyncio
    async def test_foreign_tenant_read_is_byte_identical_to_absent(
        self, engine: AsyncEngine, repo: PostgresExecutionRepository
    ) -> None:
        execution = make_execution()
        await _seed_user(engine, TENANT, execution.user_id)
        await repo.put(execution)
        with pytest.raises(ExecutionNotFound) as foreign:
            await repo.get(OTHER_TENANT, execution.id)
        with pytest.raises(ExecutionNotFound) as absent:
            await repo.get(TENANT, uuid4())
        # Same type, same message SHAPE (20 §6): only the id differs.
        assert type(foreign.value) is type(absent.value)
        assert str(foreign.value).startswith("unknown execution id: ")
        assert str(absent.value).startswith("unknown execution id: ")

    @pytest.mark.asyncio
    async def test_idempotency_conflict_raises_named_error(
        self, engine: AsyncEngine, repo: PostgresExecutionRepository
    ) -> None:
        first = make_execution(idempotency_key="dup-key")
        await _seed_user(engine, TENANT, first.user_id)
        await repo.put(first)
        second = make_execution(idempotency_key="dup-key")
        await _seed_user(engine, TENANT, second.user_id)
        with pytest.raises(DuplicateIdempotencyKey) as exc:
            await repo.put(second)
        assert exc.value.idempotency_key == "dup-key"
        # Same key in ANOTHER tenant is legal (constraint is per-tenant).
        other = make_execution(tenant_id=OTHER_TENANT, idempotency_key="dup-key")
        await _seed_user(engine, OTHER_TENANT, other.user_id)
        await repo.put(other)

    @pytest.mark.asyncio
    async def test_re_put_updates_terminal_fields_and_replaces_nodes(
        self, engine: AsyncEngine, repo: PostgresExecutionRepository
    ) -> None:
        running = make_execution(status=ExecutionStatus.RUNNING)
        await _seed_user(engine, TENANT, running.user_id)
        await repo.put(running, (make_node(running.id, node_key="old"),))
        finished = running.model_copy(
            update={"status": ExecutionStatus.SUCCEEDED, "completed_at": NOW}
        )
        new_nodes = (make_node(running.id, node_key="new"),)
        await repo.put(finished, new_nodes)
        record = await repo.get(TENANT, running.id)
        assert record.execution.status is ExecutionStatus.SUCCEEDED
        assert tuple(n.node_key for n in record.nodes) == ("new",)

    @pytest.mark.asyncio
    async def test_list_filters_scope_and_order(
        self, engine: AsyncEngine, repo: PostgresExecutionRepository
    ) -> None:
        user = uuid4()
        await _seed_user(engine, TENANT, user)
        older = make_execution(user_id=user, created_at=NOW - timedelta(hours=2))
        newer = make_execution(
            user_id=user,
            status=ExecutionStatus.FAILED,
            created_at=NOW - timedelta(hours=1),
        )
        foreign = make_execution(tenant_id=OTHER_TENANT)
        await _seed_user(engine, OTHER_TENANT, foreign.user_id)
        for e in (older, newer, foreign):
            await repo.put(e)

        rows = await repo.list(TENANT)
        assert [r.id for r in rows] == [newer.id, older.id]  # newest first
        assert all(r.tenant_id == TENANT for r in rows)  # foreign absent

        failed = await repo.list(TENANT, status=ExecutionStatus.FAILED)
        assert [r.id for r in failed] == [newer.id]

        by_user = await repo.list(TENANT, initiated_by=user)
        assert len(by_user) == 2

        after = await repo.list(
            TENANT, created_after=NOW - timedelta(hours=1, minutes=30)
        )
        assert [r.id for r in after] == [newer.id]

        limited = await repo.list(TENANT, limit=1)
        assert [r.id for r in limited] == [newer.id]
