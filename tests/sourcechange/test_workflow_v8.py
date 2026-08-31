"""V8 chunk 5 — SourceChangeWorkflow state machine (ADR-0009).

Acceptance-criteria mapping (this chunk's share):

- criterion 6 -> a REGRESSION differential forces FAILED_VERIFICATION and
  approve is then refused (no edge exists).
- criterion 7 -> workflow-level re-proof: approve with a stale/forged hash
  is refused, names both hashes, persists nothing.
- criterion 8 -> rollback replays the recorded inverse through the same
  apply machinery; restored snapshot content-equals the base.
- criterion 10 -> apply re-verifies the applied snapshot and records the
  post-apply report in the audit row.
- criterion 11 -> every act appends an APPROVAL_DECISION row via the
  EXISTING audit port; the closed event set is untouched.
- §14 -> AuthoritativeApplierPort has NO implementation in the repo
  (asserted by subclass scan); the workflow composes None; the honesty
  surface answers {"available": False, "gate": "S14_OPERATOR_GATE"}.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.sourcechange import (
    SOURCE_VERIFICATION_CHECKS,
    ApprovalHashMismatch,
    AuthoritativeApplierPort,
    ChangeProposal,
    HermeticSandbox,
    InMemoryProposalStore,
    InMemorySnapshotStore,
    InvalidTransition,
    PatchOperation,
    PatchOpKind,
    ProposalNotFound,
    ProposalState,
    SourceChangeWorkflow,
    SourcePatch,
    SourceSnapshot,
    UnknownSnapshot,
    VerificationSuite,
)

TENANT = uuid4()
ACTOR = uuid4()
APPROVER = uuid4()

BASE = SourceSnapshot.from_files(
    {"src/app.py": b"print('v1')\n", "README.md": b"# demo\n"}
)
GOOD_PATCH = SourcePatch(
    operations=(
        PatchOperation(
            kind=PatchOpKind.MODIFY_FILE, path="src/app.py", content=b"print('v2')\n"
        ),
    )
)
BREAKING_PATCH = SourcePatch(
    operations=(
        PatchOperation(
            kind=PatchOpKind.MODIFY_FILE, path="src/app.py", content=b"def broken(:\n"
        ),
    )
)
SUITE = VerificationSuite(name="default", checks=SOURCE_VERIFICATION_CHECKS)


def _workflow(
    audit: InMemoryAuditLog | None = None,
) -> tuple[SourceChangeWorkflow, InMemorySnapshotStore]:
    snapshots = InMemorySnapshotStore()
    snapshots.save_snapshot(TENANT, BASE)
    workflow = SourceChangeWorkflow(
        proposals=InMemoryProposalStore(),
        snapshots=snapshots,
        sandbox=HermeticSandbox(),
        suite=SUITE,
        audit=audit,
    )
    return workflow, snapshots


# --- propose ---------------------------------------------------------------------------


def test_propose_requires_stored_base_snapshot() -> None:
    workflow, _ = _workflow()
    with pytest.raises(UnknownSnapshot):
        workflow.propose(TENANT, ACTOR, "0" * 64, GOOD_PATCH, "against ghost base")


def test_propose_creates_draft_with_derived_version() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    assert proposal.state is ProposalState.DRAFT
    assert len(proposal.patch_hash) == 64
    assert workflow.get(TENANT, proposal.proposal_id).patch_hash == proposal.patch_hash


# --- verify (criterion 6 wiring) ---------------------------------------------------------


def test_verify_pass_stores_patched_snapshot_and_marks_verified() -> None:
    workflow, snapshots = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    verified = workflow.verify(TENANT, proposal.proposal_id)
    assert verified.state is ProposalState.VERIFIED
    # the patched snapshot became addressable content
    patched = snapshots.get_snapshot(
        TENANT,
        SourceSnapshot.from_files(
            {"src/app.py": b"print('v2')\n", "README.md": b"# demo\n"}
        ).snapshot_id,
    )
    assert patched.files["src/app.py"] == b"print('v2')\n"


def test_verify_regression_marks_failed_and_stores_no_candidate() -> None:
    workflow, snapshots = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, BREAKING_PATCH, "boom")
    failed = workflow.verify(TENANT, proposal.proposal_id)
    assert failed.state is ProposalState.FAILED_VERIFICATION
    broken_id = SourceSnapshot.from_files(
        {"src/app.py": b"def broken(:\n", "README.md": b"# demo\n"}
    ).snapshot_id
    with pytest.raises(UnknownSnapshot):
        snapshots.get_snapshot(TENANT, broken_id)  # failing candidate never stored


def test_failed_verification_blocks_approval_structurally() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, BREAKING_PATCH, "boom")
    failed = workflow.verify(TENANT, proposal.proposal_id)
    with pytest.raises(InvalidTransition):
        workflow.approve(TENANT, failed.proposal_id, APPROVER, failed.patch_hash)


# --- approve / reject (criterion 7 workflow-level) ----------------------------------------


def test_approve_with_exact_hash_succeeds_and_binds() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    approved = workflow.approve(TENANT, proposal.proposal_id, APPROVER, proposal.patch_hash)
    assert approved.state is ProposalState.APPROVED
    assert approved.approval is not None
    assert approved.approval.approved_patch_hash == proposal.patch_hash


def test_approve_with_forged_hash_refused_named_persists_nothing() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    with pytest.raises(ApprovalHashMismatch) as excinfo:
        workflow.approve(TENANT, proposal.proposal_id, APPROVER, "f" * 64)
    assert proposal.patch_hash in str(excinfo.value)
    assert workflow.get(TENANT, proposal.proposal_id).state is ProposalState.VERIFIED


def test_reject_is_terminal() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    rejected = workflow.reject(TENANT, proposal.proposal_id, APPROVER, "not now")
    assert rejected.state is ProposalState.REJECTED
    with pytest.raises(InvalidTransition):
        workflow.approve(TENANT, proposal.proposal_id, APPROVER, proposal.patch_hash)


# --- apply (criteria 8 evidence + 10 post-apply) -------------------------------------------


def _approved(workflow: SourceChangeWorkflow) -> ChangeProposal:
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    return workflow.approve(TENANT, proposal.proposal_id, APPROVER, proposal.patch_hash)


def test_apply_records_evidence_pair_and_stays_in_store_space() -> None:
    audit = InMemoryAuditLog()
    workflow, snapshots = _workflow(audit)
    approved = _approved(workflow)
    applied = workflow.apply(TENANT, approved.proposal_id)
    assert applied.state is ProposalState.APPLIED
    assert applied.applied_snapshot_id is not None
    assert applied.inverse_patch is not None
    stored = snapshots.get_snapshot(TENANT, applied.applied_snapshot_id)
    assert stored.files["src/app.py"] == b"print('v2')\n"
    # post-apply verification recorded (criterion 10)
    rows = audit.read(TENANT, AuditEventType.APPROVAL_DECISION)
    apply_rows = [r for r in rows if r.details.get("act") == "apply"]
    assert len(apply_rows) == 1
    assert apply_rows[0].details["post_apply_passed"] is True
    assert "post_apply_report" in apply_rows[0].details
    # §14 posture recorded IN the evidence (never claimed active)
    assert apply_rows[0].details["authoritative_apply"] == {
        "available": False,
        "gate": "S14_OPERATOR_GATE",
    }


def test_apply_from_unapproved_state_is_refused() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    with pytest.raises(InvalidTransition):
        workflow.apply(TENANT, proposal.proposal_id)


# --- rollback (criterion 8) -----------------------------------------------------------------


def test_rollback_restores_base_by_content_address() -> None:
    audit = InMemoryAuditLog()
    workflow, snapshots = _workflow(audit)
    approved = _approved(workflow)
    applied = workflow.apply(TENANT, approved.proposal_id)
    rolled = workflow.rollback(TENANT, applied.proposal_id)
    assert rolled.state is ProposalState.ROLLED_BACK
    restored = snapshots.get_snapshot(TENANT, BASE.snapshot_id)
    assert dict(restored.files) == dict(BASE.files)
    rows = [
        r
        for r in audit.read(TENANT, AuditEventType.APPROVAL_DECISION)
        if r.details.get("act") == "rollback"
    ]
    assert rows[0].details["restored_matches_base"] is True
    assert rows[0].details["restored_snapshot_id"] == BASE.snapshot_id


def test_rollback_before_apply_is_refused() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    with pytest.raises(InvalidTransition):
        workflow.rollback(TENANT, proposal.proposal_id)


# --- audit trail (criterion 11) ---------------------------------------------------------------


def test_every_act_appends_an_approval_decision_row() -> None:
    audit = InMemoryAuditLog()
    workflow, _ = _workflow(audit)
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    workflow.verify(TENANT, proposal.proposal_id)
    workflow.approve(TENANT, proposal.proposal_id, APPROVER, proposal.patch_hash)
    workflow.apply(TENANT, proposal.proposal_id)
    workflow.rollback(TENANT, proposal.proposal_id)
    rows = audit.read(TENANT, AuditEventType.APPROVAL_DECISION)
    acts = [row.details["act"] for row in rows]
    assert acts == ["propose", "verify", "approve", "apply", "rollback"]
    # every row cites the version identity (criterion 7 traceability)
    assert all(row.details["patch_hash"] == proposal.patch_hash for row in rows)
    # and the verify row carries the FULL differential evidence
    verify_row = rows[1]
    assert verify_row.details["verdict"] == "pass"
    assert "base_report" in verify_row.details
    assert "patched_report" in verify_row.details


def test_workflow_without_audit_seam_still_functions() -> None:
    workflow, _ = _workflow(audit=None)
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    assert workflow.verify(TENANT, proposal.proposal_id).state is ProposalState.VERIFIED


# --- tenant scope / anti-enumeration ------------------------------------------------------------


def test_foreign_tenant_cannot_reach_a_proposal() -> None:
    workflow, _ = _workflow()
    proposal = workflow.propose(TENANT, ACTOR, BASE.snapshot_id, GOOD_PATCH, "bump")
    with pytest.raises(ProposalNotFound):
        workflow.verify(uuid4(), proposal.proposal_id)
    with pytest.raises(ProposalNotFound):
        workflow.get(uuid4(), proposal.proposal_id)


# --- §14 gate (structural) -----------------------------------------------------------------------


def test_authoritative_applier_has_no_implementation_in_repo() -> None:
    """§14 structural fact: NO class anywhere in the loaded core/apps
    modules implements AuthoritativeApplierPort's method name. The port
    exists only as a Protocol — activation requires writing new code."""
    import sys

    implementors = []
    for name, module in list(sys.modules.items()):
        if not (name.startswith("core") or name.startswith("apps")):
            continue
        for attr in vars(module).values():
            if not isinstance(attr, type) or attr is AuthoritativeApplierPort:
                continue
            if "apply_to_authoritative_source" in dir(attr):
                implementors.append(attr)
    assert implementors == []


def test_authoritative_apply_status_is_honestly_gated() -> None:
    workflow, _ = _workflow()
    assert workflow.authoritative_apply_status() == {
        "available": False,
        "gate": "S14_OPERATOR_GATE",
    }


def test_workflow_has_no_path_to_authoritative_source() -> None:
    """The workflow module imports no IO machinery and its only outward
    seam is the None-defaulted applier port."""
    import inspect
    import sys

    module = sys.modules["core.sourcechange.workflow"]
    names = set(vars(module))
    for forbidden in ("os", "subprocess", "socket", "shutil", "pathlib"):
        assert forbidden not in names
    signature = inspect.signature(SourceChangeWorkflow.__init__)
    assert signature.parameters["authoritative_applier"].default is None
