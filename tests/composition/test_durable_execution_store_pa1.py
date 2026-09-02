"""P-A.1 — DurableExecutionStore + AsyncBridge tests.

Two layers (the recorded V1 repository-test pattern, 41 §49):

1. Hermetic: a FAKE async repository (dict-backed, same semantics as
   ``PostgresExecutionRepository``'s surface) exercised through the REAL
   ``AsyncBridge`` — proves write-through ordering, read-through
   reconstruction, tenant isolation, named-refusal translation, and the
   restart story (new store instance, same repository) WITHOUT a
   database and WITHOUT faking a green Postgres round-trip.
2. Live (env-gated, skip-when-absent): the real repository against a
   real Postgres proves restart-parity end to end — state survives a
   simulated process restart (fresh store + fresh cache over the same
   database).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.api.store import (
    ExecutionNotFound,
    ExecutionStorePort,
    InMemoryExecutionStore,
)
from apps.composition.bridge import AsyncBridge, BridgeClosed
from apps.composition.durability import (
    DurableExecutionStore,
    report_from_record,
)
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.contracts.provider import (
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateResponse,
)
from core.execution.service import ExecutionReport, NodeReport
from infrastructure.db.repositories.errors import (
    ExecutionNotFound as RepositoryExecutionNotFound,
)
from infrastructure.db.repositories.executions import ExecutionRecord

TENANT = uuid4()
OTHER_TENANT = uuid4()
NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def make_execution(
    *,
    execution_id: UUID | None = None,
    tenant_id: UUID = TENANT,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    created_at: datetime = NOW,
) -> Execution:
    return Execution(
        id=execution_id or uuid4(),
        tenant_id=tenant_id,
        user_id=uuid4(),
        conversation_id=None,
        request_hash="sha256:abc",
        idempotency_key=None,
        status=status,
        strategy=ExecutionStrategy.SINGLE,
        cost_snapshot={"estimated_units": 1},
        created_at=created_at,
        completed_at=created_at,
    )


def make_node(
    execution_id: UUID,
    *,
    node_key: str = "single",
    status: ExecutionNodeStatus = ExecutionNodeStatus.SUCCEEDED,
    output_ref: Any = None,
    error: dict[str, Any] | None = None,
) -> ExecutionNode:
    return ExecutionNode(
        id=uuid4(),
        execution_id=execution_id,
        node_key=node_key,
        type=ExecutionNodeType.MODEL_CALL,
        status=status,
        input_ref={"prompt": "hi"},
        output_ref=output_ref,
        retry_count=0,
        error=error,
    )


def make_report(execution: Execution, nodes: tuple[ExecutionNode, ...]) -> ExecutionReport:
    node_reports = tuple(
        NodeReport(
            node=node,
            attempts=(),
            response=(
                ProviderGenerateResponse(
                    request_id=uuid4(),
                    succeeded=True,
                    output=node.output_ref,
                )
                if isinstance(node.output_ref, dict)
                else None
            ),
        )
        for node in nodes
    )
    return ExecutionReport(
        execution=execution,
        nodes=node_reports,
        status_history=(ExecutionStatus.QUEUED, execution.status),
    )


class FakeExecutionRepository:
    """Dict-backed async repository with the V1 surface semantics.

    Mirrors ``PostgresExecutionRepository``: tenant-scoped get (foreign
    == absent, same named refusal), list returns ROOT entities only,
    newest-first, strict after/before, limit keeps newest N.
    """

    def __init__(self) -> None:
        self.records: dict[UUID, ExecutionRecord] = {}
        self.put_calls = 0

    async def put(self, execution: Execution, nodes: tuple[ExecutionNode, ...] = ()) -> None:
        self.put_calls += 1
        self.records[execution.id] = ExecutionRecord(execution=execution, nodes=nodes)

    async def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionRecord:
        record = self.records.get(execution_id)
        if record is None or record.execution.tenant_id != tenant_id:
            raise RepositoryExecutionNotFound(execution_id)
        return record

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[Execution, ...]:
        rows = [
            record.execution
            for record in self.records.values()
            if record.execution.tenant_id == tenant_id
            and (status is None or record.execution.status is status)
            and (initiated_by is None or record.execution.user_id == initiated_by)
            and (created_after is None or record.execution.created_at > created_after)
            and (created_before is None or record.execution.created_at < created_before)
        ]
        rows.sort(key=lambda e: e.created_at, reverse=True)
        if limit is not None:
            rows = rows[:limit]
        return tuple(rows)


class ExplodingRepository(FakeExecutionRepository):
    """put() fails — proves write-through never caches unpersisted state."""

    async def put(self, execution: Execution, nodes: tuple[ExecutionNode, ...] = ()) -> None:
        raise RuntimeError("database unavailable")


@pytest.fixture()
def bridge():  # type: ignore[no-untyped-def]
    with AsyncBridge() as b:
        yield b


@pytest.fixture()
def repository() -> FakeExecutionRepository:
    return FakeExecutionRepository()


@pytest.fixture()
def store(bridge: AsyncBridge, repository: FakeExecutionRepository) -> DurableExecutionStore:
    return DurableExecutionStore(repository=repository, bridge=bridge)


class TestBridge:
    def test_runs_coroutine_and_returns_result(self, bridge: AsyncBridge) -> None:
        async def add(a: int, b: int) -> int:
            return a + b

        assert bridge.run(add(2, 3)) == 5

    def test_exceptions_propagate_verbatim(self, bridge: AsyncBridge) -> None:
        marker = uuid4()

        async def boom() -> None:
            raise RepositoryExecutionNotFound(marker)

        with pytest.raises(RepositoryExecutionNotFound) as excinfo:
            bridge.run(boom())
        assert excinfo.value.execution_id == marker

    def test_usable_from_inside_a_running_event_loop(self, bridge: AsyncBridge) -> None:
        """The FastAPI-handler scenario: sync store call inside async code."""
        import asyncio

        async def inner_value() -> str:
            return "from-bridge-loop"

        async def handler() -> str:
            # Sync-looking call while THIS loop is running — must not
            # deadlock because the coroutine runs on the bridge's loop.
            return bridge.run(inner_value())

        assert asyncio.run(handler()) == "from-bridge-loop"

    def test_closed_bridge_refuses_loudly(self) -> None:
        bridge = AsyncBridge()
        bridge.close()

        async def never() -> None:  # pragma: no cover - must not run
            raise AssertionError("must not execute")

        with pytest.raises(BridgeClosed):
            bridge.run(never())

    def test_close_is_idempotent(self) -> None:
        bridge = AsyncBridge()
        bridge.close()
        bridge.close()  # second close must not raise


class TestWriteThrough:
    def test_put_persists_then_serves_full_fidelity(
        self, store: DurableExecutionStore, repository: FakeExecutionRepository
    ) -> None:
        execution = make_execution()
        node = make_node(execution.id, output_ref={"answer": "42"})
        report = make_report(execution, (node,))
        store.put(report)
        assert repository.put_calls == 1
        assert repository.records[execution.id].nodes == (node,)
        # Same-process read is the FULL report (cache hit), including
        # the parts the database does not keep (status_history).
        got = store.get(TENANT, execution.id)
        assert got is report

    def test_durable_failure_caches_nothing(self, bridge: AsyncBridge) -> None:
        exploding = ExplodingRepository()
        store = DurableExecutionStore(repository=exploding, bridge=bridge)
        execution = make_execution()
        report = make_report(execution, (make_node(execution.id),))
        with pytest.raises(RuntimeError, match="database unavailable"):
            store.put(report)
        # The cache must NOT serve state the database never accepted:
        # a working repository underneath now proves the miss path.
        with pytest.raises(ExecutionNotFound):
            store.get(TENANT, execution.id)


class TestReadThroughReconstruction:
    def test_restart_recovers_succeeded_execution(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        """THE restart-parity story: new store instance, same repository."""
        first = DurableExecutionStore(repository=repository, bridge=bridge)
        execution = make_execution()
        node = make_node(execution.id, output_ref={"answer": "42"})
        first.put(make_report(execution, (node,)))

        # "Restart": a brand-new store with an EMPTY cache.
        second = DurableExecutionStore(repository=repository, bridge=bridge)
        got = second.get(TENANT, execution.id)
        assert got.execution == execution
        assert got.execution.status is ExecutionStatus.SUCCEEDED
        # final_output — the API-visible result — survives the restart.
        assert got.final_output == {"answer": "42"}
        # Honest degradation: attempts were never durably promised.
        assert got.nodes[0].attempts == ()
        assert got.status_history == (ExecutionStatus.SUCCEEDED,)

    def test_restart_recovers_failed_execution_error(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        error_dump = ProviderError(
            category=ProviderErrorCategory.RATE_LIMITED,
            retryable=True,
            safe_message="Provider rate limited the request.",
        ).model_dump(mode="json", exclude_none=True)
        execution = make_execution(status=ExecutionStatus.FAILED)
        node = make_node(
            execution.id,
            status=ExecutionNodeStatus.FAILED,
            error=error_dump,
        )
        first = DurableExecutionStore(repository=repository, bridge=bridge)
        first.put(make_report(execution, (node,)))

        second = DurableExecutionStore(repository=repository, bridge=bridge)
        got = second.get(TENANT, execution.id)
        assert got.execution.status is ExecutionStatus.FAILED
        # The stored normalized error (the fact streaming.py reads)
        # survives on the node — nothing invented, nothing lost.
        assert got.nodes[0].node.error == error_dump
        assert got.final_output is None

    def test_reconstruction_progress_matches_live_shape(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        """_progress() derives from node statuses — stored facts."""
        execution = make_execution()
        nodes = (
            make_node(execution.id, node_key="stage-0", output_ref={"a": 1}),
            make_node(execution.id, node_key="stage-1", output_ref={"b": 2}),
        )
        DurableExecutionStore(repository=repository, bridge=bridge).put(
            make_report(execution, nodes)
        )
        got = DurableExecutionStore(repository=repository, bridge=bridge).get(TENANT, execution.id)
        terminal = ("succeeded", "failed", "skipped")
        done = sum(1 for e in got.nodes if e.node.status.value in terminal)
        assert done == 2 and len(got.nodes) == 2  # → 100% progress

    def test_recovered_report_is_recached(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        execution = make_execution()
        DurableExecutionStore(repository=repository, bridge=bridge).put(
            make_report(execution, (make_node(execution.id),))
        )
        cache = InMemoryExecutionStore()
        second = DurableExecutionStore(repository=repository, bridge=bridge, cache=cache)
        assert len(cache) == 0
        second.get(TENANT, execution.id)
        assert len(cache) == 1  # repeated polls stay off the database


class TestTenantIsolation:
    def test_foreign_tenant_get_is_not_found_after_restart(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        """20 §6 through BOTH layers: cache miss → repo refusal → app error."""
        execution = make_execution(tenant_id=TENANT)
        DurableExecutionStore(repository=repository, bridge=bridge).put(make_report(execution, ()))
        second = DurableExecutionStore(repository=repository, bridge=bridge)
        with pytest.raises(ExecutionNotFound) as excinfo:
            second.get(OTHER_TENANT, execution.id)
        # The app-level type route handlers already catch — and the id
        # matches, indistinguishable from truly absent.
        assert excinfo.value.execution_id == execution.id

    def test_list_never_leaks_foreign_rows(self, store: DurableExecutionStore) -> None:
        mine = make_execution(tenant_id=TENANT)
        foreign = make_execution(tenant_id=OTHER_TENANT)
        store.put(make_report(mine, ()))
        store.put(make_report(foreign, ()))
        rows = store.list(TENANT)
        assert [r.execution.id for r in rows] == [mine.id]


class TestListParity:
    def test_list_survives_restart_with_filters(
        self, bridge: AsyncBridge, repository: FakeExecutionRepository
    ) -> None:
        older = make_execution(created_at=NOW - timedelta(hours=2))
        newer = make_execution(created_at=NOW - timedelta(hours=1))
        failed = make_execution(
            status=ExecutionStatus.FAILED, created_at=NOW - timedelta(minutes=30)
        )
        first = DurableExecutionStore(repository=repository, bridge=bridge)
        for execution in (older, newer, failed):
            first.put(make_report(execution, ()))

        second = DurableExecutionStore(repository=repository, bridge=bridge)
        everything = second.list(TENANT)
        assert [r.execution.id for r in everything] == [
            failed.id,
            newer.id,
            older.id,
        ]  # newest first
        only_ok = second.list(TENANT, status=ExecutionStatus.SUCCEEDED)
        assert [r.execution.id for r in only_ok] == [newer.id, older.id]
        limited = second.list(TENANT, limit=1)
        assert [r.execution.id for r in limited] == [failed.id]

    def test_cached_rows_present_full_reports(self, store: DurableExecutionStore) -> None:
        execution = make_execution()
        node = make_node(execution.id, output_ref={"answer": "42"})
        report = make_report(execution, (node,))
        store.put(report)
        rows = store.list(TENANT)
        assert rows[0] is report  # cache hit — full fidelity, not a stub


class TestPortConformance:
    def test_both_stores_satisfy_the_port(self, store: DurableExecutionStore) -> None:
        """create_app/worker annotations accept either binding (P2)."""
        durable: ExecutionStorePort = store
        in_memory: ExecutionStorePort = InMemoryExecutionStore()
        assert durable is not None and in_memory is not None

    def test_report_from_record_handles_empty_nodes(self) -> None:
        execution = make_execution(status=ExecutionStatus.FAILED)
        report = report_from_record(ExecutionRecord(execution=execution, nodes=()))
        assert report.nodes == ()
        assert report.final_output is None
        assert report.status_history == (ExecutionStatus.FAILED,)


# --- Live layer (env-gated, skip-when-absent per 41 §49) ----------------------

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


@requires_live_postgres
class TestLiveRestartParity:
    def test_execution_survives_simulated_restart(self) -> None:
        """Full P-A.1 acceptance: durable truth outlives the 'process'.

        ALL database work (setup, store calls, cleanup) runs on the
        bridge's single loop — asyncpg pools are loop-bound, so the
        engine must live and die on ONE loop (the same discipline the
        production composition follows: the bridge loop IS the DB loop).
        """
        from sqlalchemy import text

        from apps.composition.database import (
            build_database_bindings,
            database_settings_from_env,
        )
        from infrastructure.db.tables import metadata

        settings = database_settings_from_env()
        assert settings is not None

        execution = make_execution()

        with AsyncBridge() as bridge:
            bindings = build_database_bindings(settings)

            async def prepare() -> None:
                async with bindings.engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)
                    plan_id = uuid4()
                    await conn.execute(
                        text(
                            "INSERT INTO plans (id, name) VALUES (:id, :name)"
                            " ON CONFLICT (id) DO NOTHING"
                        ),
                        {"id": plan_id, "name": f"plan-{plan_id}"},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO tenants (id, name, type, status,"
                            " plan_id) VALUES (:id, :name, 'personal',"
                            " 'active', :plan) ON CONFLICT (id) DO NOTHING"
                        ),
                        {"id": TENANT, "name": f"t-{TENANT}", "plan": plan_id},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, tenant_id, email,"
                            " preferred_language, status, created_at,"
                            " updated_at) VALUES (:id, :tenant, :email, 'en',"
                            " 'active', :now, :now)"
                            " ON CONFLICT (id) DO NOTHING"
                        ),
                        {
                            "id": execution.user_id,
                            "tenant": TENANT,
                            "email": f"{execution.user_id}@example.test",
                            "now": NOW,
                        },
                    )

            async def cleanup() -> None:
                async with bindings.engine.begin() as conn:
                    await conn.execute(
                        text("DELETE FROM execution_nodes WHERE execution_id = :id"),
                        {"id": execution.id},
                    )
                    await conn.execute(
                        text("DELETE FROM executions WHERE id = :id"),
                        {"id": execution.id},
                    )
                await bindings.engine.dispose()

            bridge.run(prepare())
            try:
                node = make_node(execution.id, output_ref={"answer": "live"})
                first = DurableExecutionStore(repository=bindings.executions, bridge=bridge)
                first.put(make_report(execution, (node,)))
                # "Restart": fresh store + fresh cache, same database.
                second = DurableExecutionStore(repository=bindings.executions, bridge=bridge)
                got = second.get(TENANT, execution.id)
                assert got.final_output == {"answer": "live"}
                assert got.execution.status is ExecutionStatus.SUCCEEDED
            finally:
                bridge.run(cleanup())
