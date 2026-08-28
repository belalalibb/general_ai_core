"""models + providers — FINAL Phase 3 registry slice

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-28

Maps the 03 §4 Model and Provider entities in core/contracts/domain.py,
field-for-field. PLATFORM catalogs — no tenant_id (03 §4 defines none;
tenant visibility is admin policy DATA, 21 §10). List/nested contract
fields (modalities, capabilities, auth_types, agent_capability) are JSONB
— the contract validates their shapes at the boundary; agent_capability
nullable (None = undeclared; 30 §4.3: unknown must NOT read as supported).
Scores/context_window nullable — unset means unscored, never invented.

NO credential-value column anywhere: Credential VALUES live in the Secret
Manager (41 §6 verbatim); the Credential row arrives with the
secret-manager binding slice. Downgrade drops both tables (40 §8.2).

Closed-set CHECK constraints carry the contract enum values verbatim:

- models.tier      IN ('fast', 'medium', 'max', 'custom')        (ModelTier)
- models.status    IN ('active', 'disabled', 'deprecated')       (ModelStatus)
- providers.status IN ('active', 'disabled', 'maintenance')      (ProviderStatus)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "models",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_key", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("modalities", JSONB(), nullable=False),
        sa.Column("capabilities", JSONB(), server_default="[]", nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("speed_score", sa.Float(), nullable=True),
        sa.Column("cost_score", sa.Float(), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("agent_capability", JSONB(), nullable=True),
        sa.CheckConstraint(
            "tier IN ('fast', 'medium', 'max', 'custom')",
            name="ck_models_tier_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'deprecated')",
            name="ck_models_status_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_models"),
        sa.UniqueConstraint("model_key", name="uq_models_model_key"),
    )

    op.create_table(
        "providers",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider_key", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("auth_types", JSONB(), nullable=False),
        sa.Column("supports_account_pool", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'maintenance')",
            name="ck_providers_status_closed_set",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_providers"),
        sa.UniqueConstraint("provider_key", name="uq_providers_provider_key"),
    )


def downgrade() -> None:
    op.drop_table("providers")
    op.drop_table("models")
