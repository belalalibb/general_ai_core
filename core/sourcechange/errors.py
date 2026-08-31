"""Source-change errors (closed, minimal set — ADR-0009 / V8).

Same explainable-refusal posture as core/workspace and core/tools
(11 §14): every refusal names the violated rule. Path validation
deliberately REUSES :class:`core.workspace.errors.InvalidWorkspacePath`
through the shared validator (P1 REUSE — one path contract, not two).
"""

from __future__ import annotations


class SourceChangeError(Exception):
    """Base class for source-change failures."""


class PatchNotApplicable(SourceChangeError):
    """The patch cannot apply to the given snapshot — named per operation.

    Raised BEFORE any derived snapshot exists: an inapplicable patch
    produces nothing (P6 — no partially-applied state can ever be
    observed, because application is a pure function that either returns
    a complete new snapshot or raises).
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"patch not applicable at {path!r}: {reason}")


class MalformedPatch(SourceChangeError):
    """The patch violates its own shape rules (P7 — patches are input).

    Duplicate paths within one patch are refused at construction: two
    operations on one path would make application order-dependent, and
    ADR-0009 requires deterministic, order-independent semantics per path.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"malformed patch: {reason}")


class InvalidTransition(SourceChangeError):
    """A proposal lifecycle act violates the closed transition map.

    ADR-0009 criterion 6 rides here: FAILED_VERIFICATION allows NO outgoing
    transitions, so a failed proposal can never be approved — refused by
    the state machine's shape, not by a policy check someone could skip.
    """

    def __init__(self, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"invalid proposal transition: {current} -> {requested}"
        )


class ApprovalHashMismatch(SourceChangeError):
    """The approval cites a different version than the proposal carries.

    Criterion 7: approval binds to the exact ``patch_hash``. An approval
    row citing hash X can never attach to content Y — the mismatch is a
    construction-time refusal, and both hashes are named in the message
    so the refusal is auditable.
    """

    def __init__(self, expected: str, cited: str) -> None:
        self.expected = expected
        self.cited = cited
        super().__init__(
            "approval hash mismatch: proposal carries "
            f"{expected} but the approval cites {cited}"
        )


class ProposalNotFound(SourceChangeError):
    """Absent, foreign-tenant, and malformed proposal ids answer identically
    (anti-enumeration, 20 §6 — same posture as ScenarioNotFound)."""

    def __init__(self) -> None:
        super().__init__("proposal not found")


class UnknownSnapshot(SourceChangeError):
    """The referenced snapshot id is not in the store — named, id cited."""

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"unknown snapshot {snapshot_id!r}")


class SnapshotIntegrityError(SourceChangeError):
    """A snapshot failed content-address verification at the store boundary.

    A store must never hold bytes whose id lies about them (criterion 1) —
    tampered or mis-addressed snapshots are refused on save AND on read.
    """

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(
            f"snapshot {snapshot_id!r} failed integrity verification"
        )
