"""Workspace-primitive errors (closed, minimal set — Phase V5).

Same explainable-refusal posture as core/tools and core/storage (11 §14):
every refusal names the violated rule. File-not-found deliberately REUSES
:class:`core.storage.errors.ObjectNotFound` from the underlying port —
one anti-enumeration error, not a parallel taxonomy (P1 REUSE).
"""

from __future__ import annotations


class WorkspaceError(Exception):
    """Base class for workspace-primitive failures."""


class InvalidWorkspacePath(WorkspaceError):
    """The file path violates the workspace path contract (P7).

    Paths are untrusted input: empty, absolute, traversal (``..``),
    backslash, or control-character paths are refused BEFORE any storage
    operation — a malformed path must never reach a key namespace.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"invalid workspace path {path!r}: {reason}")
