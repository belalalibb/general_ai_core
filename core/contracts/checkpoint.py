"""Checkpoint / undo contracts for the dev-agent write path (R172 C5; INV-1, INV-2).

A :class:`Checkpoint` records, for ONE ``source.write`` apply, the content hash
of the target before the write (``pre_sha256``; ``None`` = file did not exist)
and after it (``post_sha256``; ``None`` = file deleted, or not yet sealed).
The bytes themselves live in a content-addressed object store outside the
working tree; the index only carries hashes and metadata.

States: ``open`` (snapshot taken, apply in flight) -> ``sealed`` (apply
succeeded) | ``partial`` (apply refused or crashed) -> ``restored``.
Restore outcomes and refusals are data.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, utc_now
from core.contracts.source_write import RelPath, Sha256Hex, SourceWriteOp

CHECKPOINT_INDEX_VERSION: Literal[1] = 1

CheckpointState = Literal["open", "sealed", "partial", "restored"]
CheckpointSourceState = Literal["missing", "ok", "partial", "malformed", "unreadable"]
RestoreOutcome = Literal["noop", "reverted"]


class CheckpointRefusalCode(StrEnum):
    CHECKPOINT_UNKNOWN = "checkpoint_unknown"
    CHECKPOINT_CONFLICT = "checkpoint_conflict"
    OBJECT_STORE_CORRUPT = "object_store_corrupt"
    PATH_REFUSED = "path_refused"
    IO_ERROR = "io_error"


class Checkpoint(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    path: RelPath
    op: SourceWriteOp
    pre_sha256: Sha256Hex | None
    post_sha256: Sha256Hex | None = None
    state: CheckpointState = "open"
    created_at: datetime = Field(default_factory=utc_now)
    sealed_at: datetime | None = None
    restored_at: datetime | None = None


class CheckpointIndexDocument(ContractModel):
    version: Literal[1] = CHECKPOINT_INDEX_VERSION
    checkpoints: tuple[Checkpoint, ...] = ()


class CheckpointSkippedRecord(ContractModel):
    index: int = Field(ge=0)
    reason: BoundedStr


class CheckpointLoadReport(ContractModel):
    checkpoints: tuple[Checkpoint, ...] = ()
    skipped: tuple[CheckpointSkippedRecord, ...] = ()
    source_state: CheckpointSourceState


class RestoreResult(ContractModel):
    ok: bool = True
    checkpoint_id: UUID
    outcome: RestoreOutcome
    path: RelPath
    restored_sha256: Sha256Hex | None


class CheckpointRefusal(ContractModel):
    ok: bool = False
    code: CheckpointRefusalCode
    reason: BoundedStr
    checkpoint_id: UUID | None = None
    path: str | None = None


__all__ = [
    "CHECKPOINT_INDEX_VERSION",
    "Checkpoint",
    "CheckpointIndexDocument",
    "CheckpointLoadReport",
    "CheckpointRefusal",
    "CheckpointRefusalCode",
    "CheckpointSkippedRecord",
    "CheckpointSourceState",
    "CheckpointState",
    "RestoreOutcome",
    "RestoreResult",
]
