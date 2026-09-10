"""DEC03 B: governed learning custody; no historical payload backfill.

Downgrade is safe only when empty. A populated custody ledger must be retained;
rollback disables ingestion and keeps a fail-closed reader, never erases evidence.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_executions_custody_identity", "executions", ["id", "tenant_id"])
    op.create_unique_constraint(
        "uq_learning_samples_custody_identity",
        "learning_samples",
        ["id", "tenant_id", "source_execution_id"],
    )
    op.create_table(
        "learning_sample_custody",
        sa.Column("sample_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rights_ref", UUID(as_uuid=True), nullable=False),
        sa.Column("retention_seconds", sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("descriptor_digest", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("payload", JSONB(none_as_null=True), nullable=True),
        sa.Column("quarantined", sa.Boolean, nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["sample_id", "tenant_id", "source_execution_id"],
            [
                "learning_samples.id",
                "learning_samples.tenant_id",
                "learning_samples.source_execution_id",
            ],
            name="fk_custody_sample_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_execution_id", "tenant_id"],
            ["executions.id", "executions.tenant_id"],
            name="fk_custody_execution_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_custody_tenant_idempotency"),
        sa.CheckConstraint(
            "retention_seconds > 0 AND expires_at > created_at", name="custody_retention"
        ),
        sa.CheckConstraint("revision >= 0", name="custody_revision"),
        sa.CheckConstraint("source_kind IN ('external', 'execution')", name="custody_source_kind"),
        sa.CheckConstraint(
            "NOT (quarantined OR revoked) OR payload IS NULL", name="custody_no_quarantined_payload"
        ),
        sa.CheckConstraint("jsonb_typeof(state) = 'object'", name="custody_state_object"),
    )
    op.create_index(
        "ix_custody_tenant_expiry", "learning_sample_custody", ["tenant_id", "expires_at"]
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("custody downgrade requires online proof that the table is empty")
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM learning_sample_custody)"))
        .scalar()
    ):
        raise RuntimeError(
            "populated custody rollback must preserve evidence; disable intake instead"
        )
    op.drop_table("learning_sample_custody")
    op.drop_constraint("uq_learning_samples_custody_identity", "learning_samples", type_="unique")
    op.drop_constraint("uq_executions_custody_identity", "executions", type_="unique")
