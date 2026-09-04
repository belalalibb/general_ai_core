"""Approval payload binding refusals (R172 C6; HARVEST row 6).

An approval in the tool fabric is a string state (``approval_state ==
"approved"``) checked by ``core/tools/gate.py``. That check alone does not
bind the approval to the *payload* the human actually saw: a caller may obtain
approval for one write and submit another under the same state. C6 closes
that gap ABOVE the gate — the dev surface hashes the canonical JSON of the
call arguments and compares it against the hash the approval was granted for.

These contracts carry the typed refusal (INV-2). They echo hashes only — never
the arguments — so the refusal itself cannot leak file content or secrets.

Owner decision (pinned by ``tests/agent_dev/test_payload_binding_r172.py``):
the gate signature stays string-state only; binding is a surface concern and
is opt-in per composition (``payload_binding=True``).
"""

from __future__ import annotations

from enum import StrEnum

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.source_write import Sha256Hex


class ApprovalBindingRefusalCode(StrEnum):
    """Closed set of payload-binding refusal reasons (verbatim gate reasons)."""

    APPROVAL_HASH_REQUIRED = "approval_hash_required"
    """Write-class call under ``approved`` state but no approved payload hash."""

    APPROVAL_PAYLOAD_MISMATCH = "approval_payload_mismatch"
    """Canonical hash of the submitted arguments differs from the approved hash."""

    PAYLOAD_NOT_CANONICALISABLE = "payload_not_canonicalisable"
    """Arguments contain floats / non-JSON values and cannot be hashed stably."""


class ApprovalBindingRefusal(ContractModel):
    """Typed data attached to a payload-binding refusal (``error_detail``)."""

    code: ApprovalBindingRefusalCode
    permission: BoundedStr
    approved_hash: BoundedStr | None = None
    """Hash the caller claimed approval for, verbatim (may be malformed)."""

    payload_hash: Sha256Hex | None = None
    """sha256 of the canonical arguments; ``None`` when not canonicalisable."""

    reason: BoundedStr
