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
- ``memory_items`` (FINAL Phase 3, 41 §6 "memory") maps the 03 §3
  MemoryItem in ``core/contracts/memory.py`` (incl. the 13 §3
  ``sensitivity`` field the contract already carries). TENANT-SCOPED:
  tenant_id FK + index (20 §6). The memory port's upsert semantics
  (keyed by tenant/user/scope/key) are enforced by a UNIQUE constraint
  with NULLS NOT DISTINCT — user_id NULL (tenant-shared memory) must
  collide like a value, or the upsert key would silently duplicate.
- ``memory_embeddings`` (41 §6 "pgvector: semantic retrieval") is
  INFRASTRUCTURE RETRIEVAL DATA, not a contract entity — 03 §3 defines
  NO embedding field on MemoryItem, so the vector lives in a SEPARATE
  table (schema must not invent contract state; recorded). One row per
  memory item (PK = FK, ondelete CASCADE — derived data must never
  outlive its source; an orphan embedding would be a semantic leak).
  ``embedding`` is a dimension-UNCONSTRAINED pgvector column: the
  embedding model (and thus dimension) is admin configuration — fixing a
  dimension or creating an ANN index here would invent a decision the
  specs leave to configuration (recorded; the index arrives when the
  embedding model is pinned). ``model_key`` records WHICH embedding model
  produced the vector — required so retrieval never compares vectors
  from incompatible spaces (13 §9 retrieval integrity; recorded
  derivation, not contract invention).
- ``executions`` / ``execution_nodes`` (FINAL Phase 3, 41 §6
  "executions") map the 03 §5 entities in
  ``core/contracts/execution.py`` field-for-field. executions is
  TENANT-SCOPED: tenant_id FK + index (20 §6). The 10 §10 idempotency
  rule ("Same tenant + same idempotency key should not create duplicate
  executions") is enforced by UNIQUE (tenant_id, idempotency_key) with
  the Postgres DEFAULT null treatment (NULLS DISTINCT) — the key is
  nullable BY SPEC and executions WITHOUT a key must never collide
  (the opposite posture from the memory upsert key; recorded).
  execution_nodes carries NO tenant_id BY SPEC (03 §5 defines none) —
  isolation flows through the execution_id FK to its tenant-scoped
  parent (RESTRICT; indexed — same recorded posture as messages).
  UNIQUE (execution_id, node_key): the execution service already
  rejects duplicate node_keys per run (InvalidPipeline) — the DB
  enforces the same invariant. ``input_ref``/``output_ref`` are JSONB:
  the spec says ``string/json`` and the contract is
  ``BoundedStr | JsonObject`` — a bare JSON string is valid JSONB, so
  ONE column carries both shapes without inventing a discriminator
  (recorded). ``cost_snapshot``/``error`` JSONB per spec ``json``.
  Timestamps are the entity's own audit fields (created_at NOT NULL,
  completed_at nullable — running executions have no completion).
- ``usage_ledger`` (FINAL Phase 3, 41 §6 "usage") maps the 03 §7
  UsageLedger in ``core/contracts/usage.py`` field-for-field.
  TENANT-SCOPED: tenant_id FK + index (20 §6). ONE ledger entry per
  execution — the usage port keys the ledger by execution_id
  (core/usage/memory.py) and a reservation resolves exactly once
  (ReservationAlreadyResolved) — so execution_id is UNIQUE + FK
  (RESTRICT: accounting records must never dangle). Deny-by-default in
  DB defaults: units_settled server_default '0' and modality_costs
  server_default '{}' equal the contract defaults — an unresolved entry
  claims NO settled consumption; ``status`` has NO server_default — the
  lifecycle stage must be explicit (same recorded posture as
  skills.status). units CHECKs >= 0 match the contract Field(ge=0).
- ``evaluations`` (FINAL Phase 3, 41 §6 "evaluations") maps
  EvaluationRecord in ``core/contracts/evaluation.py`` field-for-field.
  TENANT-SCOPED: tenant_id FK + index (20 §6) — the contract ITSELF
  carries tenant_id (recorded R049 storage-shape decision), so the pair
  matches bidirectionally with no schema-side addition. NO node_id
  column: R049 boundary (d) attaches evaluation at EXECUTION level in
  MVP (03 §8 'Evaluation belongs to Execution/Node' — node-level is
  representable later, never silently pre-built). execution_id FK
  RESTRICT + index; deliberately NOT unique — the contract permits
  multiple evaluations per execution and no spec forbids it (nothing
  invented). score/confidence are SEPARATE nullable [0,1] columns
  (22 §4 'never merge them into one number' — embodied in DDL exactly
  as in the contract); CHECKs allow NULL explicitly. ``graders`` JSONB
  server_default '[]' == contract default () — an evaluation that
  recorded no grader rows claims none. ``level`` has NO server_default
  — the verification level must be explicit (RAW is a real claim, not
  a fallback; same posture as skills.status/usage_ledger.status).
