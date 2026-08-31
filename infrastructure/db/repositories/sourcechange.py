"""PostgreSQL source-change repository — snapshot/proposal rows (ADR-0010).

Design decisions (recorded in ADR-0010, restated at the binding):

- WHAT IS DURABLE: the V8 records the sync ports already hold in memory
  (``core/sourcechange/store.py``) — ``SourceSnapshot`` values and the
  LATEST ``ChangeProposal`` record per (tenant, proposal) id. §14 scope
  guard: these are RECORDS — persisting a proposal is NOT applying it;
  ``authoritative_applier`` stays None and R3 stays never-registrable.
- ROWS NEVER CARRY TRUST (ADR-0010 / criterion 1): reconstruction goes
  through the domain constructors, so ``ChangeProposal.__post_init__``
  RE-DERIVES ``patch_hash`` against the stored patch + base snapshot id —
  a tampered patch row raises the named :class:`ApprovalHashMismatch`
  instead of ever producing an object that lies. Snapshot integrity
  (``verify_integrity``) is enforced by the STORE layer on save and read
  (apps/composition/sourcechange.py) — the schema just holds the facts.
- BYTES ↔ JSONB: snapshot file contents and patch operation contents are
  arbitrary bytes; they cross JSONB's UTF-8 boundary as base64 (ADR-0010
  recorded trade-off; object storage per 41 §6 is the recorded
  alternative once snapshots outgrow row-sized documents).
- TENANT ISOLATION IS STRUCTURAL (20 §6): composite PKs keyed by
  tenant_id; every read filters in SQL, so a foreign row is never
  fetched and absent == foreign through the SAME named refusal
  (:class:`ProposalNotFound` / :class:`UnknownSnapshot`) the in-memory
  bindings raise — identical through both layers.
- UPSERT posture mirrors the in-memory dict: ``save_proposal`` keeps the
  LATEST record per id (lifecycle transitions derive new records via
  ``dataclasses.replace`` and re-save). ``save_snapshot`` is
  content-addressed — a conflicting id IS the same content, so the
  insert is ``ON CONFLICT DO NOTHING``.
- ``list_proposals`` orders by ``(created_at, proposal_id::text)`` in
  SQL — byte-identical to the in-memory sort key
  ``(item.created_at, str(item.proposal_id))``.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy import Text, cast, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.base import utc_now
from core.sourcechange.errors import ProposalNotFound, UnknownSnapshot
from core.sourcechange.patch import PatchOperation, PatchOpKind, SourcePatch
from core.sourcechange.proposal import (
    ApprovalRecord,
    ChangeProposal,
    ProposalState,
)
from core.sourcechange.snapshot import SourceSnapshot
from infrastructure.db.tables import source_change_proposals, source_snapshots

__all__ = ["PostgresSourceChangeRepository"]


def _encode_files(files: Mapping[str, bytes]) -> dict[str, str]:
    """``{path: bytes}`` → ``{path: base64}`` (JSONB is UTF-8 text)."""
    return {
        path: base64.b64encode(content).decode("ascii")
        for path, content in files.items()
    }


def _decode_files(payload: dict[str, str]) -> Mapping[str, bytes]:
    return MappingProxyType(
        {path: base64.b64decode(encoded) for path, encoded in payload.items()}
    )


def _encode_patch(patch: SourcePatch) -> dict[str, Any]:
    return {
        "operations": [
            {
                "kind": op.kind.value,
                "path": op.path,
                "content": (
                    base64.b64encode(op.content).decode("ascii")
                    if op.content is not None
                    else None
                ),
            }
            for op in patch.operations
        ]
    }


def _decode_patch(payload: dict[str, Any]) -> SourcePatch:
    return SourcePatch(
        operations=tuple(
            PatchOperation(
                kind=PatchOpKind(op["kind"]),
                path=op["path"],
                content=(
                    base64.b64decode(op["content"])
                    if op["content"] is not None
                    else None
                ),
            )
            for op in payload["operations"]
        )
    )


def _encode_approval(approval: ApprovalRecord) -> dict[str, str]:
    return {
        "approver_id": str(approval.approver_id),
        "approved_patch_hash": approval.approved_patch_hash,
        "decided_at": approval.decided_at.isoformat(),
    }


def _decode_approval(payload: dict[str, str]) -> ApprovalRecord:
    return ApprovalRecord(
        approver_id=UUID(payload["approver_id"]),
        approved_patch_hash=payload["approved_patch_hash"],
        decided_at=datetime.fromisoformat(payload["decided_at"]),
    )


def _proposal_values(proposal: ChangeProposal) -> dict[str, Any]:
    return {
        "tenant_id": proposal.tenant_id,
        "proposal_id": proposal.proposal_id,
        "actor_id": proposal.actor_id,
        "base_snapshot_id": proposal.base_snapshot_id,
        "rationale": proposal.rationale,
        "state": proposal.state.value,
        "patch_hash": proposal.patch_hash,
        "patch": _encode_patch(proposal.patch),
        "inverse_patch": (
            _encode_patch(proposal.inverse_patch)
            if proposal.inverse_patch is not None
            else None
        ),
        "approval": (
            _encode_approval(proposal.approval)
            if proposal.approval is not None
            else None
        ),
        "applied_snapshot_id": proposal.applied_snapshot_id,
        "created_at": proposal.created_at,
    }


def _row_to_proposal(row: Any) -> ChangeProposal:
    """Row → domain record THROUGH the constructor (never around it).

    ``__post_init__`` re-derives ``patch_hash`` from the stored patch and
    base snapshot id and compares it to the stored hash — a tampered row
    raises :class:`core.sourcechange.errors.ApprovalHashMismatch` naming
    both values (ADR-0010: rows never carry trust).
    """
    return ChangeProposal(
        tenant_id=row.tenant_id,
        actor_id=row.actor_id,
        base_snapshot_id=row.base_snapshot_id,
        patch=_decode_patch(row.patch),
        rationale=row.rationale,
        proposal_id=row.proposal_id,
        state=ProposalState(row.state),
        patch_hash=row.patch_hash,
        created_at=row.created_at,
        approval=(
            _decode_approval(row.approval) if row.approval is not None else None
        ),
        applied_snapshot_id=row.applied_snapshot_id,
        inverse_patch=(
            _decode_patch(row.inverse_patch)
            if row.inverse_patch is not None
            else None
        ),
    )


class PostgresSourceChangeRepository:
    """Durable snapshot/proposal persistence over asyncpg sessions.

    The session FACTORY is injected (never constructed here) — engine,
    credentials and pooling belong to the composition root, mirroring
    every other repository binding.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def save_snapshot(
        self, tenant_id: UUID, snapshot: SourceSnapshot
    ) -> None:
        """Persist one content-addressed snapshot (idempotent by identity).

        A conflicting (tenant_id, snapshot_id) IS the same content — the
        id is the sha256 manifest digest — so the insert does nothing on
        conflict (never an update: content-addressed rows are immutable).
        Integrity refusal happens at the STORE layer before this call.
        """
        stmt = (
            pg_insert(source_snapshots)
            .values(
                tenant_id=tenant_id,
                snapshot_id=snapshot.snapshot_id,
                files=_encode_files(snapshot.files),
                created_at=utc_now(),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    source_snapshots.c.tenant_id,
                    source_snapshots.c.snapshot_id,
                ]
            )
        )
        async with self._sessions() as session, session.begin():
            await session.execute(stmt)

    async def get_snapshot(
        self, tenant_id: UUID, snapshot_id: str
    ) -> SourceSnapshot:
        """Tenant-scoped read; absent == foreign (20 §6).

        The snapshot is rebuilt with the STORED id (never recomputed
        here) so the store layer's ``verify_integrity`` re-derivation can
        catch tampered bytes — recomputing the id at read time would
        launder tampering into a "valid" object.
        """
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(source_snapshots).where(
                        source_snapshots.c.tenant_id == tenant_id,
                        source_snapshots.c.snapshot_id == snapshot_id,
                    )
                )
            ).one_or_none()
        if row is None:
            raise UnknownSnapshot(snapshot_id)
        return SourceSnapshot(
            snapshot_id=row.snapshot_id, files=_decode_files(row.files)
        )

    async def save_proposal(self, proposal: ChangeProposal) -> None:
        """Upsert the LATEST record per (tenant, proposal) id.

        Lifecycle transitions derive new frozen records
        (``dataclasses.replace``) and re-save — the row mirrors the
        in-memory dict's latest-record semantics exactly.
        """
        values = _proposal_values(proposal)
        stmt = pg_insert(source_change_proposals).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                source_change_proposals.c.tenant_id,
                source_change_proposals.c.proposal_id,
            ],
            set_={
                key: getattr(stmt.excluded, key)
                for key in values
                if key not in ("tenant_id", "proposal_id")
            },
        )
        async with self._sessions() as session, session.begin():
            await session.execute(stmt)

    async def get_proposal(
        self, tenant_id: UUID, proposal_id: UUID
    ) -> ChangeProposal:
        """Tenant-scoped read; absent and foreign answer the identical
        named :class:`ProposalNotFound` (anti-enumeration, 20 §6)."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(source_change_proposals).where(
                        source_change_proposals.c.tenant_id == tenant_id,
                        source_change_proposals.c.proposal_id == proposal_id,
                    )
                )
            ).one_or_none()
        if row is None:
            raise ProposalNotFound()
        return _row_to_proposal(row)

    async def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        """Tenant-scoped list, ordered ``(created_at, proposal_id::text)``
        — byte-identical to the in-memory store's sort key."""
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(source_change_proposals)
                    .where(source_change_proposals.c.tenant_id == tenant_id)
                    .order_by(
                        source_change_proposals.c.created_at,
                        cast(source_change_proposals.c.proposal_id, Text),
                    )
                )
            ).all()
        return tuple(_row_to_proposal(row) for row in rows)
