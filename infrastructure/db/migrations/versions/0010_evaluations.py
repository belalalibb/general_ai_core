"""evaluations — FINAL Phase 3 evaluations slice

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-28

Maps EvaluationRecord in core/contracts/evaluation.py field-for-field
(03 §7 Evaluation entity + the recorded R049 tenant_id storage-shape
addition — the CONTRACT carries tenant_id, so the parity pair matches
bidirectionally with no schema-side invention).

TENANT-SCOPED: tenant_id FK + index (20 §6). NO node_id column: R049
boundary (d) attaches evaluation at EXECUTION level in MVP (03 §8
"Evaluation belongs to Execution/Node" — node-level stays representable
for a later phase, never silently pre-built). execution_id FK RESTRICT +
index; deliberately NOT unique — multiple evaluations per execution are
permitted by the contract and no spec forbids it.

22 §4 embodied in DDL: score and confidence are SEPARATE nullable [0,1]
columns — "Never merge them into one number." CHECKs allow NULL
explicitly (NULL = no judgment recorded; RAW). ``graders`` JSONB
server_default '[]' == contract default () — an evaluation that recorded
no grader rows claims none. ``level`` has NO server_default — the
verification level must be an explicit claim (same posture as
skills.status / usage_ledger.status). Downgrade fully reverses (40 §8.2).

Closed-set CHECK carries the contract enum values verbatim:

- evaluations.level IN ('RAW', 'EVALUATED', 'VALIDATED', 'VERIFIED',
  'GOLD')                                            (VerificationLevel)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=512), nullable=True),
        sa.Column("graders", JSONB(), server_default="[]", nullable=False),
        sa.CheckConstraint(
            "level IN ('RAW', 'EVALUATED', 'VALIDATED', 'VERIFIED', 'GOLD')",
            name="ck_evaluations_level_closed_set",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name="ck_evaluations_score_bounds",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evaluations_confidence_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_evaluations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_evaluations_execution_id_executions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluations"),
    )
    op.create_index("ix_evaluations_tenant_id", "evaluations", ["tenant_id"])
    op.create_index("ix_evaluations_execution_id", "evaluations", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_execution_id", table_name="evaluations")
    op.drop_index("ix_evaluations_tenant_id", table_name="evaluations")
    op.drop_table("evaluations")
