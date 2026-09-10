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
    if "learning_sample_custody" in metadata.tables:
        names.add("learning_sample_custody")
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


@pytest.fixture
def runtime_database(database):
    """A fresh database for the actual build_runtime_profile, not test rewiring.

    All runtime metadata except the unrelated pgvector embedding table is created.
    No vector query/migration/extension behavior is claimed. The parent fixture
    already proved this connection targets the private workspace-only cluster.
    """
    from apps.composition.runtime import build_runtime_profile  # noqa: F401

    bridge, _ = database
    raw = make_url(os.environ["R178_TEST_DATABASE_URL"])
    name = "r178_runtime_" + uuid4().hex
    catalog = create_async_engine(raw, isolation_level="AUTOCOMMIT")
    url = raw.set(database=name)
    engine = create_async_engine(url)

    async def setup():
        async with catalog.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda c: metadata.create_all(
                    c, tables=[t for n, t in metadata.tables.items() if n != "memory_embeddings"]
                )
            )

    async def cleanup():
        await engine.dispose()
        try:
            async with catalog.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        finally:
            await catalog.dispose()

    try:
        bridge.run(setup())
        yield url.render_as_string(hide_password=False)
    finally:
        bridge.run(cleanup())


def test_backend_closure_actual_runtime_restart_preserves_sample(runtime_database):
    import httpx

    from apps.composition.runtime import build_runtime_profile
    from tests.api.test_self_evolution_r161 import _admin
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL

    env = {"DATABASE_URL": runtime_database, "ADMIN_EMAILS": ADMIN_EMAIL}
    profiles = []

    async def request(profile, headers, method, path, body=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
        ) as client:
            return await client.request(method, path, headers=headers, json=body)

    try:
        first = build_runtime_profile(environ=env)
        profiles.append(first)
        assert first.durable and first.demo_principal is None
        headers, _ = _admin(first)
        captured = run(
            request(
                first,
                headers,
                "POST",
                SAMPLES,
                {
                    "knowledge_key": "runtime.restart",
                    "knowledge_value": {"answer": "fact"},
                },
            )
        )
        assert captured.status_code == 201
        sample = captured.json()
        graded = run(
            request(
                first,
                headers,
                "POST",
                f"{SAMPLES}/{sample['id']}/evaluate",
                {
                    "output": {"answer": "fact"},
                },
            )
        )
        assert graded.status_code == 200 and graded.json()["evaluated"] is True
        first.bridge.run(first.bindings.engine.dispose())
        first.bridge.close()
        profiles.remove(first)
        second = build_runtime_profile(environ=env)
        profiles.append(second)
        # Reuse the REAL durable session: no demo principal or replacement actor.
        receipt = run(
            request(second, headers, "GET", f"/v1/executions/{sample['source_execution_id']}")
        )
        assert receipt.status_code == 200
        records = run(
            request(
                second,
                headers,
                "GET",
                f"/v1/admin/executions/{sample['source_execution_id']}/evaluations",
            )
        )
        assert records.status_code == 200 and len(records.json()["evaluations"]) == 1
        restored = run(request(second, headers, "GET", f"{SAMPLES}/{sample['id']}"))
        assert restored.status_code == 200
        assert restored.json()["sample"]["id"] == sample["id"]
    finally:
        for profile in profiles:
            run(profile.release_adapters())
            profile.bridge.run(profile.bindings.engine.dispose())
            profile.bridge.close()


def custody_candidate(world, *, key=None, value=None, policy=None, rights=None):
    from apps.api.ingestion import ExternalIngestionRecorder
    from apps.api.store import InMemoryExecutionStore
    from core.contracts.learning import LearningSample
    from core.learning.storage import RetentionPolicy, prepare_capture

    tenant, actor, sample_id = world.principal.tenant_id, world.principal.user_id, uuid4()
    value = {"answer": "fact"} if value is None else value
    policy = policy or RetentionPolicy(tenant, uuid4(), 3600)
    rights = rights or uuid4()
    prepared = prepare_capture(
        policy=policy,
        tenant_id=tenant,
        policy_id=policy.policy_id,
        rights_ref=rights,
        knowledge_key="fact",
        knowledge_value=value,
        now=utc_now(),
    )
    memory = InMemoryExecutionStore()
    execution_id = ExternalIngestionRecorder(memory).record(tenant, sample_id, actor, "fact", value)
    report = memory.get(tenant, execution_id)
    return dict(
        sample=LearningSample(id=sample_id, tenant_id=tenant, source_execution_id=execution_id),
        execution=report.execution,
        nodes=tuple(n.node for n in report.nodes),
        prepared=prepared,
        policy=policy,
        rights_ref=rights,
        idempotency_key=key or uuid4(),
        source_kind="external",
    )


