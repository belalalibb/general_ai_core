"""Durable Workspace/Project store bindings (closure GAP 1).

Same posture as P-A.1 (durability.py) and P-B (sourcechange.py): the
EXISTING Postgres repositories (infrastructure/db/repositories/
workspaces.py — V5, tables from migration 0002) gain their first
production consumer WITHOUT any route or call-site change. The route
module (apps/api/workspaces.py) speaks structural ports; this module
adapts the repositories onto those ports:

- **Loop affinity**: asyncpg pools are loop-bound to the AsyncBridge
  loop — every call crosses via ``bridge.run_async`` (the BridgedOutbox
  pattern verbatim; the caller loop stays free).
- **Named-refusal translation**: the repository's ``WorkspaceNotFound``/
  ``ProjectNotFound`` become the app-level twins the routes catch —
  foreign-tenant and absent stay indistinguishable through BOTH layers
  (20 §6), exactly like the ExecutionNotFound translation in
  durability.py.
- **FK RESTRICT translation**: deleting a workspace that still has
  projects hits the ``projects.workspace_id`` FK (ondelete=RESTRICT);
  the resulting IntegrityError becomes the named
  ``WorkspaceHasProjects`` refusal the route maps to 409 — the schema's
  truth surfaced honestly, never a silent cascade (and never a raw
  driver error leaking to a client, 20 §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from apps.api.workspaces import (
    ProjectNotFound,
    WorkspaceHasProjects,
    WorkspaceNotFound,
)
from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.identity import Project, Workspace
from infrastructure.db.repositories.workspaces import (
    PostgresProjectRepository,
    PostgresWorkspaceRepository,
)
from infrastructure.db.repositories.workspaces import (
    ProjectNotFound as RepoProjectNotFound,
)
from infrastructure.db.repositories.workspaces import (
    WorkspaceNotFound as RepoWorkspaceNotFound,
)

__all__ = [
    "DurableProjectStore",
    "DurableWorkspaceStore",
    "build_durable_workspace_stores",
]


@dataclass(frozen=True)
class DurableWorkspaceStore:
    """WorkspaceStorePort over the EXISTING Postgres repository (bridged)."""

    repository: PostgresWorkspaceRepository
    bridge: AsyncBridge

    async def put(self, workspace: Workspace) -> None:
        await self.bridge.run_async(self.repository.put(workspace))

    async def get(self, tenant_id: UUID, workspace_id: UUID) -> Workspace:
        try:
            return await self.bridge.run_async(
                self.repository.get(tenant_id, workspace_id)
            )
        except RepoWorkspaceNotFound as exc:
            raise WorkspaceNotFound(workspace_id) from exc

    async def list(self, tenant_id: UUID) -> tuple[Workspace, ...]:
        return await self.bridge.run_async(self.repository.list(tenant_id))

    async def delete(self, tenant_id: UUID, workspace_id: UUID) -> None:
        try:
            await self.bridge.run_async(
                self.repository.delete(tenant_id, workspace_id)
            )
        except RepoWorkspaceNotFound as exc:
            raise WorkspaceNotFound(workspace_id) from exc
        except IntegrityError as exc:
            # projects.workspace_id FK (ondelete=RESTRICT) — the schema
            # refused the delete; name it (route maps to 409).
            raise WorkspaceHasProjects(workspace_id) from exc


@dataclass(frozen=True)
class DurableProjectStore:
    """ProjectStorePort over the EXISTING Postgres repository (bridged)."""

    repository: PostgresProjectRepository
    bridge: AsyncBridge

    async def put(self, project: Project) -> None:
        await self.bridge.run_async(self.repository.put(project))

    async def get(self, tenant_id: UUID, project_id: UUID) -> Project:
        try:
            return await self.bridge.run_async(
                self.repository.get(tenant_id, project_id)
            )
        except RepoProjectNotFound as exc:
            raise ProjectNotFound(project_id) from exc

    async def list(
        self, tenant_id: UUID, *, workspace_id: UUID | None = None
    ) -> tuple[Project, ...]:
        return await self.bridge.run_async(
            self.repository.list(tenant_id, workspace_id=workspace_id)
        )

    async def delete(self, tenant_id: UUID, project_id: UUID) -> None:
        try:
            await self.bridge.run_async(
                self.repository.delete(tenant_id, project_id)
            )
        except RepoProjectNotFound as exc:
            raise ProjectNotFound(project_id) from exc


def build_durable_workspace_stores(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> tuple[DurableWorkspaceStore, DurableProjectStore]:
    """Adapt the ALREADY-COMPOSED repositories (DatabaseBindings built
    them since V5) onto the route ports — same builder shape as
    ``build_durable_sourcechange_stores`` (P1: one pattern)."""
    return (
        DurableWorkspaceStore(repository=bindings.workspaces, bridge=bridge),
        DurableProjectStore(repository=bindings.projects, bridge=bridge),
    )
