"""Workspace/Project repositories — durable bindings for the V5 primitive.

Vision V5 (frozen roadmap): repositories for the EXISTING ``workspaces``/
``projects`` tables (V1 made them durable via migration 0002) and the
EXISTING ``Workspace``/``Project`` contracts (core/contracts/identity.py,
03 §2 field-for-field). Nothing here invents schema or contracts — this
module is purely the missing row↔contract binding (P1 COMPLETE).

Shared V1 posture (verbatim from the seven proven repositories):

- Session FACTORY injected; repositories never construct engines.
- Rows ↔ frozen contract models at the boundary; no live ORM state
  escapes (engine.py: ``expire_on_commit=False``).
- Tenant isolation is structural IN SQL (20 §6): every read/delete is
  tenant-scoped; a foreign row and an absent row raise the SAME named
  error (anti-enumeration); lists simply omit foreign rows.
- ``put`` is an id-keyed upsert (pg_insert ``on_conflict_do_update``) —
  the catalog pattern; durable row is the single source of truth.
- Referential integrity stays with the schema authority: deleting a
  workspace that still has projects hits the ``projects.workspace_id``
  FK (ondelete=RESTRICT) and the IntegrityError surfaces LOUDLY — the
  repository does not paper over it with cascades the schema refused.

Scope note (roadmap V5): the workspace FILE area is core/workspace/
over ObjectStoragePort — this module persists the workspace/project
ENTITIES only. NOT the source-edit area; NOT admin-owned.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.identity import Project, Workspace
from infrastructure.db.repositories.errors import RepositoryError
from infrastructure.db.tables import projects, workspaces


class WorkspaceNotFound(RepositoryError):
    """No workspace exists for the requested id IN THIS TENANT.

    Deliberately identical for "absent" and "foreign tenant" (20 §6).
    """

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(f"unknown workspace id: {workspace_id}")
        self.workspace_id = workspace_id


class ProjectNotFound(RepositoryError):
    """No project exists for the requested id IN THIS TENANT.

    Deliberately identical for "absent" and "foreign tenant" (20 §6).
    """

    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"unknown project id: {project_id}")
        self.project_id = project_id


def _row_to_workspace(row: Any) -> Workspace:
    return Workspace(id=row.id, tenant_id=row.tenant_id, name=row.name)


def _row_to_project(row: Any) -> Project:
    return Project(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        metadata=row.metadata,
    )


class PostgresWorkspaceRepository:
    """Durable workspace entities over the existing ``workspaces`` table."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def put(self, workspace: Workspace) -> None:
        """Insert or update by id (id-keyed upsert; tenant never mutates)."""
        stmt = pg_insert(workspaces).values(
            id=workspace.id,
            tenant_id=workspace.tenant_id,
            name=workspace.name,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"name": stmt.excluded.name},
        )
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(stmt)

    async def get(self, tenant_id: UUID, workspace_id: UUID) -> Workspace:
        stmt = select(workspaces).where(
            workspaces.c.id == workspace_id,
            workspaces.c.tenant_id == tenant_id,
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).one_or_none()
        if row is None:  # absent == foreign (20 §6)
            raise WorkspaceNotFound(workspace_id)
        return _row_to_workspace(row)

    async def list(self, tenant_id: UUID) -> tuple[Workspace, ...]:
        stmt = (
            select(workspaces)
            .where(workspaces.c.tenant_id == tenant_id)
            .order_by(workspaces.c.name, workspaces.c.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_row_to_workspace(row) for row in rows)

    async def delete(self, tenant_id: UUID, workspace_id: UUID) -> None:
        """Delete IN THIS TENANT; a workspace with projects fails LOUDLY.

        The ``projects.workspace_id`` FK is ondelete=RESTRICT — the
        resulting IntegrityError propagates unwrapped (schema authority;
        silently cascading would destroy rows the schema protects).
        """
        stmt = (
            delete(workspaces)
            .where(
                workspaces.c.id == workspace_id,
                workspaces.c.tenant_id == tenant_id,
            )
            .returning(workspaces.c.id)
        )
        async with self._sessions() as session:
            async with session.begin():
                deleted = (await session.execute(stmt)).one_or_none()
        if deleted is None:  # absent == foreign (20 §6)
            raise WorkspaceNotFound(workspace_id)


class PostgresProjectRepository:
    """Durable project entities over the existing ``projects`` table."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def put(self, project: Project) -> None:
        """Insert or update by id (id-keyed upsert; tenant never mutates)."""
        stmt = pg_insert(projects).values(
            id=project.id,
            tenant_id=project.tenant_id,
            workspace_id=project.workspace_id,
            name=project.name,
            metadata=dict(project.metadata),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "workspace_id": stmt.excluded.workspace_id,
                "name": stmt.excluded.name,
                "metadata": stmt.excluded.metadata,
            },
        )
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(stmt)

    async def get(self, tenant_id: UUID, project_id: UUID) -> Project:
        stmt = select(projects).where(
            projects.c.id == project_id,
            projects.c.tenant_id == tenant_id,
        )
        async with self._sessions() as session:
            row = (await session.execute(stmt)).one_or_none()
        if row is None:  # absent == foreign (20 §6)
            raise ProjectNotFound(project_id)
        return _row_to_project(row)

    async def list(
        self,
        tenant_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> tuple[Project, ...]:
        """Tenant-scoped list, optionally narrowed to one workspace.

        ``workspace_id=None`` means "all projects in the tenant" (the
        column is nullable — unscoped projects are first-class per 03
        §2), so narrowing is opt-in via the keyword.
        """
        stmt = select(projects).where(projects.c.tenant_id == tenant_id)
        if workspace_id is not None:
            stmt = stmt.where(projects.c.workspace_id == workspace_id)
        stmt = stmt.order_by(projects.c.name, projects.c.id)
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_row_to_project(row) for row in rows)

    async def delete(self, tenant_id: UUID, project_id: UUID) -> None:
        stmt = (
            delete(projects)
            .where(
                projects.c.id == project_id,
                projects.c.tenant_id == tenant_id,
            )
            .returning(projects.c.id)
        )
        async with self._sessions() as session:
            async with session.begin():
                deleted = (await session.execute(stmt)).one_or_none()
        if deleted is None:  # absent == foreign (20 §6)
            raise ProjectNotFound(project_id)
