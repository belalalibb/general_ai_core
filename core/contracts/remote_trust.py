"""Explicit remote trust for the dev agent's git surface (R172 C3; INV-1, INV-5).

A remote URL is **untrusted by default**. Trust exists only as a
:class:`RemoteTrustGrant` recorded by a named granter for one (tenant,
remote_url) pair. Revocation is a second timestamped act on the same record.

``trusted`` is a *strict* bool: the string ``"true"`` (or ``1``) is a
validation error, never trust. Enforcement lives in ``GitToolset`` for the two
network-reaching acts (``git.fetch``, ``git.publish``) and is checked BEFORE
any credential is resolved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, field_validator

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.repo_binding import RemoteUrl

TRUST_STORE_VERSION: Literal[1] = 1

TrustSourceState = Literal["missing", "ok", "partial", "malformed", "unreadable"]


class RemoteTrustGrant(ContractModel):
    """One explicit trust decision for a remote, scoped to a tenant."""

    tenant_id: UUID
    remote_url: RemoteUrl
    trusted: StrictBool
    granted_by: BoundedStr
    granted_at: datetime
    revoked_by: BoundedStr | None = None
    revoked_at: datetime | None = None
    note: BoundedStr | None = None

    @field_validator("remote_url")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @property
    def effective(self) -> bool:
        """Trust in force right now: granted, not revoked."""
        return self.trusted is True and self.revoked_at is None


class TrustStoreDocument(ContractModel):
    version: Literal[1] = TRUST_STORE_VERSION
    grants: tuple[RemoteTrustGrant, ...] = ()


class TrustSkippedRecord(ContractModel):
    index: int = Field(ge=0)
    reason: BoundedStr


class TrustStoreLoadReport(ContractModel):
    grants: tuple[RemoteTrustGrant, ...] = ()
    skipped: tuple[TrustSkippedRecord, ...] = ()
    source_state: TrustSourceState


__all__ = [
    "TRUST_STORE_VERSION",
    "RemoteTrustGrant",
    "TrustSkippedRecord",
    "TrustSourceState",
    "TrustStoreDocument",
    "TrustStoreLoadReport",
]
