"""credentials — FINAL Phase 3 secret-manager row slice

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-28

Maps the 03 §4 Credential in core/contracts/domain.py field-for-field —
the row explicitly DEFERRED at R068 ("the Credential entity row with its
opaque credential_ref arrives with the secret-manager binding slice").

20 §5 / 40 §5.1 verbatim: the DB stores ``credential_ref`` ONLY — the
secret value lives in the Secret Manager; NO secret-value column exists.
NOT tenant-scoped in the 20 §6 sense BY SPEC: ownership is the
(owner_type, owner_id) pair — platform|tenant|user — with owner_id
nullable (03 §4 uuid|null; the platform owner has no UUID row). No
polymorphic FK exists in SQL for that union — owner_id stays a recorded
reference resolved at the application layer; no conditional CHECK is
invented since the spec states none.

provider_id FK→providers RESTRICT + index. ``credential_ref`` UNIQUE —
derived from the SecretManagerPort rotation model (store() mints a NEW
immutable ref per custody record; audit trails stay unambiguous).
``status`` has NO server_default — the lifecycle state is an explicit
claim (same posture as skills.status). Downgrade fully reverses (40
§8.2).

Closed-set CHECK constraints carry the contract enum values verbatim:

- credentials.owner_type IN ('platform', 'tenant', 'user')    (OwnerType)
- credentials.status IN ('active', 'revoked', 'expired',
  'invalid')                                          (CredentialStatus)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("provider_id", UUID(as_uuid=True), nullable=False),
        sa.Column("credential_ref", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "owner_type IN ('platform', 'tenant', 'user')",
            name="ck_credentials_owner_type_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired', 'invalid')",
            name="ck_credentials_status_closed_set",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name="fk_credentials_provider_id_providers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_credentials"),
        sa.UniqueConstraint("credential_ref", name="uq_credentials_credential_ref"),
    )
    op.create_index("ix_credentials_provider_id", "credentials", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_credentials_provider_id", table_name="credentials")
    op.drop_table("credentials")
