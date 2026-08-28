"""roles + permissions — FINAL Phase 3 catalog slice

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-28

Maps core/contracts/roles.py (03 §6 Role entity, field-for-field — the
agent prompt role, NOT an RBAC role; distinction recorded in
core/contracts/security.py) and core/contracts/permission.py (derivation
recorded there: 20 §4 identifier + 14 §8 catalog/approval rule). Both are
PLATFORM catalogs — no tenant_id (20 §6 applies to tenant-scoped tables;
role applicability is the 03 §6 ``scope`` field, part of the entity).

Deny-by-default (41 §1 rule 9): permissions.approval server_default
'always' — the MOST RESTRICTIVE value; roles JSONB fields default to
empty (a role that requests nothing is valid; an implicit request is
not). Downgrade drops both tables (40 §8.2 rollback).

Closed-set CHECK constraints carry the contract enum values verbatim:

- roles.scope  IN ('system', 'tenant', 'user', 'project')        (RoleScope)
- roles.status IN ('draft', 'active', 'disabled')                (RoleStatus)
- permissions.approval IN ('none', 'before_action', 'always')    (ApprovalRequirement)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("version", sa.String(length=512), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("behavior_policies", JSONB(), server_default="{}", nullable=False),
        sa.Column("output_contract", JSONB(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capabilities_requested", JSONB(), server_default="[]", nullable=False),
        sa.CheckConstraint(
            "scope IN ('system', 'tenant', 'user', 'project')",
            name="ck_roles_scope_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name="ck_roles_status_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", "version", name="uq_roles_name_version"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("approval", sa.String(length=32), server_default="always", nullable=False),
        sa.CheckConstraint(
            "approval IN ('none', 'before_action', 'always')",
            name="ck_permissions_approval_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("key", name="uq_permissions_key"),
    )


def downgrade() -> None:
    op.drop_table("permissions")
    op.drop_table("roles")
