"""Root-jailed, bounded, WRITE-capable workspace file engine (ADR-0012 §2).

Mirrors the admission rules of :class:`core.tools.source_reader.SourceReader`
(the read side is REUSED — a ``WorkspaceFs`` exposes its ``reader``) and adds
the mutation side: write, move, delete, and an atomic multi-file change set.

- ROOT JAIL — every path resolves inside ``root``; absolute paths, ``..``
  segments and symlinks pointing outside are refused as typed data.
- DENYLIST — ``.git/**`` and credential-shaped files are never written,
  moved or deleted here (Git acts go through ``GitPort``).
- BOUNDED — writes are byte-capped; change sets are operation-capped.
- ATOMIC — ``apply_change_set`` restores every touched path on failure.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.engineering import ChangeSet, ChangeSetResult, FileChange
from core.engineering.errors import WorkspaceRefused
from core.tools.source_reader import (
    DEFAULT_DENIED_PATTERNS,
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MAX_FILE_BYTES,
    SourceReader,
)
from core.workspace.errors import InvalidWorkspacePath
from core.workspace.files import validate_path

#: Write cap per file (bytes of UTF-8) — larger content is refused, not cut.
DEFAULT_MAX_WRITE_BYTES = 262_144


@dataclass(frozen=True)
class WorkspaceFs:
    """One jailed, mutable directory tree (composition data)."""

    root: Path
    max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_entries: int = DEFAULT_MAX_ENTRIES
    denied_patterns: tuple[str, ...] = field(default=DEFAULT_DENIED_PATTERNS)

    def __post_init__(self) -> None:
        resolved = self.root.resolve()
        if not resolved.is_dir():
            msg = f"workspace root is not a directory: {resolved}"
            raise ValueError(msg)
        object.__setattr__(self, "root", resolved)

    @property
    def reader(self) -> SourceReader:
        return SourceReader(
            root=self.root,
            max_file_bytes=self.max_file_bytes,
            max_entries=self.max_entries,
            denied_patterns=self.denied_patterns,
        )

    # --- admission ------------------------------------------------------------------

    def admit(self, rel_path: str) -> Path:
        """Resolve ``rel_path`` inside the jail or refuse with typed data.

        The target may not exist yet (writes create); the deepest EXISTING
        ancestor is resolved so a symlinked directory cannot escape.
        """
        try:
            validate_path(rel_path)
        except InvalidWorkspacePath as exc:
            raise WorkspaceRefused(f"invalid path: {exc}") from exc
        candidate = self.root / rel_path
        probe = candidate
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        resolved_probe = probe.resolve()
        if resolved_probe != self.root and self.root not in resolved_probe.parents:
            raise WorkspaceRefused("path escapes the workspace root")
        resolved = (
            resolved_probe / candidate.relative_to(probe) if probe != candidate else resolved_probe
        )
        rel_posix = resolved.relative_to(self.root).as_posix()
        if self.reader._denied(rel_posix):  # noqa: SLF001 - same policy, one place
            raise WorkspaceRefused(f"path is denied by policy: {rel_posix}")
        return resolved

    def _rel(self, target: Path) -> str:
        return target.relative_to(self.root).as_posix()

    # --- single operations ---------------------------------------------------------

    def write_file(self, rel_path: str, content: str) -> dict[str, object]:
        target = self.admit(rel_path)
        blob = content.encode("utf-8")
        if len(blob) > self.max_write_bytes:
            raise WorkspaceRefused(
                f"content exceeds write cap ({len(blob)} > {self.max_write_bytes} bytes)"
            )
        if target.is_dir():
            raise WorkspaceRefused(f"path is a directory: {rel_path}")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        return {"path": self._rel(target), "bytes": len(blob), "created": not existed}

    def move_file(self, rel_path: str, to_rel_path: str) -> dict[str, object]:
        source = self.admit(rel_path)
        dest = self.admit(to_rel_path)
        if not source.is_file():
            raise WorkspaceRefused(f"not a file: {rel_path}")
        if dest.exists():
            raise WorkspaceRefused(f"destination exists: {to_rel_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
        return {"from": self._rel(source), "to": self._rel(dest)}

    def delete_file(self, rel_path: str) -> dict[str, object]:
        target = self.admit(rel_path)
        if not target.is_file():
            raise WorkspaceRefused(f"not a file: {rel_path}")
        target.unlink()
        return {"path": self._rel(target), "deleted": True}

    # --- atomic change set ---------------------------------------------------------

    def apply_change_set(self, change_set: ChangeSet) -> ChangeSetResult:
        """Apply every change or none: prior bytes are restored on failure."""
        plan: list[tuple[FileChange, Path, Path | None]] = []
        for change in change_set.changes:
            target = self.admit(change.path)
            dest: Path | None = None
            if change.kind == "write":
                if change.content is None:
                    raise WorkspaceRefused(f"write needs content: {change.path}")
                if len(change.content.encode("utf-8")) > self.max_write_bytes:
                    raise WorkspaceRefused(f"content exceeds write cap: {change.path}")
            elif change.kind == "move":
                if change.to_path is None:
                    raise WorkspaceRefused(f"move needs to_path: {change.path}")
                dest = self.admit(change.to_path)
            plan.append((change, target, dest))

        prior: dict[Path, bytes | None] = {}
        for _change, target, dest in plan:
            for path in (target, dest):
                if path is not None and path not in prior:
                    prior[path] = path.read_bytes() if path.is_file() else None

        touched: list[str] = []
        try:
            for change, target, dest in plan:
                if change.kind == "write":
                    self.write_file(change.path, change.content or "")
                    touched.append(self._rel(target))
                elif change.kind == "move":
                    assert dest is not None
                    self.move_file(change.path, change.to_path or "")
                    touched.append(self._rel(target))
                    touched.append(self._rel(dest))
                else:
                    self.delete_file(change.path)
                    touched.append(self._rel(target))
        except (WorkspaceRefused, OSError) as exc:
            self._restore(prior)
            return ChangeSetResult(
                applied=False,
                operations=len(plan),
                paths=sorted(set(touched)),
                rolled_back=True,
                error=str(exc),
            )
        return ChangeSetResult(applied=True, operations=len(plan), paths=sorted(set(touched)))

    def _restore(self, prior: dict[Path, bytes | None]) -> None:
        for path, blob in prior.items():
            if blob is None:
                if path.is_file():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)


__all__ = ["DEFAULT_MAX_WRITE_BYTES", "WorkspaceFs"]
