"""JSON-file persistence for ``RepoBinding`` records (R172 C2).

Durability (D4 finding closed for bindings): same-directory temp file ->
write -> flush -> fsync -> ``os.replace``. The directory is created ``0o700``
and the file ends up ``0o600``. A crash between any two steps leaves the prior
document intact; the caller sees :class:`BindingStoreRefused`.

Location: the constructor refuses a path inside any root passed as
``outside_of`` (the bound working trees) so state never lands in a repository
that ``git.publish`` could ship.

Load is fail-closed *and reported* (see :mod:`core.contracts.binding_store`):
nothing raises into the tool path; bad records are skipped with a reason and
never partially resurrected. INV-3: only ``credential_ref`` is serialised.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from core.contracts.binding_store import (
    BINDING_STORE_VERSION,
    BindingStoreDocument,
    BindingStoreLoadReport,
    SkippedRecord,
    SourceState,
)
from core.contracts.repo_binding import RepoBinding

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_MAX_REASON = 512


class BindingStoreRefused(Exception):
    """Typed store failure (bad location or interrupted write)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _clip(reason: str) -> str:
    return reason if len(reason) <= _MAX_REASON else reason[: _MAX_REASON - 1] + "\u2026"


class JsonBindingStore:
    """Atomic, permission-tightened JSON store for a tenant-mixed binding set."""

    def __init__(self, path: Path, outside_of: tuple[Path, ...] = ()) -> None:
        resolved = Path(path).expanduser().resolve(strict=False)
        for root in outside_of:
            root_r = Path(root).expanduser().resolve(strict=False)
            if _is_within(resolved, root_r):
                raise BindingStoreRefused(
                    f"binding store path {resolved} is inside a protected working tree {root_r}"
                )
        self._path = resolved

    @property
    def path(self) -> Path:
        return self._path

    # --- write -------------------------------------------------------------

    def save(self, bindings: Iterable[RepoBinding]) -> None:
        doc = BindingStoreDocument(version=BINDING_STORE_VERSION, bindings=tuple(bindings))
        payload = json.dumps(doc.model_dump(mode="json"), sort_keys=True, indent=2)
        data = (payload + "\n").encode("utf-8")

        directory = self._path.parent
        try:
            directory.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
            os.chmod(directory, _DIR_MODE)
        except OSError as exc:
            raise BindingStoreRefused(f"cannot prepare binding store directory: {exc}") from exc

        tmp = directory / f".{self._path.name}.{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, _FILE_MODE)
            os.replace(tmp, self._path)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise BindingStoreRefused(f"binding store write interrupted: {exc}") from exc
        # Durability of the rename itself.
        try:
            dfd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            # Directory fsync is best-effort on some filesystems; data is already replaced.
            pass

    # --- read --------------------------------------------------------------

    def load(self) -> BindingStoreLoadReport:
        try:
            st = os.stat(self._path)
        except FileNotFoundError:
            return BindingStoreLoadReport(source_state="missing")
        except OSError as exc:
            return self._unreadable(f"stat failed: {exc}")

        if not stat.S_ISREG(st.st_mode):
            return self._malformed("binding store path is not a regular file")

        try:
            raw = self._path.read_bytes()
        except OSError as exc:
            return self._unreadable(f"read failed: {exc}")

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            return self._malformed(f"malformed document: {exc}")

        if not isinstance(parsed, dict):
            return self._malformed("malformed document: top level is not an object")
        if parsed.get("version") != BINDING_STORE_VERSION:
            return self._malformed(
                f"malformed document: unsupported version {parsed.get('version')!r}"
            )
        records = parsed.get("bindings")
        if not isinstance(records, list):
            return self._malformed("malformed document: 'bindings' is not a list")

        good: list[RepoBinding] = []
        skipped: list[SkippedRecord] = []
        seen: set[object] = set()
        for index, record in enumerate(records):
            try:
                binding = RepoBinding.model_validate(record)
            except ValidationError as exc:
                reason = f"invalid record: {exc.error_count()} error(s)"
                skipped.append(SkippedRecord(index=index, reason=_clip(reason)))
                continue
            except Exception as exc:  # defensive: never raise into the tool path
                skipped.append(SkippedRecord(index=index, reason=_clip(f"invalid record: {exc!r}")))
                continue
            if binding.id in seen:
                skipped.append(SkippedRecord(index=index, reason="duplicate binding id"))
                continue
            seen.add(binding.id)
            good.append(binding)

        state: SourceState = "partial" if skipped else "ok"
        return BindingStoreLoadReport(
            bindings=tuple(good), skipped=tuple(skipped), source_state=state
        )

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _malformed(reason: str) -> BindingStoreLoadReport:
        prefixed = reason if reason.startswith("malformed") else f"malformed: {reason}"
        return BindingStoreLoadReport(
            skipped=(SkippedRecord(index=0, reason=_clip(prefixed)),), source_state="malformed"
        )

    @staticmethod
    def _unreadable(reason: str) -> BindingStoreLoadReport:
        return BindingStoreLoadReport(
            skipped=(SkippedRecord(index=0, reason=_clip(f"unreadable: {reason}")),),
            source_state="unreadable",
        )


__all__ = ["BindingStoreRefused", "JsonBindingStore"]
