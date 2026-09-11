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
    if "learning_policy_revocations" in metadata.tables:
        names.add("learning_policy_revocations")
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
            await session.execute(plans.insert().values(id=plan, name=f"r178-test-plan-{plan}"))
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
    from core.learning.storage import RetentionPolicy
    from tests.api.test_external_evidence_p01_r178 import custody_body, governed_app

    # DEC03 changed admission prerequisites, not these recovery assertions.
    # Supply operator policy explicitly; never infer one from a durable store.
    world, store, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    app = governed_app(world, custody_adapter(database, policy), store=store)
    body = custody_body()
    body["policy_id"] = str(policy.policy_id)
    captured = run(_post(app, SAMPLES, body))
    assert captured.status_code == 201
    sample = captured.json()
    bridge, sessions = database
    fresh = DurableExecutionStore(repository=PostgresExecutionRepository(sessions), bridge=bridge)
    restarted = governed_app(world, custody_adapter(database, policy), store=fresh)
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
    import json

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
        bootstrap = build_runtime_profile(environ=env)
        profiles.append(bootstrap)
        headers, tenant = _admin(bootstrap)
        # Negative control: durable runtime without a policy refuses even when
        # all opaque references are present; no legacy in-memory fallback.
        policy_id, rights_ref, retry_key = uuid4(), uuid4(), uuid4()
        refs = dict(policy_id=str(policy_id), rights_ref=str(rights_ref),
                    idempotency_key=str(retry_key))
        refused = run(request(bootstrap, headers, "POST", SAMPLES, dict(
            **refs, knowledge_key="runtime.restart", knowledge_value={"answer": "fact"}
        )))
        assert refused.status_code == 404
        assert bootstrap.app.state.learning_lifecycle_service._samples == {}
        assert bootstrap.app.state.learning_lifecycle_service.list_samples(tenant) == ()
        run(bootstrap.release_adapters())
        bootstrap.bridge.run(bootstrap.bindings.engine.dispose())
        bootstrap.bridge.close()
        profiles.remove(bootstrap)
        # Test-operator configuration for the registered tenant, before boot.
        # These are NOT application defaults or an internal policy-map mutation.
        env["LEARNING_STORAGE_POLICIES"] = json.dumps([dict(
            tenant_id=str(tenant), policy_id=str(policy_id), retention_seconds=3600
        )])
        first = build_runtime_profile(environ=env)
        profiles.append(first)
        assert first.durable and first.demo_principal is None
        captured = run(
            request(
                first,
                headers,
                "POST",
                SAMPLES,
                {
                    **refs,
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
        replay = run(request(second, headers, "POST", SAMPLES, dict(
            **refs, knowledge_key="runtime.restart", knowledge_value={"answer": "fact"}
        )))
        assert replay.status_code == 201
        assert replay.json() == restored.json()["sample"]
        assert len(second.app.state.learning_lifecycle_service.list_samples(tenant)) == 1
        assert second.app.state.learning_lifecycle_service._samples == {}
    finally:
        for profile in profiles:
            run(profile.release_adapters())
            profile.bridge.run(profile.bindings.engine.dispose())
            profile.bridge.close()


def custody_candidate(world, *, key=None, value=None, policy=None, rights=None):
    from apps.api.ingestion import build_external_ingestion_report
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
    report = build_external_ingestion_report(tenant, sample_id, actor, "fact", value)
    execution_id = report.execution.id
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


def test_custody_receipt_builder_never_uses_standalone_subject_write(database, monkeypatch):
    from apps.api.ingestion import ExternalIngestionRecorder
    from core.learning.storage import recover_capture
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)

    def refuse_record(*args, **kwargs):
        pytest.fail("atomic capture must not use the standalone recorder")

    monkeypatch.setattr(ExternalIngestionRecorder, "record", refuse_record)
    args = custody_candidate(world)
    assert count(database, executions) == count(database, learning_samples) == 0
    assert args["nodes"][0].input_ref["content_sha256"] == args["prepared"].content_digest
    assert args["nodes"][0].output_ref == args["prepared"].receipt
    first = database[0].run(LearningCustodyRepository(database[1]).capture(**args))
    assert count(database, executions) == count(database, learning_samples) == 1
    row = database[0].run(
        LearningCustodyRepository(database[1]).get(world.principal.tenant_id, first["sample_id"])
    )
    restored = recover_capture(
        row, tenant_id=world.principal.tenant_id, policy=args["policy"], now=utc_now()
    )
    assert restored.sample.source_execution_id == args["execution"].id
    assert restored.payload == args["prepared"].payload


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


@pytest.mark.parametrize("mode", ["clean", "quarantined", "expired", "revoked", "no_policy"])
def test_custody_codec_recovers_real_rows_without_restoring_unavailable_payload(database, mode):
    from core.contracts.learning import LearningEligibility
    from core.learning.storage import recover_capture
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    tenant = world.principal.tenant_id
    args = custody_candidate(
        world, value={"password": "private"} if mode == "quarantined" else None
    )
    first = database[0].run(repo.capture(**args))
    if mode == "expired":
        database[0].run(repo.expire(tenant, args["prepared"].expires_at))
    elif mode == "revoked":
        database[0].run(repo.revoke_policy(tenant, args["policy"].policy_id))
    elif mode == "clean":
        sample = args["sample"].model_copy(update={"eligibility": LearningEligibility.INELIGIBLE})
        database[0].run(repo.save(sample, {"version": 1}, expected_revision=0))
    # A new repository instance, not the capture return value or an in-process cache.
    loaded = database[0].run(LearningCustodyRepository(database[1]).get(tenant, first["sample_id"]))
    restored = recover_capture(
        loaded, tenant_id=tenant, policy=None if mode == "no_policy" else args["policy"],
        now=utc_now(),
    )
    assert restored.sample.id == first["sample_id"]
    assert restored.sample.source_execution_id == first["source_execution_id"]
    assert restored.sample.verification_level.value == "RAW"
    if mode == "clean":
        assert restored.payload == args["prepared"].payload
        assert restored.revision == 1 and restored.sample.eligibility.value == "ineligible"
        restored.payload["knowledge_value"]["answer"] = "local mutation"
        assert (
            database[0].run(repo.get(tenant, first["sample_id"]))["payload"]
            == args["prepared"].payload
        )
    else:
        assert restored.payload is None
    assert count(database, executions) == count(database, learning_samples) == 1


@pytest.mark.parametrize("field,value", [
    ("state", {"version": 999}),
    ("payload", {"knowledge_key": "fact", "knowledge_value": {"answer": "corrupt-marker"}}),
])
def test_custody_codec_refuses_corrupt_persisted_json(database, field, value):
    from core.learning.storage import LearningStorageError, recover_capture
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_sample_custody

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    first = database[0].run(repo.capture(**args))

    async def corrupt():
        async with database[1].begin() as session:
            await session.execute(
                learning_sample_custody.update()
                .where(learning_sample_custody.c.sample_id == first["sample_id"])
                .values(**{field: value})
            )

    database[0].run(corrupt())
    row = database[0].run(repo.get(world.principal.tenant_id, first["sample_id"]))
    with pytest.raises(LearningStorageError, match="invalid custody record") as exc:
        recover_capture(
            row, tenant_id=world.principal.tenant_id, policy=args["policy"], now=utc_now()
        )
    assert "corrupt-marker" not in str(exc.value)


# Adapter acceptance over real PostgreSQL; not HTTP binding or process-crash proof.
def custody_adapter(database, policy, *, configured=True, repository=None):
    import json
    from types import SimpleNamespace

    from apps.composition.learning import (
        DurableLearningCustody,
        build_durable_learning_custody,
        learning_storage_policies_from_env,
    )

    env = {}
    if configured:
        env["LEARNING_STORAGE_POLICIES"] = json.dumps([{
            "tenant_id": str(policy.tenant_id),
            "policy_id": str(policy.policy_id),
            "retention_seconds": policy.retention_seconds,
        }])
    policies = learning_storage_policies_from_env(env)
    if repository is not None:
        return DurableLearningCustody(
            repository=repository, bridge=database[0], policies=policies
        )
    return build_durable_learning_custody(
        SimpleNamespace(session_factory=database[1]), database[0], policies=policies
    )


def custody_adapter_request(world, policy):
    return dict(
        tenant_id=policy.tenant_id,
        actor_id=world.principal.user_id,
        policy_id=policy.policy_id,
        rights_ref=uuid4(),
        idempotency_key=uuid4(),
        knowledge_key="adapter.fact",
        knowledge_value={"answer": "bounded fact"},
    )


@pytest.mark.parametrize("quarantined", [False, True])
def test_custody_adapter_capture_retry_and_fresh_recovery(database, quarantined):
    from core.learning.storage import LearningStorageConflict, LearningStorageError, RetentionPolicy
    from infrastructure.db.tables import execution_nodes, learning_sample_custody

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    marker = "ghp_" + "X" * 36
    if quarantined:
        args["knowledge_value"] = {marker: "private"}
    first = custody_adapter(database, policy).capture_external(**args)
    fresh = custody_adapter(database, policy)
    assert fresh.get(policy.tenant_id, first.sample.id) == first
    assert fresh.list(policy.tenant_id) == (first,)
    assert fresh.capture_external(**args) == first
    assert first.sample.verification_level.value == "RAW"
    assert first.sample.eligibility.value == "pending"
    assert first.payload == (None if quarantined else {
        "knowledge_key": args["knowledge_key"], "knowledge_value": args["knowledge_value"]
    })
    with pytest.raises(LearningStorageConflict):
        fresh.capture_external(**{**args, "knowledge_value": {"answer": "changed"}})
    with pytest.raises(LearningStorageError, match="unknown learning sample"):
        fresh.get(uuid4(), first.sample.id)
    assert fresh.list(uuid4()) == ()

    async def stored_rows():
        async with database[1]() as session:
            return [
                (await session.execute(select(table))).mappings().all()
                for table in (
                    executions, execution_nodes, learning_samples, learning_sample_custody
                )
            ]

    assert marker not in str(database[0].run(stored_rows()))
    assert count(database, executions) == count(database, learning_samples) == 1
    assert count(database, execution_nodes) == count(database, learning_sample_custody) == 1


def test_custody_adapter_policy_removal_denies_capture_and_save(database):
    from core.learning.storage import LearningStorageConflict, LearningStorageError, RetentionPolicy

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    first = custody_adapter(database, policy).capture_external(**args)
    removed = custody_adapter(database, policy, configured=False)
    assert removed.get(policy.tenant_id, first.sample.id).payload is None
    assert removed.list(policy.tenant_id)[0].payload is None
    with pytest.raises(LearningStorageError, match="storage policy unavailable"):
        removed.capture_external(**{**args, "idempotency_key": uuid4()})
    with pytest.raises(LearningStorageConflict):
        removed.save(first.sample, first.state, expected_revision=first.revision)
    # Suppression is not erasure/revocation: unchanged configured readers still see it.
    assert custody_adapter(database, policy).get(policy.tenant_id, first.sample.id) == first
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_adapter_cas_and_repository_revocation(database):
    from core.contracts.learning import LearningEligibility
    from core.learning.storage import LearningStorageConflict, RetentionPolicy
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    adapter = custody_adapter(database, policy)
    first = adapter.capture_external(**args)
    changed = first.sample.model_copy(update={"eligibility": LearningEligibility.INELIGIBLE})
    assert adapter.save(changed, first.state, expected_revision=0) == 1
    fresh = custody_adapter(database, policy)
    loaded = fresh.get(policy.tenant_id, first.sample.id)
    assert loaded.sample == changed and loaded.revision == 1
    with pytest.raises(LearningStorageConflict):
        adapter.save(first.sample, first.state, expected_revision=0)
    assert database[0].run(
        LearningCustodyRepository(database[1]).revoke_policy(policy.tenant_id, policy.policy_id)
    ) == 1
    revoked = fresh.get(policy.tenant_id, first.sample.id)
    assert revoked.payload is None and revoked.revision == 2
    assert revoked.sample.source_execution_id == first.sample.source_execution_id
    assert fresh.capture_external(**args) == revoked
    with pytest.raises(LearningStorageConflict):
        fresh.save(revoked.sample, revoked.state, expected_revision=2)
    # This proves existing-custody revocation, NOT a durable new-admission registry.
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_adapter_response_loss_retries_committed_identity(database):
    from core.learning.storage import RetentionPolicy
    from infrastructure.db.learning import LearningCustodyRepository

    class LostResponseRepository(LearningCustodyRepository):
        async def capture(self, **kwargs):
            await super().capture(**kwargs)
            raise ConnectionError("injected response loss after commit")

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    adapter = custody_adapter(database, policy, repository=LostResponseRepository(database[1]))
    with pytest.raises(ConnectionError, match="injected response loss after commit"):
        adapter.capture_external(**args)
    stored = database[0].run(LearningCustodyRepository(database[1]).list(policy.tenant_id))
    assert len(stored) == 1
    recovered = custody_adapter(database, policy).capture_external(**args)
    assert recovered.sample.id == stored[0]["sample_id"]
    assert recovered.sample.source_execution_id == stored[0]["source_execution_id"]
    assert recovered.payload == stored[0]["payload"]
    assert count(database, executions) == count(database, learning_samples) == 1


def test_custody_adapter_concurrent_same_key_uses_one_transactional_identity(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from core.learning.storage import RetentionPolicy
    from infrastructure.db.tables import execution_nodes, learning_sample_custody

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    ready = Barrier(4)

    def capture_one(_):
        adapter = custody_adapter(database, policy)
        ready.wait(timeout=10)
        return adapter.capture_external(**args)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(capture_one, range(4)))
    assert all(result == results[0] for result in results)
    assert count(database, executions) == count(database, learning_samples) == 1
    assert count(database, execution_nodes) == count(database, learning_sample_custody) == 1
    assert custody_adapter(database, policy).list(policy.tenant_id) == (results[0],)


def execution_source(database, world, app):
    """Actual API/service execution with the test provider, not live inference."""
    world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=100.0)
    response = run(_post(app, "/v1/execute", {"ask": "bounded source probe"}))
    assert response.status_code == 200
    source_id = UUID(response.json()["execution_id"])
    return database[0].run(
        PostgresExecutionRepository(database[1]).get(world.principal.tenant_id, source_id)
    )


@pytest.mark.parametrize("quarantined", [False, True])
def test_execution_custody_adapter_reuses_real_source_and_retry_identity(database, quarantined):
    from core.learning.storage import LearningStorageConflict, RetentionPolicy
    from infrastructure.db.tables import execution_nodes, learning_sample_custody

    world, _, app = composed(database)
    source = execution_source(database, world, app)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    args.pop("actor_id")
    args["source_execution_id"] = source.execution.id
    marker = "ghp_" + "X" * 36
    if quarantined:
        args["knowledge_value"] = {marker: marker}
    before_nodes = count(database, execution_nodes)
    first = custody_adapter(database, policy).capture_from_execution(**args)
    fresh = custody_adapter(database, policy)
    assert fresh.capture_from_execution(**args) == first
    assert fresh.get(policy.tenant_id, first.sample.id) == first
    assert first.source_kind == "execution"
    assert first.sample.source_execution_id == source.execution.id
    assert first.sample.verification_level.value == "RAW"
    assert first.sample.eligibility.value == "pending"
    assert (first.payload is None) == quarantined
    assert count(database, executions) == 1
    assert count(database, execution_nodes) == before_nodes
    assert count(database, learning_samples) == count(database, learning_sample_custody) == 1
    assert database[0].run(
        PostgresExecutionRepository(database[1]).get(policy.tenant_id, source.execution.id)
    ) == source
    with pytest.raises(LearningStorageConflict):
        fresh.capture_from_execution(**{**args, "knowledge_value": {"changed": True}})
    other = execution_source(database, world, app)
    with pytest.raises(LearningStorageConflict):
        fresh.capture_from_execution(**{**args, "source_execution_id": other.execution.id})

    async def rows():
        async with database[1]() as session:
            return (await session.execute(select(learning_sample_custody))).mappings().all()

    assert marker not in str(database[0].run(rows()))
    assert count(database, learning_samples) == 1


def test_execution_custody_adapter_missing_and_foreign_source_refuse(database):
    from core.learning.storage import LearningStorageError, RetentionPolicy

    world, _, app = composed(database)
    source = execution_source(database, world, app)
    foreign, _, _ = composed(database)
    policy = RetentionPolicy(foreign.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(foreign, policy)
    args.pop("actor_id")
    errors = []
    for source_id in (source.execution.id, uuid4()):
        with pytest.raises(LearningStorageError) as exc:
            custody_adapter(database, policy).capture_from_execution(
                **args, source_execution_id=source_id
            )
        errors.append(str(exc.value))
    assert errors == ["source unavailable", "source unavailable"]
    assert count(database, learning_samples) == 0 and count(database, executions) == 1


def test_execution_custody_adapter_late_failure_keeps_source_without_sample(database):
    from sqlalchemy.exc import DBAPIError

    from core.learning.storage import RetentionPolicy

    world, _, app = composed(database)
    source = execution_source(database, world, app)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    args.pop("actor_id")

    async def fail_write():
        async with database[1].begin() as session:
            await session.execute(text(
                "CREATE FUNCTION fail_custody() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'custody write failed'; END; $$"
            ))
            await session.execute(text(
                "CREATE TRIGGER fail_custody_insert BEFORE INSERT ON learning_sample_custody "
                "FOR EACH ROW EXECUTE FUNCTION fail_custody()"
            ))

    database[0].run(fail_write())
    with pytest.raises(DBAPIError):
        custody_adapter(database, policy).capture_from_execution(
            **args, source_execution_id=source.execution.id
        )
    assert count(database, learning_samples) == 0 and count(database, executions) == 1
    assert database[0].run(
        PostgresExecutionRepository(database[1]).get(policy.tenant_id, source.execution.id)
    ) == source


def custody_lifecycle(database, policy, *, evaluation=None):
    from core.learning.lifecycle import LearningLifecycleService
    from core.memory.memory import InMemoryMemoryStore

    return LearningLifecycleService(
        knowledge=InMemoryMemoryStore(), evaluation=evaluation,
        custody=custody_adapter(database, policy),
    )


def test_custody_lifecycle_postgres_recomposition_preserves_review_and_evidence(database):
    from core.contracts.evaluation import VerificationLevel
    from core.evaluation.policy import EvaluationPolicyService
    from core.learning.storage import RetentionPolicy
    from tests.learning.test_learning_lifecycle_e2e import ALL_ELIGIBLE

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    pipeline = EvaluationPolicyService(store=world.evaluations)
    service = custody_lifecycle(database, policy, evaluation=pipeline)
    args = custody_adapter_request(world, policy)
    sample = service.capture_external(**args)
    t, s = policy.tenant_id, sample.id
    service.mark_sanitized(t, s, passed=True)
    evaluated = run(service.evaluate(t, s, {"content": "bounded fact"}))
    recorded = world.evaluations.list_for_execution(t, sample.source_execution_id)
    assert len(recorded) == 1 and evaluated.verification_level == recorded[0].level
    assert custody_adapter(database, policy).get(t, s).state["evaluation_id"] == str(recorded[0].id)
    service.set_verification_level(t, s, VerificationLevel.VERIFIED)
    admitted = service.admit_to_training(t, s, ALL_ELIGIBLE, dataset_id=uuid4())
    fresh = custody_lifecycle(database, policy)
    assert fresh.get(t, s) == admitted and fresh.list_samples(t) == (admitted,)
    assert fresh.capture_external(**args) == admitted
    assert all(fresh.sample_report(t, s)["eligibility_verdicts"].values())
    assert fresh.sample_report(t, s)["sanitization_report"] is None
    assert custody_adapter(database, policy).get(t, s).revision == 4
    assert service._samples == fresh._samples == {}
    assert count(database, evaluations) == count(database, learning_samples) == 1


@pytest.mark.parametrize("race", ["review", "revocation"])
def test_custody_lifecycle_postgres_evaluation_race_keeps_evidence_not_trust(database, race):
    from core.contracts.evaluation import VerificationLevel
    from core.evaluation.policy import EvaluationPolicyService
    from core.learning.storage import LearningStorageConflict, RetentionPolicy
    from infrastructure.db.learning import LearningCustodyRepository

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    pipeline = EvaluationPolicyService(store=world.evaluations)
    first = custody_lifecycle(database, policy)
    sample = first.capture_external(**custody_adapter_request(world, policy))

    class RacingEvaluation:
        async def evaluate(self, tenant_id, execution_id, output):
            result = await pipeline.evaluate(tenant_id, execution_id, output)
            if race == "review":
                custody_lifecycle(database, policy).mark_sanitized(
                    tenant_id, sample.id, passed=True
                )
            else:
                database[0].run(
                    LearningCustodyRepository(database[1]).revoke_policy(
                        tenant_id, policy.policy_id
                    )
                )
            return result

    service = custody_lifecycle(database, policy, evaluation=RacingEvaluation())
    with pytest.raises(LearningStorageConflict):
        run(service.evaluate(policy.tenant_id, sample.id, {"content": "bounded fact"}))
    current = custody_adapter(database, policy).get(policy.tenant_id, sample.id)
    assert current.revision == 1 and current.sample.verification_level is VerificationLevel.RAW
    assert "evaluation_id" not in current.state
    assert count(database, evaluations) == 1
    assert service._samples == {}
    if race == "revocation":
        assert current.payload is None
        assert service.sample_report(policy.tenant_id, sample.id)["knowledge_key"] is None


def test_custody_lifecycle_postgres_failed_sample_update_rolls_back_custody_cas(database):
    from sqlalchemy.exc import DBAPIError

    from core.contracts.learning import SanitizationState
    from core.learning.storage import RetentionPolicy

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    service = custody_lifecycle(database, policy)
    sample = service.capture_external(**custody_adapter_request(world, policy))

    async def fail_update():
        async with database[1].begin() as session:
            await session.execute(text(
                "CREATE FUNCTION fail_sample_update() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'sample update failed'; END; $$"
            ))
            await session.execute(text(
                "CREATE TRIGGER fail_sample_update BEFORE UPDATE ON learning_samples "
                "FOR EACH ROW EXECUTE FUNCTION fail_sample_update()"
            ))

    database[0].run(fail_update())
    with pytest.raises(DBAPIError):
        service.mark_sanitized(policy.tenant_id, sample.id, passed=True)
    current = custody_adapter(database, policy).get(policy.tenant_id, sample.id)
    assert current.revision == 0
    assert current.sample.sanitization_state is SanitizationState.PENDING
    assert current.state == {"version": 1}
    assert service._samples == {}


def test_custody_lifecycle_postgres_quarantine_is_metadata_only(database):
    from core.learning.errors import LearningError
    from core.learning.storage import RetentionPolicy
    from infrastructure.db.tables import learning_sample_custody

    world, _, _ = composed(database)
    policy = RetentionPolicy(world.principal.tenant_id, uuid4(), 3600)
    args = custody_adapter_request(world, policy)
    marker = "ghp_" + "Q" * 36
    args["knowledge_value"] = {marker: "sensitive field name"}
    service = custody_lifecycle(database, policy)
    sample = service.capture_external(**args)
    fresh = custody_lifecycle(database, policy)
    report = fresh.sample_report(policy.tenant_id, sample.id)
    assert report["knowledge_key"] is None and report["sanitization_report"] is None
    assert report["derived_signals"] == {"deduplicated": False, "scan_clean": False}
    with pytest.raises(LearningError):
        fresh.mark_sanitized(policy.tenant_id, sample.id, passed=True)
    assert service._samples == fresh._samples == {}

    async def stored():
        async with database[1]() as session:
            return (await session.execute(select(learning_sample_custody))).mappings().all()

    assert marker not in str(database[0].run(stored())) and marker not in str(report)


@pytest.mark.parametrize("preexisting", [False, True])
@pytest.mark.parametrize("fresh_reader", [False, True])
def test_policy_revocation_denies_new_api_capture_with_stale_config(
    database, preexisting, fresh_reader
):
    """Revocation must survive cached/reloaded policy config, even with zero rows.

    This is real API/adapter/PostgreSQL composition, not a process-kill test.
    The constant policy-unavailable 404 is the existing response contract.
    """
    from core.learning.storage import RetentionPolicy
    from infrastructure.db.learning import LearningCustodyRepository
    from tests.api.test_external_evidence_p01_r178 import custody_body, governed_app

    world, store, _ = composed(database)
    tenant = world.principal.tenant_id
    policy = RetentionPolicy(tenant, uuid4(), 3600)
    stale = custody_adapter(database, policy)
    app = governed_app(world, stale, store=store)
    body = custody_body()
    body["policy_id"] = str(policy.policy_id)
    sample = None
    if preexisting:
        response = run(_post(app, SAMPLES, body))
        assert response.status_code == 201
        sample = response.json()
        graded = run(_post(app, f"{SAMPLES}/{sample['id']}/evaluate", {"output": {"v": "fact"}}))
        assert graded.status_code == 200 and graded.json()["evaluated"] is True
    repo = LearningCustodyRepository(database[1])
    assert database[0].run(repo.revoke_policy(tenant, policy.policy_id)) == int(preexisting)
    assert database[0].run(repo.revoke_policy(tenant, policy.policy_id)) == 0
    if sample is not None:
        report = run(get(app, f"{SAMPLES}/{sample['id']}"))
        assert report.status_code == 200
        assert report.json()["knowledge_key"] is None
        assert report.json()["sample"]["eligibility"] == "ineligible"
        assert count(database, evaluations) == 1
    if fresh_reader:
        app = governed_app(world, custody_adapter(database, policy), store=store)
    body["idempotency_key"] = str(uuid4())
    body["knowledge_key"] = "new.admission.after.revocation"
    refused = run(_post(app, SAMPLES, body))
    assert refused.status_code == 404
    assert refused.json()["error"]["message"] == "Learning storage unavailable."
    assert count(database, learning_samples) == int(preexisting)
    assert count(database, executions) == int(preexisting)
    assert count(database, evaluations) == int(preexisting)
    assert app.state.learning_lifecycle_service._samples == {}


def test_policy_revocation_does_not_cross_tenant_or_other_policy(database):
    from core.learning.storage import RetentionPolicy
    from infrastructure.db.learning import LearningCustodyRepository

    first, _, _ = composed(database)
    second, _, _ = composed(database)
    revoked = RetentionPolicy(first.principal.tenant_id, uuid4(), 3600)
    other_policy = RetentionPolicy(first.principal.tenant_id, uuid4(), 3600)
    other_tenant = RetentionPolicy(second.principal.tenant_id, revoked.policy_id, 3600)
    repo = LearningCustodyRepository(database[1])
    assert database[0].run(repo.revoke_policy(revoked.tenant_id, revoked.policy_id)) == 0
    for world, policy in ((first, other_policy), (second, other_tenant)):
        recovered = custody_adapter(database, policy).capture_external(
            **custody_adapter_request(world, policy)
        )
        assert recovered.payload is not None
        assert recovered.sample.tenant_id == policy.tenant_id
    assert count(database, learning_samples) == 2


@pytest.mark.parametrize("capture_first", [False, True])
def test_policy_revocation_transaction_orderings(database, capture_first):
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from core.learning.storage import LearningStorageError
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_policy_revocations

    world, _, _ = composed(database)
    args = custody_candidate(world)
    tenant, policy = args["policy"].tenant_id, args["policy"].policy_id

    async def race():
        locked, attempted, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class PausingSession(AsyncSession):
            async def execute(self, statement, params=None, **kw):
                # SQLAlchemy executemany passes a list (receipt nodes), not a mapping.
                lock = isinstance(params, dict) and params.get("key") == (
                    f"learning-policy:{tenant}:{policy}"
                )
                if lock and self.info["role"] == "second":
                    attempted.set()
                result = await super().execute(statement, params, **kw)
                if lock and self.info["role"] == "first":
                    locked.set()
                    await asyncio.wait_for(release.wait(), 5)
                return result

        def repo(role):
            return LearningCustodyRepository(async_sessionmaker(
                database[1].kw["bind"], class_=PausingSession, info={"role": role}
            ))

        first, second = repo("first"), repo("second")
        a = asyncio.create_task(
            first.capture(**args) if capture_first else first.revoke_policy(tenant, policy)
        )
        b = None
        try:
            await asyncio.wait_for(locked.wait(), 5)
            b = asyncio.create_task(
                second.revoke_policy(tenant, policy) if capture_first else second.capture(**args)
            )
            await asyncio.wait_for(attempted.wait(), 5)
            async with asyncio.timeout(5):
                while True:
                    async with database[1]() as observer:
                        waiting = await observer.scalar(text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks "
                            "WHERE locktype = 'advisory' AND NOT granted)"
                        ))
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
            assert not a.done() and not b.done()  # real PostgreSQL lock wait observed
            release.set()
            results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 5)
            if capture_first:
                assert isinstance(results[0], dict) and results[1] == 1
            else:
                assert results[0] == 0 and isinstance(results[1], LearningStorageError)
        finally:
            release.set()
            for task in (a, b):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(t for t in (a, b) if t is not None), return_exceptions=True)

    database[0].run(race())
    assert count(database, learning_policy_revocations) == 1
    assert count(database, executions) == count(database, learning_samples) == int(capture_first)
    repo = LearningCustodyRepository(database[1])
    if capture_first:
        row = database[0].run(repo.get(tenant, args["sample"].id))
        assert row["payload"] is None and row["revoked"] and row["eligibility"] == "ineligible"
        assert row["revision"] == 1
    with pytest.raises(LearningStorageError):
        database[0].run(repo.capture(**custody_candidate(world, policy=args["policy"])))


