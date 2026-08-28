"""learning_samples — FINAL Phase 3 learning-metadata slice (LAST §6 entity)

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-28

Maps LearningSample in core/contracts/learning.py field-for-field
(03 §7 yaml verbatim). tenant_id is NULLABLE BY SPEC (03 §7 uuid|null):
the recorded reading is "sample not attributed to a tenant" — no richer
semantics invented. Attributed samples keep the 20 §6 posture (FK +
index; NULLs are simply absent from tenant-filtered queries).

source_execution_id FK RESTRICT + index — 22 §9 requires "source trace
exists"; a dangling source would break training-eligibility forensics.
dataset_id is a PLAIN nullable UUID — NO Dataset table exists in the
41 §6 list, so there is NO FK target (03 §8: a sample enters Dataset
only after eligibility + verification; the Dataset entity belongs to a
later phase — never invented here).

Deny-by-default DB defaults equal the contract defaults: eligibility
'pending', sanitization_state 'pending', verification_level 'RAW' — a
new row grants NOTHING toward the 22 §9 training gate. Downgrade fully
reverses (40 §8.2).

Closed-set CHECK constraints carry the contract enum values verbatim:

- eligibility IN ('eligible', 'ineligible', 'pending')  (LearningEligibility)
- sanitization_state IN ('pending', 'passed', 'failed')  (SanitizationState)
- verification_level IN ('RAW', 'EVALUATED', 'VALIDATED', 'VERIFIED',
  'GOLD')                                               (VerificationLevel)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_samples",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "eligibility",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "sanitization_state",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "verification_level",
            sa.String(length=32),
            server_default="RAW",
            nullable=False,
        ),
        sa.Column("dataset_id", UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "eligibility IN ('eligible', 'ineligible', 'pending')",
            name="ck_learning_samples_eligibility_closed_set",
        ),
        sa.CheckConstraint(
            "sanitization_state IN ('pending', 'passed', 'failed')",
            name="ck_learning_samples_sanitization_state_closed_set",
        ),
        sa.CheckConstraint(
            "verification_level IN ('RAW', 'EVALUATED', 'VALIDATED', "
            "'VERIFIED', 'GOLD')",
            name="ck_learning_samples_verification_level_closed_set",
        ),
        sa.ForeignKeyConstraint(
            ["source_execution_id"],
            ["executions.id"],
            name="fk_learning_samples_source_execution_id_executions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_learning_samples_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_samples"),
    )
    op.create_index("ix_learning_samples_tenant_id", "learning_samples", ["tenant_id"])
    op.create_index(
        "ix_learning_samples_source_execution_id",
        "learning_samples",
        ["source_execution_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_samples_source_execution_id", table_name="learning_samples"
    )
    op.drop_index("ix_learning_samples_tenant_id", table_name="learning_samples")
    op.drop_table("learning_samples")
