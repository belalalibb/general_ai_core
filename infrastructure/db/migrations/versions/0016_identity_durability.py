"""identity durability — credentials, sessions, verification tokens (P-A.2)

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-31

Backs the durable identity binding (apps/composition/identity.py) for the
PROVEN ``InMemoryIdentityService`` semantics (core/identity/service.py,
41 §41).  The 0001 schema has users/tenants but — verified R138 — NO
password storage and NO session persistence; these three tables close
exactly that gap and nothing more.

Design decisions (recorded):

- NOT contract entities (same standing as worker_idempotency_keys /
  outbox_records): 03 defines no Credential/Session/VerificationToken
  entity — this is identity-infrastructure state behind the service
  surface.  User/Tenant remain THE contract entities in 0001 tables.
- 20 §5 secrets rules: ``user_credentials.password_hash`` stores ONLY
  the opaque hash from the PasswordHasherPort (Argon2id in production,
  ADR-0005).  Session and verification TOKENS ARE NEVER STORED RAW —
  the durable columns hold SHA-256 digests; the bearer token exists
  only in transit and in the client's hands.  A database leak therefore
  exposes no replayable token (preimage resistance).
- ``sessions``: one row per issued session, keyed by token digest;
  logout DELETES the row (revocation = absence, deny-by-default —
  matching InMemoryIdentityService.logout's pop()).
- ``email_verification_tokens``: single-use enforced by DELETE-on-redeem
  inside one transaction (matching the in-memory pop()).
- Tenant scoping (20 §6): sessions carry tenant_id denormalized so
  session resolution is one read and can never resolve across tenants.
- ON DELETE CASCADE from users: removing a user removes credentials and
  sessions with it — no orphaned secrets.

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_sha256", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "email_verification_tokens",
        sa.Column("token_sha256", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(512), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("user_credentials")
