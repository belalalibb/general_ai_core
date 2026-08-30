"""Workspace primitive (MASTER VISION v2 roadmap, Phase V5 / #8).

A shared file/manifest surface over the EXISTING ObjectStoragePort —
serves IDE/marketing/research/Agent/future apps alike. Deliberately NOT
the source-edit area and NOT admin-owned (frozen definition). Durable
workspace/project ENTITIES ride the V1 repository layer (infrastructure/
db/repositories/workspaces.py); this package owns bytes-and-paths only.
"""

from core.workspace.errors import InvalidWorkspacePath, WorkspaceError
from core.workspace.files import (
    WorkspaceFile,
    WorkspaceFiles,
    WorkspaceManifest,
    validate_path,
)

__all__ = [
    "InvalidWorkspacePath",
    "WorkspaceError",
    "WorkspaceFile",
    "WorkspaceFiles",
    "WorkspaceManifest",
    "validate_path",
]
