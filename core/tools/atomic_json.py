"""Shared durable-JSON primitives for dev-agent state files (R172 C2/C3).

Write: same-directory temp (``O_EXCL``, 0o600) -> write -> flush -> fsync ->
chmod -> ``os.replace`` -> best-effort directory fsync. Directory is created and
forced to 0o700. Any ``OSError`` unlinks the temp file and raises
:class:`AtomicJsonRefused`; the previous document is untouched.

Read: :func:`read_document` never raises for I/O or shape problems. It returns
``(state, payload_records, reason)`` where ``state`` is one of
``missing | ok | malformed | unreadable`` and ``payload_records`` is the list
found under ``list_key`` (only when ``state == "ok"``). Callers validate each
record and decide ``partial``.

Location guard: :func:`resolve_outside` refuses a path inside any protected root.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from typing import Literal

DIR_MODE = 0o700
FILE_MODE = 0o600
MAX_REASON = 512

DocState = Literal["missing", "ok", "malformed", "unreadable"]


class AtomicJsonRefused(Exception):
    """Typed failure for a bad location or an interrupted write."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def clip(reason: str) -> str:
    return reason if len(reason) <= MAX_REASON else reason[: MAX_REASON - 1] + "\u2026"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_outside(path: Path, outside_of: tuple[Path, ...], *, what: str) -> Path:
    """Resolve ``path`` and refuse it if it sits inside any ``outside_of`` root."""
    resolved = Path(path).expanduser().resolve(strict=False)
    for root in outside_of:
        root_r = Path(root).expanduser().resolve(strict=False)
        if _is_within(resolved, root_r):
            raise AtomicJsonRefused(
                f"{what} path {resolved} is inside a protected working tree {root_r}"
            )
    return resolved


def write_document(path: Path, document: object, *, what: str) -> None:
    """Atomically replace ``path`` with ``document`` serialised as sorted JSON."""
    payload = json.dumps(document, sort_keys=True, indent=2)
    data = (payload + "\n").encode("utf-8")

    directory = path.parent
    try:
        directory.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        os.chmod(directory, DIR_MODE)
    except OSError as exc:
        raise AtomicJsonRefused(f"cannot prepare {what} directory: {exc}") from exc

    tmp = directory / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise AtomicJsonRefused(f"{what} write interrupted: {exc}") from exc
    # Durability of the rename itself (best-effort; data is already replaced).
    try:
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def read_document(
    path: Path, *, version: int, list_key: str, what: str
) -> tuple[DocState, list[object], str | None]:
    """Fail-closed read of a versioned ``{version, <list_key>: [...]}`` envelope."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return "missing", [], None
    except OSError as exc:
        return "unreadable", [], clip(f"unreadable: stat failed: {exc}")

    if not stat.S_ISREG(st.st_mode):
        return "malformed", [], clip(f"malformed: {what} path is not a regular file")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return "unreadable", [], clip(f"unreadable: read failed: {exc}")

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return "malformed", [], clip(f"malformed document: {exc}")

    if not isinstance(parsed, dict):
        return "malformed", [], "malformed document: top level is not an object"
    if parsed.get("version") != version:
        return (
            "malformed",
            [],
            clip(f"malformed document: unsupported version {parsed.get('version')!r}"),
        )
    records = parsed.get(list_key)
    if not isinstance(records, list):
        return "malformed", [], clip(f"malformed document: {list_key!r} is not a list")
    return "ok", records, None


__all__ = [
    "DIR_MODE",
    "FILE_MODE",
    "AtomicJsonRefused",
    "DocState",
    "clip",
    "read_document",
    "resolve_outside",
    "write_document",
]
