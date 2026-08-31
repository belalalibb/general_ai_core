"""Source-change primitives (ADR-0009, MASTER VISION v2 phase V8).

Framework-free building blocks for the R3 Source-Change Workflow:
immutable content-addressed snapshots + deterministic invertible patch
algebra. Higher layers (proposal lifecycle, sandbox, differential
verification, workflow) build on these values.

§14 POSTURE (ADR-0009): this package contains NO authoritative-write,
push, or secret capability of any kind — it is pure value manipulation.
Real R3 activation remains operator-gated.
"""

from core.sourcechange.errors import (
    ApprovalHashMismatch,
    InvalidTransition,
    MalformedPatch,
    PatchNotApplicable,
    ProposalNotFound,
    SnapshotIntegrityError,
    SourceChangeError,
    UnknownSnapshot,
)
from core.sourcechange.patch import (
    PatchOperation,
    PatchOpKind,
    SourcePatch,
    apply_patch,
    invert_patch,
    patch_hash,
)
from core.sourcechange.proposal import (
    PROPOSAL_TRANSITIONS,
    ApprovalRecord,
    ChangeProposal,
    ProposalState,
)
from core.sourcechange.sandbox import (
    SOURCE_VERIFICATION_CHECKS,
    CheckResult,
    DifferentialReport,
    DifferentialVerdict,
    DifferentialVerifier,
    HermeticSandbox,
    NonDeterministicVerification,
    SandboxPort,
    SourceCheck,
    VerificationReport,
    VerificationSuite,
)
from core.sourcechange.snapshot import SourceSnapshot, file_content_hash
from core.sourcechange.store import (
    InMemoryProposalStore,
    InMemorySnapshotStore,
    ProposalStorePort,
    SnapshotStorePort,
)
from core.sourcechange.workflow import (
    AuthoritativeApplierPort,
    SourceChangeWorkflow,
)

__all__ = [
    "PROPOSAL_TRANSITIONS",
    "SOURCE_VERIFICATION_CHECKS",
    "ApprovalHashMismatch",
    "ApprovalRecord",
    "AuthoritativeApplierPort",
    "ChangeProposal",
    "CheckResult",
    "DifferentialReport",
    "DifferentialVerdict",
    "DifferentialVerifier",
    "HermeticSandbox",
    "InMemoryProposalStore",
    "InMemorySnapshotStore",
    "InvalidTransition",
    "MalformedPatch",
    "NonDeterministicVerification",
    "PatchNotApplicable",
    "PatchOpKind",
    "PatchOperation",
    "ProposalNotFound",
    "ProposalState",
    "ProposalStorePort",
    "SandboxPort",
    "SnapshotIntegrityError",
    "SnapshotStorePort",
    "SourceChangeError",
    "SourceChangeWorkflow",
    "SourceCheck",
    "SourcePatch",
    "SourceSnapshot",
    "UnknownSnapshot",
    "VerificationReport",
    "VerificationSuite",
    "apply_patch",
    "file_content_hash",
    "invert_patch",
    "patch_hash",
]
