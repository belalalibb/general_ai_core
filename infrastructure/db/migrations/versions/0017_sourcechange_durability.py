"""source-change durability — snapshots + proposals (P-A.3, ADR-0010)

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-31

Backs the durable bindings for the EXISTING V8 sync ports
(``core/sourcechange/store.py``: SnapshotStorePort / ProposalStorePort).
ADR-0010 records every schema decision; the §14 scope guard is restated
there and here: these are RECORDS — persisting a proposal is NOT applying
it; ``authoritative_applier=None`` stays; R3 stays never-registrable.

Design decisions (ADR-0010, summarized):

- Tenant-scoped entity data (20 §6): composite PKs keyed by tenant_id;
  a foreign row is structurally invisible to every read.
- ``source_snapshots.files`` JSONB ``{path: base64(content)}`` — snapshot
  content is arbitrary BYTES; base64 crosses JSONB's UTF-8 boundary.
  Object storage (41 §6) deferred until snapshots outgrow row-sized
  documents (recorded alternative).
- ``source_change_proposals`` UPSERT latest-record-per-id semantics (the
  port's contract); ``state`` CHECK-constrained to the closed
  ProposalState set (same closed-set discipline as every 0001+ table).
- Integrity is RE-DERIVED on read, never trusted from rows (ADR-0010):
  enforcement lives in the store layer, the schema just holds the facts.
- No FK to tenants: proposals ride the workflow before any identity
  row necessarily exists in dev profiles; tenant scoping is structural
  via the PK (same standing as worker_idempotency_keys).

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROPOSAL_STATES = (
    "'draft', 'verified', 'failed_verification', 'approved', "
    "'rejected', 'applied', 'rolled_back'"
)


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.Text(), nullable=False),
        sa.Column("files", JSONB, nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "snapshot_id", name="pk_source_snapshots"
        ),
    )
    op.create_table(
        "source_change_proposals",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("base_snapshot_id", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("patch_hash", sa.Text(), nullable=False),
        sa.Column("patch", JSONB, nullable=False),
        sa.Column("inverse_patch", JSONB, nullable=True),
        sa.Column("approval", JSONB, nullable=True),
        sa.Column("applied_snapshot_id", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "proposal_id", name="pk_source_change_proposals"
        ),
        sa.CheckConstraint(
            f"state IN ({_PROPOSAL_STATES})",
            name="ck_source_change_proposals_state_closed_set",
        ),
    )


def downgrade() -> None:
    op.drop_table("source_change_proposals")
    op.drop_table("source_snapshots")
