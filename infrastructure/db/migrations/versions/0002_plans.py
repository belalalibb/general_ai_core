"""plans — FINAL Phase 3 first storage slice (plans catalog + tenants FK)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-28

Maps core/contracts/plan.py (shapes from 21 §5/§10; derivation recorded in
the contract module — 03 lists Plan in the entity inventory without a yaml
table). Reviewed by hand against infrastructure/db/tables.py; the parity
test enforces table/column-name sync.

Also lands the FK the 0001 docstring deferred in phase order:
``tenants.plan_id -> plans.id`` (ondelete RESTRICT — a plan in use cannot
be deleted). Existing tenants rows would need their plan_id present in
plans before this upgrade; there is no production data yet (Lane C is
closed), so no backfill step is fabricated.

Deny-by-default (41 §1 rule 9): limits/entitlements/model_control JSONB
default to '{}' — an empty object parses to contract defaults that grant
NOTHING. Downgrade drops the FK and the table (40 §8.2 rollback).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("limits", JSONB(), server_default="{}", nullable=False),
        sa.Column("entitlements", JSONB(), server_default="{}", nullable=False),
        sa.Column("model_control", JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
        sa.UniqueConstraint("name", name="uq_plans_name"),
    )

    op.create_foreign_key(
        "fk_tenants_plan_id_plans",
        "tenants",
        "plans",
        ["plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tenants_plan_id_plans", "tenants", type_="foreignkey")
    op.drop_table("plans")
