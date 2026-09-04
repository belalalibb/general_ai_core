"""Bounded source writer — the write counterpart of :mod:`core.tools.source_reader`.

R169 A2. Design posture:

* The writer is a *separate primitive*; it is not registered anywhere by this
  module. Composition roots decide who may hold it (INV-7).
* The path jail mirrors ``SourceReader._admit`` exactly and shares the same
  denylist, so what cannot be read cannot be written either.
* Every refusal is returned as typed **data** (``ok: False`` + machine-readable
  ``code``), so the ToolExecutor records the attempt as a *succeeded* call whose
  result is a refusal — the write itself never happens (INV-2).
* ``overwrite`` and ``delete`` require an ``expected_sha256`` precondition that
  must match the current on-disk bytes; this makes every destructive write a
  compare-and-swap on content the caller has demonstrably read.
* Byte and operation caps bound blast radius per writer instance.
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from core.contracts.base import JsonObject
from core.contracts.source_write import (
    SourceWriteOp,
    SourceWriteRefusal,
    SourceWriteRefusalCode,
    SourceWriteRequest,
    SourceWriteResult,
)
from core.tools.source_reader import DEFAULT_DENIED_PATTERNS, is_denied

DEFAULT_MAX_WRITE_BYTES = 65_536
DEFAULT_MAX_OPS = 50


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _atomic_write(target: Path, blob: bytes) -> None:
    """R172 C4: same-directory temp -> write -> flush -> fsync -> ``os.replace``.

    An interruption at any step leaves ``target`` byte-identical to before and
    removes the temp file; the ``OSError`` propagates to ``write()`` where it
    becomes an ``io_error`` refusal. Mode: an existing file keeps its mode; a
    new file gets the umask default (``0o666 & ~umask``), same as ``write_bytes``.
    """
    directory = target.parent
    tmp = directory / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:  # best-effort durability of the rename itself
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


class _Refuse(Exception):
    """Internal control flow only; converted to ``SourceWriteRefusal`` data."""

    def __init__(self, code: SourceWriteRefusalCode, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


@dataclass
class SourceWriter:
    """Jailed, capped, precondition-checked file writer under ``root``."""

    root: Path
    max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES
    max_ops: int = DEFAULT_MAX_OPS
    denied_patterns: tuple[str, ...] = field(default=DEFAULT_DENIED_PATTERNS)
    ops_used: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        resolved = self.root.resolve()
        if not resolved.is_dir():
            raise ValueError(f"source root is not a directory: {resolved}")
        self.root = resolved

    # -- admission (mirrors SourceReader._admit) ------------------------------

    def _admit(self, rel_path: str) -> Path:
        if not rel_path or rel_path.startswith(("/", "\\")) or ".." in Path(rel_path).parts:
            raise _Refuse(
                SourceWriteRefusalCode.PATH_NOT_RELATIVE,
                "path must be relative to the source root and contain no '..'",
            )
        candidate = (self.root / rel_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise _Refuse(
                SourceWriteRefusalCode.PATH_OUTSIDE_ROOT,
                "path resolves outside the source root",
            )
        rel_posix = candidate.relative_to(self.root).as_posix()
        if self._denied(rel_posix):
            raise _Refuse(
                SourceWriteRefusalCode.PATH_DENIED,
                "path matches the denylist",
            )
        return candidate

    def _denied(self, rel_posix: str) -> bool:
        return is_denied(rel_posix, self.denied_patterns)

    # -- helpers ----------------------------------------------------------------

    def _payload(self, content: str | None) -> bytes:
        if content is None:
            raise _Refuse(
                SourceWriteRefusalCode.CONTENT_REQUIRED,
                "content is required for create/overwrite",
            )
        blob = content.encode("utf-8")
        if len(blob) > self.max_write_bytes:
            raise _Refuse(
                SourceWriteRefusalCode.WRITE_TOO_LARGE,
                f"payload is {len(blob)} bytes; cap is {self.max_write_bytes}",
            )
        return blob

    def _existing_file_digest(self, target: Path, expected_sha256: str | None) -> str:
        if not target.exists():
            raise _Refuse(SourceWriteRefusalCode.FILE_MISSING, "target does not exist")
        if not target.is_file():
            raise _Refuse(SourceWriteRefusalCode.NOT_A_FILE, "target is not a regular file")
        if expected_sha256 is None:
            raise _Refuse(
                SourceWriteRefusalCode.PRECONDITION_REQUIRED,
                "expected_sha256 is required for overwrite/delete",
            )
        current = _sha256(target.read_bytes())
        if current != expected_sha256:
            raise _Refuse(
                SourceWriteRefusalCode.PRECONDITION_MISMATCH,
                "expected_sha256 does not match current content",
            )
        return current

    # -- public -----------------------------------------------------------------

    def write(
        self,
        *,
        op: SourceWriteOp | str,
        path: str,
        content: str | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        """Perform one write; refusals are returned as data, never raised."""

        operation = SourceWriteOp(op)  # unknown op is a caller defect -> ValueError
        try:
            return self._perform(operation, path, content, expected_sha256)
        except _Refuse as refusal:
            return SourceWriteRefusal(
                code=refusal.code, reason=refusal.reason, path=path
            ).model_dump(mode="json")
        except OSError as error:
            return SourceWriteRefusal(
                code=SourceWriteRefusalCode.IO_ERROR,
                reason=f"filesystem error: {type(error).__name__}",
                path=path,
            ).model_dump(mode="json")

    def _perform(
        self,
        operation: SourceWriteOp,
        path: str,
        content: str | None,
        expected_sha256: str | None,
    ) -> dict[str, object]:
        if self.ops_used >= self.max_ops:
            raise _Refuse(
                SourceWriteRefusalCode.OP_CAP_EXCEEDED,
                f"operation cap of {self.max_ops} reached for this writer",
            )
        target = self._admit(path)
        rel_posix = target.relative_to(self.root).as_posix()

        previous: str | None
        new: str | None
        if operation is SourceWriteOp.CREATE:
            blob = self._payload(content)
            if target.exists():
                raise _Refuse(SourceWriteRefusalCode.FILE_EXISTS, "target already exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, blob)
            previous, new, written = None, _sha256(blob), len(blob)
        elif operation is SourceWriteOp.OVERWRITE:
            blob = self._payload(content)
            previous = self._existing_file_digest(target, expected_sha256)
            _atomic_write(target, blob)
            new, written = _sha256(blob), len(blob)
        else:
            previous = self._existing_file_digest(target, expected_sha256)
            target.unlink()
            new, written = None, 0

        self.ops_used += 1
        return SourceWriteResult(
            op=operation,
            path=rel_posix,
            bytes_written=written,
            sha256=new,
            previous_sha256=previous,
            ops_remaining=self.max_ops - self.ops_used,
        ).model_dump(mode="json")


def source_write_handler(
    writer: SourceWriter,
) -> Callable[[JsonObject], Awaitable[JsonObject]]:
    """Bind a writer as a ToolExecutor handler; invalid arguments become data."""

    async def handle(arguments: JsonObject) -> JsonObject:
        try:
            request = SourceWriteRequest.model_validate(arguments)
        except ValidationError as error:
            return {
                "ok": False,
                "code": "validation_error",
                "reason": "; ".join(
                    f"{'.'.join(str(loc) for loc in item['loc'])}: {item['msg']}"
                    for item in error.errors()
                ),
                "path": str(arguments.get("path", "")),
            }
        return writer.write(
            op=request.op,
            path=request.path,
            content=request.content,
            expected_sha256=request.expected_sha256,
        )

    return handle
