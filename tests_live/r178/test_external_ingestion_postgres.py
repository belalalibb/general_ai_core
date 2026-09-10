"""R178 actual local PostgreSQL evidence, not an ambient/production DB test.

Run via run_local_postgres.sh. Each test creates its own schema over the real
metadata's complete FK dependency closure. This is NOT a migration rehearsal.
The failing-first closure cases deliberately live beside the live proof, never
as xfail/skip added to the hermetic gate. No training/model provider is called.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.composition.bridge import AsyncBridge
from apps.composition.durability import DurableExecutionStore
from apps.composition.evaluations import DurableEvaluationStore
from core.contracts.base import utc_now
from core.evaluation.errors import DuplicateEvaluation, EvaluationNotFound
from infrastructure.db.repositories.evaluations import PostgresEvaluationRepository
from infrastructure.db.repositories.executions import PostgresExecutionRepository
from infrastructure.db.tables import (
    evaluations,
    executions,
    learning_samples,
    metadata,
    plans,
    tenants,
    users,
)
from tests.api.test_admin_api import World
from tests.api.test_external_evidence_p01_r178 import capture, get
from tests.api.test_promotion_evidence_r177 import SAMPLES, _app, _post, run


@pytest.fixture
def database():
    raw = os.environ.get("R178_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Use tests_live/r178/run_local_postgres.sh for isolated local PostgreSQL")
    url = make_url(raw)
    assert url.drivername == "postgresql+asyncpg" and url.database == "postgres"
    socket = str(url.query.get("host", ""))
    root = os.path.realpath(os.path.join(os.path.dirname(__file__), "../..", ".venv"))
    assert socket.startswith(root + "/r178_pg_") and socket.endswith("/socket")
    assert url.host is None and url.password is None
    schema = "r178_" + uuid4().hex
    bridge = AsyncBridge()
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    names = {"executions", "execution_nodes", "evaluations", "learning_samples"}
    while True:
        parents = {f.column.table.name for n in names for f in metadata.tables[n].foreign_keys}
        if parents <= names:
            break
        names |= parents

    async def setup():
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(
                lambda c: metadata.create_all(c, tables=[metadata.tables[n] for n in names])
            )

    async def close():
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()

    bridge.run(setup())
    try:
        yield bridge, sessions
    finally:
        bridge.run(close())
        bridge.close()


def composed(database):
    bridge, sessions = database
    world = World()
    tenant, actor, plan = world.principal.tenant_id, world.principal.user_id, uuid4()

    async def seed():
        async with sessions.begin() as session:
            await session.execute(plans.insert().values(id=plan, name="r178-test-plan"))
            await session.execute(
                tenants.insert().values(
                    id=tenant,
                    name="r178-test-tenant",
                    type="personal",
                    status="active",
                    plan_id=plan,
                )
            )
            await session.execute(
                users.insert().values(
                    id=actor,
                    tenant_id=tenant,
                    email=f"{actor}@example.invalid",
                    email_verified=True,
                    preferred_language="en",
                    status="active",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )

    bridge.run(seed())
    world.evaluations = DurableEvaluationStore(
        repository=PostgresEvaluationRepository(sessions), bridge=bridge
    )
    store = DurableExecutionStore(repository=PostgresExecutionRepository(sessions), bridge=bridge)
    return world, store, _app(world, strict=True, store=store)


def count(database, table):
    bridge, sessions = database

    async def query():
        async with sessions() as session:
            return await session.scalar(select(func.count()).select_from(table))

    return bridge.run(query())


def test_real_subject_evidence_survive_fresh_stores_and_enforce_integrity(database):
    world, store, app = composed(database)
    tenant = world.principal.tenant_id
    first, second = capture(app, "row.one"), capture(app, "row.two")
    response = run(_post(app, f"{SAMPLES}/{first['id']}/evaluate", {"output": {"answer": "fact"}}))
    assert response.status_code == 200 and response.json()["evaluated"] is True
    records = world.evaluations.list_for_execution(tenant, UUID(first["source_execution_id"]))
    assert len(records) == 1 and count(database, evaluations) == 1
    assert world.evaluations.list_for_execution(tenant, UUID(second["source_execution_id"])) == ()
    bridge, sessions = database
    fresh = DurableExecutionStore(repository=PostgresExecutionRepository(sessions), bridge=bridge)
    receipt = fresh.get(tenant, UUID(first["source_execution_id"]))
    assert receipt.nodes[0].response is None
    assert receipt.nodes[0].node.input_ref["sample_id"] == first["id"]
    assert receipt.nodes[0].node == store.get(tenant, receipt.execution.id).nodes[0].node
    with pytest.raises(KeyError):
        fresh.get(uuid4(), receipt.execution.id)
    again = DurableEvaluationStore(repository=PostgresEvaluationRepository(sessions), bridge=bridge)
    assert again.get(tenant, records[0].id) == records[0]
    with pytest.raises(EvaluationNotFound):
        again.get(uuid4(), records[0].id)
    with pytest.raises(DuplicateEvaluation):
        again.record(records[0])
    with pytest.raises(IntegrityError):
        again.record(records[0].model_copy(update={"id": uuid4(), "execution_id": uuid4()}))
    assert count(database, evaluations) == 1

    async def remove_subject():
        async with sessions.begin() as session:
            await session.execute(delete(executions).where(executions.c.id == receipt.execution.id))

    with pytest.raises(IntegrityError):
        bridge.run(remove_subject())
    assert count(database, executions) == 2


def test_missing_actor_fk_leaves_no_sample_or_execution(database):
    world, _, app = composed(database)
    lifecycle = app.state.learning_lifecycle_service
    with pytest.raises(IntegrityError):
        lifecycle.capture_external(
            world.principal.tenant_id,
            actor_id=uuid4(),
            knowledge_key="absent",
            knowledge_value={"fact": "x"},
        )
    assert lifecycle.list_samples(world.principal.tenant_id) == ()
    assert count(database, executions) == count(database, evaluations) == 0


def test_backend_closure_sample_survives_recomposition(database):
    world, _, app = composed(database)
    sample = capture(app)
    bridge, sessions = database
    fresh = DurableExecutionStore(repository=PostgresExecutionRepository(sessions), bridge=bridge)
    restarted = _app(world, strict=True, store=fresh)
    # Subject and evaluation durability alone cannot satisfy this assertion.
    response = run(get(restarted, f"{SAMPLES}/{sample['id']}"))
    assert response.status_code == 200
    assert response.json()["sample"]["id"] == sample["id"]
    assert count(database, learning_samples) == 1
