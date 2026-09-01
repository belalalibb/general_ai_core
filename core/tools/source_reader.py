"""Bounded, root-jailed, read-only source inspection primitive.

The smallest safe shared capability that lets an agent inspect repository
source and tests (mandate §9): pure stdlib, no framework imports, usable
by ANY composition root as a tool handler's engine — the admin agent is
one consumer; future consumers bind the same reader through their own
tool runtimes.

Security posture (deny-by-default, capability != authority):

- READ ONLY — this module contains no write, delete, or execute path.
- ROOT JAIL — every path resolves inside the constructor's ``root``;
  absolute paths, ``..`` escapes, and symlinks pointing outside the root
  are refused as typed :class:`SourceReadRefused` DATA (never raised
  through a tool handler as a crash).
- DENYLIST — likely credential FILES are refused by relative-path
  pattern before any byte is read (``.git/**`` included: git config can
  embed tokens). Content-level secret scrubbing remains the CALLER's
  duty (the admin agent already scrubs every tool result).
- BOUNDED — reads are byte-capped (truncation is loud data), listings
  and searches are entry-capped, search is literal substring (no regex —
  no ReDoS surface).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

#: Relative-posix-path patterns that must never be readable or listable.
DEFAULT_DENIED_PATTERNS: tuple[str, ...] = (
    ".git",
    ".git/*",
    "*/.git",
    "*/.git/*",
    ".env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*credentials*",
    "*.git-credentials*",
)

#: Read cap per file — truncation is reported, never silent.
DEFAULT_MAX_FILE_BYTES = 65_536

#: Entry cap for listings and search results.
DEFAULT_MAX_ENTRIES = 500


class SourceReadRefused(Exception):
    """A refused read/list/search — ``reason`` is safe, loggable data."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SourceReader:
    """Read-only, jailed view over ONE directory tree (composition data)."""

    root: Path
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_entries: int = DEFAULT_MAX_ENTRIES
    denied_patterns: tuple[str, ...] = field(default=DEFAULT_DENIED_PATTERNS)

    def __post_init__(self) -> None:
        resolved = self.root.resolve()
        if not resolved.is_dir():
            msg = f"source root is not a directory: {resolved}"
            raise ValueError(msg)
        object.__setattr__(self, "root", resolved)

    # --- admission -----------------------------------------------------------

    def _admit(self, rel_path: str) -> Path:
        """Resolve ``rel_path`` inside the jail or refuse with typed data."""
        if (
            not rel_path
            or rel_path.startswith(("/", "\\"))
            or ".." in Path(rel_path).parts
        ):
            raise SourceReadRefused("path must be relative and inside the source root")
        candidate = (self.root / rel_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise SourceReadRefused("path escapes the source root")
        rel_posix = candidate.relative_to(self.root).as_posix()
        if self._denied(rel_posix):
            raise SourceReadRefused(f"path is denied by policy: {rel_posix}")
        return candidate

    def _denied(self, rel_posix: str) -> bool:
        return any(fnmatch(rel_posix, pattern) for pattern in self.denied_patterns)

    # --- operations ----------------------------------------------------------

    def read_file(self, rel_path: str) -> dict[str, object]:
        """Read one file, byte-capped; refusals are typed, truncation loud."""
        target = self._admit(rel_path)
        if not target.is_file():
            raise SourceReadRefused(f"not a readable file: {rel_path}")
        size = target.stat().st_size
        with target.open("rb") as handle:
            blob = handle.read(self.max_file_bytes)
        return {
            "path": target.relative_to(self.root).as_posix(),
            "size_bytes": size,
            "truncated": size > self.max_file_bytes,
            "content": blob.decode("utf-8", errors="replace"),
        }

    def list_files(self, rel_path: str = "", glob: str = "**/*") -> dict[str, object]:
        """List files under ``rel_path`` matching ``glob`` — entry-capped."""
        base = self._admit(rel_path) if rel_path else self.root
        if not base.is_dir():
            raise SourceReadRefused(f"not a directory: {rel_path}")
        entries: list[str] = []
        truncated = False
        for candidate in sorted(base.glob(glob)):
            if not candidate.is_file():
                continue
            rel_posix = candidate.relative_to(self.root).as_posix()
            if self._denied(rel_posix):
                continue
            if len(entries) >= self.max_entries:
                truncated = True
                break
            entries.append(rel_posix)
        return {"files": entries, "truncated": truncated}

    def search(
        self, text: str, rel_path: str = "", glob: str = "**/*.py"
    ) -> dict[str, object]:
        """Literal substring search (no regex) — match- and byte-capped."""
        if not text:
            raise SourceReadRefused("search text must be non-empty")
        base = self._admit(rel_path) if rel_path else self.root
        if not base.is_dir():
            raise SourceReadRefused(f"not a directory: {rel_path}")
        matches: list[dict[str, object]] = []
        truncated = False
        for candidate in sorted(base.glob(glob)):
            if truncated:
                break
            if not candidate.is_file():
                continue
            rel_posix = candidate.relative_to(self.root).as_posix()
            if self._denied(rel_posix):
                continue
            try:
                lines = (
                    candidate.read_bytes()[: self.max_file_bytes]
                    .decode("utf-8", errors="replace")
                    .splitlines()
                )
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                if text in line:
                    if len(matches) >= self.max_entries:
                        truncated = True
                        break
                    matches.append(
                        {"path": rel_posix, "line": number, "text": line[:512]}
                    )
        return {"matches": matches, "truncated": truncated}
