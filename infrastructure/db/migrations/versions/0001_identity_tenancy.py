"""identity/tenancy — first schema slice (tenants, users, workspaces, projects)

Revision ID: 0001
Revises: None
Create Date: 2026-08-25

Maps core/contracts/identity.py (03 §2 field-for-field) — reviewed by hand
against infrastructure/db/tables.py; kept in sync (test enforces parity of
table/column names). Downgrade drops everything this revision created
(40 §8.2 rollback capability).

Closed-set CHECK constraints carry the contract enum values verbatim:

- tenants.type   IN ('personal', 'organization')      (TenantType)
- tenants.status IN ('active', 'suspended')            (TenantStatus)
- users.status   IN ('active', 'disabled', 'pending')  (UserStatus)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('personal', 'organization')",
            name="ck_tenants_type_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_tenants_status_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=512), nullable=False),
        sa.Column("email_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("preferred_language", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'pending')",
            name="ck_users_status_closed_set",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_users_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_workspaces_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
    )
    op.create_index("ix_workspaces_tenant_id", "workspaces", ["tenant_id"])

    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_projects_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_projects_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_tenant_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_workspaces_tenant_id", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
