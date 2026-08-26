"""Role contract (MVP Phase 6, 41 §45 "system roles").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §6
  (Role entity, field-for-field).
- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §8
  (relationship rule, verbatim): "Role can request capabilities but cannot
  grant permissions."

Naming note (recorded): this is the 03 §6 Role ENTITY (a persona/system-role
definition with an objective and behavior policies). It is distinct from
:class:`core.contracts.conversation.MessageRole`, the chat-turn role — the
name collision comes from the spec, and both are kept verbatim.

Permission posture (03 §8, binds at the contract level): a Role carries
``capabilities_requested`` as DATA. Nothing in this contract, the registry,
or the composer treats a requested capability as a granted permission —
grants happen only in the (later-phase) Capability Firewall, never here.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Closed sets ----------------------------------------------------------------


class RoleScope(StrEnum):
    """Role scope (03 §6) — closed set, verbatim."""

    SYSTEM = "system"
    TENANT = "tenant"
    USER = "user"
    PROJECT = "project"


class RoleStatus(StrEnum):
    """Role lifecycle status (03 §6) — closed set, verbatim.

    Only ``active`` roles are selectable (registry rule); ``draft`` and
    ``disabled`` roles are loadable-but-not-selectable, mirroring the
    31 §10 template posture.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


# --- Entity ----------------------------------------------------------------------


class Role(ContractModel):
    """Role entity — 03 §6 field-for-field.

    ``behavior_policies`` and ``output_contract`` are opaque JSON per the
    entity definition (03 §6: ``json``); their interpretation belongs to the
    context composer / execution layers, not the contract.

    ``capabilities_requested`` records what the role ASKS for (03 §8);
    it is never a grant. Defensive default: empty list (a role that requests
    nothing is valid; an implicit request is not).
    """

    id: UUID
    scope: RoleScope
    name: BoundedStr
    version: BoundedStr
    objective: str = Field(min_length=1, max_length=20_000)
    behavior_policies: JsonObject = Field(default_factory=dict)
    output_contract: JsonObject = Field(default_factory=dict)
    status: RoleStatus
    capabilities_requested: list[BoundedStr] = Field(default_factory=list)
