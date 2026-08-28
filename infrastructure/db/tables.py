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
  nullable (optional future scope, 03 §2). ``tenants.plan_id`` -> plans.id
  (the FK landed with the plans migration 0002, exactly as the original
  phase-order note recorded).
- ``plans`` (FINAL Phase 3, 41 §6) maps ``core/contracts/plan.py``. It is
  a PLATFORM catalog — deliberately NOT tenant-scoped (no tenant_id; the
  tenant side of the relation is ``tenants.plan_id``, 20 §6 applies to
  tenant-scoped tables only). ``name`` is unique — it is the ``plan:``
  configuration lookup key (21 §5). ``limits``/``entitlements``/
  ``model_control`` are JSONB with server_default ``{}``: an empty object
  parses to the contract defaults, which grant NOTHING (deny-by-default,
  41 §1 rule 9) — the DB default can never grant more than the contract
  default.
- ``roles`` (FINAL Phase 3, 41 §6) maps ``core/contracts/roles.py`` — the
  03 §6 Role ENTITY (agent prompt role, NOT an RBAC role — distinction
  recorded in core/contracts/security.py). PLATFORM catalog: the 03 §6
  ``scope`` field (system|tenant|user|project) is the role's APPLICABILITY
  dimension, part of the entity itself — not a tenant-ownership column, so
  no tenant_id (20 §6 applies to tenant-scoped tables). (name, version)
  unique — the registry lists by name; versions coexist. Closed sets
  (RoleScope/RoleStatus) via CHECK constraints from the contract enums.
- ``permissions`` (FINAL Phase 3, 41 §6) maps
  ``core/contracts/permission.py``. PLATFORM catalog (20 §4: catalogs are
  admin-configurable; per-tenant grants are firewall policy DATA, not
  catalog rows) — no tenant_id. ``key`` unique = the 20 §4 dotted
  identifier. ``approval`` server_default 'always' — the DB default is the
  MOST RESTRICTIVE value, matching the contract default (deny-by-default,
  41 §1 rule 9 + 14 §8).
- ``skills`` (FINAL Phase 3, 41 §6 "skills metadata") maps
  ``core/contracts/skills.py`` — the 03 §6 Skill entity field-for-field.
  METADATA ONLY per §6: provenance/manifest are stored as JSONB catalog
  data (the contract binds their shapes to 14 §2/§3 at the boundary);
  skill CONTENT/artifacts belong to object storage, not this table.
  PLATFORM catalog — no tenant_id (03 §6 defines none). (name, version)
  unique — versions coexist, same posture as roles. Closed sets
  (SkillType/SkillSource/SkillStatus incl. the 14 §3 seven-state import
  lifecycle) via CHECK constraints from the contract enums; ``status`` has
  NO permissive server_default — a row must state its lifecycle stage
  explicitly (14 §9 forbids implicit activation).
- ``models`` / ``providers`` (FINAL Phase 3, 41 §6) map the 03 §4 entities
  in ``core/contracts/domain.py``. PLATFORM catalogs — no tenant_id (03 §4
  defines none; tenant visibility is admin policy DATA, 21 §10).
  ``model_key`` / ``provider_key`` unique — the registry lookup keys.
  List/nested contract fields (modalities, capabilities, auth_types,
  agent_capability) are stored as JSONB — the contract validates their
  shapes at the boundary; agent_capability nullable (None = undeclared,
  30 §4.3: unknown must NOT read as supported — no permissive default).
  Scores/context_window nullable — unset means unscored, never invented.
  NO credential-value column anywhere: Credential VALUES live in the
  Secret Manager (41 §6 verbatim); the Credential entity's
  ``credential_ref`` is an opaque reference and its storage row arrives
  with the secret-manager binding slice, not here.
- ``conversations`` / ``messages`` (FINAL Phase 3, 41 §6) map the 03 §3
  entities in ``core/contracts/conversation.py``. conversations is
  TENANT-SCOPED: tenant_id FK + index (20 §6) — the first Phase 3 slice
  where that posture applies (the catalogs above are platform-scope).
  messages carries NO tenant_id BY SPEC (03 §3 defines none) — tenant
  isolation flows through the conversation_id FK to its tenant-scoped
  parent (ondelete RESTRICT; conversation_id indexed for retrieval and
  because 20 §6 isolation checks resolve through it). ``attachments``
  JSONB default '[]' — attachment ROWS are references; large artifacts
  live in object storage per 41 §6, never inline. ``content`` is Text
  (03 §3 ``text/json``; the contract bounds it at 200k).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from core.contracts.conversation import ConversationStatus, MessageRole
