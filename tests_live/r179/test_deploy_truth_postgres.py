"""R179 4.6 DEPLOY TRUTH — real alembic forward/backward, rolling-upgrade pair, crash DURING write.

Run via tests_live/r179/run_local_postgres.sh. Disposable local cluster only; single node;
NOT a production migration procedure. Failing results are findings, never repaired off-books.
"""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from apps.composition.bridge import AsyncBridge

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
ALEMBIC_INI = os.path.join(ROOT, "infrastructure", "db", "alembic.ini")


@pytest.fixture
def cluster():
    raw = os.environ.get("R179_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Use tests_live/r179/run_local_postgres.sh for isolated local PostgreSQL")
    url = make_url(raw)
    assert url.drivername == "postgresql+asyncpg" and url.database == "postgres"
    socket = str(url.query.get("host", ""))
    root = os.path.join(ROOT, ".venv")
    assert socket.startswith(root + "/r179_pg_") and socket.endswith("/socket")
    return url


def fresh_database(cluster):
    """A brand-new database on the disposable cluster; returns (name, url_string)."""
    name = "r179_" + uuid4().hex
    bridge = AsyncBridge()
    catalog = create_async_engine(cluster, isolation_level="AUTOCOMMIT")

    async def create():
        async with catalog.connect() as c:
            await c.execute(text(f'CREATE DATABASE "{name}"'))
        await catalog.dispose()

    bridge.run(create())
    bridge.close()
    return name, cluster.set(database=name).render_as_string(hide_password=False)


def alembic(database_url, *args):
    """The REAL migration tool, as an operator runs it (docs/OPERATIONS.md §1)."""
    env = {
        "PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "LANG": "C.UTF-8",
        "PYTHONPATH": ROOT, "DATABASE_URL": database_url,
    }
    return subprocess.run(  # noqa: S603 — fixed argv, isolated env
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        env=env, cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


def sql(database_url, statement, **params):
    bridge = AsyncBridge()
    engine = create_async_engine(database_url)

    async def run():
        try:
            async with engine.begin() as c:
                result = await c.execute(text(statement), params)
                return result.all() if result.returns_rows else []
        finally:
            await engine.dispose()

    try:
        return bridge.run(run())
    finally:
        bridge.close()


def current_revision(database_url):
    rows = sql(database_url, "SELECT version_num FROM alembic_version")
    return rows[0][0] if rows else None


def tables(database_url):
    return {
        r[0] for r in sql(
            database_url,
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname='public' AND tablename<>'alembic_version'",
        )
    }


def test_alembic_forward_0001_to_head_then_backward_to_base_through_the_real_tool(cluster):
    """No metadata.create_all anywhere: every table comes from the migration chain."""
    _, url = fresh_database(cluster)
    assert current_revision(url) is None and tables(url) == set()
    up = alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    assert current_revision(url) == "0020"
    created = tables(url)
    from infrastructure.db.tables import metadata

    # Every metadata table exists after the real chain (no drift between code and migrations).
    assert set(metadata.tables) <= created, sorted(set(metadata.tables) - created)
    ext = sql(url, "SELECT extname FROM pg_extension WHERE extname='vector'")
    assert ext, "0007 creates the pgvector extension through the real tool"
    down = alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr[-2000:]
    assert tables(url) == set()
    assert current_revision(url) is None
    again = alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr[-2000:]
    assert current_revision(url) == "0020"


def test_alembic_downgrade_refuses_populated_0020_and_succeeds_when_empty(cluster):
    """Populated downgrade preserves evidence (fail-closed); empty downgrade is reversible."""
    _, url = fresh_database(cluster)
    assert alembic(url, "upgrade", "head").returncode == 0
    plan, tenant = uuid4(), uuid4()
    sql(url, "INSERT INTO plans (id, name) VALUES (:p, :n)", p=plan, n=f"r179-{plan}")
    sql(
        url,
        "INSERT INTO tenants (id, name, type, status, plan_id) "
        "VALUES (:t, 'r179', 'personal', 'active', :p)",
        t=tenant, p=plan,
    )
    sql(
        url,
        "INSERT INTO learning_policy_revocations (tenant_id, policy_id, reason) "
        "VALUES (:t, NULL, 'legacy_unresolved')",
        t=tenant,
    )
    blocked = alembic(url, "downgrade", "-1")
    assert blocked.returncode != 0, "populated 0020 downgrade must refuse"
    assert current_revision(url) == "0020"
    assert sql(url, "SELECT count(*) FROM learning_policy_revocations")[0][0] == 1
    sql(url, "DELETE FROM learning_policy_revocations")
    freed = alembic(url, "downgrade", "-1")
    assert freed.returncode == 0, freed.stderr[-2000:]
    assert current_revision(url) == "0019"
    assert "learning_policy_revocations" not in tables(url)
