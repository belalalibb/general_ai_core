"""DEC03 persistent revocation, with fail-closed unresolved legacy history.

Stop old learning writers before migrating; do not roll old binaries back into
service. 0019 lost zero-row revocations and conflated expiry with revocation.
All preexisting tenants therefore receive a deny-only reconciliation hold, even
without custody rows. No policy intent or consent is inferred from sample flags.
No automatic release is safe; evidence-preserving operator reconciliation is a
separate prerequisite to enabling learning for these legacy tenants.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Stabilize the legacy tenant snapshot and custody writes during migration.
    # This cannot make old application binaries safe after the transaction ends.
    op.execute("LOCK TABLE tenants, learning_sample_custody IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "learning_policy_revocations",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "policy_id", name="uq_learning_policy_revocation_scope",
                            postgresql_nulls_not_distinct=True),
        sa.CheckConstraint(
            "(policy_id IS NULL AND reason = 'legacy_unresolved') OR "
            "(policy_id IS NOT NULL AND reason = 'revoked')",
            name="learning_policy_revocation_reason",
        ),
    )
    op.execute(
        "INSERT INTO learning_policy_revocations (tenant_id, policy_id, reason) "
        "SELECT id, NULL, 'legacy_unresolved' FROM tenants"
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("revocation downgrade requires online proof of empty state")
    op.execute("LOCK TABLE learning_policy_revocations IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM learning_policy_revocations)"
    )).scalar():
        raise RuntimeError("rollback must preserve revocations and holds; disable intake instead")
    op.drop_table("learning_policy_revocations")
