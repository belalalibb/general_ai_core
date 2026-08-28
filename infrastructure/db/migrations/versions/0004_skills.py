"""skills — FINAL Phase 3 "skills metadata" slice

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28

Maps core/contracts/skills.py (03 §6 Skill entity, field-for-field).
METADATA ONLY per 41 §6: provenance/manifest are JSONB catalog data (the
contract binds their shapes to 14 §2/§3 at the boundary); skill
CONTENT/artifacts belong to object storage, not this table. PLATFORM
catalog — no tenant_id (03 §6 defines none). ``status`` has NO permissive
server_default — a row must state its lifecycle stage explicitly (14 §9
forbids implicit activation: "Imported skill becomes active without
review" is FORBIDDEN). Downgrade drops the table (40 §8.2 rollback).

Closed-set CHECK constraints carry the contract enum values verbatim:

- skills.type   IN ('instruction', 'workflow', 'tool_enabled')   (SkillType)
- skills.source IN ('local', 'imported')                          (SkillSource)
- skills.status IN ('imported', 'scanned', 'validated', 'reviewed',
                    'approved', 'active', 'disabled')              (SkillStatus, 14 §3)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("version", sa.String(length=512), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("provenance", JSONB(), server_default="{}", nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "type IN ('instruction', 'workflow', 'tool_enabled')",
            name="ck_skills_type_closed_set",
        ),
        sa.CheckConstraint(
            "source IN ('local', 'imported')",
            name="ck_skills_source_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('imported', 'scanned', 'validated', 'reviewed', "
            "'approved', 'active', 'disabled')",
            name="ck_skills_status_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.UniqueConstraint("name", "version", name="uq_skills_name_version"),
    )


def downgrade() -> None:
    op.drop_table("skills")