- ``learning_samples`` (FINAL Phase 3, 41 §6 "learning metadata" — the
  LAST §6 entity) maps LearningSample in ``core/contracts/learning.py``
  field-for-field (03 §7 yaml verbatim). tenant_id is NULLABLE BY SPEC
  (03 §7 ``uuid|null``): the honest recorded reading is "sample not
  attributed to a tenant" — no richer semantics invented. Attributed
  samples get the 20 §6 posture: FK + partial-value index (the index
  covers the column; NULLs are simply absent from tenant-filtered
  queries). source_execution_id FK RESTRICT + index — 22 §9 requires
  "source trace exists"; a dangling source would break training
  eligibility forensics. dataset_id is a PLAIN nullable UUID — NO
  Dataset table exists in the 41 §6 list, so there is NO FK target
  (03 §8: a sample enters Dataset only after eligibility+verification;
  the Dataset entity belongs to a later phase — never invented).
  Deny-by-default DB defaults equal the contract defaults:
  eligibility 'pending', sanitization_state 'pending',
  verification_level 'RAW' — a new row grants NOTHING toward the 22 §9
  training gate (this differs from level-must-be-explicit on
  evaluations: HERE the spec defines a semantically-safe zero state,
  and the contract defaults to it — DB == contract, recorded).
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
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
from core.contracts.evaluation import VerificationLevel
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.contracts.identity import TenantStatus, TenantType, UserStatus
from core.contracts.learning import LearningEligibility, SanitizationState
from core.contracts.memory import MemoryScope, MemorySensitivity
from core.contracts.roles import RoleScope, RoleStatus
from core.contracts.skills import SkillSource, SkillStatus, SkillType
from core.contracts.tools import ApprovalRequirement
from core.contracts.usage import UsageLedgerStatus

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

memory_items = Table(
    "memory_items",
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
        nullable=True,
    ),
    Column("scope", String(32), nullable=False),
    Column("key", String(512), nullable=False),
    Column("value", JSONB, nullable=False),
    Column("source", String(512), nullable=False),
    Column("confidence", Float, nullable=False),
    Column("evidence_count", Integer, nullable=False),
    Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("sensitivity", String(32), nullable=False, server_default="low"),
    CheckConstraint(f"scope IN ({_enum_values(MemoryScope)})", name="scope_closed_set"),
    CheckConstraint(
        f"sensitivity IN ({_enum_values(MemorySensitivity)})",
        name="sensitivity_closed_set",
    ),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_bounds"),
    CheckConstraint("evidence_count >= 0", name="evidence_count_nonnegative"),
    UniqueConstraint(
        "tenant_id",
        "user_id",
        "scope",
        "key",
        name="uq_memory_items_logical_key",
        postgresql_nulls_not_distinct=True,
    ),
    Index("ix_memory_items_tenant_id", "tenant_id"),
)

