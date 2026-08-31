"""Proposal + snapshot stores: port protocols and in-memory bindings.

ADR-0009 recorded posture: in-process bindings now (same as
ScenarioService / review markers); a durable repository binding is a
later conscious slice. The PORTS are the architecture — criterion 12:
swapping the binding never touches the workflow.

Store integrity duties:

- Snapshots are verified on save AND on read (criterion 1): a store must
  never hold or serve bytes whose content-address lies about them.
- Tenant scoping is double-checked: every read takes ``tenant_id`` and a
  foreign/absent/malformed proposal id answers the identical
  :class:`ProposalNotFound` (anti-enumeration, 20 §6).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.sourcechange.errors import (
    ProposalNotFound,
    SnapshotIntegrityError,
    UnknownSnapshot,
)
from core.sourcechange.proposal import ChangeProposal
from core.sourcechange.snapshot import SourceSnapshot

__all__ = [
    "InMemoryProposalStore",
    "InMemorySnapshotStore",
    "ProposalStorePort",
    "SnapshotStorePort",
]


class SnapshotStorePort(Protocol):
    """Content-addressed snapshot storage — save/get by snapshot id."""

    def save_snapshot(self, tenant_id: UUID, snapshot: SourceSnapshot) -> None:
        """Persist a snapshot; MUST refuse an integrity-failing snapshot."""
        ...

    def get_snapshot(self, tenant_id: UUID, snapshot_id: str) -> SourceSnapshot:
        """Return the snapshot or raise :class:`UnknownSnapshot`; MUST
        re-verify integrity before serving."""
        ...


class ProposalStorePort(Protocol):
    """Tenant-scoped proposal records — latest record per proposal id."""

    def save_proposal(self, proposal: ChangeProposal) -> None: ...

    def get_proposal(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        """Return the proposal or raise :class:`ProposalNotFound` — absent
        and foreign-tenant ids answer identically (20 §6)."""
        ...

    def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]: ...


class InMemorySnapshotStore:
    """Hermetic binding — dict per tenant, integrity enforced both ways."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[UUID, str], SourceSnapshot] = {}

    def save_snapshot(self, tenant_id: UUID, snapshot: SourceSnapshot) -> None:
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(snapshot.snapshot_id)
        self._snapshots[(tenant_id, snapshot.snapshot_id)] = snapshot

    def get_snapshot(self, tenant_id: UUID, snapshot_id: str) -> SourceSnapshot:
        snapshot = self._snapshots.get((tenant_id, snapshot_id))
        if snapshot is None:
            raise UnknownSnapshot(snapshot_id)
        if not snapshot.verify_integrity():  # pragma: no cover - defensive
            raise SnapshotIntegrityError(snapshot_id)
        return snapshot


class InMemoryProposalStore:
    """Hermetic binding — latest record per (tenant, proposal) id."""

    def __init__(self) -> None:
        self._proposals: dict[tuple[UUID, UUID], ChangeProposal] = {}

    def save_proposal(self, proposal: ChangeProposal) -> None:
        self._proposals[(proposal.tenant_id, proposal.proposal_id)] = proposal

    def get_proposal(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        proposal = self._proposals.get((tenant_id, proposal_id))
        if proposal is None:
            raise ProposalNotFound()
        return proposal

    def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        return tuple(
            sorted(
                (
                    proposal
                    for (owner, _), proposal in self._proposals.items()
                    if owner == tenant_id
                ),
                key=lambda item: (item.created_at, str(item.proposal_id)),
            )
        )
