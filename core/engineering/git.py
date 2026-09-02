"""Git PORT + reference validation (ADR-0012 §2).

Core owns the seam and the rules; the ``git`` binary is driven by the
``infrastructure/engineering`` adapter. Methods return DATA — conflicts,
rejections and unknown refs are results; ``GitRefused`` is raised only for
acts refused BEFORE anything runs (bad ref names, unconfigured remote).
"""

from __future__ import annotations

import re
from typing import Protocol

from core.contracts.engineering import (
    GitCommitInfo,
    GitCommitResult,
    GitMergeResult,
    GitPushResult,
    GitStatus,
)
from core.engineering.errors import GitRefused

_REF_FORBIDDEN = re.compile(r"[\s~^:?*\[\\\x00-\x1f\x7f]")


def validate_ref(ref: str) -> str:
    """Admit a branch/ref name or refuse with typed data."""
    if not ref or len(ref) > 255:
        raise GitRefused("ref must be non-empty and short")
    if ref.startswith("-") or ".." in ref or ref.endswith("/") or ref.endswith(".lock"):
        raise GitRefused(f"ref rejected: {ref}")
    if _REF_FORBIDDEN.search(ref):
        raise GitRefused(f"ref contains forbidden characters: {ref}")
    return ref


class GitPort(Protocol):
    """The Git operations the shared runtime may drive over ONE workspace."""

    @property
    def remote(self) -> str:
        """The only remote name push may address (composition data)."""
        ...

    async def status(self) -> GitStatus: ...

    async def diff(self, *, ref: str | None = None, staged: bool = False) -> str: ...

    async def log(self, *, limit: int = 20) -> list[GitCommitInfo]: ...

    async def branches(self) -> list[str]: ...

    async def compare(self, base: str, head: str) -> str: ...

    async def checkout(self, branch: str, *, create: bool = False) -> str: ...

    async def commit(self, message: str, *, add_all: bool = True) -> GitCommitResult: ...

    async def push(self, branch: str, *, remote: str | None = None) -> GitPushResult: ...

    async def merge(self, source: str, *, into: str) -> GitMergeResult: ...


__all__ = ["GitPort", "validate_ref"]
