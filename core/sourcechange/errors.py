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