from core.contracts.domain import ModelStatus, ModelTier, ProviderStatus
from core.contracts.identity import TenantStatus, TenantType, UserStatus
from core.contracts.roles import RoleScope, RoleStatus
from core.contracts.skills import SkillSource, SkillStatus, SkillType
from core.contracts.tools import ApprovalRequirement

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


plans = Table(
    "plans",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(512), nullable=False, unique=True),
    Column("limits", JSONB, nullable=False, server_default="{}"),
    Column("entitlements", JSONB, nullable=False, server_default="{}"),
    Column("model_control", JSONB, nullable=False, server_default="{}"),
)

tenants = Table(
    "tenants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("type", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column(
        "plan_id",
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    ),
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

roles = Table(
    "roles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("scope", String(32), nullable=False),
    Column("name", String(512), nullable=False),
    Column("version", String(512), nullable=False),
    Column("objective", Text, nullable=False),
    Column("behavior_policies", JSONB, nullable=False, server_default="{}"),
    Column("output_contract", JSONB, nullable=False, server_default="{}"),
    Column("status", String(32), nullable=False),
    Column("capabilities_requested", JSONB, nullable=False, server_default="[]"),
    CheckConstraint(f"scope IN ({_enum_values(RoleScope)})", name="scope_closed_set"),
    CheckConstraint(f"status IN ({_enum_values(RoleStatus)})", name="status_closed_set"),
    UniqueConstraint("name", "version", name="uq_roles_name_version"),
)

permissions = Table(
    "permissions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("key", String(512), nullable=False, unique=True),
    Column("approval", String(32), nullable=False, server_default="always"),
    CheckConstraint(
        f"approval IN ({_enum_values(ApprovalRequirement)})",
        name="approval_closed_set",
    ),
)

skills = Table(
    "skills",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("version", String(512), nullable=False),
    Column("type", String(32), nullable=False),
    Column("source", String(32), nullable=False),
    Column("provenance", JSONB, nullable=False, server_default="{}"),
    Column("manifest", JSONB, nullable=False),
    Column("status", String(32), nullable=False),
    CheckConstraint(f"type IN ({_enum_values(SkillType)})", name="type_closed_set"),
    CheckConstraint(f"source IN ({_enum_values(SkillSource)})", name="source_closed_set"),
    CheckConstraint(f"status IN ({_enum_values(SkillStatus)})", name="status_closed_set"),
    UniqueConstraint("name", "version", name="uq_skills_name_version"),
)

models = Table(
    "models",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("model_key", String(512), nullable=False, unique=True),
    Column("display_name", String(512), nullable=False),
    Column("tier", String(32), nullable=False),
    Column("modalities", JSONB, nullable=False),
    Column("capabilities", JSONB, nullable=False, server_default="[]"),
    Column("context_window", Integer, nullable=True),
    Column("quality_score", Float, nullable=True),
    Column("speed_score", Float, nullable=True),
    Column("cost_score", Float, nullable=True),
    Column("reliability_score", Float, nullable=True),
    Column("status", String(32), nullable=False),
    Column("agent_capability", JSONB, nullable=True),
    CheckConstraint(f"tier IN ({_enum_values(ModelTier)})", name="tier_closed_set"),
    CheckConstraint(f"status IN ({_enum_values(ModelStatus)})", name="status_closed_set"),
)

providers = Table(
    "providers",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("provider_key", String(512), nullable=False, unique=True),
    Column("display_name", String(512), nullable=False),
    Column("status", String(32), nullable=False),
    Column("auth_types", JSONB, nullable=False),
    Column("supports_account_pool", Boolean, nullable=False),
    CheckConstraint(f"status IN ({_enum_values(ProviderStatus)})", name="status_closed_set"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "project_id",
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("title", String(512), nullable=False),
    Column("status", String(32), nullable=False),
    CheckConstraint(
        f"status IN ({_enum_values(ConversationStatus)})", name="status_closed_set"
    ),
    Index("ix_conversations_tenant_id", "tenant_id"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "conversation_id",
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("role", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("attachments", JSONB, nullable=False, server_default="[]"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    CheckConstraint(f"role IN ({_enum_values(MessageRole)})", name="role_closed_set"),
    Index("ix_messages_conversation_id", "conversation_id"),
)
