"""outbox_records — durable transactional outbox (Vision V2)

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-30

Backs core/runtime/outbox.py OutboxPort (40 §4.2): the module docstring
records "the real binding writes the outbox row in the SAME PostgreSQL
transaction as the state change" — this is that binding's table.

Design decisions (recorded):

- NOT a contract entity (same standing as worker_idempotency_keys): 03
  defines no OutboxRecord entity; this is infrastructure reliability data.
- ``id`` BIGINT GENERATED ALWAYS AS IDENTITY: insertion order IS the
  "oldest first" order ``pending`` promises — a monotone sequence, never
  timestamp parsing.
- ``payload`` JSONB carries the port's flat ``Mapping[str, str]`` verbatim.
- ``dispatched`` boolean (server_default false) settles a record after a
  successful publish (mark_dispatched). Dispatched rows are retained as
  delivery evidence; pruning belongs to a later, justified slice.
- Partial index on pending rows only (WHERE NOT dispatched): the relay
  polls "oldest pending first" and must not scan settled history.
- No tenant_id: platform runtime traffic keyed by stream; tenant scoping
  rides inside payloads (20 §6 applies to tenant-scoped ENTITY tables).

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("stream", sa.String(length=512), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column(
            "dispatched", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_records"),
    )
    op.create_index("ix_outbox_records_pending",
        "outbox_records",
        ["id"],
        postgresql_where=sa.text("NOT dispatched"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_records_pending", table_name="outbox_records")
    op.drop_table("outbox_records")
