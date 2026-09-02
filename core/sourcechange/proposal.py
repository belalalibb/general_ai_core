"""Change proposals: versioned records + closed lifecycle (ADR-0009 / V8).

A :class:`ChangeProposal` is a frozen record binding a patch to a base
snapshot through ``patch_hash`` — the content-addressed VERSION identity
approvals bind to (criterion 7). The lifecycle is a closed transition map
(criterion 6: ``FAILED_VERIFICATION`` has NO outgoing transitions, so a
failed proposal can never be approved — structurally).

Lifecycle (ADR-0009, verbatim):

    DRAFT -> VERIFIED | FAILED_VERIFICATION
    VERIFIED -> APPROVED | REJECTED
    APPROVED -> APPLIED
    APPLIED -> ROLLED_BACK

Records are immutable; every transition derives a NEW record via
``dataclasses.replace`` after the closed map admits it. History therefore
cannot be rewritten — only appended (evidence-first, criterion 11: the
store keeps each proposal's latest record, and audit rows carry the acts).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4

from core.contracts.base import utc_now
from core.sourcechange.errors import ApprovalHashMismatch, InvalidTransition
from core.sourcechange.patch import SourcePatch, patch_hash

__all__ = [
    "ApprovalRecord",
    "ChangeProposal",
    "PROPOSAL_TRANSITIONS",
    "ProposalState",
]


class ProposalState(StrEnum):
    """Closed proposal lifecycle — ADR-0009."""

    DRAFT = "draft"
    VERIFIED = "verified"
    FAILED_VERIFICATION = "failed_verification"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


#: The complete transition map. Absence = refusal. FAILED_VERIFICATION,
#: REJECTED and ROLLED_BACK map to the EMPTY set explicitly (terminal —
#: written out so the closure is visible, not implied).
PROPOSAL_TRANSITIONS: Mapping[ProposalState, frozenset[ProposalState]] = MappingProxyType(
    {
        ProposalState.DRAFT: frozenset({ProposalState.VERIFIED, ProposalState.FAILED_VERIFICATION}),
        ProposalState.VERIFIED: frozenset({ProposalState.APPROVED, ProposalState.REJECTED}),
        ProposalState.FAILED_VERIFICATION: frozenset(),
        ProposalState.APPROVED: frozenset({ProposalState.APPLIED}),
        ProposalState.REJECTED: frozenset(),
        ProposalState.APPLIED: frozenset({ProposalState.ROLLED_BACK}),
        ProposalState.ROLLED_BACK: frozenset(),
    }
)


@dataclass(frozen=True)
class ApprovalRecord:
    """One human approval act, bound to the exact proposal version.

    ``approved_patch_hash`` is REQUIRED and is checked against the
    proposal at transition time (criterion 7). The record carries who and
    when — audit rows reference it; it never carries authority by itself.
    """

    approver_id: UUID
    approved_patch_hash: str
    decided_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ChangeProposal:
    """One immutable proposal record (a version in the lifecycle).

    ``patch_hash`` is DERIVED at construction from the patch and base
    snapshot id — it cannot be supplied, so it cannot lie (criterion 1).
    """

    tenant_id: UUID
    actor_id: UUID
    base_snapshot_id: str
    patch: SourcePatch
    rationale: str
    proposal_id: UUID = field(default_factory=uuid4)
    state: ProposalState = ProposalState.DRAFT
    patch_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)
    approval: ApprovalRecord | None = None
    applied_snapshot_id: str | None = None
    inverse_patch: SourcePatch | None = None

    def __post_init__(self) -> None:
        derived = patch_hash(self.patch, self.base_snapshot_id)
        if self.patch_hash and self.patch_hash != derived:
            raise ApprovalHashMismatch(derived, self.patch_hash)
        object.__setattr__(self, "patch_hash", derived)

    def _transition(self, target: ProposalState) -> None:
        if target not in PROPOSAL_TRANSITIONS[self.state]:
            raise InvalidTransition(self.state.value, target.value)

    def with_state(self, target: ProposalState) -> ChangeProposal:
        """Derive the successor record — closed-map enforced, named refusal."""
        self._transition(target)
        return replace(self, state=target)

    def with_approval(self, approval: ApprovalRecord) -> ChangeProposal:
        """VERIFIED -> APPROVED, iff the approval cites this exact version.

        Criterion 7 enforced HERE, at the only door into APPROVED: a
        mismatched hash is an :class:`ApprovalHashMismatch` naming both
        values, and no state change occurs.
        """
        self._transition(ProposalState.APPROVED)
        if approval.approved_patch_hash != self.patch_hash:
            raise ApprovalHashMismatch(self.patch_hash, approval.approved_patch_hash)
        return replace(self, state=ProposalState.APPROVED, approval=approval)

    def with_applied(self, applied_snapshot_id: str, inverse_patch: SourcePatch) -> ChangeProposal:
        """APPROVED -> APPLIED, recording the evidence pair.

        The applied snapshot id and the inverse patch (the rollback
        instrument, criterion 8) are recorded ON the proposal — apply
        without rollback evidence cannot be represented.
        """
        self._transition(ProposalState.APPLIED)
        return replace(
            self,
            state=ProposalState.APPLIED,
            applied_snapshot_id=applied_snapshot_id,
            inverse_patch=inverse_patch,
        )
