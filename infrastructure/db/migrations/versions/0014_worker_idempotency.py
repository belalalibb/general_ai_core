"""worker_idempotency_keys — durable processed-key registry (Vision V1)

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-30

Backs core/runtime/worker.py IdempotencyPort (40 §4.3): the port docstring
records "durable binding is PostgreSQL" — this is that binding's table.

Design decisions (recorded):

- NOT a contract entity (same standing as memory_embeddings): 03 defines
  no ProcessedKey entity; this is infrastructure reliability data.
- ONE column: ``key`` PRIMARY KEY. The primary-key uniqueness IS the
  mechanism — a concurrent duplicate ``record`` hits the constraint and
  the worker treats the message as already processed (at-least-once
  delivery becomes exactly-once in effect, 40 §4.1 durable truth).
- String(512) matches the established bounded-identifier width
  (executions.idempotency_key). No timestamp, tenant, or payload column
  is invented: the port carries a bare string; retention/observability
  columns belong to a later, justified slice.

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_idempotency_keys",
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_worker_idempotency_keys"),
    )


def downgrade() -> None:
    op.drop_table("worker_idempotency_keys")
