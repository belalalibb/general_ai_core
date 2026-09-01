"""provider_model_bindings + gateway registrations (Gap 1; ADR-0011)

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-01

The PRV-4 record in infrastructure/db/repositories/catalog.py explicitly
reserved provider_model_bindings for "the runtime binding-registration
surface that needs it (a justified migration then, not a speculative one
now)". That surface is now real: the admin provider-onboarding path
(31 §19, core/providers/onboarding.py) writes providers/models/bindings
through the Postgres catalogs so an onboarded provider survives restart.
This migration is that justified slice — the ProviderModelBinding entity
(03 §4, core/contracts/domain.py) mapped field-for-field — plus the
ADR-0011 per-provider gateway registration record.

Design decisions (mirroring migration 0005's models/providers posture):

- PLATFORM catalogs — no tenant_id (03 §4 defines none; tenant
  visibility is admin policy DATA, 21 §10).
- provider_model_bindings composite PK (provider_id, model_id): the
  contract binds ONE model to ONE provider; the same model may bind to
  multiple providers, so neither column alone is a key. FKs RESTRICT —
  no silent orphaning.
- ``availability`` CHECK-constrained to the closed BindingAvailability
  set; NO permissive server_default — a row states its availability
  explicitly (same closed-set discipline as every 0001+ table).
- limits_metadata/capabilities JSONB server_default '{}' — the empty
  object parses to contract defaults that grant NOTHING
  (deny-by-default, 41 §1 rule 9). agent_runtime nullable: None =
  undeclared (30 §4.3 — unknown must NOT read as supported).
- provider_gateway_registrations (ADR-0011): one JSONB ``definition``
  row per canonical-gateway provider — the OPERATOR's declared surface
  plus OPAQUE route_token_ref/credential_ref and credential_mode, from
  which the composition root rebuilds the RemoteGatewayAdapter at
  startup (executability across restart). Canonical-gateway providers
  ONLY (DECISION 2): foreign/native-API providers still require an
  adapter/shim and never get a row here.
- NO credential material anywhere (20 §5): secret values live in the
  Secret Manager; these rows carry opaque references only.

Downgrade fully reverses (40 §8.2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AVAILABILITY_VALUES = "'available', 'unavailable', 'degraded'"


def upgrade() -> None:
    op.create_table(
        "provider_model_bindings",
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider_model_name", sa.String(512), nullable=False),
        sa.Column("endpoint_ref", sa.String(512), nullable=True),
        sa.Column("availability", sa.String(32), nullable=False),
        sa.Column("limits_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("capabilities", JSONB, nullable=False, server_default="{}"),
        sa.Column("agent_runtime", JSONB, nullable=True),
        sa.PrimaryKeyConstraint(
            "provider_id", "model_id", name="pk_provider_model_bindings"
        ),
        sa.CheckConstraint(
            f"availability IN ({_AVAILABILITY_VALUES})",
            name="availability_closed_set",
        ),
    )
    op.create_table(
        "provider_gateway_registrations",
        sa.Column(
            "provider_id",
            UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("definition", JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_gateway_registrations")
    op.drop_table("provider_model_bindings")
