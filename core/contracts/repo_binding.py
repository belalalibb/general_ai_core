"""Repository binding + git operation contracts for the dev agent (R169 A5; INV-1).

A :class:`RepoBinding` is the ONLY thing that ties the development agent to a
remote repository. It carries an opaque ``credential_ref`` (INV-3: the token
itself lives behind ``SecretManagerPort`` and is resolved at the last moment by
the transport adapter, never stored on the binding or in audit). Every refusal
crosses the tool boundary as :class:`GitRefusal` data with a
:class:`GitRefusalCode` (INV-2).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.publish_mode import DEFAULT_ALLOWED_MODES, DEFAULT_PUBLISH_MODE, PublishMode

BranchName = Annotated[str, Field(min_length=1, max_length=255)]
RemoteUrl = Annotated[str, Field(min_length=8, max_length=2048, pattern=r"^https://")]
LocalRoot = Annotated[str, Field(min_length=1, max_length=4096)]


class GitOperation(StrEnum):
    """Closed set of git acts exposed as dev tools (``git.<op>``)."""

    FETCH = "fetch"
    STATUS = "status"
    COMMIT = "commit"
    PUBLISH = "publish"


class GitRefusalCode(StrEnum):
    """Machine-readable refusal codes for git tools (INV-2)."""

    BINDING_UNKNOWN = "binding_unknown"
    BINDING_TENANT_MISMATCH = "binding_tenant_mismatch"
    PATH_OUTSIDE_BINDING = "path_outside_binding"
    CREDENTIAL_UNRESOLVED = "credential_unresolved"
    PUBLISH_MODE_NOT_ALLOWED = "publish_mode_not_allowed"
    REMOTE_REJECTED_PROTECTED_BRANCH = "remote_rejected_protected_branch"
    REMOTE_REJECTED = "remote_rejected"
    NOTHING_TO_COMMIT = "nothing_to_commit"
    INVALID_REF = "invalid_ref"
    TRANSPORT_ERROR = "transport_error"
    VALIDATION_ERROR = "validation_error"


class RepoBinding(ContractModel):
    """One tenant-scoped binding of a local root to a remote branch."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    remote_url: RemoteUrl
    branch: BranchName
    local_root: LocalRoot
    allowed_modes: frozenset[PublishMode] = Field(default=frozenset(DEFAULT_ALLOWED_MODES))
    credential_ref: BoundedStr
    label: BoundedStr | None = None

    def mode_allowed(self, mode: PublishMode) -> bool:
        return mode in self.allowed_modes


class GitFetchRequest(ContractModel):
    binding_id: UUID


class GitStatusRequest(ContractModel):
    binding_id: UUID


class GitCommitRequest(ContractModel):
    binding_id: UUID
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    paths: Annotated[list[BoundedStr], Field(min_length=1, max_length=256)]


class GitPublishRequest(ContractModel):
    binding_id: UUID
    mode: PublishMode = DEFAULT_PUBLISH_MODE
    work_branch: BranchName | None = None
    title: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class GitRefusal(ContractModel):
    """A refused git act, returned as data."""

    ok: bool = False
    code: GitRefusalCode
    reason: str
    binding_id: str | None = None
    suggested_mode: PublishMode | None = None


class GitFetchResult(ContractModel):
    ok: bool = True
    binding_id: str
    remote_head: str | None = None


class GitStatusResult(ContractModel):
    ok: bool = True
    binding_id: str
    branch: str
    head: str | None
    clean: bool
    entries: list[str] = Field(default_factory=list)


class GitCommitResult(ContractModel):
    ok: bool = True
    binding_id: str
    sha: str
    files: int


class GitPublishResult(ContractModel):
    ok: bool = True
    binding_id: str
    mode: PublishMode
    branch: str
    pushed: bool
    pull_request_url: str | None = None
    diff_summary: str | None = None


__all__ = [
    "BranchName",
    "GitCommitRequest",
    "GitCommitResult",
    "GitFetchRequest",
    "GitFetchResult",
    "GitOperation",
    "GitPublishRequest",
    "GitPublishResult",
    "GitRefusal",
    "GitRefusalCode",
    "GitStatusRequest",
    "GitStatusResult",
    "LocalRoot",
    "RemoteUrl",
    "RepoBinding",
]
