"""memory_items + memory_embeddings — FINAL Phase 3 memory + pgvector slice

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-28

Maps the 03 §3 MemoryItem in core/contracts/memory.py, field-for-field
(incl. the 13 §3 ``sensitivity`` classification). memory_items is
TENANT-SCOPED: tenant_id FK + index (20 §6). user_id is nullable BY
SPEC — NULL means tenant-shared memory (03 §3). The memory port's
upsert semantics (core/memory/ports.py: keyed by tenant/user/scope/key)
are enforced by ``uq_memory_items_logical_key`` with NULLS NOT DISTINCT,
so user_id NULL collides like a value and tenant-shared upserts update
rather than duplicate.

memory_embeddings (41 §6 "pgvector: semantic retrieval") is
INFRASTRUCTURE RETRIEVAL DATA, not a contract entity — 03 §3 defines NO
embedding field on MemoryItem, and the schema must not invent contract
state. Exactly one embedding row per memory item (PK = FK, ondelete
CASCADE — derived data must never outlive its source). ``model_key``
records the producing embedding model so vectors from incompatible
spaces are never compared. ``embedding`` is dimension-UNCONSTRAINED:
the embedding model is admin configuration; no ANN index is created
until a model is pinned (an index requires a fixed dimension).

The pgvector extension is created idempotently in upgrade (the vector
type requires it). Downgrade drops the tables (children first, 40 §8.2)
but deliberately does NOT drop the extension — extension lifecycle is
database-level administration and other consumers may depend on it.

Closed-set CHECK constraints carry the contract enum values verbatim:

- memory_items.scope IN ('global', 'tenant', 'workspace', 'project',
  'conversation', 'role')                                   (MemoryScope)
- memory_items.sensitivity IN ('low', 'medium', 'high')     (MemorySensitivity)

Deny-by-default posture: sensitivity server_default 'low' matches the
contract default (MemorySensitivity.LOW); confidence bounded [0, 1];
evidence_count >= 0.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_items",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sensitivity", sa.String(length=32), server_default="low", nullable=False),
        sa.CheckConstraint(
            "scope IN ('global', 'tenant', 'workspace', 'project', 'conversation', 'role')",
            name="ck_memory_items_scope_closed_set",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('low', 'medium', 'high')",
            name="ck_memory_items_sensitivity_closed_set",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_memory_items_confidence_bounds",
        ),
        sa.CheckConstraint(
            "evidence_count >= 0",
            name="ck_memory_items_evidence_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_memory_items_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memory_items_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_items"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "scope",
            "key",
            name="uq_memory_items_logical_key",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_memory_items_tenant_id", "memory_items", ["tenant_id"])

    op.create_table(
        "memory_embeddings",
        sa.Column("memory_item_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_key", sa.String(length=512), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.ForeignKeyConstraint(
            ["memory_item_id"],
            ["memory_items.id"],
            name="fk_memory_embeddings_memory_item_id_memory_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("memory_item_id", name="pk_memory_embeddings"),
    )


def downgrade() -> None:
    op.drop_table("memory_embeddings")
    op.drop_index("ix_memory_items_tenant_id", table_name="memory_items")
    op.drop_table("memory_items")