def test_custody_atomic_roundtrip_and_same_key_retry(database):
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    first = database[0].run(repo.capture(**args))
    second = database[0].run(
        repo.capture(
            **custody_candidate(
                world, key=args["idempotency_key"], policy=args["policy"], rights=args["rights_ref"]
            )
        )
    )
    assert first["sample_id"] == second["sample_id"]
    assert first["source_execution_id"] == second["source_execution_id"]
    assert count(database, learning_samples) == count(database, executions) == 1
    loaded = database[0].run(repo.get(world.principal.tenant_id, first["sample_id"]))
    assert loaded["payload"] == args["prepared"].payload


def test_custody_changed_content_conflicts(database):
    from core.learning.storage import LearningStorageConflict
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    first = database[0].run(repo.capture(**args))
    with pytest.raises(LearningStorageConflict):
        database[0].run(
            repo.capture(
                **custody_candidate(
                    world,
                    key=args["idempotency_key"],
                    value={"answer": "changed"},
                    policy=args["policy"],
                    rights=args["rights_ref"],
                )
            )
        )
    assert (
        database[0].run(repo.get(world.principal.tenant_id, first["sample_id"]))["payload"]
        == args["prepared"].payload
    )


def test_custody_quarantine_never_writes_raw_secret(database):
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_sample_custody

    world, _, _ = composed(database)
    marker = "ghp_" + "X" * 36
    record = database[0].run(
        LearningCustodyRepository(database[1]).capture(
            **custody_candidate(world, value={marker: "private"})
        )
    )
    assert record["payload"] is None and record["quarantined"] is True

    async def rows():
        async with database[1]() as session:
            return (await session.execute(select(learning_sample_custody))).mappings().all()

    assert marker not in str(database[0].run(rows()))


def test_custody_foreign_equals_missing(database):
    from core.learning.storage import LearningStorageError
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    record = database[0].run(repo.capture(**custody_candidate(world)))
    for tenant, sample in ((uuid4(), record["sample_id"]), (world.principal.tenant_id, uuid4())):
        with pytest.raises(LearningStorageError, match="unknown learning sample"):
            database[0].run(repo.get(tenant, sample))


def test_custody_concurrent_retry_has_one_committed_subject(database):
    import asyncio

    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    others = [
        custody_candidate(
            world, key=args["idempotency_key"], policy=args["policy"], rights=args["rights_ref"]
        )
        for _ in range(4)
    ]

    async def concurrent():
        return await asyncio.gather(*(repo.capture(**a) for a in [args, *others]))

    rows = database[0].run(concurrent())
    assert len({r["sample_id"] for r in rows}) == 1
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_late_write_failure_rolls_back_subject_and_sample(database):
    from sqlalchemy.exc import DBAPIError

    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)

    async def fail_write():
        async with database[1].begin() as session:
            await session.execute(
                text(
                    "CREATE FUNCTION fail_custody() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    "BEGIN RAISE EXCEPTION 'custody write failed'; END; $$"
                )
            )
            await session.execute(
                text(
                    "CREATE TRIGGER fail_custody_insert BEFORE INSERT ON learning_sample_custody "
                    "FOR EACH ROW EXECUTE FUNCTION fail_custody()"
                )
            )

    database[0].run(fail_write())
    with pytest.raises(DBAPIError):
        database[0].run(LearningCustodyRepository(database[1]).capture(**custody_candidate(world)))
    assert count(database, executions) == count(database, learning_samples) == 0


