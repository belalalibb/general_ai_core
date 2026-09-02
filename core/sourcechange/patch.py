"""Deterministic patch algebra over source snapshots (ADR-0009 / V8).

A :class:`SourcePatch` is an ordered tuple of closed-set operations with
FULL-CONTENT semantics (deterministic by construction — no fuzzy hunks,
recorded trade-off: deterministic > compact). The two pure functions:

- :func:`apply_patch` — total for an applicable patch; returns a complete
  NEW snapshot or raises a named refusal. No partial state can exist.
- :func:`invert_patch` — total for an applicable patch; returns the exact
  inverse patch such that ``apply(apply(s, p), invert(p, s)) == s``.
  This IS the rollback model (criterion 8): rollback replays the recorded
  inverse through the SAME apply machinery — one code path, not two.

``patch_hash`` (canonical serialization + base snapshot id) is the
proposal VERSION identity that approvals bind to (criterion 7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from core.sourcechange.errors import MalformedPatch, PatchNotApplicable
from core.sourcechange.snapshot import SourceSnapshot, file_content_hash
from core.workspace.files import validate_path

__all__ = [
    "PatchOpKind",
    "PatchOperation",
    "SourcePatch",
    "apply_patch",
    "invert_patch",
    "patch_hash",
]


class PatchOpKind(StrEnum):
    """Closed operation set — nothing else can be expressed."""

    ADD_FILE = "add_file"
    MODIFY_FILE = "modify_file"
    DELETE_FILE = "delete_file"


@dataclass(frozen=True)
class PatchOperation:
    """One full-content operation on one path.

    Shape rules (enforced at construction, P7 — patches are input):
    ADD/MODIFY carry content; DELETE carries none. A violated rule is a
    named :class:`MalformedPatch` at construction, never a latent surprise
    at application time.
    """

    kind: PatchOpKind
    path: str
    content: bytes | None = None

    def __post_init__(self) -> None:
        validate_path(self.path)
        if self.kind is PatchOpKind.DELETE_FILE:
            if self.content is not None:
                raise MalformedPatch(f"delete_file at {self.path!r} must not carry content")
        elif self.content is None:
            raise MalformedPatch(f"{self.kind.value} at {self.path!r} requires content")


@dataclass(frozen=True)
class SourcePatch:
    """An ordered, duplicate-free tuple of operations.

    Duplicate paths are refused at construction: two operations on one
    path would make the result order-dependent, and ADR-0009 requires
    per-path deterministic semantics.
    """

    operations: tuple[PatchOperation, ...]

    def __post_init__(self) -> None:
        if not self.operations:
            raise MalformedPatch("a patch must contain at least one operation")
        seen: set[str] = set()
        for op in self.operations:
            if op.path in seen:
                raise MalformedPatch(f"duplicate operation path {op.path!r}")
            seen.add(op.path)


def _canonical(patch: SourcePatch) -> bytes:
    """Canonical byte serialization — the hash input (sorted by path so the
    hash is order-independent, matching the order-independent semantics)."""
    digest_parts: list[bytes] = []
    for op in sorted(patch.operations, key=lambda item: item.path):
        content_hash = file_content_hash(op.content) if op.content is not None else ""
        digest_parts.append(f"{op.kind.value}\x00{op.path}\x00{content_hash}\x01".encode())
    return b"".join(digest_parts)


def patch_hash(patch: SourcePatch, base_snapshot_id: str) -> str:
    """The proposal VERSION identity: hash(canonical patch + base id).

    Approval binds to this value (criterion 7): change one byte of any
    operation OR retarget the base snapshot and the identity changes —
    an approval citing hash X can never authorize content Y.
    """
    digest = hashlib.sha256()
    digest.update(_canonical(patch))
    digest.update(b"\x02")
    digest.update(base_snapshot_id.encode("ascii"))
    return digest.hexdigest()


def apply_patch(snapshot: SourceSnapshot, patch: SourcePatch) -> SourceSnapshot:
    """Pure application: a complete new snapshot, or a named refusal.

    Applicability is checked for EVERY operation BEFORE any file map is
    built, so an inapplicable patch produces nothing (P6 — no observable
    partial application).
    """
    for op in patch.operations:
        exists = op.path in snapshot.files
        if op.kind is PatchOpKind.ADD_FILE and exists:
            raise PatchNotApplicable(op.path, "add_file target already exists")
        if op.kind is PatchOpKind.MODIFY_FILE and not exists:
            raise PatchNotApplicable(op.path, "modify_file target does not exist")
        if op.kind is PatchOpKind.DELETE_FILE and not exists:
            raise PatchNotApplicable(op.path, "delete_file target does not exist")

    files: dict[str, bytes] = dict(snapshot.files)
    for op in patch.operations:
        if op.kind is PatchOpKind.DELETE_FILE:
            del files[op.path]
        else:
            assert op.content is not None  # construction rule (MalformedPatch)
            files[op.path] = op.content
    return SourceSnapshot.from_files(files)


def invert_patch(patch: SourcePatch, base: SourceSnapshot) -> SourcePatch:
    """The exact inverse patch, computed against the base snapshot.

    Total for an applicable patch (the same applicability rules are
    checked, named). Round-trip law, tested:
    ``apply(apply(base, patch), invert(patch, base)).snapshot_id ==
    base.snapshot_id``.
    """
    inverse_ops: list[PatchOperation] = []
    for op in patch.operations:
        exists = op.path in base.files
        if op.kind is PatchOpKind.ADD_FILE:
            if exists:
                raise PatchNotApplicable(op.path, "add_file target already exists")
            inverse_ops.append(PatchOperation(kind=PatchOpKind.DELETE_FILE, path=op.path))
        elif op.kind is PatchOpKind.MODIFY_FILE:
            if not exists:
                raise PatchNotApplicable(op.path, "modify_file target does not exist")
            inverse_ops.append(
                PatchOperation(
                    kind=PatchOpKind.MODIFY_FILE,
                    path=op.path,
                    content=base.files[op.path],
                )
            )
        else:  # DELETE_FILE
            if not exists:
                raise PatchNotApplicable(op.path, "delete_file target does not exist")
            inverse_ops.append(
                PatchOperation(
                    kind=PatchOpKind.ADD_FILE,
                    path=op.path,
                    content=base.files[op.path],
                )
            )
    return SourcePatch(operations=tuple(inverse_ops))
