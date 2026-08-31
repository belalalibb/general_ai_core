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
    MalformedPatch,
    PatchNotApplicable,
    SourceChangeError,
)
from core.sourcechange.patch import (
    PatchOperation,
    PatchOpKind,
    SourcePatch,
    apply_patch,
    invert_patch,
    patch_hash,
)
from core.sourcechange.snapshot import SourceSnapshot, file_content_hash

__all__ = [
    "MalformedPatch",
    "PatchNotApplicable",
    "PatchOpKind",
    "PatchOperation",
    "SourceChangeError",
    "SourcePatch",
    "SourceSnapshot",
    "apply_patch",
    "file_content_hash",
    "invert_patch",
    "patch_hash",
]
