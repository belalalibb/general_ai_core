"""Workspace/Project HTTP surface — the EXISTING 03 §2 entities over /v1/*.

Closure directive (operator-verified GAP 1): the Workspace/Project
contracts (core/contracts/identity.py, field-for-field 03 §2) and their
durable repositories (infrastructure/db/repositories/workspaces.py,
tables from migration 0002) have existed with ZERO consumer routes.
This module exposes them over HTTP — it invents NO entity, NO schema,
NO workflow (P1: reuse; P2: compose).

Recorded decisions (the same postures every /v1/* route already holds):

- **Port pattern = the ExecutionStorePort pattern** (apps/api/store.py):
  a structural Protocol matching the EXISTING Postgres repository
  signatures verbatim (async; the repositories are async), plus
  in-memory defaults so the in-memory profile serves the same surface —
  exactly how ``store``/``source_proposals`` behave. The composition
  root binds the durable repositories through the AsyncBridge
  (apps/composition/workspaces.py) — same seam discipline as P-A.1.
- **Tenant isolation**: every read/delete is scoped to the caller's
  tenant_id from the per-request Principal; ``tenant_id`` in bodies
  does NOT exist — the server assigns it from the session (a client
  must not be able to write into a foreign tenant by naming it).
- **Anti-enumeration (20 §6)**: unknown and foreign-tenant ids return
  the SAME recorded unknown-resource mapping — ``validation_error``
  body with HTTP 404 (the closed 10 §9 set has no not_found; this is
  the exact decision apps/api/errors.py records and the executions/
  webhooks routes already apply).
- **Closed shapes**: request bodies are ``extra="forbid"`` models
  (auth-router posture); ids are server-generated UUIDs — no
  client-supplied ids (an id-keyed upsert must not become a
  cross-tenant overwrite probe).
- **No update route**: no doc defines one (absent, not fabricated —
  the WBH-1 posture). Deleting a workspace that still has projects is
  refused with a named 409-style conflict mapped onto the closed set as
  ``validation_error`` 409 — the FK RESTRICT truth surfaced honestly,
  never a silent cascade.
- **Referential check on create**: a project naming a workspace_id is
  admitted only if that workspace exists IN THE CALLER'S TENANT (the
  DB FK would enforce this durably; the port surface enforces it
  uniformly so both profiles behave identically and the error is a
  named 404, not a raw IntegrityError).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from apps.api.errors import error_response
from core.contracts.errors import ErrorCode
from core.contracts.identity import Project, Workspace

if TYPE_CHECKING:
    from apps.api.app import Principal

__all__ = [
    "InMemoryProjectStore",
    "InMemoryWorkspaceStore",
    "ProjectNotFound",
    "ProjectStorePort",
    "WorkspaceHasProjects",
    "WorkspaceNotFound",
    "WorkspaceStorePort",
    "create_workspace_router",
    "unknown_project",
]

_MAX_NAME = 512  # BoundedStr bound (core/contracts/base.py)
_MAX_METADATA_KEYS = 100  # bounded input (P7) — metadata is a JSON object


# --- named refusals (same shapes as the repository layer; app-level) ---------


class WorkspaceNotFound(KeyError):
    """No workspace exists for the requested id IN THIS TENANT.

    Deliberately identical for "absent" and "foreign tenant" (20 §6) —
    mirrors infrastructure/db/repositories/workspaces.py verbatim.
    """

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(f"unknown workspace id: {workspace_id}")
        self.workspace_id = workspace_id


class ProjectNotFound(KeyError):
    """No project exists for the requested id IN THIS TENANT (20 §6)."""

    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"unknown project id: {project_id}")
        self.project_id = project_id


class WorkspaceHasProjects(RuntimeError):
    """Deleting a workspace that still has projects is refused LOUDLY.

    The durable schema enforces this with ondelete=RESTRICT; the port
    surface names the same refusal so the route can map it honestly
    instead of leaking an IntegrityError (20 §4).
    """

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(f"workspace still has projects: {workspace_id}")
        self.workspace_id = workspace_id


# --- ports (structural; match the EXISTING Postgres repositories) ------------


class WorkspaceStorePort(Protocol):
    """What the routes need — satisfied by the Postgres repository
    (via the composition bridge adapter) and the in-memory default."""

    async def put(self, workspace: Workspace) -> None: ...

    async def get(self, tenant_id: UUID, workspace_id: UUID) -> Workspace: ...

    async def list(self, tenant_id: UUID) -> tuple[Workspace, ...]: ...

    async def delete(self, tenant_id: UUID, workspace_id: UUID) -> None: ...


class ProjectStorePort(Protocol):
    async def put(self, project: Project) -> None: ...

    async def get(self, tenant_id: UUID, project_id: UUID) -> Project: ...

    async def list(
        self, tenant_id: UUID, *, workspace_id: UUID | None = None
    ) -> tuple[Project, ...]: ...

    async def delete(self, tenant_id: UUID, project_id: UUID) -> None: ...


# --- in-memory defaults (the InMemoryExecutionStore posture) ------------------


class InMemoryWorkspaceStore:
    """Process-local WorkspaceStorePort; tenant-scoped like the DB rows."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Workspace] = {}

    async def put(self, workspace: Workspace) -> None:
        self._rows[workspace.id] = workspace

    async def get(self, tenant_id: UUID, workspace_id: UUID) -> Workspace:
        row = self._rows.get(workspace_id)
        if row is None or row.tenant_id != tenant_id:  # absent == foreign (20 §6)
            raise WorkspaceNotFound(workspace_id)
        return row

    async def list(self, tenant_id: UUID) -> tuple[Workspace, ...]:
        rows = [w for w in self._rows.values() if w.tenant_id == tenant_id]
        return tuple(sorted(rows, key=lambda w: (w.name, str(w.id))))

    async def delete(self, tenant_id: UUID, workspace_id: UUID) -> None:
        row = self._rows.get(workspace_id)
        if row is None or row.tenant_id != tenant_id:
            raise WorkspaceNotFound(workspace_id)
        del self._rows[workspace_id]


