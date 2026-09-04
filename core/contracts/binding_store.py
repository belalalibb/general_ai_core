"""Persistence contracts for :class:`RepoBinding` records (R172 C2; INV-1, INV-3).

The on-disk document is versioned so a future shape change is detected as
``malformed`` instead of being half-parsed. Only ``credential_ref`` is ever
serialised (INV-3): the token lives behind ``SecretManagerPort``.

Loading is *fail-closed and reported*: every record that does not validate is
skipped and listed in :class:`BindingStoreLoadReport.skipped` with its index and
reason. Nothing here raises into the tool path — the report is data (INV-2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.repo_binding import RepoBinding

BINDING_STORE_VERSION: Literal[1] = 1

SourceState = Literal["missing", "ok", "partial", "malformed", "unreadable"]
"""Where the loaded records came from.

* ``missing``    — no file; empty registry is the correct state.
* ``ok``         — every record validated.
* ``partial``    — at least one record skipped; the valid ones are usable.
* ``malformed``  — the document itself is unusable; nothing loaded.
* ``unreadable`` — the file exists but could not be read; nothing loaded.
"""


class BindingStoreDocument(ContractModel):
    """Versioned on-disk envelope. ``version`` must equal :data:`BINDING_STORE_VERSION`."""

    version: Literal[1] = BINDING_STORE_VERSION
    bindings: tuple[RepoBinding, ...] = ()


class SkippedRecord(ContractModel):
    """One record that did not survive the fail-closed load."""

    index: int = Field(ge=0)
    reason: BoundedStr


class BindingStoreLoadReport(ContractModel):
    """Result of a load: valid bindings, skipped records, and the source state."""

    bindings: tuple[RepoBinding, ...] = ()
    skipped: tuple[SkippedRecord, ...] = ()
    source_state: SourceState

    @property
    def clean(self) -> bool:
        return self.source_state in ("missing", "ok")


__all__ = [
    "BINDING_STORE_VERSION",
    "BindingStoreDocument",
    "BindingStoreLoadReport",
    "SkippedRecord",
    "SourceState",
]