memory_embeddings = Table(
    "memory_embeddings",
    metadata,
    Column(
        "memory_item_id",
        UUID(as_uuid=True),
        ForeignKey("memory_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("model_key", String(512), nullable=False),
    Column("embedding", Vector(), nullable=False),
)

executions = Table(
    "executions",
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
        "conversation_id",
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("request_hash", String(512), nullable=False),
    Column("idempotency_key", String(512), nullable=True),
    Column("status", String(32), nullable=False),
    Column("strategy", String(32), nullable=False),
    Column("cost_snapshot", JSONB, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
    CheckConstraint(f"status IN ({_enum_values(ExecutionStatus)})", name="status_closed_set"),
    CheckConstraint(
        f"strategy IN ({_enum_values(ExecutionStrategy)})",
        name="strategy_closed_set",
    ),
    # 10 §10: same tenant + same idempotency key must not create duplicate
    # executions. Postgres DEFAULT null treatment (NULLS DISTINCT) is the
    # REQUIRED posture here: idempotency_key is nullable by spec, and
    # executions submitted WITHOUT a key must never collide with each other.
    UniqueConstraint("tenant_id", "idempotency_key", name="uq_executions_idempotency_key"),
    Index("ix_executions_tenant_id", "tenant_id"),
)

execution_nodes = Table(
    "execution_nodes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "execution_id",
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("node_key", String(512), nullable=False),
    Column("type", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    # 03 §5 "string/json": a bare JSON string is valid JSONB, so one column
    # carries both contract shapes (BoundedStr | JsonObject) — recorded.
    Column("input_ref", JSONB, nullable=False),
    Column("output_ref", JSONB, nullable=True),
    Column("retry_count", Integer, nullable=False),
    Column("error", JSONB, nullable=True),
    CheckConstraint(f"type IN ({_enum_values(ExecutionNodeType)})", name="type_closed_set"),
    CheckConstraint(
        f"status IN ({_enum_values(ExecutionNodeStatus)})",
        name="status_closed_set",
    ),
    CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
    # The execution service rejects duplicate node_keys per run
    # (InvalidPipeline) — the DB enforces the same invariant.
    UniqueConstraint("execution_id", "node_key", name="uq_execution_nodes_node_key"),
    Index("ix_execution_nodes_execution_id", "execution_id"),
)

usage_ledger = Table(
    "usage_ledger",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "execution_id",
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,  # one ledger entry per execution (core/usage/memory.py keying)
    ),
    Column("units_reserved", Float, nullable=False),
    Column("units_settled", Float, nullable=False, server_default="0"),
    Column("modality_costs", JSONB, nullable=False, server_default="{}"),
    Column("status", String(32), nullable=False),  # NO default — stage must be explicit
    CheckConstraint(
        f"status IN ({_enum_values(UsageLedgerStatus)})",
        name="status_closed_set",
    ),
    CheckConstraint("units_reserved >= 0", name="units_reserved_nonnegative"),
    CheckConstraint("units_settled >= 0", name="units_settled_nonnegative"),
    Index("ix_usage_ledger_tenant_id", "tenant_id"),
)

evaluations = Table(
    "evaluations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "execution_id",
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="RESTRICT"),
        nullable=False,
        # NOT unique — multiple evaluations per execution are permitted
        # by the contract; no spec forbids it (nothing invented).
    ),
    Column("level", String(32), nullable=False),  # NO default — level must be explicit
    # 22 §4: score and confidence stay SEPARATE nullable columns — never
    # merged into one number. NULL = no judgment recorded (RAW).
    Column("score", Float, nullable=True),
    Column("confidence", Float, nullable=True),
    Column("evidence_ref", String(512), nullable=True),
    Column("graders", JSONB, nullable=False, server_default="[]"),
    CheckConstraint(
        f"level IN ({_enum_values(VerificationLevel)})",
        name="level_closed_set",
    ),
    CheckConstraint(
        "score IS NULL OR (score >= 0 AND score <= 1)",
        name="score_bounds",
    ),
    CheckConstraint(
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
        name="confidence_bounds",
    ),
    Index("ix_evaluations_tenant_id", "tenant_id"),
    Index("ix_evaluations_execution_id", "execution_id"),
)

learning_samples = Table(
    "learning_samples",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_execution_id",
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True,  # BY SPEC (03 §7 uuid|null): unattributed samples exist
    ),
    Column("eligibility", String(32), nullable=False, server_default="pending"),
    Column(
        "sanitization_state",
        String(32),
        nullable=False,
        server_default="pending",
    ),
    Column("verification_level", String(32), nullable=False, server_default="RAW"),
    # PLAIN nullable UUID — no Dataset table exists in 41 §6 (recorded).
    Column("dataset_id", UUID(as_uuid=True), nullable=True),
    CheckConstraint(
        f"eligibility IN ({_enum_values(LearningEligibility)})",
        name="eligibility_closed_set",
    ),
    CheckConstraint(
        f"sanitization_state IN ({_enum_values(SanitizationState)})",
        name="sanitization_state_closed_set",
    ),
    CheckConstraint(
        f"verification_level IN ({_enum_values(VerificationLevel)})",
        name="verification_level_closed_set",
    ),
    Index("ix_learning_samples_tenant_id", "tenant_id"),
    Index("ix_learning_samples_source_execution_id", "source_execution_id"),
)
