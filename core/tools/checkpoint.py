"""Checkpoint / undo for the dev-agent ``source.write`` apply path (R172 C5).

Design (see ``docs/r172`` and IMPL-022):

* ``CheckpointStore`` keeps content-addressed blobs (``objects/<sha256>``) and a
  JSON index (``checkpoints.json``) in a directory that MUST live outside the
  protected working tree.  Every directory is 0o700 and every file 0o600; all
  writes are atomic (temp + fsync + ``os.replace``) and fail closed.
* ``CheckpointManager.begin`` snapshots the pre-apply content of a path before
  the writer touches it.  A missing file yields ``pre_sha256 = None`` so a
  later restore deletes what the write created.
* After the write, the caller ``seal``s the checkpoint with the post-apply hash
  or ``mark_partial``s it when the writer refused/failed after the snapshot.
* ``restore`` compares the current content hash: ``cur == pre`` is a no-op,
  ``cur == post`` reverts, anything else is a typed ``checkpoint_conflict``
  refusal and the file is left untouched.  A blob that is missing or fails
  hash verification yields ``object_store_corrupt`` (reason names the
  "object store"), again without touching the file.
* ``checkpointed_write_handler`` wraps a ``SourceWriter`` for the dev surface;
  when no manager is configured the surface keeps the plain handler so the
  result shape is byte-for-byte identical to pre-C5 behaviour.

No subprocesses, no shell, no hooks.
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from core.contracts.base import JsonObject, utc_now
from core.contracts.checkpoint import (
    CHECKPOINT_INDEX_VERSION,
    Checkpoint,
    CheckpointIndexDocument,
    CheckpointLoadReport,
    CheckpointRefusal,
    CheckpointRefusalCode,
    CheckpointSkippedRecord,
    CheckpointSourceState,
    RestoreOutcome,
    RestoreResult,
)
from core.contracts.source_write import SourceWriteOp, SourceWriteRequest
from core.tools.atomic_json import (
    DIR_MODE,
    FILE_MODE,
    AtomicJsonRefused,
    clip,
    read_document,
    resolve_outside,
    write_document,
)
from core.tools.source_reader import DEFAULT_DENIED_PATTERNS, is_denied
from core.tools.source_writer import SourceWriter

INDEX_FILE = "checkpoints.json"
OBJECTS_DIR = "objects"
_HEX = frozenset("0123456789abcdef")


class CheckpointRefused(Exception):
    """Raised by ``CheckpointManager`` when a checkpoint cannot be opened/transitioned."""

    def __init__(self, code: CheckpointRefusalCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _current_umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def _atomic_bytes(target: Path, blob: bytes, *, mode: int | None) -> None:
    """Atomically write ``blob`` to ``target`` (temp file, fsync, replace, dir fsync).

    ``mode=None`` preserves the existing file mode (or umask default for a new file).
    """

    directory = target.parent
    tmp = directory / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        if mode is None:
            if target.exists():
                mode = stat.S_IMODE(target.stat().st_mode)
            else:
                mode = 0o666 & ~_current_umask()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


class CheckpointStore:
    """Content-addressed blob store + JSON index, outside the protected tree."""

    def __init__(self, directory: Path, outside_of: tuple[Path, ...] = ()) -> None:
        self._dir = resolve_outside(Path(directory), tuple(outside_of), what="checkpoint store")
        self._objects = self._dir / OBJECTS_DIR
        self._index = self._dir / INDEX_FILE
        try:
            self._dir.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
            os.chmod(self._dir, DIR_MODE)
            self._objects.mkdir(mode=DIR_MODE, exist_ok=True)
            os.chmod(self._objects, DIR_MODE)
        except OSError as exc:
            raise AtomicJsonRefused(f"cannot prepare checkpoint store: {exc}") from exc

    @property
    def directory(self) -> Path:
        return self._dir

    def put_blob(self, blob: bytes) -> str:
        digest = _sha256(blob)
        target = self._objects / digest
        if target.is_file() and _sha256(target.read_bytes()) == digest:
            return digest
        _atomic_bytes(target, blob, mode=FILE_MODE)
        return digest

    def get_blob(self, digest: str) -> bytes | None:
        """Return the blob for ``digest`` or ``None`` when missing/corrupt."""

        if len(digest) != 64 or not set(digest) <= _HEX:
            return None
        try:
            blob = (self._objects / digest).read_bytes()
        except OSError:
            return None
        return blob if _sha256(blob) == digest else None

    def save(self, checkpoints: list[Checkpoint]) -> None:
        document = CheckpointIndexDocument(checkpoints=tuple(checkpoints)).model_dump(mode="json")
        write_document(self._index, document, what="checkpoint index")

    def load(self) -> CheckpointLoadReport:
        state, records, reason = read_document(
            self._index,
            version=CHECKPOINT_INDEX_VERSION,
            list_key="checkpoints",
            what="checkpoint index",
        )
        if state == "missing":
            return CheckpointLoadReport(source_state="missing")
        if state != "ok":
            return CheckpointLoadReport(
                skipped=(CheckpointSkippedRecord(index=0, reason=clip(reason or state)),),
                source_state=state,
            )
        good: list[Checkpoint] = []
        skipped: list[CheckpointSkippedRecord] = []
        seen: set[UUID] = set()
        for index, record in enumerate(records):
            try:
                cp = Checkpoint.model_validate(record)
            except ValidationError as exc:
                skipped.append(
                    CheckpointSkippedRecord(index=index, reason=clip(f"invalid record: {exc!r}"))
                )
                continue
            if cp.id in seen:
                skipped.append(
                    CheckpointSkippedRecord(index=index, reason="duplicate checkpoint id")
                )
                continue
            seen.add(cp.id)
            good.append(cp)
        final: CheckpointSourceState = "partial" if skipped else "ok"
        return CheckpointLoadReport(
            checkpoints=tuple(good), skipped=tuple(skipped), source_state=final
        )


class CheckpointManager:
    """Pre-apply snapshot / post-apply seal / typed restore for one source root."""

    def __init__(
        self,
        *,
        root: Path,
        tenant_id: UUID,
        store: CheckpointStore,
        denied_patterns: tuple[str, ...] = DEFAULT_DENIED_PATTERNS,
    ) -> None:
        resolved = Path(root).resolve()
        if not resolved.is_dir():
            raise ValueError(f"checkpoint root is not a directory: {resolved}")
        self.root = resolved
        self.tenant_id = tenant_id
        self.store = store
        self.denied_patterns = tuple(denied_patterns)
        self.load_report: CheckpointLoadReport | None = None
        self._checkpoints: dict[UUID, Checkpoint] = {}
        self._reload()

    # -- persistence -----------------------------------------------------------

    def _reload(self) -> None:
        report = self.store.load()
        self.load_report = report
        self._checkpoints = {cp.id: cp for cp in report.checkpoints}

    def _persist(self) -> None:
        self.store.save(list(self._checkpoints.values()))

    # -- admission -------------------------------------------------------------

    def _admit(self, rel_path: str, denied_patterns: tuple[str, ...]) -> tuple[Path, str]:
        if not rel_path or rel_path.startswith(("/", "\\")) or ".." in Path(rel_path).parts:
            raise CheckpointRefused(
                CheckpointRefusalCode.PATH_REFUSED,
                "path must be relative to the source root and contain no '..'",
            )
        candidate = (self.root / rel_path).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise CheckpointRefused(
                CheckpointRefusalCode.PATH_REFUSED, "path resolves outside the source root"
            )
        rel_posix = candidate.relative_to(self.root).as_posix()
        if is_denied(rel_posix, denied_patterns):
            raise CheckpointRefused(
                CheckpointRefusalCode.PATH_REFUSED, "path matches the denylist"
            )
        return candidate, rel_posix

    # -- lifecycle -------------------------------------------------------------

    def begin(
        self,
        rel_path: str,
        *,
        op: SourceWriteOp | str,
        denied_patterns: tuple[str, ...] | None = None,
    ) -> Checkpoint:
        """Snapshot ``rel_path`` before a write.  Missing file => ``pre_sha256`` is ``None``."""

        patterns = self.denied_patterns if denied_patterns is None else tuple(denied_patterns)
        target, rel_posix = self._admit(rel_path, patterns)
        if target.exists() and not target.is_file():
            raise CheckpointRefused(
                CheckpointRefusalCode.PATH_REFUSED, "path is not a regular file"
            )
        try:
            pre = self.store.put_blob(target.read_bytes()) if target.is_file() else None
        except (OSError, AtomicJsonRefused) as exc:
            raise CheckpointRefused(
                CheckpointRefusalCode.IO_ERROR, clip(f"snapshot failed: {exc}")
            ) from exc
        cp = Checkpoint(
            tenant_id=self.tenant_id, path=rel_posix, op=SourceWriteOp(op), pre_sha256=pre
        )
        self._checkpoints[cp.id] = cp
        try:
            self._persist()
        except AtomicJsonRefused as exc:
            self._checkpoints.pop(cp.id, None)
            raise CheckpointRefused(
                CheckpointRefusalCode.IO_ERROR, clip(f"index write failed: {exc.reason}")
            ) from exc
        return cp

    def seal(self, checkpoint_id: UUID, *, post_sha256: str | None) -> Checkpoint:
        return self._transition(checkpoint_id, state="sealed", post_sha256=post_sha256)

    def mark_partial(self, checkpoint_id: UUID) -> Checkpoint:
        return self._transition(checkpoint_id, state="partial", post_sha256=None)

    def _transition(
        self, checkpoint_id: UUID, *, state: str, post_sha256: str | None
    ) -> Checkpoint:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise CheckpointRefused(
                CheckpointRefusalCode.CHECKPOINT_UNKNOWN, f"unknown checkpoint {checkpoint_id}"
            )
        updated = cp.model_copy(
            update={
                "state": state,
                "post_sha256": post_sha256,
                "sealed_at": utc_now() if state == "sealed" else cp.sealed_at,
            }
        )
        self._checkpoints[checkpoint_id] = updated
        try:
            self._persist()
        except AtomicJsonRefused as exc:
            self._checkpoints[checkpoint_id] = cp
            raise CheckpointRefused(CheckpointRefusalCode.IO_ERROR, clip(exc.reason)) from exc
        return updated

    # -- queries ---------------------------------------------------------------

    def get(self, checkpoint_id: UUID) -> Checkpoint | None:
        return self._checkpoints.get(checkpoint_id)

    def list(self) -> list[Checkpoint]:
        return sorted(self._checkpoints.values(), key=lambda cp: cp.created_at)

    # -- restore ---------------------------------------------------------------

    def restore(self, checkpoint_id: UUID) -> dict[str, object]:
        """Restore the pre-checkpoint content; returns ``RestoreResult`` or refusal data."""

        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            return self._refuse(
                CheckpointRefusalCode.CHECKPOINT_UNKNOWN,
                f"unknown checkpoint {checkpoint_id}",
                checkpoint_id=checkpoint_id,
            )
        target = self.root / cp.path
        try:
            current = _sha256(target.read_bytes()) if target.is_file() else None
        except OSError as exc:
            return self._refuse(
                CheckpointRefusalCode.IO_ERROR, clip(f"cannot read target: {exc}"), cp=cp
            )
        if current == cp.pre_sha256:
            return self._done(cp, outcome="noop")
        if cp.state == "partial" or current != cp.post_sha256:
            return self._refuse(
                CheckpointRefusalCode.CHECKPOINT_CONFLICT,
                "target has drifted from both the pre- and post-checkpoint content; "
                "file left untouched",
                cp=cp,
            )
        try:
            if cp.pre_sha256 is None:
                target.unlink()
            else:
                blob = self.store.get_blob(cp.pre_sha256)
                if blob is None:
                    return self._refuse(
                        CheckpointRefusalCode.OBJECT_STORE_CORRUPT,
                        "object store blob for the pre-checkpoint content is missing or "
                        "fails hash verification; file left untouched",
                        cp=cp,
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_bytes(target, blob, mode=None)
        except OSError as exc:
            return self._refuse(
                CheckpointRefusalCode.IO_ERROR, clip(f"restore failed: {exc}"), cp=cp
            )
        return self._done(cp, outcome="reverted")

    def _done(self, cp: Checkpoint, *, outcome: RestoreOutcome) -> dict[str, object]:
        updated = cp.model_copy(update={"state": "restored", "restored_at": utc_now()})
        self._checkpoints[cp.id] = updated
        try:
            self._persist()
        except AtomicJsonRefused:
            self._checkpoints[cp.id] = cp
        return RestoreResult(
            checkpoint_id=cp.id, outcome=outcome, path=cp.path, restored_sha256=cp.pre_sha256
        ).model_dump(mode="json")

    @staticmethod
    def _refuse(
        code: CheckpointRefusalCode,
        reason: str,
        *,
        cp: Checkpoint | None = None,
        checkpoint_id: UUID | None = None,
    ) -> dict[str, object]:
        return CheckpointRefusal(
            code=code,
            reason=clip(reason),
            checkpoint_id=cp.id if cp is not None else checkpoint_id,
            path=cp.path if cp is not None else None,
        ).model_dump(mode="json")


def checkpointed_write_handler(
    writer: SourceWriter, manager: CheckpointManager
) -> Callable[[JsonObject], Awaitable[JsonObject]]:
    """``source.write`` handler that snapshots before apply and seals / marks-partial after.

    * Validation errors mirror ``source_write_handler`` exactly.
    * A ``PATH_REFUSED`` from ``begin`` (same denylist as the writer) falls through to the
      writer's own typed refusal: no snapshot, no ``checkpoint_id``.
    * Any other ``begin`` failure (I/O) is returned as typed ``CheckpointRefusal`` data and
      the write is NOT attempted -- never write without a snapshot (fail closed).
    * Success adds ``checkpoint_id``; a writer refusal after the snapshot marks the
      checkpoint ``partial`` and returns the writer's refusal unchanged.
    """

    async def handle(arguments: JsonObject) -> JsonObject:
        try:
            request = SourceWriteRequest.model_validate(arguments)
        except ValidationError as error:
            reason = "; ".join(
                f"{'.'.join(str(loc) for loc in item['loc'])}: {item['msg']}"
                for item in error.errors()
            )
            return {
                "ok": False,
                "code": "validation_error",
                "reason": reason,
                "path": str(arguments.get("path", "")),
            }
        cp: Checkpoint | None
        try:
            cp = manager.begin(
                request.path, op=request.op, denied_patterns=writer.denied_patterns
            )
        except CheckpointRefused as refused:
            if refused.code is CheckpointRefusalCode.PATH_REFUSED:
                cp = None
            else:
                return CheckpointRefusal(
                    code=refused.code, reason=clip(refused.reason), path=request.path
                ).model_dump(mode="json")
        result = writer.write(
            op=request.op,
            path=request.path,
            content=request.content,
            expected_sha256=request.expected_sha256,
        )
        if cp is None:
            return result
        if result.get("ok") is True:
            sha = result.get("sha256")
            manager.seal(cp.id, post_sha256=sha if isinstance(sha, str) else None)
            return {**result, "checkpoint_id": str(cp.id)}
        manager.mark_partial(cp.id)
        return result

    return handle


__all__ = [
    "INDEX_FILE",
    "OBJECTS_DIR",
    "CheckpointManager",
    "CheckpointRefused",
    "CheckpointStore",
    "checkpointed_write_handler",
]
