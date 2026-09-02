"""Engineering-capability contracts (ADR-0012).

Data crossing the shared engineering seam: file change sets, command
results, Git facts, and the Admin-issued authorization that a privileged
act consumes. Contracts only — no I/O, no implementation (41 Phase 1 rule).

- ``EngineeringAct`` is a CLOSED set of privileged acts. Reads are not acts
  (they need a grant + entitlement, never an authorization ticket).
- ``EngineeringAuthorization`` is bounded on every axis: tenant, workspace
  label, acts, uses, expiry, issuer. It never carries secrets or paths.
- Result models carry what happened as DATA (exit codes, conflicts,
  truncation) — a failed command is a successful *observation*.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, utc_now


class EngineeringAct(StrEnum):
    """Acts that require an Admin-issued authorization (closed set)."""

    FS_WRITE = "fs.write"
    CMD_RUN = "cmd.run"
    GIT_COMMIT = "git.commit"
    GIT_PUSH = "git.push"
    GIT_MERGE = "git.merge"


class FileChange(ContractModel):
    """One file operation inside a :class:`ChangeSet`."""

    kind: Literal["write", "move", "delete"]
    path: BoundedStr
    content: str | None = None
    to_path: BoundedStr | None = None


class ChangeSet(ContractModel):
    """An atomic multi-file change: all operations apply or none do."""

    changes: Annotated[list[FileChange], Field(min_length=1, max_length=64)]
    reason: BoundedStr | None = None


class ChangeSetResult(ContractModel):
    applied: bool
    operations: int
    paths: list[str] = Field(default_factory=list)
    rolled_back: bool = False
    error: str | None = None


#: Hard ceiling on one command's wall-clock (ADR-0012 §2).
MAX_COMMAND_TIMEOUT_MS = 120_000
#: Cap on captured stdout/stderr bytes each (truncation is loud data).
MAX_COMMAND_OUTPUT_BYTES = 65_536


class CommandRequest(ContractModel):
    """One bounded command: argv (no shell), workspace-relative cwd, timeout."""

    argv: Annotated[list[BoundedStr], Field(min_length=1, max_length=64)]
    cwd: BoundedStr | None = None
    timeout_ms: Annotated[int, Field(ge=1, le=MAX_COMMAND_TIMEOUT_MS)] = 60_000


class CommandResult(ContractModel):
    argv: list[str]
    exit_code: int | None
    timed_out: bool = False
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class GitStatus(ContractModel):
    branch: str
    head: str | None
    clean: bool
    entries: list[str] = Field(default_factory=list)


class GitCommitInfo(ContractModel):
    sha: str
    subject: str


class GitCommitResult(ContractModel):
    committed: bool
    sha: str | None = None
    reason: str | None = None


class GitPushResult(ContractModel):
    pushed: bool
    remote: str
    branch: str
    reason: str | None = None


class GitMergeResult(ContractModel):
    merged: bool
    into: str
    source: str
    conflicts: list[str] = Field(default_factory=list)
    sha: str | None = None
    reason: str | None = None


class EngineeringAuthorization(ContractModel):
    """A bounded, consumable ticket for privileged engineering acts."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    workspace: BoundedStr
    acts: Annotated[list[EngineeringAct], Field(min_length=1)]
    uses_remaining: Annotated[int, Field(ge=0, le=1_000)] = 1
    expires_at: datetime
    issued_by: UUID
    issued_at: datetime = Field(default_factory=utc_now)
    note: BoundedStr | None = None
    revoked: bool = False


__all__ = [
    "MAX_COMMAND_OUTPUT_BYTES",
    "MAX_COMMAND_TIMEOUT_MS",
    "ChangeSet",
    "ChangeSetResult",
    "CommandRequest",
    "CommandResult",
    "EngineeringAct",
    "EngineeringAuthorization",
    "FileChange",
    "GitCommitInfo",
    "GitCommitResult",
    "GitMergeResult",
    "GitPushResult",
    "GitStatus",
]
