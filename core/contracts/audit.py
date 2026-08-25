"""Audit contract — AuditEvent domain entity (MVP Phase 3, 41 §42 "basic audit logs").

Contract authority:

- 03_DOMAIN_MODEL.md §1 lists ``AuditEvent`` as a domain entity but defines
  no field schema — so the schema here is built *minimally* from the two
  places the specs do constrain auditing:
- 20_SECURITY_THREAT_MODEL.md §9 "Must audit" — carried verbatim as the
  closed :class:`AuditEventType` set (10 values, nothing added or dropped).
- 21_ADMIN_CONTROL_PLANE.md §8 "Every published config change records:
  who / what / previous version / new version / validation result /
  impact preview / timestamp / rollback target" — carried as
  :class:`AdminChangeRecord`, attached only when the event is an admin
  config publish/rollback.

Field-mapping notes (documented, not invented):

- ``who`` (21 §8)      -> ``actor_id`` on the event (the acting user/system id).
- ``what`` (21 §8)     -> ``what`` bounded string on AdminChangeRecord.
- ``timestamp`` (21 §8)-> the event's own ``occurred_at``.
- remaining 21 §8 fields map 1:1 on AdminChangeRecord.
- ``tenant_id``: every audit event is tenant-scoped (20 §6); the
  ``cross_tenant_access_denied`` event is recorded in the tenant whose
  boundary was probed.
- ``details``: open JsonObject for event-specific context. 20 §5 rule:
  secret values NEVER appear here — only opaque ``credential_ref`` handles.
  Structural enforcement of "no secret in an open JSON object" is
  impossible at the schema level; the rule is stated here, honoured by the
  services that emit events, and regression-guarded by tests + the repo
  secret scan.

Append-only posture: AuditEvent is immutable (frozen contract) and the
audit port exposes no update/delete surface — tamper-resistance by design.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject, utc_now

# --- Closed event set (20 §9 "Must audit", verbatim) ---------------------------


class AuditEventType(StrEnum):
    """Must-audit events (20 §9) — closed set, carried verbatim.

    ``login/logout`` and ``credential create/revoke`` are compound lines in
    the spec and expand to one value per action; ``admin config
    publish/rollback`` likewise.
    """

    LOGIN = "login"
    LOGOUT = "logout"
    CREDENTIAL_CREATED = "credential_created"
    CREDENTIAL_REVOKED = "credential_revoked"
    PROVIDER_ACCOUNT_USED = "provider_account_used"
    PERMISSION_DENIED = "permission_denied"
    TOOL_CALL = "tool_call"
    APPROVAL_DECISION = "approval_decision"
    ADMIN_CONFIG_PUBLISHED = "admin_config_published"
    ADMIN_CONFIG_ROLLED_BACK = "admin_config_rolled_back"
    SECURITY_POLICY_CHANGED = "security_policy_changed"
    TRAINING_DATASET_PROMOTED = "training_dataset_promoted"
    CROSS_TENANT_ACCESS_DENIED = "cross_tenant_access_denied"


# Event types that MUST carry an AdminChangeRecord (21 §8 applies to
# "every published config change").
ADMIN_CHANGE_EVENT_TYPES: frozenset[AuditEventType] = frozenset(
    {
        AuditEventType.ADMIN_CONFIG_PUBLISHED,
        AuditEventType.ADMIN_CONFIG_ROLLED_BACK,
    }
)


class AdminChangeRecord(ContractModel):
    """21 §8 admin-audit record — field-for-field from the spec list.

    ``who`` and ``timestamp`` live on the enclosing AuditEvent
    (``actor_id`` / ``occurred_at``); the remaining fields are here.
    """

    what: BoundedStr
    previous_version: BoundedStr
    new_version: BoundedStr
    validation_result: BoundedStr
    impact_preview: BoundedStr
    rollback_target: BoundedStr


class AuditEvent(ContractModel):
    """One immutable audit record (03 §1 entity; events per 20 §9).

    20 §5 rule restated: ``details`` must never contain secret values —
    opaque ``credential_ref`` handles only.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_type: AuditEventType
    actor_id: UUID | None = None  # None = system-initiated (e.g. policy job)
    occurred_at: datetime = Field(default_factory=utc_now)
    details: JsonObject = Field(default_factory=dict)
    admin_change: AdminChangeRecord | None = None
