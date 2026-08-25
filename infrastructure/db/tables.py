"""Identity/tenancy table metadata — maps core/contracts/identity.py 1:1.

Authority:

- Entity shape: ``core/contracts/identity.py`` (carried from 03 §2
  field-for-field). Tables map those contracts; they do not redefine truth
  (40 §2.1). Column names match contract field names exactly.
- Tenant isolation: every tenant-scoped table carries ``tenant_id`` and an
  index on it (20 §6: "Every tenant-scoped table must include tenant_id").
- Closed sets (UserStatus/TenantType/TenantStatus) are stored as short
  strings validated by CHECK constraints built from the contract enums —
  the enum in core stays the single source of the value set; a DB-native
  ENUM type would create a second, migration-heavy definition of the same
  closed set.

Design decisions (recorded):

- SQLAlchemy Core ``Table`` objects (not ORM declarative classes): the
  repository layer converts rows <-> Pydantic contracts at the boundary
  (ADR-0002 Decision: "Core-expression style preferred over heavy ORM
  features"). No mapped classes are needed for that.
- Timestamps are ``TIMESTAMP(timezone=True)`` — contracts use aware
  datetimes (``utc_now``).
- ``users.email`` is unique per the identity service's registration rule
  (duplicate email -> RegistrationError). Uniqueness is global, matching
  the in-memory service semantics (one account per email address).
- No password/hash column here: credential material is NOT part of the
  identity contracts (20 §5). The account-credential table arrives with the
  real identity binding in a later slice, designed against the hasher port.
- FKs: users/workspaces/projects -> tenants.id; projects.workspace_id is
  nullable (optional future scope, 03 §2). ``tenants.plan_id`` is a plain
  UUID (no FK) — the Plan entity is not yet contracted; the FK lands with
  the plans migration in phase order.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from core.contracts.identity import TenantStatus, TenantType, UserStatus

# Naming convention -> deterministic constraint names -> reviewable,
# reversible autogenerate diffs (Alembic best practice).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enum_values(enum_cls: type) -> str:
    """SQL literal list from a core StrEnum — core stays the value authority."""
    return ", ".join(f"'{member.value}'" for member in enum_cls)  # type: ignore[attr-defined]


tenants = Table(
    "tenants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("type", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("plan_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(f"type IN ({_enum_values(TenantType)})", name="type_closed_set"),
    CheckConstraint(f"status IN ({_enum_values(TenantStatus)})", name="status_closed_set"),
)

users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("email", String(512), nullable=False, unique=True),
    Column("email_verified", Boolean, nullable=False, server_default="false"),
    Column("preferred_language", String(512), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    CheckConstraint(f"status IN ({_enum_values(UserStatus)})", name="status_closed_set"),
    Index("ix_users_tenant_id", "tenant_id"),
)

workspaces = Table(
    "workspaces",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("name", String(512), nullable=False),
    Index("ix_workspaces_tenant_id", "tenant_id"),
)

projects = Table(
    "projects",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "workspace_id",
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("name", String(512), nullable=False),
    Column("metadata", JSONB, nullable=False, server_default="{}"),
    Index("ix_projects_tenant_id", "tenant_id"),
)
