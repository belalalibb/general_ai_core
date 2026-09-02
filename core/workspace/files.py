"""Workspace file surface over ObjectStoragePort (Phase V5, roadmap #8).

The frozen definition, verbatim: "`core/workspace/` over ObjectStoragePort
(files, listing, manifests) + repositories for the existing `workspaces`/
`projects` tables (V1 made them durable). Shared primitive — serves IDE/
marketing/research/Agent/future apps; NOT the source-edit area; NOT
admin-owned. Resource Control rides existing usage seams (reuse, P2)."

Design (P1 REUSE — this module owns NO storage):

- Every byte lives behind the EXISTING :class:`ObjectStoragePort`
  (core/storage/ports.py) — the workspace primitive is a NAMESPACING and
  PATH-DISCIPLINE layer, not a second storage engine. The binding
  (in-memory today, S3 via the existing infrastructure adapter at
  composition) is invisible here.
- Tenant isolation is DOUBLE-scoped: the port itself is tenant-scoped
  (20 §6), and workspace files additionally namespace keys as
  ``ws/{workspace_id}/{path}`` so two workspaces of one tenant can never
  address each other's files through this surface.
- Paths are untrusted input (P7): validated BEFORE any storage call —
  relative, ``/``-separated, no ``..`` segments, no backslash, no control
  characters, no empty segments. A refused path never touches a key.
- The MANIFEST is derived data — a listing of :class:`WorkspaceFile`
  entries computed from storage metadata, never a stored document that
  could drift from reality (P6: the manifest IS the evidence).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from core.storage.ports import ObjectStoragePort
from core.workspace.errors import InvalidWorkspacePath

_KEY_PREFIX = "ws"


@dataclass(frozen=True)
class WorkspaceFile:
    """One workspace file's metadata (never the payload)."""

    workspace_id: UUID
    path: str
    size_bytes: int
    content_type: str
    created_at: datetime


@dataclass(frozen=True)
class WorkspaceManifest:
    """Derived listing of a workspace's files — computed, never stored."""

    workspace_id: UUID
    files: tuple[WorkspaceFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(entry.size_bytes for entry in self.files)


def validate_path(path: str) -> str:
    """Validate one workspace-relative path (P7) or raise, named.

    Rules: non-empty, relative, ``/`` separators only, no ``..`` or ``.``
    segments, no empty segments, no backslash, printable characters only.
    Returns the path unchanged — no normalization, no repair (a path the
    caller did not literally write is a path the caller cannot audit).
    """
    if not path:
        raise InvalidWorkspacePath(path, "path must be non-empty")
    if path.startswith("/"):
        raise InvalidWorkspacePath(path, "path must be relative")
    if "\\" in path:
        raise InvalidWorkspacePath(path, "backslash separators are not allowed")
    if any(ch < " " or ch == "\x7f" for ch in path):
        raise InvalidWorkspacePath(path, "control characters are not allowed")
    for segment in path.split("/"):
        if not segment:
            raise InvalidWorkspacePath(path, "empty path segment")
        if segment in (".", ".."):
            raise InvalidWorkspacePath(path, f"segment {segment!r} is not allowed")
    return path


def _key(workspace_id: UUID, path: str) -> str:
    return f"{_KEY_PREFIX}/{workspace_id}/{path}"


class WorkspaceFiles:
    """Tenant- and workspace-scoped file operations over the storage port.

    Stateless besides the injected port: all identity travels as explicit
    parameters (the port's own posture) — nothing ambient, nothing cached.
    """

    def __init__(self, storage: ObjectStoragePort) -> None:
        self._storage = storage

    def put(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        path: str,
        data: bytes,
        content_type: str,
    ) -> WorkspaceFile:
        """Store ``data`` at ``path`` within the workspace; overwrite allowed."""
        validate_path(path)
        stored = self._storage.put(tenant_id, _key(workspace_id, path), data, content_type)
        return WorkspaceFile(
            workspace_id=workspace_id,
            path=path,
            size_bytes=stored.size_bytes,
            content_type=stored.content_type,
            created_at=stored.created_at,
        )

    def get(self, tenant_id: UUID, workspace_id: UUID, path: str) -> bytes:
        """Return the payload or raise ObjectNotFound (absent == foreign)."""
        validate_path(path)
        return self._storage.get(tenant_id, _key(workspace_id, path))

    def head(self, tenant_id: UUID, workspace_id: UUID, path: str) -> WorkspaceFile:
        """Metadata only — no payload — or raise ObjectNotFound."""
        validate_path(path)
        stored = self._storage.head(tenant_id, _key(workspace_id, path))
        return WorkspaceFile(
            workspace_id=workspace_id,
            path=path,
            size_bytes=stored.size_bytes,
            content_type=stored.content_type,
            created_at=stored.created_at,
        )

    def delete(self, tenant_id: UUID, workspace_id: UUID, path: str) -> None:
        """Delete the file; raise ObjectNotFound if absent."""
        validate_path(path)
        self._storage.delete(tenant_id, _key(workspace_id, path))

    def list_paths(self, tenant_id: UUID, workspace_id: UUID, prefix: str = "") -> tuple[str, ...]:
        """List file paths under ``prefix`` — only within this workspace.

        A prefix MAY end with ``/`` (directory-style listing); the same
        path rules apply to what precedes it.
        """
        if prefix:
            validate_path(prefix.removesuffix("/"))
        namespace = f"{_KEY_PREFIX}/{workspace_id}/"
        keys = self._storage.list_keys(tenant_id, f"{namespace}{prefix}")
        return tuple(key[len(namespace) :] for key in keys)

    def manifest(self, tenant_id: UUID, workspace_id: UUID) -> WorkspaceManifest:
        """Derive the workspace manifest from live storage metadata."""
        entries = [
            self.head(tenant_id, workspace_id, path)
            for path in self.list_paths(tenant_id, workspace_id)
        ]
        return WorkspaceManifest(workspace_id=workspace_id, files=tuple(entries))
