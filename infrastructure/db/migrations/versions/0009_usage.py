"""usage_ledger — FINAL Phase 3 usage slice

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-28

Maps the 03 §7 UsageLedger in core/contracts/usage.py, field-for-field.
TENANT-SCOPED: tenant_id FK + index (20 §6). ONE ledger entry per
execution — the usage port keys the ledger by execution_id
(core/usage/memory.py) and a reservation resolves exactly once
(ReservationAlreadyResolved) — so execution_id is UNIQUE + FK
(RESTRICT: accounting records must never dangle).

Deny-by-default in DB defaults: units_settled server_default '0' and
modality_costs server_default '{}' equal the contract defaults — an
unresolved entry claims NO settled consumption. ``status`` has NO
server_default — the lifecycle stage must be explicit (same recorded
posture as skills.status). Downgrade fully reverses (40 §8.2).

Closed-set CHECK carries the contract enum values verbatim:

- usage_ledger.status IN ('reserved', 'settled', 'refunded', 'failed')
                                                      (UsageLedgerStatus)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_ledger",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("units_reserved", sa.Float(), nullable=False),
        sa.Column("units_settled", sa.Float(), server_default="0", nullable=False),
        sa.Column("modality_costs", JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled', 'refunded', 'failed')",
            name="ck_usage_ledger_status_closed_set",
        ),
        sa.CheckConstraint(
            "units_reserved >= 0",
            name="ck_usage_ledger_units_reserved_nonnegative",
        ),
        sa.CheckConstraint(
            "units_settled >= 0",
            name="ck_usage_ledger_units_settled_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_usage_ledger_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_usage_ledger_execution_id_executions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_ledger"),
        sa.UniqueConstraint("execution_id", name="uq_usage_ledger_execution_id"),
    )
    op.create_index("ix_usage_ledger_tenant_id", "usage_ledger", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_tenant_id", table_name="usage_ledger")
    op.drop_table("usage_ledger")
