"""Audit-log repository — hermetic + live gates (V1 chunk 3).

Same two-layer posture as the sibling V1 suites: hermetic conversion /
pre-I/O-validation / append-only-surface tests always run; live
round-trips are gated on DATABASE_URL (skip-when-absent, 41 §49).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from core.audit.errors import InvalidAuditEvent
from core.contracts.audit import AdminChangeRecord, AuditEvent, AuditEventType
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import PostgresAuditLogRepository
from infrastructure.db.repositories.audit import _row_to_event
from infrastructure.db.tables import audit_events, metadata

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)

TENANT = uuid4()
OTHER_TENANT = uuid4()
PLAN_ID = uuid4()
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)

ADMIN_CHANGE = AdminChangeRecord(
    what="set_plan",
    previous_version="v1",
    new_version="v2",
    validation_result="passed",
    impact_preview="2 tenants affected",
    rollback_target="v1",
)


def make_event(
    *,
    event_type: AuditEventType = AuditEventType.LOGIN,
    tenant_id: Any = None,
    occurred_at: datetime = NOW,
    admin_change: AdminChangeRecord | None = None,
) -> AuditEvent:
    return AuditEvent(
        tenant_id=tenant_id or TENANT,
        event_type=event_type,
        actor_id=uuid4(),
        occurred_at=occurred_at,
        details={"ref": "opaque"},
        admin_change=admin_change,
    )


# --- Hermetic layer -----------------------------------------------------------


class _Row:
    def __init__(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(self, key, value)


def _exploding_factory() -> Any:  # pragma: no cover - must not run
    raise AssertionError("no session may be opened for refused input")


class TestHermetic:
    def test_event_row_conversion_with_admin_change(self) -> None:
        event = make_event(
            event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED,
            admin_change=ADMIN_CHANGE,
        )
        row = _Row(
            {
                "id": event.id,
                "tenant_id": event.tenant_id,
                "event_type": event.event_type.value,
                "actor_id": event.actor_id,
                "occurred_at": event.occurred_at,
                "details": event.details,
                "admin_change": event.admin_change.model_dump() if event.admin_change else None,
            }
        )
        assert _row_to_event(row) == event

    def test_event_row_conversion_without_admin_change(self) -> None:
        event = make_event()
        row = _Row(
            {
                "id": event.id,
                "tenant_id": event.tenant_id,
                "event_type": event.event_type.value,
                "actor_id": event.actor_id,
                "occurred_at": event.occurred_at,
                "details": event.details,
                "admin_change": None,
            }
        )
        assert _row_to_event(row) == event

    @pytest.mark.asyncio
    async def test_admin_event_without_record_refused_before_io(self) -> None:
        repo = PostgresAuditLogRepository(_exploding_factory)
        with pytest.raises(InvalidAuditEvent, match="requires an AdminChangeRecord"):
            await repo.append(make_event(event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED))

    @pytest.mark.asyncio
    async def test_non_admin_event_with_record_refused_before_io(self) -> None:
        repo = PostgresAuditLogRepository(_exploding_factory)
        with pytest.raises(InvalidAuditEvent, match="must not carry"):
            await repo.append(make_event(admin_change=ADMIN_CHANGE))

    def test_surface_is_append_only(self) -> None:
        # Port contract: append + tenant-scoped reads ONLY. No mutation
        # method may exist (tamper resistance by construction).
        public = {name for name in dir(PostgresAuditLogRepository) if not name.startswith("_")}
        assert public == {"append", "read", "count"}


# --- Live layer (env-gated) ---------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    eng: AsyncEngine = create_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(audit_events))
    await eng.dispose()


@pytest_asyncio.fixture()
async def repo(engine: AsyncEngine) -> PostgresAuditLogRepository:
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"),
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
    return PostgresAuditLogRepository(create_session_factory(engine))


@requires_live_postgres
class TestLiveAudit:
    @pytest.mark.asyncio
    async def test_append_read_round_trip_chronological(
        self, repo: PostgresAuditLogRepository
    ) -> None:
        late = make_event(occurred_at=NOW + timedelta(minutes=5))
        early = make_event(occurred_at=NOW)
        admin = make_event(
            event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED,
            occurred_at=NOW + timedelta(minutes=2),
            admin_change=ADMIN_CHANGE,
        )
        # Append out of order; read must be chronological.
        for e in (late, early, admin):
            await repo.append(e)
        events = await repo.read(TENANT)
        assert [e.id for e in events] == [early.id, admin.id, late.id]
        # AdminChangeRecord survives the JSONB round-trip intact.
        assert events[1].admin_change == ADMIN_CHANGE
        assert await repo.count(TENANT) == 3

    @pytest.mark.asyncio
    async def test_filter_and_newest_n_limit(self, repo: PostgresAuditLogRepository) -> None:
        events = [make_event(occurred_at=NOW + timedelta(minutes=i)) for i in range(4)]
        logout = make_event(
            event_type=AuditEventType.LOGOUT,
            occurred_at=NOW + timedelta(minutes=10),
        )
        for e in [*events, logout]:
            await repo.append(e)
        only_logins = await repo.read(TENANT, event_type=AuditEventType.LOGIN)
        assert [e.id for e in only_logins] == [e.id for e in events]
        # limit keeps NEWEST N, returned chronologically.
        tail = await repo.read(TENANT, limit=2)
        assert [e.id for e in tail] == [events[3].id, logout.id]

    @pytest.mark.asyncio
    async def test_tenant_isolation_no_cross_read(self, repo: PostgresAuditLogRepository) -> None:
        mine = make_event()
        foreign = make_event(tenant_id=OTHER_TENANT)
        await repo.append(mine)
        await repo.append(foreign)
        assert [e.id for e in await repo.read(TENANT)] == [mine.id]
        assert [e.id for e in await repo.read(OTHER_TENANT)] == [foreign.id]
        assert await repo.count(TENANT) == 1
        assert await repo.count(OTHER_TENANT) == 1
