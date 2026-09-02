"""P-A.3 — DurableProposalStore/DurableSnapshotStore port-parity tests.

Mirrors the PROVEN V8 in-memory store tests
(tests/sourcechange/test_proposal_lifecycle_v8.py, the "Stores" section)
against the durable bindings, in two layers (41 §49):

1. Hermetic: a FAKE async source-change repository (dict-backed, holding
   the SAME encoded row shapes ``PostgresSourceChangeRepository`` writes,
   reconstructed through the SAME row decoders) through the REAL
   AsyncBridge — proves port parity (integrity refusal on save AND read,
   anti-enumeration, latest-record semantics, tenant scoping, list
   ordering) plus the durability-specific facts: restart ("new store
   instances, same repository") preserves everything, and TAMPERED rows
   are refused by re-derivation, never served (ADR-0010 / criterion 1).
2. Live (env-gated, skip-when-absent): real Postgres round-trip against
   the migration-0017 tables, proving snapshot + proposal state survives
   an engine restart.

§14 scope guard: nothing here applies a change — these are RECORDS.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from types import MappingProxyType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from apps.composition.sourcechange import (
    DurableProposalStore,
    DurableSnapshotStore,
)
from core.sourcechange.errors import (
    ApprovalHashMismatch,
    ProposalNotFound,
    SnapshotIntegrityError,
    UnknownSnapshot,
)
from core.sourcechange.patch import (
    PatchOperation,
    PatchOpKind,
    SourcePatch,
    invert_patch,
    patch_hash,
)
from core.sourcechange.proposal import (
    ApprovalRecord,
    ChangeProposal,
    ProposalState,
)
from core.sourcechange.snapshot import SourceSnapshot
from core.sourcechange.store import ProposalStorePort, SnapshotStorePort
from infrastructure.db.repositories.sourcechange import (
    _encode_files,
    _proposal_values,
    _row_to_proposal,
)

TENANT = uuid4()
ACTOR = uuid4()
BASE = SourceSnapshot.from_files({"app/main.py": b"print('v1')\n", "README.md": b"# demo\n"})
PATCH = SourcePatch(
    operations=(
        PatchOperation(
            kind=PatchOpKind.MODIFY_FILE,
            path="app/main.py",
            content=b"print('v2')\n",
        ),
    )
)


def _proposal(**overrides: Any) -> ChangeProposal:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "actor_id": ACTOR,
        "base_snapshot_id": BASE.snapshot_id,
        "patch": PATCH,
        "rationale": "modernize the greeting",
    }
    values.update(overrides)
    return ChangeProposal(**values)


# --- fake async repository (real row shapes, real decoders) --------------------


@dataclass
class FakeSourceChangeRepository:
    """Dict-backed async repo holding the SAME encoded row payloads the
    Postgres binding writes — reads reconstruct through the SAME decoders
    (``_row_to_proposal``), so hash re-derivation is exercised for real."""

    snapshot_rows: dict[tuple[UUID, str], dict[str, str]] = field(default_factory=dict)
    proposal_rows: dict[tuple[UUID, UUID], dict[str, Any]] = field(default_factory=dict)

    async def save_snapshot(self, tenant_id: UUID, snapshot: SourceSnapshot) -> None:
        key = (tenant_id, snapshot.snapshot_id)
        if key not in self.snapshot_rows:  # ON CONFLICT DO NOTHING
            self.snapshot_rows[key] = _encode_files(snapshot.files)

    async def get_snapshot(self, tenant_id: UUID, snapshot_id: str) -> SourceSnapshot:
        row = self.snapshot_rows.get((tenant_id, snapshot_id))
        if row is None:
            raise UnknownSnapshot(snapshot_id)
        return SourceSnapshot(
            snapshot_id=snapshot_id,
            files=MappingProxyType({p: base64.b64decode(c) for p, c in row.items()}),
        )

    async def save_proposal(self, proposal: ChangeProposal) -> None:
        values = _proposal_values(proposal)  # UPSERT latest record
        self.proposal_rows[(proposal.tenant_id, proposal.proposal_id)] = values

    async def get_proposal(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        row = self.proposal_rows.get((tenant_id, proposal_id))
        if row is None:
            raise ProposalNotFound()
        return _row_to_proposal(SimpleNamespace(**row))

    async def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        rows = sorted(
            (row for (owner, _), row in self.proposal_rows.items() if owner == tenant_id),
            key=lambda row: (row["created_at"], str(row["proposal_id"])),
        )
        return tuple(_row_to_proposal(SimpleNamespace(**row)) for row in rows)


class ExplodingRepository:
    """Every call fails — proves durable-write failures surface loudly."""

    async def save_snapshot(self, tenant_id: UUID, snapshot: SourceSnapshot) -> None:
        raise ConnectionError("database unreachable")

    async def get_snapshot(self, tenant_id: UUID, snapshot_id: str) -> SourceSnapshot:
        raise ConnectionError("database unreachable")

    async def save_proposal(self, proposal: ChangeProposal) -> None:
        raise ConnectionError("database unreachable")

    async def get_proposal(self, tenant_id: UUID, proposal_id: UUID) -> ChangeProposal:
        raise ConnectionError("database unreachable")

    async def list_proposals(self, tenant_id: UUID) -> tuple[ChangeProposal, ...]:
        raise ConnectionError("database unreachable")


# --- fixtures -------------------------------------------------------------------


@pytest.fixture()
def bridge() -> Iterator[AsyncBridge]:
    with AsyncBridge() as b:
        yield b


@pytest.fixture()
def repository() -> FakeSourceChangeRepository:
    return FakeSourceChangeRepository()


@pytest.fixture()
def snapshots(repository: FakeSourceChangeRepository, bridge: AsyncBridge) -> SnapshotStorePort:
    return DurableSnapshotStore(repository=repository, bridge=bridge)


@pytest.fixture()
def proposals(repository: FakeSourceChangeRepository, bridge: AsyncBridge) -> ProposalStorePort:
    return DurableProposalStore(repository=repository, bridge=bridge)


# --- snapshot store parity (mirrors the V8 in-memory pins) ----------------------


class TestDurableSnapshotStore:
    def test_round_trip_and_unknown(self, snapshots: SnapshotStorePort) -> None:
        snapshots.save_snapshot(TENANT, BASE)
        restored = snapshots.get_snapshot(TENANT, BASE.snapshot_id)
        assert restored.snapshot_id == BASE.snapshot_id
        assert dict(restored.files) == dict(BASE.files)
        assert restored.verify_integrity()
        with pytest.raises(UnknownSnapshot):
            snapshots.get_snapshot(TENANT, "0" * 64)

    def test_refuses_integrity_failure_on_save_and_persists_nothing(
        self,
        snapshots: SnapshotStorePort,
        repository: FakeSourceChangeRepository,
    ) -> None:
        forged = SourceSnapshot(snapshot_id="0" * 64, files=BASE.files)
        with pytest.raises(SnapshotIntegrityError):
            snapshots.save_snapshot(TENANT, forged)
        assert repository.snapshot_rows == {}  # refusal BEFORE any row

    def test_tenant_scoped_foreign_is_unknown(self, snapshots: SnapshotStorePort) -> None:
        snapshots.save_snapshot(TENANT, BASE)
        with pytest.raises(UnknownSnapshot):
            snapshots.get_snapshot(uuid4(), BASE.snapshot_id)

    def test_tampered_row_is_refused_on_read(
        self,
        snapshots: SnapshotStorePort,
        repository: FakeSourceChangeRepository,
    ) -> None:
        """Criterion 1: the stored id is read back as stored, so tampered
        bytes fail re-verification — the store never serves a liar."""
        snapshots.save_snapshot(TENANT, BASE)
        row = repository.snapshot_rows[(TENANT, BASE.snapshot_id)]
        row["app/main.py"] = base64.b64encode(b"print('evil')\n").decode()
        with pytest.raises(SnapshotIntegrityError):
            snapshots.get_snapshot(TENANT, BASE.snapshot_id)

    def test_save_is_idempotent_by_content_address(
        self,
        snapshots: SnapshotStorePort,
        repository: FakeSourceChangeRepository,
    ) -> None:
        snapshots.save_snapshot(TENANT, BASE)
        snapshots.save_snapshot(TENANT, BASE)  # ON CONFLICT DO NOTHING
        assert len(repository.snapshot_rows) == 1

    def test_durable_write_failure_propagates_loudly(self, bridge: AsyncBridge) -> None:
        store = DurableSnapshotStore(repository=ExplodingRepository(), bridge=bridge)
        with pytest.raises(ConnectionError, match="database unreachable"):
            store.save_snapshot(TENANT, BASE)


# --- proposal store parity ------------------------------------------------------


class TestDurableProposalStore:
    def test_absent_and_foreign_answer_identically(self, proposals: ProposalStorePort) -> None:
        proposal = _proposal()
        proposals.save_proposal(proposal)
        with pytest.raises(ProposalNotFound) as absent:
            proposals.get_proposal(TENANT, uuid4())
        with pytest.raises(ProposalNotFound) as foreign:
            proposals.get_proposal(uuid4(), proposal.proposal_id)
        assert str(absent.value) == str(foreign.value)

    def test_keeps_latest_record_and_lists_by_tenant(self, proposals: ProposalStorePort) -> None:
        proposal = _proposal()
        proposals.save_proposal(proposal)
        proposals.save_proposal(proposal.with_state(ProposalState.VERIFIED))
        assert proposals.get_proposal(TENANT, proposal.proposal_id).state is ProposalState.VERIFIED
        other_tenant = uuid4()
        foreign = _proposal(tenant_id=other_tenant, rationale="other tenant")
        proposals.save_proposal(foreign)
        assert [p.proposal_id for p in proposals.list_proposals(TENANT)] == [proposal.proposal_id]
        assert [p.proposal_id for p in proposals.list_proposals(other_tenant)] == [
            foreign.proposal_id
        ]

    def test_list_orders_by_created_at_then_id_string(self, proposals: ProposalStorePort) -> None:
        """The in-memory sort key ``(created_at, str(proposal_id))``,
        byte-identical through the durable binding."""
        first = _proposal(rationale="first")
        second = _proposal(rationale="second")
        tied_a = _proposal(
            rationale="tied-a",
            created_at=second.created_at,
            proposal_id=UUID(int=1),
        )
        tied_b = _proposal(
            rationale="tied-b",
            created_at=second.created_at,
            proposal_id=UUID(int=2),
        )
        for item in (tied_b, second, tied_a, first):
            proposals.save_proposal(item)
        listed = proposals.list_proposals(TENANT)
        expected = sorted(
            (first, second, tied_a, tied_b),
            key=lambda item: (item.created_at, str(item.proposal_id)),
        )
        assert [p.proposal_id for p in listed] == [p.proposal_id for p in expected]

    def test_full_fidelity_round_trip_through_row_encoding(
        self, proposals: ProposalStorePort
    ) -> None:
        """approval / applied_snapshot_id / inverse_patch survive the
        encode→row→decode round-trip losslessly."""
        derived = ChangeProposal(
            tenant_id=TENANT,
            actor_id=ACTOR,
            base_snapshot_id=BASE.snapshot_id,
            patch=PATCH,
            rationale="full lifecycle",
        )
        approved = derived.with_state(ProposalState.VERIFIED).with_approval(
            ApprovalRecord(
                approver_id=uuid4(),
                approved_patch_hash=patch_hash(PATCH, BASE.snapshot_id),
            )
        )
        applied = approved.with_applied(
            applied_snapshot_id="b" * 64,
            inverse_patch=invert_patch(PATCH, BASE),
        )
        proposals.save_proposal(applied)
        restored = proposals.get_proposal(TENANT, applied.proposal_id)
        assert restored == applied  # frozen dataclass equality — every field

    def test_tampered_patch_row_raises_hash_mismatch(
        self,
        proposals: ProposalStorePort,
        repository: FakeSourceChangeRepository,
    ) -> None:
        """ADR-0010: rows never carry trust — ``__post_init__`` re-derives
        ``patch_hash`` on reconstruction, so a tampered patch column can
        never yield an object whose hash lies."""
        proposal = _proposal()
        proposals.save_proposal(proposal)
        row = repository.proposal_rows[(TENANT, proposal.proposal_id)]
        row["patch"]["operations"][0]["content"] = base64.b64encode(b"print('backdoor')\n").decode()
        with pytest.raises(ApprovalHashMismatch):
            proposals.get_proposal(TENANT, proposal.proposal_id)


# --- restart survival (hermetic) --------------------------------------------------


class TestRestartSurvivalHermetic:
    def test_new_store_instances_serve_persisted_state(
        self, repository: FakeSourceChangeRepository, bridge: AsyncBridge
    ) -> None:
        """ "Restart" = fresh store objects over the same repository: the
        durable rows are the only carried state, and they suffice."""
        before_snap = DurableSnapshotStore(repository=repository, bridge=bridge)
        before_prop = DurableProposalStore(repository=repository, bridge=bridge)
        proposal = _proposal().with_state(ProposalState.VERIFIED)
        before_snap.save_snapshot(TENANT, BASE)
        before_prop.save_proposal(proposal)

        after_snap = DurableSnapshotStore(repository=repository, bridge=bridge)
        after_prop = DurableProposalStore(repository=repository, bridge=bridge)
        restored_snapshot = after_snap.get_snapshot(TENANT, BASE.snapshot_id)
        assert restored_snapshot.verify_integrity()
        assert dict(restored_snapshot.files) == dict(BASE.files)
        restored = after_prop.get_proposal(TENANT, proposal.proposal_id)
        assert restored == proposal
        assert [p.proposal_id for p in after_prop.list_proposals(TENANT)] == [proposal.proposal_id]


# --- live Postgres round-trip (env-gated, 41 §49) ---------------------------------

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


@requires_live_postgres
class TestLiveSourceChangeDurability:
    def test_snapshot_and_proposal_survive_restart(self) -> None:
        from sqlalchemy import text

        from apps.composition.database import (
            build_database_bindings,
            database_settings_from_env,
        )
        from apps.composition.sourcechange import (
            build_durable_sourcechange_stores,
        )
        from infrastructure.db.tables import metadata

        settings = database_settings_from_env()
        assert settings is not None
        tenant_id = uuid4()
        proposal = ChangeProposal(
            tenant_id=tenant_id,
            actor_id=uuid4(),
            base_snapshot_id=BASE.snapshot_id,
            patch=PATCH,
            rationale="live restart-survival proof",
        ).with_state(ProposalState.VERIFIED)

        with AsyncBridge() as bridge:
            # --- process 1: write ---
            bindings = build_database_bindings(settings)

            async def prepare() -> None:
                async with bindings.engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)

            bridge.run(prepare())
            prop_store, snap_store = build_durable_sourcechange_stores(bindings, bridge)
            try:
                snap_store.save_snapshot(tenant_id, BASE)
                prop_store.save_proposal(proposal)
                with pytest.raises(SnapshotIntegrityError):
                    snap_store.save_snapshot(
                        tenant_id,
                        SourceSnapshot(snapshot_id="0" * 64, files=BASE.files),
                    )
            finally:

                async def dispose_first() -> None:
                    await bindings.engine.dispose()

                bridge.run(dispose_first())

            # --- process 2: fresh engine + stores (the restart) ---
            bindings2 = build_database_bindings(settings)
            prop2, snap2 = build_durable_sourcechange_stores(bindings2, bridge)
            try:
                restored_snapshot = snap2.get_snapshot(tenant_id, BASE.snapshot_id)
                assert restored_snapshot.verify_integrity()
                assert dict(restored_snapshot.files) == dict(BASE.files)
                restored = prop2.get_proposal(tenant_id, proposal.proposal_id)
                assert restored == proposal  # every field, hash re-derived
                assert [p.proposal_id for p in prop2.list_proposals(tenant_id)] == [
                    proposal.proposal_id
                ]
                # foreign tenant sees nothing (20 §6)
                with pytest.raises(ProposalNotFound):
                    prop2.get_proposal(uuid4(), proposal.proposal_id)
                with pytest.raises(UnknownSnapshot):
                    snap2.get_snapshot(uuid4(), BASE.snapshot_id)
            finally:

                async def cleanup() -> None:
                    async with bindings2.engine.begin() as conn:
                        await conn.execute(
                            text("DELETE FROM source_change_proposals WHERE tenant_id = :tid"),
                            {"tid": tenant_id},
                        )
                        await conn.execute(
                            text("DELETE FROM source_snapshots WHERE tenant_id = :tid"),
                            {"tid": tenant_id},
                        )
                    await bindings2.engine.dispose()

                bridge.run(cleanup())