def test_policy_revocation_late_failure_is_atomic(database):
    from sqlalchemy.exc import DBAPIError

    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_policy_revocations

    world, _, _ = composed(database)
    repo = LearningCustodyRepository(database[1])
    args = custody_candidate(world)
    original = database[0].run(repo.capture(**args))

    async def trigger():
        async with database[1].begin() as s:
            await s.execute(text(
                "CREATE FUNCTION fail_revoke() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'injected late invalidation failure'; END; $$"
            ))
            await s.execute(text(
                "CREATE TRIGGER fail_revoke BEFORE UPDATE ON learning_samples "
                "FOR EACH ROW EXECUTE FUNCTION fail_revoke()"
            ))

    database[0].run(trigger())
    with pytest.raises(DBAPIError):
        database[0].run(repo.revoke_policy(args["policy"].tenant_id, args["policy"].policy_id))
    assert count(database, learning_policy_revocations) == 0
    assert database[0].run(repo.get(args["policy"].tenant_id, args["sample"].id)) == original
    database[0].run(repo.capture(**custody_candidate(world, policy=args["policy"])))
    assert count(database, learning_samples) == count(database, executions) == 2


def revocation_migrate(connection, *, stamp=None, target="0020"):
    """Actual Alembic traversal from metadata-built 0019 prerequisites, not 0001..0018."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(
        Path(__file__).resolve().parents[2] / "infrastructure/db/migrations"
    ))
    script = ScriptDirectory.from_config(config)
    context = MigrationContext.configure(connection)
    if stamp is not None:
        context.stamp(script, stamp)
    fn = script._upgrade_revs if target == "0020" else script._downgrade_revs
    context = MigrationContext.configure(connection, opts={
        "fn": lambda revision, _context: fn(target, revision)
    })
    with Operations.context(context):
        context.run_migrations()
    return context.get_current_revision()


@pytest.mark.parametrize("legacy", ["empty", "zero_row", "expired", "clean"])
def test_policy_revocation_stamped_upgrade_legacy_denies(database, legacy):
    from core.learning.storage import LearningStorageError
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_policy_revocations

    world = args = None
    repo = LearningCustodyRepository(database[1])
    if legacy != "empty":
        world, _, _ = composed(database)
        args = custody_candidate(world)
        if legacy != "zero_row":
            database[0].run(repo.capture(**args))
        if legacy == "expired":
            from datetime import timedelta
            database[0].run(repo.expire(world.principal.tenant_id, utc_now() + timedelta(hours=2)))

    async def upgrade():
        async with database[1].begin() as s:
            c = await s.connection()
            await c.run_sync(lambda sync: learning_policy_revocations.drop(sync))
            assert await c.run_sync(lambda sync: revocation_migrate(sync, stamp="0019")) == "0020"
            return (await s.execute(select(learning_policy_revocations))).mappings().all()

    rows = database[0].run(upgrade())
    if legacy == "empty":
        assert rows == []
    else:
        # No invented policy UUID or inferred historical revocation/consent.
        assert len(rows) == 1 and rows[0]["tenant_id"] == world.principal.tenant_id
        assert rows[0]["policy_id"] is None and rows[0]["reason"] == "legacy_unresolved"
        with pytest.raises(LearningStorageError):
            database[0].run(repo.capture(**args))
        with pytest.raises(LearningStorageError):
            database[0].run(repo.list(world.principal.tenant_id))
        if legacy != "zero_row":
            with pytest.raises(LearningStorageError):
                database[0].run(repo.get(world.principal.tenant_id, args["sample"].id))
            with pytest.raises(LearningStorageError):
                database[0].run(repo.save(args["sample"], {"version": 1}, expected_revision=0))
        assert count(database, executions) == count(database, learning_samples) == int(
            legacy != "zero_row"
        )
    other, _, _ = composed(database)
    database[0].run(repo.capture(**custody_candidate(other)))


@pytest.mark.parametrize("populated", [False, True])
def test_policy_revocation_stamped_downgrade_preserves_evidence(database, populated):
    from infrastructure.db.learning import LearningCustodyRepository
    from infrastructure.db.tables import learning_policy_revocations

    async def upgrade():
        async with database[1].begin() as s:
            c = await s.connection()
            await c.run_sync(lambda sync: learning_policy_revocations.drop(sync))
            assert await c.run_sync(lambda sync: revocation_migrate(sync, stamp="0019")) == "0020"
    database[0].run(upgrade())
    if populated:
        world, _, _ = composed(database)
        database[0].run(LearningCustodyRepository(database[1]).revoke_policy(
            world.principal.tenant_id, uuid4()
        ))

    async def downgrade():
        async with database[1].begin() as s:
            c = await s.connection()
            return await c.run_sync(lambda sync: revocation_migrate(sync, target="0019"))
    if populated:
        with pytest.raises(RuntimeError, match="preserve"):
            database[0].run(downgrade())
        assert count(database, learning_policy_revocations) == 1
        async def revision():
            async with database[1]() as s:
                return await s.scalar(text("SELECT version_num FROM alembic_version"))
        assert database[0].run(revision()) == "0020"
    else:
        assert database[0].run(downgrade()) == "0019"
