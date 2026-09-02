"""Workspace/Project repositories — hermetic + live gates (Vision V5 chunk 2).

Two layers, same posture as the execution/memory/usage repository suites:

1. Hermetic (always run): row↔contract conversion fidelity, SQL compiles
   for the postgresql dialect, pre-I/O behavior via exploding factory,
   surface pins — no server needed.
2. Live (env-gated, skip-when-absent per 41 §49): round-trip/upsert,
   tenant isolation structural in SQL (foreign == absent, same named
   error), project list narrowed by workspace, FK RESTRICT surfacing
   LOUDLY on workspace-with-projects delete — against REAL PostgreSQL.

Run the live layer with:

    DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/db \\
    python3 -m pytest tests/infrastructure/test_workspace_repository_v1.py -v
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from core.contracts.identity import Project, Workspace
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    PostgresProjectRepository,
    PostgresWorkspaceRepository,
    ProjectNotFound,
    RepositoryError,
    WorkspaceNotFound,
)
from infrastructure.db.repositories.workspaces import (
    _row_to_project,
    _row_to_workspace,
)
from infrastructure.db.tables import metadata, projects, workspaces

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
            raise AssertionError("session factory must not be touched before I/O")

    return _Boom()


def _workspace(tenant_id: UUID = TENANT, name: str = "research") -> Workspace:
    return Workspace(id=uuid4(), tenant_id=tenant_id, name=name)


def _project(
    tenant_id: UUID = TENANT,
    workspace_id: UUID | None = None,
    name: str = "site",
    metadata_: dict[str, Any] | None = None,
) -> Project:
    return Project(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        name=name,
        metadata=metadata_ or {},
    )


# --- Hermetic layer ---------------------------------------------------------------


class TestHermetic:
    def test_row_to_workspace_conversion_fidelity(self) -> None:
        row = _Row(id=uuid4(), tenant_id=TENANT, name="marketing")
        ws = _row_to_workspace(row)
        assert isinstance(ws, Workspace)
        assert ws.id == row.id
        assert ws.tenant_id == TENANT
        assert ws.name == "marketing"

    def test_row_to_project_conversion_fidelity(self) -> None:
        workspace_id = uuid4()
        row = _Row(
            id=uuid4(),
            tenant_id=TENANT,
            workspace_id=workspace_id,
            name="landing-page",
            metadata={"stack": "static", "iteration": 3},
        )
        project = _row_to_project(row)
        assert isinstance(project, Project)
        assert project.workspace_id == workspace_id
        assert project.metadata == {"stack": "static", "iteration": 3}

    def test_row_to_project_unscoped_workspace_is_none(self) -> None:
        row = _Row(id=uuid4(), tenant_id=TENANT, workspace_id=None, name="p", metadata={})
        assert _row_to_project(row).workspace_id is None

    def test_errors_are_repository_errors_with_anti_enumeration_shape(self) -> None:
        # 20 §6: one message shape for absent AND foreign.
        ws_id, pr_id = uuid4(), uuid4()
        ws_err = WorkspaceNotFound(ws_id)
        pr_err = ProjectNotFound(pr_id)
        assert isinstance(ws_err, RepositoryError)
        assert isinstance(pr_err, RepositoryError)
        assert str(ws_err) == f"unknown workspace id: {ws_id}"
        assert str(pr_err) == f"unknown project id: {pr_id}"
        assert ws_err.workspace_id == ws_id
        assert pr_err.project_id == pr_id

    def test_workspace_select_compiles_for_postgresql(self) -> None:
        from sqlalchemy import select

        stmt = select(workspaces).where(
            workspaces.c.id == uuid4(), workspaces.c.tenant_id == TENANT
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "workspaces.tenant_id" in compiled  # tenant scoping IN SQL

    def test_project_upsert_compiles_for_postgresql(self) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(projects).values(
            id=uuid4(),
            tenant_id=TENANT,
            workspace_id=None,
            name="p",
            metadata={},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "workspace_id": stmt.excluded.workspace_id,
                "name": stmt.excluded.name,
                "metadata": stmt.excluded.metadata,
            },
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT (id) DO UPDATE" in compiled

    def test_workspace_repository_surface_pin(self) -> None:
        public = {name for name in dir(PostgresWorkspaceRepository) if not name.startswith("_")}
        assert public == {"put", "get", "list", "delete"}

    def test_project_repository_surface_pin(self) -> None:
        public = {name for name in dir(PostgresProjectRepository) if not name.startswith("_")}
        assert public == {"put", "get", "list", "delete"}

    def test_constructors_do_no_io(self) -> None:
        # Building a repository must not touch the factory (lazy engine
        # posture — same pin as the other seven repositories).
        PostgresWorkspaceRepository(_exploding_factory())
        PostgresProjectRepository(_exploding_factory())


# --- Live layer -------------------------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng: AsyncEngine = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(projects))
        await conn.execute(delete(workspaces))
    await eng.dispose()


SEED_PLAN_ID = uuid4()


@pytest_asyncio.fixture()
async def repos(
    engine: AsyncEngine,
) -> tuple[PostgresWorkspaceRepository, PostgresProjectRepository]:
    # Seed FK parents (plan -> tenants) required by the schema (columns
    # verified against infrastructure/db/tables.py, not assumed).
    factory = create_session_factory(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"),
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
    return (
        PostgresWorkspaceRepository(factory),
        PostgresProjectRepository(factory),
    )


@requires_live_postgres
class TestLiveWorkspaces:
    @pytest.mark.asyncio
    async def test_round_trip_and_upsert(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        ws_repo, _ = repos
        ws = _workspace(name="alpha")
        await ws_repo.put(ws)
        assert await ws_repo.get(TENANT, ws.id) == ws
        renamed = Workspace(id=ws.id, tenant_id=TENANT, name="alpha-renamed")
        await ws_repo.put(renamed)  # id-keyed upsert, no duplicate
        assert await ws_repo.get(TENANT, ws.id) == renamed
        listed = await ws_repo.list(TENANT)
        assert renamed in listed
        assert sum(1 for w in listed if w.id == ws.id) == 1

    @pytest.mark.asyncio
    async def test_tenant_isolation_foreign_equals_absent(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        ws_repo, _ = repos
        ws = _workspace(tenant_id=TENANT)
        await ws_repo.put(ws)
        # Foreign tenant: same error as a genuinely absent id (20 §6).
        with pytest.raises(WorkspaceNotFound):
            await ws_repo.get(OTHER_TENANT, ws.id)
        with pytest.raises(WorkspaceNotFound):
            await ws_repo.get(TENANT, uuid4())
        with pytest.raises(WorkspaceNotFound):
            await ws_repo.delete(OTHER_TENANT, ws.id)
        # The foreign delete attempt destroyed nothing.
        assert await ws_repo.get(TENANT, ws.id) == ws
        # And the list of the other tenant omits the row entirely.
        assert all(w.id != ws.id for w in await ws_repo.list(OTHER_TENANT))

    @pytest.mark.asyncio
    async def test_delete_with_projects_fails_loudly_fk_restrict(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        ws_repo, pr_repo = repos
        ws = _workspace()
        await ws_repo.put(ws)
        project = _project(workspace_id=ws.id)
        await pr_repo.put(project)
        # Schema authority: projects.workspace_id is ondelete=RESTRICT.
        with pytest.raises(IntegrityError):
            await ws_repo.delete(TENANT, ws.id)
        # Nothing was destroyed.
        assert await ws_repo.get(TENANT, ws.id) == ws
        assert await pr_repo.get(TENANT, project.id) == project
        # Unblock: delete the project first, then the workspace.
        await pr_repo.delete(TENANT, project.id)
        await ws_repo.delete(TENANT, ws.id)
        with pytest.raises(WorkspaceNotFound):
            await ws_repo.get(TENANT, ws.id)


@requires_live_postgres
class TestLiveProjects:
    @pytest.mark.asyncio
    async def test_round_trip_upsert_and_metadata(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        _, pr_repo = repos
        project = _project(name="landing", metadata_={"stack": "static"})
        await pr_repo.put(project)
        assert await pr_repo.get(TENANT, project.id) == project
        updated = Project(
            id=project.id,
            tenant_id=TENANT,
            workspace_id=None,
            name="landing-v2",
            metadata={"stack": "static", "iteration": 2},
        )
        await pr_repo.put(updated)
        assert await pr_repo.get(TENANT, project.id) == updated

    @pytest.mark.asyncio
    async def test_list_narrowed_by_workspace(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        ws_repo, pr_repo = repos
        ws = _workspace(name="narrow")
        await ws_repo.put(ws)
        scoped = _project(workspace_id=ws.id, name="inside")
        unscoped = _project(workspace_id=None, name="outside")
        await pr_repo.put(scoped)
        await pr_repo.put(unscoped)
        narrowed = await pr_repo.list(TENANT, workspace_id=ws.id)
        assert scoped in narrowed
        assert all(p.workspace_id == ws.id for p in narrowed)
        everything = await pr_repo.list(TENANT)
        assert scoped in everything and unscoped in everything

    @pytest.mark.asyncio
    async def test_tenant_isolation_foreign_equals_absent(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        _, pr_repo = repos
        project = _project(tenant_id=TENANT)
        await pr_repo.put(project)
        with pytest.raises(ProjectNotFound):
            await pr_repo.get(OTHER_TENANT, project.id)
        with pytest.raises(ProjectNotFound):
            await pr_repo.get(TENANT, uuid4())
        with pytest.raises(ProjectNotFound):
            await pr_repo.delete(OTHER_TENANT, project.id)
        assert await pr_repo.get(TENANT, project.id) == project
        assert all(p.id != project.id for p in await pr_repo.list(OTHER_TENANT))

    @pytest.mark.asyncio
    async def test_delete_removes_row(
        self,
        repos: tuple[PostgresWorkspaceRepository, PostgresProjectRepository],
    ) -> None:
        _, pr_repo = repos
        project = _project()
        await pr_repo.put(project)
        await pr_repo.delete(TENANT, project.id)
        with pytest.raises(ProjectNotFound):
            await pr_repo.get(TENANT, project.id)
