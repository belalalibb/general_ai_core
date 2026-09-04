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

The durable primitives live in :mod:`core.tools.atomic_json` (shared with the
C3 trust store).
"""

from __future__ import annotations

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
from core.tools.atomic_json import (
    AtomicJsonRefused,
    clip,
    read_document,
    resolve_outside,
    write_document,
)

_WHAT = "binding store"


class BindingStoreRefused(AtomicJsonRefused):
    """Typed store failure (bad location or interrupted write)."""


class JsonBindingStore:
    """Atomic, permission-tightened JSON store for a tenant-mixed binding set."""

    def __init__(self, path: Path, outside_of: tuple[Path, ...] = ()) -> None:
        try:
            self._path = resolve_outside(path, outside_of, what=_WHAT)
        except AtomicJsonRefused as exc:
            raise BindingStoreRefused(exc.reason) from None

    @property
    def path(self) -> Path:
        return self._path

    # --- write -------------------------------------------------------------

    def save(self, bindings: Iterable[RepoBinding]) -> None:
        doc = BindingStoreDocument(version=BINDING_STORE_VERSION, bindings=tuple(bindings))
        try:
            write_document(self._path, doc.model_dump(mode="json"), what=_WHAT)
        except AtomicJsonRefused as exc:
            raise BindingStoreRefused(exc.reason) from exc

    # --- read --------------------------------------------------------------

    def load(self) -> BindingStoreLoadReport:
        state, records, reason = read_document(
            self._path, version=BINDING_STORE_VERSION, list_key="bindings", what=_WHAT
        )
        if state == "missing":
            return BindingStoreLoadReport(source_state="missing")
        if state != "ok":
            return BindingStoreLoadReport(
                skipped=(SkippedRecord(index=0, reason=reason or state),), source_state=state
            )

        good: list[RepoBinding] = []
        skipped: list[SkippedRecord] = []
        seen: set[object] = set()
        for index, record in enumerate(records):
            try:
                binding = RepoBinding.model_validate(record)
            except ValidationError as exc:
                reason_txt = f"invalid record: {exc.error_count()} error(s)"
                skipped.append(SkippedRecord(index=index, reason=clip(reason_txt)))
                continue
            except Exception as exc:  # defensive: never raise into the tool path
                skipped.append(SkippedRecord(index=index, reason=clip(f"invalid record: {exc!r}")))
                continue
            if binding.id in seen:
                skipped.append(SkippedRecord(index=index, reason="duplicate binding id"))
                continue
            seen.add(binding.id)
            good.append(binding)

        final: SourceState = "partial" if skipped else "ok"
        return BindingStoreLoadReport(
            bindings=tuple(good), skipped=tuple(skipped), source_state=final
        )


__all__ = ["BindingStoreRefused", "JsonBindingStore"]
