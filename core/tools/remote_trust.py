"""Explicit remote trust registry and durable store (R172 C3).

Semantics
---------
* A (tenant, remote_url) pair is **untrusted by default**. Only a validated
  :class:`RemoteTrustGrant` with ``trusted is True`` and no revocation makes it
  trusted. A string ``"true"`` never validates (``StrictBool``) and is skipped.
* Lookup normalisation is deliberately conservative: only surrounding
  whitespace is stripped. Case/scheme/``.git`` variants are *different*
  remotes and stay untrusted.
* ``is_trusted`` never raises into the tool path: any store problem means
  "not trusted" and is reported through :attr:`RemoteTrustRegistry.load_report`.
* Persistence reuses the C2 durability primitives (:mod:`core.tools.atomic_json`):
  0o700 directory, 0o600 file, atomic replace, fail-closed corrupt handling.

Enforcement of trust lives in ``apps.agent_dev.git_tools.GitToolset`` only.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from core.contracts.remote_trust import (
    TRUST_STORE_VERSION,
    RemoteTrustGrant,
    TrustSkippedRecord,
    TrustSourceState,
    TrustStoreDocument,
    TrustStoreLoadReport,
)
from core.tools.atomic_json import (
    AtomicJsonRefused,
    clip,
    read_document,
    resolve_outside,
    write_document,
)

_WHAT = "trust store"


class RemoteTrustRefused(AtomicJsonRefused):
    """Typed trust-store failure (bad location or interrupted write)."""


class TrustStorePort(Protocol):
    def load(self) -> TrustStoreLoadReport: ...

    def save(self, grants: Iterable[RemoteTrustGrant]) -> None: ...


def _key(tenant_id: UUID, remote_url: str) -> tuple[UUID, str]:
    return (tenant_id, remote_url.strip())


class JsonRemoteTrustStore:
    """Atomic, permission-tightened JSON store for trust grants."""

    def __init__(self, path: Path, outside_of: tuple[Path, ...] = ()) -> None:
        try:
            self._path = resolve_outside(path, outside_of, what=_WHAT)
        except AtomicJsonRefused as exc:
            raise RemoteTrustRefused(exc.reason) from None

    @property
    def path(self) -> Path:
        return self._path

    def save(self, grants: Iterable[RemoteTrustGrant]) -> None:
        doc = TrustStoreDocument(version=TRUST_STORE_VERSION, grants=tuple(grants))
        try:
            write_document(self._path, doc.model_dump(mode="json"), what=_WHAT)
        except AtomicJsonRefused as exc:
            raise RemoteTrustRefused(exc.reason) from exc

    def load(self) -> TrustStoreLoadReport:
        state, records, reason = read_document(
            self._path, version=TRUST_STORE_VERSION, list_key="grants", what=_WHAT
        )
        if state == "missing":
            return TrustStoreLoadReport(source_state="missing")
        if state != "ok":
            return TrustStoreLoadReport(
                skipped=(TrustSkippedRecord(index=0, reason=reason or state),),
                source_state=state,
            )

        good: list[RemoteTrustGrant] = []
        skipped: list[TrustSkippedRecord] = []
        seen: set[tuple[UUID, str]] = set()
        for index, record in enumerate(records):
            try:
                grant = RemoteTrustGrant.model_validate(record)
            except ValidationError as exc:
                reason_txt = f"invalid record: {exc.error_count()} error(s)"
                skipped.append(TrustSkippedRecord(index=index, reason=clip(reason_txt)))
                continue
            except Exception as exc:  # defensive: never raise into the tool path
                skipped.append(
                    TrustSkippedRecord(index=index, reason=clip(f"invalid record: {exc!r}"))
                )
                continue
            key = _key(grant.tenant_id, grant.remote_url)
            if key in seen:
                skipped.append(TrustSkippedRecord(index=index, reason="duplicate grant"))
                continue
            seen.add(key)
            good.append(grant)

        final: TrustSourceState = "partial" if skipped else "ok"
        return TrustStoreLoadReport(grants=tuple(good), skipped=tuple(skipped), source_state=final)


class RemoteTrustRegistry:
    """In-memory trust table, optionally backed by a :class:`TrustStorePort`.

    Loading happens once at construction; a corrupt or unreadable store yields
    an empty table (nothing trusted) and a ``load_report`` describing why.
    """

    def __init__(self, store: TrustStorePort | None = None) -> None:
        self._store = store
        self._grants: dict[tuple[UUID, str], RemoteTrustGrant] = {}
        self.load_report: TrustStoreLoadReport | None = None
        if store is not None:
            report = store.load()
            self.load_report = report
            for grant in report.grants:
                self._grants[_key(grant.tenant_id, grant.remote_url)] = grant

    # --- queries -----------------------------------------------------------

    def get(self, tenant_id: UUID, remote_url: str) -> RemoteTrustGrant | None:
        return self._grants.get(_key(tenant_id, remote_url))

    def is_trusted(self, tenant_id: UUID, remote_url: str) -> bool:
        grant = self.get(tenant_id, remote_url)
        return grant is not None and grant.effective

    # --- mutations ---------------------------------------------------------

    def grant(self, grant: RemoteTrustGrant) -> None:
        self._grants[_key(grant.tenant_id, grant.remote_url)] = grant
        self._persist()

    def revoke(self, tenant_id: UUID, remote_url: str, *, revoked_by: str) -> None:
        key = _key(tenant_id, remote_url)
        current = self._grants.get(key)
        now = datetime.now(UTC)
        if current is None:
            # Record the revocation explicitly so the decision is auditable.
            current = RemoteTrustGrant(
                tenant_id=tenant_id,
                remote_url=key[1],
                trusted=False,
                granted_by=revoked_by,
                granted_at=now,
            )
        self._grants[key] = current.model_copy(update={"revoked_by": revoked_by, "revoked_at": now})
        self._persist()

    def _persist(self) -> None:
        if self._store is not None:
            self._store.save(self._grants.values())


__all__ = [
    "JsonRemoteTrustStore",
    "RemoteTrustRefused",
    "RemoteTrustRegistry",
    "TrustStorePort",
]
