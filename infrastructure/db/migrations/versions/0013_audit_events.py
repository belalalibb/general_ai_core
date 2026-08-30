"""audit_events — durable audit log (Vision V1)

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-30

Maps core/contracts/audit.py AuditEvent field-for-field (03 §1 entity;
must-audit set 20 §9). TENANT-SCOPED: tenant_id FK + index (20 §6).

Design decisions (recorded):

- actor_id has NO users FK: None = system-initiated (contract docstring) —
  a policy job has no user row; the reference stays a recorded id.
- details JSONB server_default '{}' equals the contract default; 20 §5
  rule (no secret values, opaque refs only) is enforced at the appending
  boundary, not expressible as a CHECK.
- admin_change nullable JSONB: present IFF event_type is an admin change
  (21 §8) — validated by the binding (mirrors core/audit/memory.py); a
  CHECK would duplicate ADMIN_CHANGE_EVENT_TYPES outside core.
- Append-only posture: no UPDATE/DELETE path exists in the repository;
  the schema deliberately adds no updated_at column.
- Closed-set CHECK carries the AuditEventType values verbatim:
  event_type IN ('login','logout','credential_created','credential_revoked',
  'provider_account_used','permission_denied','tool_call',
  'approval_decision','admin_config_published','admin_config_rolled_back',
  'security_policy_changed','training_dataset_promoted',
  'cross_tenant_access_denied').

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("details", JSONB(), server_default="{}", nullable=False),
        sa.Column("admin_change", JSONB(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('login', 'logout', 'credential_created',"
            " 'credential_revoked', 'provider_account_used',"
            " 'permission_denied', 'tool_call', 'approval_decision',"
            " 'admin_config_published', 'admin_config_rolled_back',"
            " 'security_policy_changed', 'training_dataset_promoted',"
            " 'cross_tenant_access_denied')",
            name="ck_audit_events_event_type_closed_set",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_audit_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_table("audit_events")
