"""Source-change admin surface helpers (ADR-0009 / V8 chunk 6).

Request contracts + JSON serialization for the human-only
``/v1/admin/source-changes/*`` routes. The routes drive the
:class:`core.sourcechange.workflow.SourceChangeWorkflow` directly —
this module adds NO workflow logic (P1: one state machine, one consumer
surface; the agent gains NO tools here — R3 stays never-registrable).

Honesty rules carried into serialization:

- Proposal JSON carries operation METADATA (kind, path, content hash,
  size) — never file bytes. Proposed source content is workshop material,
  not an admin-response payload; what crosses the surface is evidence
  (hashes are verifiable, bytes would be an exfiltration channel — the
  criterion 9 secret-boundary posture).
- The §14 posture rides EVERY proposal response
  (``authoritative_apply``) so no reader can mistake a hermetic APPLIED
  state for a real source change.
"""

from __future__ import annotations

import base64
import binascii

from pydantic import Field

from core.contracts.base import ContractModel, JsonObject
from core.sourcechange.errors import MalformedPatch
from core.sourcechange.patch import PatchOperation, PatchOpKind, SourcePatch
from core.sourcechange.proposal import ChangeProposal
from core.sourcechange.snapshot import SourceSnapshot, file_content_hash

__all__ = [
    "ApproveRequest",
    "PatchOperationRequest",
    "ProposeRequest",
    "RejectRequest",
    "SnapshotCreateRequest",
    "build_patch",
    "build_snapshot",
    "proposal_json",
]

_MAX_FILES = 200
_MAX_CONTENT_B64 = 400_000  # ~300 KB decoded per file — bounded input (P7)


class PatchOperationRequest(ContractModel):
    """One proposed operation — content crosses as base64 (bytes are bytes)."""

    kind: PatchOpKind
    path: str = Field(min_length=1, max_length=1_000)
    content_b64: str | None = Field(default=None, max_length=_MAX_CONTENT_B64)


class ProposeRequest(ContractModel):
    """POST /v1/admin/source-changes body."""

    base_snapshot_id: str = Field(min_length=64, max_length=64)
    operations: list[PatchOperationRequest] = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=1, max_length=10_000)


class SnapshotCreateRequest(ContractModel):
    """POST /v1/admin/source-changes/snapshots body — path -> base64 content."""

    files: dict[str, str] = Field(min_length=1, max_length=_MAX_FILES)


class ApproveRequest(ContractModel):
    """POST .../approve body — the approval MUST cite the exact version."""

    cited_hash: str = Field(min_length=64, max_length=64)


class RejectRequest(ContractModel):
    """POST .../reject body."""

    reason: str = Field(min_length=1, max_length=10_000)


def _decode(value: str, where: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MalformedPatch(f"invalid base64 content at {where}: {exc}") from exc


def build_patch(operations: list[PatchOperationRequest]) -> SourcePatch:
    """Request operations -> SourcePatch (all shape rules apply, named)."""
    built: list[PatchOperation] = []
    for op in operations:
        content = (
            _decode(op.content_b64, op.path) if op.content_b64 is not None else None
        )
        built.append(PatchOperation(kind=op.kind, path=op.path, content=content))
    return SourcePatch(operations=tuple(built))


def build_snapshot(files: dict[str, str]) -> SourceSnapshot:
    """Request files -> content-addressed snapshot (paths validated, P7)."""
    return SourceSnapshot.from_files(
        {path: _decode(content, path) for path, content in files.items()}
    )


def proposal_json(
    proposal: ChangeProposal, *, authoritative_apply: JsonObject
) -> JsonObject:
    """Serialize one proposal — metadata and hashes, NEVER file bytes."""
    operations = [
        {
            "kind": op.kind.value,
            "path": op.path,
            "content_sha256": (
                file_content_hash(op.content) if op.content is not None else None
            ),
            "size_bytes": len(op.content) if op.content is not None else None,
        }
        for op in proposal.patch.operations
    ]
    approval: JsonObject | None = None
    if proposal.approval is not None:
        approval = {
            "approver_id": str(proposal.approval.approver_id),
            "approved_patch_hash": proposal.approval.approved_patch_hash,
            "decided_at": proposal.approval.decided_at.isoformat(),
        }
    return {
        "proposal_id": str(proposal.proposal_id),
        "state": proposal.state.value,
        "base_snapshot_id": proposal.base_snapshot_id,
        "patch_hash": proposal.patch_hash,
        "rationale": proposal.rationale,
        "created_at": proposal.created_at.isoformat(),
        "operations": operations,
        "approval": approval,
        "applied_snapshot_id": proposal.applied_snapshot_id,
        "authoritative_apply": authoritative_apply,
    }
