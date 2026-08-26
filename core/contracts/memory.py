"""MemoryItem contract (MVP Phase 6, 41 §45 "basic user preferences").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §3
  (MemoryItem entity, field-for-field).
- docs/ai_orchestration_pack/final_docs_v3/13_MEMORY_AND_CONTEXT.md §3
  (memory item contract: adds ``sensitivity``), §4 (scope priority).

Field reconciliation (recorded, not silent): 03 §3 defines the entity
(id/tenant_id/user_id/scope/key/value/source/confidence/evidence_count/
last_seen/expires_at) and 13 §3 shows the same item carrying ``sensitivity``.
Both authorities are honored: this model is the 03 §3 entity plus 13 §3's
``sensitivity`` — nothing dropped, nothing invented.

Scope priority (13 §4, verbatim)::

    Conversation > Project > Workspace > User > Tenant > Global

``SCOPE_PRIORITY`` encodes that ordering as data so the context composer
(later slice) resolves conflicts from the spec, not from ad-hoc code.
03 §3 also lists a ``role`` scope; it participates in storage/retrieval but
is NOT in the 13 §4 conflict chain — role-scoped memory is selected by role
relevance (13 §9), never by scope-priority comparison. Recorded here so the
omission is a decision, not an accident.

Memory safety (13 §7, binds NOW): "storing secrets as memory" is forbidden —
the store port rejects secret-looking keys/values at the boundary.
``Memory ≠ Training Data`` and ``User Preference ≠ Truth`` (13 §2).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonValue

# --- Closed sets ----------------------------------------------------------------


class MemoryScope(StrEnum):
    """Memory scope (03 §3 MemoryItem) — closed set, verbatim."""

    GLOBAL = "global"
    TENANT = "tenant"
    WORKSPACE = "workspace"
    PROJECT = "project"
    CONVERSATION = "conversation"
    ROLE = "role"


class MemorySensitivity(StrEnum):
    """Sensitivity classification (13 §3 example: ``"sensitivity": "low"``).

    Closed low/medium/high ladder; retrieval treats HIGH as excluded unless
    policy explicitly allows it (13 §9 "security classification").
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Conflict-resolution ordering (13 §4, verbatim; most specific FIRST).
# ROLE is deliberately absent — see module docstring.
SCOPE_PRIORITY: tuple[MemoryScope, ...] = (
    MemoryScope.CONVERSATION,
    MemoryScope.PROJECT,
    MemoryScope.WORKSPACE,
    MemoryScope.TENANT,
    MemoryScope.GLOBAL,
)
# 13 §4 chain includes User between Workspace and Tenant; MemoryItem models
# "user" as user_id ownership rather than a scope value (03 §3 has no "user"
# scope). A user-owned item outranks tenant-shared items of the same scope
# tier — encoded by the composer using (scope, user_id) together.


class MemoryItem(ContractModel):
    """Memory item (03 §3 entity + 13 §3 ``sensitivity``, field-for-field).

    ``value`` is JSON per 03 §3 (``value: json``) — any JSON value, e.g. the
    13 §3 example ``"ar"`` (a bare string) or a structured object.
    ``confidence`` is bounded to [0, 1] (13 §3 example 0.92); low-confidence
    memory is excluded from context unless marked uncertain (13 §9).
    ``user_id`` is None for tenant-shared memory; set for user-owned memory
    ("using one user's memory for another" is forbidden, 13 §7).
    """

    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None
    scope: MemoryScope
    key: BoundedStr
    value: JsonValue
    source: BoundedStr
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    last_seen: datetime
    expires_at: datetime | None = None
    sensitivity: MemorySensitivity = MemorySensitivity.LOW