class InMemoryProjectStore:
    """Process-local ProjectStorePort; same ordering as the SQL list."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Project] = {}

    async def put(self, project: Project) -> None:
        self._rows[project.id] = project

    async def get(self, tenant_id: UUID, project_id: UUID) -> Project:
        row = self._rows.get(project_id)
        if row is None or row.tenant_id != tenant_id:  # absent == foreign (20 §6)
            raise ProjectNotFound(project_id)
        return row

    async def list(
        self, tenant_id: UUID, *, workspace_id: UUID | None = None
    ) -> tuple[Project, ...]:
        rows = [
            p
            for p in self._rows.values()
            if p.tenant_id == tenant_id and (workspace_id is None or p.workspace_id == workspace_id)
        ]
        return tuple(sorted(rows, key=lambda p: (p.name, str(p.id))))

    async def delete(self, tenant_id: UUID, project_id: UUID) -> None:
        row = self._rows.get(project_id)
        if row is None or row.tenant_id != tenant_id:
            raise ProjectNotFound(project_id)
        del self._rows[project_id]


# --- request bodies (closed shapes — auth-router posture) ---------------------


class WorkspaceCreateRequest(BaseModel):
    """POST /v1/workspaces body — closed shape (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_MAX_NAME)


class ProjectCreateRequest(BaseModel):
    """POST /v1/projects body — closed shape (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_MAX_NAME)
    workspace_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


# --- serialization (contract → JSON; ids as strings) ---------------------------


def _workspace_json(workspace: Workspace) -> dict[str, object]:
    return {
        "workspace_id": str(workspace.id),
        "name": workspace.name,
    }


def _project_json(project: Project) -> dict[str, object]:
    return {
        "project_id": str(project.id),
        "workspace_id": (str(project.workspace_id) if project.workspace_id is not None else None),
        "name": project.name,
        "metadata": project.metadata,
    }


def _unknown_workspace(workspace_id: str) -> JSONResponse:
    # Recorded unknown-resource mapping: validation_error body, HTTP 404 —
    # identical for absent and foreign (20 §6).
    return error_response(
        ErrorCode.VALIDATION_ERROR,
        "Unknown workspace id.",
        details={"workspace_id": workspace_id},
        http_status=404,
    )


def unknown_project(project_id: str) -> JSONResponse:
    """The ONE 404 for a project reference that does not resolve in the
    caller's tenant (absent == foreign == malformed). Shared with
    ``POST /v1/execute`` (R168 D-08) so both surfaces answer byte-identically."""
    return error_response(
        ErrorCode.VALIDATION_ERROR,
        "Unknown project id.",
        details={"project_id": project_id},
        http_status=404,
    )


_unknown_project = unknown_project


def _bad_uuid(field: str) -> JSONResponse:
    return error_response(
        ErrorCode.VALIDATION_ERROR,
        f"{field} must be a UUID.",
        details={"field": field},
    )


# --- router -------------------------------------------------------------------


def create_workspace_router(
    *,
    workspaces: WorkspaceStorePort,
    projects: ProjectStorePort,
    resolve: Callable[[Request], Principal | JSONResponse],
) -> APIRouter:
    """Build the /v1/workspaces + /v1/projects router.

    ``resolve`` is the SAME per-request principal resolver every
    tenant-scoped handler uses (create_admin_router posture) — identity
    runs FIRST, before parsing and persistence.
    """
    router = APIRouter()

    # --- workspaces -----------------------------------------------------------

    @router.post("/v1/workspaces", status_code=201)
    async def create_workspace(request: Request, body: WorkspaceCreateRequest) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        workspace = Workspace(id=uuid4(), tenant_id=caller.tenant_id, name=body.name)
        await workspaces.put(workspace)
        return JSONResponse(status_code=201, content=_workspace_json(workspace))

    @router.get("/v1/workspaces")
    async def list_workspaces(request: Request) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        rows = await workspaces.list(caller.tenant_id)
        return JSONResponse(
            status_code=200,
            content={"workspaces": [_workspace_json(w) for w in rows]},
        )

    @router.get("/v1/workspaces/{workspace_id}")
    async def get_workspace(request: Request, workspace_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(workspace_id)
        except ValueError:
            return _bad_uuid("workspace_id")
        try:
            workspace = await workspaces.get(caller.tenant_id, parsed)
        except WorkspaceNotFound:
            return _unknown_workspace(workspace_id)
        return JSONResponse(status_code=200, content=_workspace_json(workspace))

    @router.delete("/v1/workspaces/{workspace_id}")
    async def delete_workspace(request: Request, workspace_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(workspace_id)
        except ValueError:
            return _bad_uuid("workspace_id")
        # RESTRICT semantics surfaced uniformly (both profiles) THROUGH
        # THE PORT: a workspace with projects refuses deletion LOUDLY —
        # the durable FK truth, never a silent cascade. The durable
        # adapter's WorkspaceHasProjects translation below is the
        # authoritative backstop (the FK closes any check-then-act gap).
        linked = await projects.list(caller.tenant_id, workspace_id=parsed)
        if linked:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Workspace still has projects.",
                details={"workspace_id": workspace_id},
                http_status=409,
            )
        try:
            await workspaces.delete(caller.tenant_id, parsed)
        except WorkspaceNotFound:
            return _unknown_workspace(workspace_id)
        except WorkspaceHasProjects:
            # The durable adapter translates the FK IntegrityError into
            # this named refusal (apps/composition/workspaces.py).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Workspace still has projects.",
                details={"workspace_id": workspace_id},
                http_status=409,
            )
        return Response(status_code=204)

    # --- projects --------------------------------------------------------------

    @router.post("/v1/projects", status_code=201)
    async def create_project(request: Request, body: ProjectCreateRequest) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        if len(body.metadata) > _MAX_METADATA_KEYS:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "metadata has too many keys.",
                details={"field": "metadata", "max_keys": _MAX_METADATA_KEYS},
            )
        parsed_workspace: UUID | None = None
        if body.workspace_id is not None:
            try:
                parsed_workspace = UUID(body.workspace_id)
            except ValueError:
                return _bad_uuid("workspace_id")
            # Referential admission IN THE CALLER'S TENANT (20 §6): a
            # foreign or absent workspace is the same uniform 404 the
            # by-id route returns — naming a foreign workspace_id must
            # not link a project across tenants.
            try:
                await workspaces.get(caller.tenant_id, parsed_workspace)
            except WorkspaceNotFound:
                return _unknown_workspace(body.workspace_id)
        project = Project(
            id=uuid4(),
            tenant_id=caller.tenant_id,
            workspace_id=parsed_workspace,
            name=body.name,
            metadata=dict(body.metadata),
        )
        await projects.put(project)
        return JSONResponse(status_code=201, content=_project_json(project))

    @router.get("/v1/projects")
    async def list_projects(request: Request, workspace_id: str | None = None) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        parsed_workspace: UUID | None = None
        if workspace_id is not None:
            try:
                parsed_workspace = UUID(workspace_id)
            except ValueError:
                return _bad_uuid("workspace_id")
        rows = await projects.list(caller.tenant_id, workspace_id=parsed_workspace)
        return JSONResponse(
            status_code=200,
            content={"projects": [_project_json(p) for p in rows]},
        )

    @router.get("/v1/projects/{project_id}")
    async def get_project(request: Request, project_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(project_id)
        except ValueError:
            return _bad_uuid("project_id")
        try:
            project = await projects.get(caller.tenant_id, parsed)
        except ProjectNotFound:
            return _unknown_project(project_id)
        return JSONResponse(status_code=200, content=_project_json(project))

    @router.delete("/v1/projects/{project_id}")
    async def delete_project(request: Request, project_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(project_id)
        except ValueError:
            return _bad_uuid("project_id")
        try:
            await projects.delete(caller.tenant_id, parsed)
        except ProjectNotFound:
            return _unknown_project(project_id)
        return Response(status_code=204)

    return router
