"""Immutable content-addressed source snapshots (ADR-0009 / V8).

A :class:`SourceSnapshot` is a VALUE: a frozen map of ``path -> bytes``
whose identity is derived from its content. Snapshots are never mutated —
patches derive NEW snapshots (see :mod:`core.sourcechange.patch`).

Design decisions carried from ADR-0009, verbatim:

- ``snapshot_id = sha256`` over the sorted ``(path, content_hash)``
  manifest — identity IS content, so two structurally equal snapshots
  always share an id and a tampered payload can never keep one
  (evidence-first: the id is the integrity proof, criterion 1).
- Path discipline REUSES :func:`core.workspace.files.validate_path`
  verbatim (Fix Once / Benefit Everywhere: the path CONTRACT is generic;
  the frozen "NOT the source-edit area" boundary applies to the workspace
  STORAGE surface, not to its pure validator).
- No storage here: a snapshot holds its own bytes. Durable placement is a
  composition concern behind the proposal store (ADR-0009 recorded
  posture) — this module stays framework- and IO-free.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from core.workspace.files import validate_path

__all__ = ["SourceSnapshot", "file_content_hash"]


def file_content_hash(content: bytes) -> str:
    """Content hash for one file — sha256 hex (the manifest ingredient)."""
    return hashlib.sha256(content).hexdigest()


def _manifest_digest(files: Mapping[str, bytes]) -> str:
    """The snapshot identity: sha256 over the sorted (path, hash) manifest."""
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(file_content_hash(files[path]).encode("ascii"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceSnapshot:
    """One immutable, content-addressed set of source files.

    Construct via :meth:`from_files` (validates every path and freezes the
    mapping). ``files`` is a read-only view — the dataclass is frozen AND
    the mapping is a :class:`MappingProxyType`, so neither rebinding nor
    in-place mutation is possible (structural immutability, ADR-0009).
    """

    snapshot_id: str
    files: Mapping[str, bytes] = field(repr=False)

    @classmethod
    def from_files(cls, files: Mapping[str, bytes]) -> SourceSnapshot:
        """Build a snapshot from raw files — every path validated (P7)."""
        validated: dict[str, bytes] = {}
        for path in sorted(files):
            validate_path(path)
            validated[path] = bytes(files[path])
        frozen: Mapping[str, bytes] = MappingProxyType(validated)
        return cls(snapshot_id=_manifest_digest(frozen), files=frozen)

    def manifest(self) -> tuple[tuple[str, str, int], ...]:
        """Derived listing ``(path, content_hash, size_bytes)`` — computed,
        never stored (the manifest IS the evidence, P6)."""
        return tuple(
            (path, file_content_hash(content), len(content))
            for path, content in sorted(self.files.items())
        )

    def verify_integrity(self) -> bool:
        """True iff the stored id still matches the content (criterion 1:
        any tampering with bytes or paths changes the recomputed digest)."""
        return self.snapshot_id == _manifest_digest(self.files)
