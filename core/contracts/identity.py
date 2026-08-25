"""Identity / Tenancy contracts — User / Tenant / Workspace / Project.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md
§2 (Identity / Tenancy). Carried exactly — no state value added, renamed, or
dropped.

Notes carried from spec:

- Workspace / Project are "Optional future scopes" (03 §2) — the entities are
  contract-defined now so tenant-scoped references stay typed, but no runtime
  behavior is implied in Phase 2.
- Every tenant-scoped entity carries ``tenant_id`` (20 §6 tenant isolation
  rule: "Every tenant-scoped table must include tenant_id where applicable").
- MVP Phase 2 (41 §41) delivers "personal tenant": ``TenantType.PERSONAL`` is
  the registration-time default at the service layer; the contract itself
  stays neutral and closed.

Security posture: this module contains identity *shape* only — no password,
hash, token, or secret material appears in any contract object
(20 §5 secrets rules). Credential/session secret handling belongs to the
identity service and secret-store ports, never to contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Closed sets (03 §2, verbatim) --------------------------------------------


class UserStatus(StrEnum):
    """User status (03 §2 User entity) — closed set, verbatim."""

    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class TenantType(StrEnum):
    """Tenant type (03 §2 Tenant entity) — closed set, verbatim."""

    PERSONAL = "personal"
    ORGANIZATION = "organization"


class TenantStatus(StrEnum):
    """Tenant status (03 §2 Tenant entity) — closed set, verbatim."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


# --- Entities (03 §2, field-for-field) ----------------------------------------


class User(ContractModel):
    """User entity (03 §2, field-for-field).

    ``email_verified`` defaults to False: 41 §41 requires an explicit email
    verification step before a user is verified (deny-by-default posture).
    """

    id: UUID
    tenant_id: UUID
    email: BoundedStr
    email_verified: bool = False
    preferred_language: BoundedStr
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class Tenant(ContractModel):
    """Tenant entity (03 §2, field-for-field)."""

    id: UUID
    name: BoundedStr
    type: TenantType
    status: TenantStatus
    plan_id: UUID


class Workspace(ContractModel):
    """Workspace entity (03 §2, field-for-field) — optional future scope."""

    id: UUID
    tenant_id: UUID
    name: BoundedStr


class Project(ContractModel):
    """Project entity (03 §2, field-for-field) — optional future scope."""

    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None = None
    name: BoundedStr
    metadata: JsonObject
