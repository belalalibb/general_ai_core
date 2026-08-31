"""P-A.3 — durable SnapshotStore/ProposalStore bindings (ADR-0010).

The V8 workflow (``core/sourcechange/workflow.py``) talks to the sync
PORTS in ``core/sourcechange/store.py`` — criterion 12: swapping the
binding never touches the workflow. This module supplies the Postgres
binding for both ports over the shared :class:`AsyncBridge` (ONE
sync-over-async primitive, R138), exactly as P-A.1/P-A.2 did for the
execution store and identity service.

§14 scope guard (ADR-0010, restated at the binding): these stores hold
RECORDS — persisting a proposal is NOT applying it. ``create_app`` keeps
``authoritative_applier=None``; R3 stays in ``NEVER_REGISTRABLE_CLASSES``;
nothing here can execute a change.

Integrity duties (identical to the in-memory bindings, enforced HERE —
the repository holds facts, the store enforces truth):

- ``save_snapshot`` refuses an integrity-failing snapshot with the named
  :class:`SnapshotIntegrityError` BEFORE any row exists (criterion 1).
- ``get_snapshot`` re-verifies the reconstructed snapshot: the id is
  read back as STORED (never recomputed), so tampered bytes fail
  ``verify_integrity`` and raise the same named refusal.
- Proposal rows re-derive ``patch_hash`` through
  ``ChangeProposal.__post_init__`` inside the repository — a tampered
  patch row raises :class:`ApprovalHashMismatch`, never yields a lying
  object.
- Absent == foreign-tenant through BOTH layers: the repository raises
  the SAME named errors the in-memory stores raise
  (:class:`ProposalNotFound` with no arguments, :class:`UnknownSnapshot`
  citing the id), and this module passes them through verbatim
  (anti-enumeration, 20 §6).

No cache layer: unlike P-A.1's execution reports (hot polling path with
process-local full-fidelity data), proposals and snapshots are
low-frequency review artifacts and the durable record IS the full
fidelity — a read-through cache would add a staleness surface for zero
reconstruction benefit (recorded decision).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.sourcechange.errors import SnapshotIntegrityError
from core.sourcechange.proposal import ChangeProposal
from core.sourcechange.snapshot import SourceSnapshot
from infrastructure.db.repositories.sourcechange import (
    PostgresSourceChangeRepository,
)

__all__ = [
    "DurableProposalStore",
    "DurableSnapshotStore",
    "SourceChangeRepositoryPort",
    "build_durable_sourcechange_stores",
]


class SourceChangeRepositoryPort(Protocol):
    """The async repository surface both stores persist through.

    Structural mirror of ``PostgresSourceChangeRepository`` — hermetic
    tests bind a fake with identical semantics (41 §49: the live
    Postgres round-trip is tested env-gated, never simulated as green).
    """

    async def save_snapshot(
        self, tenant_id: UUID, snapshot: SourceSnapshot
    ) -> None: ...

    async def get_snapshot(
        self, tenant_id: UUID, snapshot_id: str
    ) -> SourceSnapshot: ...

    async def save_proposal(self, proposal: ChangeProposal) -> None: ...

    async def get_proposal(
        self, tenant_id: UUID, proposal_id: UUID
    ) -> ChangeProposal: ...

    async def list_proposals(
        self, tenant_id: UUID
    ) -> tuple[ChangeProposal, ...]: ...


class DurableSnapshotStore:
    """Durable ``SnapshotStorePort`` binding (sync surface, bridge inside).

    Same integrity posture as ``InMemorySnapshotStore``: refuse lying
    content on save AND on read — a store must never hold or serve bytes
    whose content-address lies about them (criterion 1).
    """

    def __init__(
        self, *, repository: SourceChangeRepositoryPort, bridge: AsyncBridge
    ) -> None:
        self._repository = repository
        self._bridge = bridge

    def save_snapshot(self, tenant_id: UUID, snapshot: SourceSnapshot) -> None:
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(snapshot.snapshot_id)
        self._bridge.run(self._repository.save_snapshot(tenant_id, snapshot))

    def get_snapshot(self, tenant_id: UUID, snapshot_id: str) -> SourceSnapshot:
        """Named refusals pass through verbatim (:class:`UnknownSnapshot`
        for absent/foreign); the reconstruction is re-verified HERE."""
        snapshot = self._bridge.run(
            self._repository.get_snapshot(tenant_id, snapshot_id)
        )
        if not snapshot.verify_integrity():
            raise SnapshotIntegrityError(snapshot_id)
        return snapshot


class DurableProposalStore:
    """Durable ``ProposalStorePort`` binding (sync surface, bridge inside).

    Latest-record-per-id semantics ride the repository UPSERT; list
    ordering is the in-memory sort key, applied in SQL. Absent and
    foreign-tenant ids answer the identical :class:`ProposalNotFound`
    through both layers (20 §6).
    """

    def __init__(
        self, *, repository: SourceChangeRepositoryPort, bridge: AsyncBridge
    ) -> None:
        self._repository = repository
        self._bridge = bridge

    def save_proposal(self, proposal: ChangeProposal) -> None:
        self._bridge.run(self._repository.save_proposal(proposal))

    def get_proposal(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        return self._bridge.run(
            self._repository.get_proposal(tenant_id, proposal_id)
        )

    def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        return self._bridge.run(self._repository.list_proposals(tenant_id))


def build_durable_sourcechange_stores(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> tuple[DurableProposalStore, DurableSnapshotStore]:
    """Compose both durable stores over ONE shared repository.

    Same posture as P-A.1/P-A.2: callers reach here only via the
    ``database_settings_from_env`` branch — no DATABASE_URL, no durable
    stores (keep the in-memory bindings, byte-identical to today).
    """
    repository = PostgresSourceChangeRepository(bindings.session_factory)
    return (
        DurableProposalStore(repository=repository, bridge=bridge),
        DurableSnapshotStore(repository=repository, bridge=bridge),
    )
