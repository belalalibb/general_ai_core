"""Usage + idempotency repositories — hermetic + live gates (Vision V1 chunk 4).

Two layers, same posture as the execution/memory/audit repository suites:

1. Hermetic (always run): row↔contract conversion fidelity, SQL compiles
   for the postgresql dialect, pre-I/O refusals via exploding factory,
   surface pins — no server needed.
2. Live (env-gated, skip-when-absent per 41 §49): the full in-memory
   refusal ladder re-verified against REAL PostgreSQL — configure/
   reserve/settle/refund/fail/get/summary, ledger-derived accounting,
   plan-change history preservation, idempotency-key durability.

Run the live layer with:

    DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/db \\
    python3 -m pytest tests/infrastructure/test_usage_repository_v1.py -v
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from core.contracts.usage import UsageLedger, UsageLedgerStatus
from core.usage.errors import (
    BudgetExceeded,
    EntitlementNotConfigured,
    ReservationAlreadyResolved,
    ReservationNotFound,
)
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    PostgresIdempotencyStore,
    PostgresUsageRepository,
)
from infrastructure.db.repositories.usage import _row_to_ledger
from infrastructure.db.tables import (
    metadata,
    usage_ledger,
    worker_idempotency_keys,
)

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)

TENANT = uuid4()
OTHER_TENANT = uuid4()


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
    def test_row_to_ledger_conversion_fidelity(self) -> None:
        row = _Row(
            id=uuid4(),
            tenant_id=TENANT,
            execution_id=uuid4(),
            units_reserved=5.0,
            units_settled=3.5,
            modality_costs={"image_generations": 2},
            status="settled",
        )
        entry = _row_to_ledger(row)
        assert isinstance(entry, UsageLedger)
        assert entry.status is UsageLedgerStatus.SETTLED
        assert entry.units_reserved == 5.0
        assert entry.units_settled == 3.5
        assert entry.modality_costs == {"image_generations": 2}

    def test_ledger_sql_compiles_for_postgresql(self) -> None:
        stmt = usage_ledger.insert().values(
            id=uuid4(),
            tenant_id=TENANT,
            execution_id=uuid4(),
            units_reserved=1.0,
            units_settled=0.0,
            modality_costs={},
            status="reserved",
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "INSERT INTO usage_ledger" in compiled
        point_read = select(worker_idempotency_keys.c.key).where(
            worker_idempotency_keys.c.key == "k"
        )
        assert "worker_idempotency_keys" in str(
            point_read.compile(dialect=postgresql.dialect())
        )

    @pytest.mark.asyncio
    async def test_negative_units_refused_before_any_io(self) -> None:
        repo = PostgresUsageRepository(_exploding_factory())
        with pytest.raises(ValueError, match="reservation units must be >= 0"):
            await repo.reserve(TENANT, uuid4(), -1.0)
        with pytest.raises(ValueError, match="units_settled must be >= 0"):
            await repo.settle(uuid4(), -0.5)
        with pytest.raises(ValueError, match="units_settled must be >= 0"):
            await repo.fail(uuid4(), -0.5)

    @pytest.mark.asyncio
    async def test_negative_limit_refused_before_any_io(self) -> None:
        repo = PostgresUsageRepository(_exploding_factory())
        with pytest.raises(ValueError, match="task_units_limit must be >= 0"):
            await repo.configure_tenant(TENANT, plan="pro", task_units_limit=-1.0)

    def test_usage_repository_surface_is_port_plus_admin_seam(self) -> None:
        public = {
            name
            for name in dir(PostgresUsageRepository)
            if not name.startswith("_")
        }
        # UsageAccountingPort methods + the configure_tenant admin seam
        # (core/usage/memory.py surface, verbatim) — nothing else.
        assert public == {
            "configure_tenant",
            "reserve",
            "settle",
            "refund",
            "fail",
            "get",
            "summary",
        }

    def test_idempotency_store_surface_is_exactly_the_port(self) -> None:
        public = {
            name
            for name in dir(PostgresIdempotencyStore)
            if not name.startswith("_")
        }
        assert public == {"seen", "record"}


# --- Live layer -----------------------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng: AsyncEngine = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(usage_ledger))
        await conn.execute(delete(worker_idempotency_keys))
    await eng.dispose()


SEED_PLAN_ID = uuid4()


@pytest_asyncio.fixture()
async def repo(engine: AsyncEngine) -> PostgresUsageRepository:
    # Seed FK parents (plan -> tenants) required by the schema (columns
    # verified against infrastructure/db/tables.py, not assumed).
    factory = create_session_factory(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO plans (id, name) VALUES (:id, :name)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"id": SEED_PLAN_ID, "name": f"seed-{SEED_PLAN_ID}"},
        )
        for tenant_id in (TENANT, OTHER_TENANT):
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, name, type, status, plan_id)"
                    " VALUES (:id, :name, 'personal', 'active', :plan_id)"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {"id": tenant_id, "name": f"t-{tenant_id}", "plan_id": SEED_PLAN_ID},
            )
    return PostgresUsageRepository(factory)


async def _seed_execution(engine: AsyncEngine, tenant_id: UUID) -> UUID:
    """Ledger rows FK executions (RESTRICT) — mint a real parent row."""
    execution_id = uuid4()
    user_id = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, preferred_language,"
                " status, created_at, updated_at)"
                " VALUES (:id, :tenant_id, :email, 'en', 'active', now(), now())"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"{user_id}@example.test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO executions (id, tenant_id, user_id, request_hash,"
                " status, strategy, cost_snapshot, created_at)"
                " VALUES (:id, :tenant_id, :user_id, 'sha256:x', 'queued',"
                " 'single', '{}', now())"
            ),
            {"id": execution_id, "tenant_id": tenant_id, "user_id": user_id},
        )
    return execution_id


@requires_live_postgres
class TestLiveUsageAccounting:
    @pytest.mark.asyncio
    async def test_reserve_settle_round_trip_and_summary_math(
        self, engine: AsyncEngine, repo: PostgresUsageRepository
    ) -> None:
        await repo.configure_tenant(
            TENANT,
            plan="pro",
            task_units_limit=10.0,
            modality_limits={"image_generations": 5},
        )
        execution_id = await _seed_execution(engine, TENANT)
        entry = await repo.reserve(TENANT, execution_id, 4.0)
        assert entry.status is UsageLedgerStatus.RESERVED
        assert entry.units_reserved == 4.0

        mid = await repo.summary(TENANT)
        assert mid.plan == "pro"
        assert mid.task_units.limit == 10.0
        assert mid.task_units.used == 4.0  # held counts as used
        assert mid.task_units.remaining == 6.0
        assert mid.modality_limits == {"image_generations": 5}

        settled = await repo.settle(
            execution_id, 3.0, modality_costs={"image_generations": 1}
        )
        assert settled.status is UsageLedgerStatus.SETTLED
        assert settled.units_settled == 3.0
        assert settled.modality_costs == {"image_generations": 1}

        after = await repo.summary(TENANT)
        assert after.task_units.used == 3.0  # hold released, consumption booked
        assert after.task_units.remaining == 7.0

        fetched = await repo.get(execution_id)
        assert fetched == settled

    @pytest.mark.asyncio
    async def test_refusal_ladder_matches_in_memory_semantics(
        self, engine: AsyncEngine, repo: PostgresUsageRepository
    ) -> None:
        # Deny-by-default: seeded plan has empty limits -> task_units == 0,
        # so any positive reservation is denied (limits grant nothing they
        # do not state); an unknown tenant has NO entitlement at all.
        unknown_tenant = uuid4()
        with pytest.raises(EntitlementNotConfigured):
            await repo.reserve(unknown_tenant, uuid4(), 1.0)
        with pytest.raises(EntitlementNotConfigured):
            await repo.summary(unknown_tenant)

        execution_id = await _seed_execution(engine, TENANT)
        await repo.configure_tenant(TENANT, plan="pro", task_units_limit=5.0)
        with pytest.raises(BudgetExceeded) as denied:
            await repo.reserve(TENANT, execution_id, 6.0)
        assert denied.value.requested == 6.0
        assert denied.value.remaining == 5.0

        await repo.reserve(TENANT, execution_id, 2.0)
        with pytest.raises(ReservationAlreadyResolved) as double:
            await repo.reserve(TENANT, execution_id, 1.0)
        assert double.value.status == "reserved"

        await repo.refund(execution_id)
        with pytest.raises(ReservationAlreadyResolved) as resettle:
            await repo.settle(execution_id, 1.0)
        assert resettle.value.status == "refunded"

        with pytest.raises(ReservationNotFound):
            await repo.get(uuid4())
        with pytest.raises(ReservationNotFound):
            await repo.settle(uuid4(), 1.0)

    @pytest.mark.asyncio
    async def test_plan_change_preserves_accounting_history(
        self, engine: AsyncEngine, repo: PostgresUsageRepository
    ) -> None:
        await repo.configure_tenant(TENANT, plan="starter", task_units_limit=5.0)
        execution_id = await _seed_execution(engine, TENANT)
        await repo.reserve(TENANT, execution_id, 2.0)
        await repo.fail(execution_id, 1.5)

        # Upgrade: consumed history survives (in-memory invariant —
        # ledger-derived accounting makes it automatic).
        await repo.configure_tenant(TENANT, plan="enterprise", task_units_limit=100.0)
        after = await repo.summary(TENANT)
        assert after.plan == "enterprise"
        assert after.task_units.limit == 100.0
        assert after.task_units.used == 1.5
        assert after.task_units.remaining == 98.5

    @pytest.mark.asyncio
    async def test_tenant_isolation_of_budgets_and_ledger(
        self, engine: AsyncEngine, repo: PostgresUsageRepository
    ) -> None:
        await repo.configure_tenant(TENANT, plan="pro-a", task_units_limit=10.0)
        await repo.configure_tenant(OTHER_TENANT, plan="pro-b", task_units_limit=3.0)
        execution_id = await _seed_execution(engine, TENANT)
        await repo.reserve(TENANT, execution_id, 8.0)

        # The other tenant's budget is untouched by TENANT's consumption.
        other = await repo.summary(OTHER_TENANT)
        assert other.plan == "pro-b"
        assert other.task_units.used == 0.0
        assert other.task_units.remaining == 3.0

    @pytest.mark.asyncio
    async def test_configure_tenant_refuses_unknown_tenant(
        self, repo: PostgresUsageRepository
    ) -> None:
        ghost = uuid4()
        with pytest.raises(ValueError, match=f"unknown tenant: {ghost}"):
            await repo.configure_tenant(ghost, plan="pro", task_units_limit=1.0)


@requires_live_postgres
class TestLiveIdempotencyStore:
    @pytest.mark.asyncio
    async def test_seen_record_and_duplicate_record_is_noop(
        self, engine: AsyncEngine
    ) -> None:
        store = PostgresIdempotencyStore(create_session_factory(engine))
        key = f"task:{uuid4()}"
        assert await store.seen(key) is False
        await store.record(key)
        assert await store.seen(key) is True
        # Duplicate record is a no-op by constraint — never an error.
        await store.record(key)
        assert await store.seen(key) is True
        assert await store.seen(f"other:{uuid4()}") is False
