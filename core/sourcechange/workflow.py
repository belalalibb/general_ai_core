"""The R3 Source-Change Workflow state machine (ADR-0009 / V8 chunk 5).

Orchestrates the full lifecycle over the chunk 2–4 primitives:

    propose -> verify (differential, in-sandbox) -> approve | reject
            -> apply -> rollback

Every human act appends an ``APPROVAL_DECISION`` audit row through the
EXISTING :class:`AuditLogPort` (no new event types — the closed 20 §9 set
stays closed; act detail rides ``AuditEvent.details``). The durable
proposal records themselves are the workflow evidence (criterion 11).

§14 ACTIVATION GATE (ADR-0009, structural):

- ``apply()`` derives the applied snapshot INSIDE the snapshot store's
  own space and records the evidence pair — it never touches
  authoritative source.
- Writing to authoritative source would require an
  :class:`AuthoritativeApplierPort` — an optional seam defaulting to
  ``None`` with NO implementation anywhere in this repository. While the
  seam is absent, :meth:`authoritative_apply_status` answers
  ``{"available": False, "gate": "S14_OPERATOR_GATE"}`` honestly (P6),
  and there is no code path that could write authoritative source even
  if asked. Activation later = implement + compose the port — a
  composition change, not a redesign (criterion 12).

Post-apply verification (criterion 10): ``apply()`` re-runs the suite
over the applied snapshot through the SAME sandbox and stores the report
in the audit details — an applied change whose verification cannot be
reproduced afterward is a rollback candidate, visible immediately.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.sourcechange.errors import UnknownSnapshot
from core.sourcechange.patch import SourcePatch, apply_patch, invert_patch
from core.sourcechange.proposal import (
    ApprovalRecord,
    ChangeProposal,
    ProposalState,
)
from core.sourcechange.sandbox import (
    DifferentialVerdict,
    DifferentialVerifier,
    SandboxPort,
    VerificationSuite,
)
from core.sourcechange.store import ProposalStorePort, SnapshotStorePort

__all__ = ["AuthoritativeApplierPort", "SourceChangeWorkflow"]


class AuthoritativeApplierPort(Protocol):
    """The ONLY doorway from applied snapshots to authoritative source.

    §14: this protocol has NO implementation anywhere in the repository
    during V8, and the workflow seam defaults to ``None``. It exists so
    that later activation is a composition act (criterion 12) — and so
    that its absence is a checkable, testable fact rather than a comment.
    """

    def apply_to_authoritative_source(
        self, tenant_id: UUID, snapshot_id: str
    ) -> None: ...


class SourceChangeWorkflow:
    """Tenant-scoped source-change lifecycle over ports (all injected).

    ``authoritative_applier`` deliberately defaults to ``None`` and V8
    composes it as ``None`` everywhere — see module docstring.
    """

    def __init__(
        self,
        *,
        proposals: ProposalStorePort,
        snapshots: SnapshotStorePort,
        sandbox: SandboxPort,
        suite: VerificationSuite,
        audit: AuditLogPort | None = None,
        authoritative_applier: AuthoritativeApplierPort | None = None,
    ) -> None:
        self._proposals = proposals
        self._snapshots = snapshots
        self._verifier = DifferentialVerifier(sandbox)
        self._sandbox = sandbox
        self._suite = suite
        self._audit = audit
        self._authoritative_applier = authoritative_applier

    # --- honesty surface (P6) -------------------------------------------------------

    def authoritative_apply_status(self) -> dict[str, object]:
        """Named §14 posture — never silent, never fabricated."""
        if self._authoritative_applier is None:
            return {"available": False, "gate": "S14_OPERATOR_GATE"}
        return {"available": True}  # pragma: no cover - unreachable in V8

    # --- audit (criterion 11; closed event set preserved) ----------------------------

    def _record(
        self, proposal: ChangeProposal, act: str, detail: dict[str, object]
    ) -> None:
        if self._audit is None:
            return
        self._audit.append(
            AuditEvent(
                tenant_id=proposal.tenant_id,
                event_type=AuditEventType.APPROVAL_DECISION,
                actor_id=proposal.actor_id,
                details={
                    "surface": "source_change_workflow",
                    "act": act,
                    "proposal_id": str(proposal.proposal_id),
                    "patch_hash": proposal.patch_hash,
                    "state": proposal.state.value,
                    **detail,
                },
            )
        )

    # --- lifecycle acts ---------------------------------------------------------------

    def propose(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        base_snapshot_id: str,
        patch: SourcePatch,
        rationale: str,
    ) -> ChangeProposal:
        """Create a DRAFT proposal against a stored, integrity-verified base.

        The base snapshot must already exist in the store — proposing
        against an unknown base is an :class:`UnknownSnapshot` refusal,
        so every proposal is anchored to verifiable content from birth.
        """
        self._snapshots.get_snapshot(tenant_id, base_snapshot_id)  # existence gate
        proposal = ChangeProposal(
            tenant_id=tenant_id,
            actor_id=actor_id,
            base_snapshot_id=base_snapshot_id,
            patch=patch,
            rationale=rationale,
        )
        self._proposals.save_proposal(proposal)
        self._record(proposal, "propose", {"rationale": rationale})
        return proposal

    def verify(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        """DRAFT -> VERIFIED | FAILED_VERIFICATION via differential run.

        The patched snapshot is derived in-memory, verified against the
        base in the sandbox, and STORED only when the differential passes
        (a failing candidate never becomes addressable content).
        """
        proposal = self._proposals.get_proposal(tenant_id, proposal_id)
        base = self._snapshots.get_snapshot(tenant_id, proposal.base_snapshot_id)
        patched = apply_patch(base, proposal.patch)
        report = self._verifier.verify(base, patched, self._suite)
        if report.verdict is DifferentialVerdict.PASS:
            self._snapshots.save_snapshot(tenant_id, patched)
            updated = proposal.with_state(ProposalState.VERIFIED)
        else:
            updated = proposal.with_state(ProposalState.FAILED_VERIFICATION)
        self._proposals.save_proposal(updated)
        self._record(
            updated,
            "verify",
            {
                "verdict": report.verdict.value,
                "regressions": list(report.regressions),
                "improvements": list(report.improvements),
                "base_report": report.base_report.canonical_json(),
                "patched_report": report.patched_report.canonical_json(),
            },
        )
        return updated

    def approve(
        self, tenant_id: UUID, proposal_id: UUID, approver_id: UUID, cited_hash: str
    ) -> ChangeProposal:
        """VERIFIED -> APPROVED — the approval must cite the exact version.

        Criterion 7 is enforced by :meth:`ChangeProposal.with_approval`;
        this method adds nothing it could get wrong (one door, one check).
        """
        proposal = self._proposals.get_proposal(tenant_id, proposal_id)
        updated = proposal.with_approval(
            ApprovalRecord(approver_id=approver_id, approved_patch_hash=cited_hash)
        )
        self._proposals.save_proposal(updated)
        self._record(
            updated, "approve", {"approver_id": str(approver_id), "cited_hash": cited_hash}
        )
        return updated

    def reject(
        self, tenant_id: UUID, proposal_id: UUID, approver_id: UUID, reason: str
    ) -> ChangeProposal:
        proposal = self._proposals.get_proposal(tenant_id, proposal_id)
        updated = proposal.with_state(ProposalState.REJECTED)
        self._proposals.save_proposal(updated)
        self._record(
            updated, "reject", {"approver_id": str(approver_id), "reason": reason}
        )
        return updated

    def apply(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        """APPROVED -> APPLIED within the snapshot store's space ONLY.

        Records the evidence pair (applied snapshot id + inverse patch —
        the rollback instrument, criterion 8) and re-verifies the applied
        snapshot post-apply (criterion 10). NEVER touches authoritative
        source: no code path from here reaches outside the store.
        """
        proposal = self._proposals.get_proposal(tenant_id, proposal_id)
        base = self._snapshots.get_snapshot(tenant_id, proposal.base_snapshot_id)
        applied_snapshot = apply_patch(base, proposal.patch)
        inverse = invert_patch(proposal.patch, base)
        self._snapshots.save_snapshot(tenant_id, applied_snapshot)
        updated = proposal.with_applied(
            applied_snapshot_id=applied_snapshot.snapshot_id, inverse_patch=inverse
        )
        self._proposals.save_proposal(updated)
        post_apply = self._sandbox.run_verification(applied_snapshot, self._suite)
        self._record(
            updated,
            "apply",
            {
                "applied_snapshot_id": applied_snapshot.snapshot_id,
                "post_apply_report": post_apply.canonical_json(),
                "post_apply_passed": post_apply.passed,
                "authoritative_apply": self.authoritative_apply_status(),
            },
        )
        return updated

    def rollback(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        """APPLIED -> ROLLED_BACK by replaying the recorded inverse patch
        through the SAME apply machinery (one code path, criterion 8).

        The restored snapshot must equal the base by content address —
        verified here, recorded in the audit row.
        """
        proposal = self._proposals.get_proposal(tenant_id, proposal_id)
        updated = proposal.with_state(ProposalState.ROLLED_BACK)
        if proposal.applied_snapshot_id is None or proposal.inverse_patch is None:
            raise UnknownSnapshot("<no applied snapshot recorded>")
        applied_snapshot = self._snapshots.get_snapshot(
            tenant_id, proposal.applied_snapshot_id
        )
        restored = apply_patch(applied_snapshot, proposal.inverse_patch)
        restored_matches_base = restored.snapshot_id == proposal.base_snapshot_id
        self._snapshots.save_snapshot(tenant_id, restored)
        self._proposals.save_proposal(updated)
        self._record(
            updated,
            "rollback",
            {
                "restored_snapshot_id": restored.snapshot_id,
                "restored_matches_base": restored_matches_base,
            },
        )
        return updated

    # --- reads -------------------------------------------------------------------------

    def get(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        return self._proposals.get_proposal(tenant_id, proposal_id)

    def list(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        return self._proposals.list_proposals(tenant_id)