def test_custody_expiry_discards_payload_but_preserves_lineage(database):
    from datetime import timedelta

    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    first = database[0].run(repo.capture(**args))
    assert (
        database[0].run(
            repo.expire(
                world.principal.tenant_id, args["prepared"].expires_at + timedelta(seconds=1)
            )
        )
        == 1
    )
    row = database[0].run(repo.get(world.principal.tenant_id, first["sample_id"]))
    assert row["payload"] is None and row["revoked"] is True
    assert row["eligibility"] == "ineligible"
    assert row["source_execution_id"] == first["source_execution_id"]
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_stale_writer_cannot_advance_state(database):
    from core.contracts.learning import LearningEligibility
    from core.learning.storage import LearningStorageConflict
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    database[0].run(repo.capture(**args))
    sample = args["sample"].model_copy(update={"eligibility": LearningEligibility.INELIGIBLE})
    database[0].run(repo.save(sample, {"version": 1}, expected_revision=0))
    with pytest.raises(LearningStorageConflict):
        database[0].run(repo.save(args["sample"], {"version": 1}, expected_revision=0))
    assert (
        database[0].run(repo.get(world.principal.tenant_id, sample.id))["eligibility"]
        == "ineligible"
    )


def test_custody_database_rejects_cross_tenant_lineage_update(database):
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_sample_custody

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    first = database[0].run(repo.capture(**custody_candidate(world)))

    async def tamper():
        async with database[1].begin() as session:
            await session.execute(
                learning_sample_custody.update()
                .where(learning_sample_custody.c.sample_id == first["sample_id"])
                .values(tenant_id=uuid4())
            )

    with pytest.raises(IntegrityError):
        database[0].run(tamper())
    assert (
        database[0].run(repo.get(world.principal.tenant_id, first["sample_id"]))["tenant_id"]
        == world.principal.tenant_id
    )


def test_custody_revocation_keeps_lineage_and_denies_further_mutation(database):
    from core.learning.storage import LearningStorageConflict
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    first = database[0].run(repo.capture(**args))
    assert (
        database[0].run(repo.revoke_policy(world.principal.tenant_id, args["policy"].policy_id))
        == 1
    )
    again = database[0].run(repo.capture(**args))
    assert again["sample_id"] == first["sample_id"]
    assert again["payload"] is None and again["revoked"]
    with pytest.raises(LearningStorageConflict):
        database[0].run(repo.save(args["sample"], {"version": 1}, expected_revision=1))
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_state_refuses_arbitrary_content_and_unknown_version(database):
    from core.learning.storage import LearningStorageError
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    database[0].run(repo.capture(**args))
    for state in (
        {"version": 2},
        {"version": True},
        {"version": 1, "raw": "forbidden"},
        {"version": 1, "promotion_verdicts": {"unexpected": True}},
        {"version": 1, "eligibility_verdicts": {"not_poisoned": "true"}},
    ):
        with pytest.raises(LearningStorageError):
            database[0].run(repo.save(args["sample"], state, expected_revision=0))
    assert database[0].run(repo.get(world.principal.tenant_id, args["sample"].id))["revision"] == 0


def custody_migration(connection, direction):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).resolve().parents[2]
        / "infrastructure/db/migrations/versions/0019_learning_custody.py"
    )
    spec = importlib.util.spec_from_file_location("custody_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


def test_custody_migration_roundtrip_empty_and_refuses_populated_downgrade(database):
    from sqlalchemy import inspect

    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_sample_custody

    async def roundtrip():
        async with database[1].begin() as session:
            connection = await session.connection()
            await connection.run_sync(lambda c: custody_migration(c, "downgrade"))
            await connection.run_sync(lambda c: custody_migration(c, "upgrade"))
            columns = await connection.run_sync(
                lambda c: inspect(c).get_columns("learning_sample_custody")
            )
            assert {c["name"] for c in columns} == set(learning_sample_custody.c.keys())

    database[0].run(roundtrip())
    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    row = database[0].run(repo.capture(**custody_candidate(world)))

    async def unsafe_downgrade():
        async with database[1].begin() as session:
            connection = await session.connection()
            await connection.run_sync(lambda c: custody_migration(c, "downgrade"))

    with pytest.raises(RuntimeError, match="preserve evidence"):
        database[0].run(unsafe_downgrade())
    assert (
        database[0].run(repo.get(world.principal.tenant_id, row["sample_id"]))["payload"]
        is not None
    )
