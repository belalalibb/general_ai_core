"""Tool contract + manifest (FINAL Phase 1 gap-fix: 41 §4 contract list "Tool").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §6
  (Tool entity, field-for-field) and §8 (relationship rules, verbatim):
  "Skill can require Tools but cannot bypass Tool permissions." /
  "Tool calls require Capability Firewall approval."
- docs/ai_orchestration_pack/final_docs_v3/14_SKILLS_AND_TOOLS.md §4
  (tool manifest shape), §5 (locations), §7 (capability-firewall check list),
  §9 (forbidden rules), §11 (provider-agent tool classification).
- docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
  §17 (Phase 14 tool contract field list: id / version / location /
  permissions / credentials / input schema / output schema / rate limits /
  sandbox policy / approval policy).

Scope boundary (contracts-first, 41 §4 — recorded, binding):

- DATA ONLY. No tool execution, no Capability Firewall wiring, no client
  runtime, no device trust — that machinery is FINAL Phase 14 (Tool Fabric).
  This module makes Tools *representable* so ``Skill.requires_tools`` names
  can later resolve against a real entity, per 03 §8.
- Security posture is encoded in the DATA DEFAULTS, not in behavior:
  permissions default to NONE granted, provider-agent tools default to the
  ``unknown_tool`` classification (which 14 §11 maps to DENY/disabled), and
  an unlisted permission's approval requirement resolves to the most
  restrictive value (41 §1 rule 9: unknown ⇒ DENY).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.domain import OwnerType

# --- Closed sets -------------------------------------------------------------------


class ToolLocation(StrEnum):
    """Where the tool runs (03 §6 / 14 §5) — closed set, verbatim."""

    SERVER = "server"
    CLIENT = "client"
    HYBRID = "hybrid"


class ToolStatus(StrEnum):
    """Tool lifecycle status (03 §6) — closed set, verbatim."""

    ACTIVE = "active"
    DISABLED = "disabled"


class ApprovalRequirement(StrEnum):
    """Per-permission approval requirement (14 §4 example values) — closed set."""

    NONE = "none"
    BEFORE_ACTION = "before_action"
    ALWAYS = "always"


class ProviderAgentToolClass(StrEnum):
    """Classification of provider-side agent tools (14 §11) — closed set."""

    PROVIDER_INTERNAL_TOOL = "provider_internal_tool"
    PLATFORM_TOOL = "platform_tool"
    HYBRID_TOOL = "hybrid_tool"
    UNKNOWN_TOOL = "unknown_tool"


#: 14 §11: "unknown provider-side tools default to DENY or disabled mode".
#: A provider-side tool that has not been explicitly classified is UNKNOWN.
DEFAULT_PROVIDER_AGENT_TOOL_CLASS: ProviderAgentToolClass = ProviderAgentToolClass.UNKNOWN_TOOL

#: 41 §1 rule 9 (unknown permissions/capabilities default to DENY): a
#: permission with no explicit approval_policy entry requires the MOST
#: restrictive approval. 14 §4's example lists only some permissions in
#: approval_policy — this constant defines what the absence means.
DEFAULT_APPROVAL_REQUIREMENT: ApprovalRequirement = ApprovalRequirement.ALWAYS

#: 14 §7 capability-firewall check list — ordered DATA (the enforcement
#: machinery is Phase 14; encoding the order here keeps later phases
#: spec-derived instead of ad-hoc, mirroring skills.IMPORT_LIFECYCLE_ORDER).
FIREWALL_CHECK_ORDER: tuple[str, ...] = (
    "identity",
    "tenant",
    "permission",
    "entitlement",
    "resource_ownership",
    "scope",
    "approval_policy",
    "tool_sandbox_policy",
    "rate_limit",
    "audit",
)


# --- Manifest parts (14 §4) --------------------------------------------------------


class ToolCredentialsSpec(ContractModel):
    """``credentials`` block (14 §4): which owner scopes may hold tool credentials.

    Owner values reuse the 03 §4 closed set (platform/tenant/user) — no
    duplicate enum. An empty list is a valid honest state: the tool accepts
    no credentials at all.
    """

    supported_owners: list[OwnerType] = Field(default_factory=list)


class ToolManifest(ContractModel):
    """Tool manifest (14 §4 shape + the 41 §17 field list, field-for-field).

    ``id`` here is the manifest's machine name (14 §4 example: ``github``),
    distinct from the stored :class:`Tool` entity's UUID — same split the
    provider manifest/domain entity pair already uses.
    """

    id: BoundedStr
    name: BoundedStr
    version: BoundedStr
    location: ToolLocation
    status: ToolStatus = ToolStatus.DISABLED
    # Deny-by-default: a manifest that declares nothing grants nothing.
    permissions: list[BoundedStr] = Field(default_factory=list)
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    credentials: ToolCredentialsSpec = Field(default_factory=ToolCredentialsSpec)
    approval_policy: dict[str, ApprovalRequirement] = Field(default_factory=dict)
    sandbox_policy: JsonObject = Field(default_factory=dict)
    # 41 §17 lists "rate limits" in the tool contract; shape is not further
    # specified in v3 → open JSON, absent by default (honest: no limit data).
    rate_limits: JsonObject | None = None

    @model_validator(mode="after")
    def _approval_policy_keys_must_be_declared_permissions(self) -> ToolManifest:
        """An approval entry for an undeclared permission is a contract error.

        14 §4's approval_policy keys are permissions of the same manifest;
        an entry that references a permission the tool never declared is
        either a typo or an attempt to smuggle an implicit grant — reject.
        """
        declared = set(self.permissions)
        unknown = [key for key in self.approval_policy if key not in declared]
        if unknown:
            msg = f"approval_policy references undeclared permissions: {sorted(unknown)}"
            raise ValueError(msg)
        return self

    def approval_for(self, permission: str) -> ApprovalRequirement:
        """Approval requirement for a DECLARED permission (data lookup only).

        Undeclared permission ⇒ raises ``KeyError`` — asking about a
        permission the tool does not have is a caller bug, never a silent
        default. A declared-but-unlisted permission resolves to
        :data:`DEFAULT_APPROVAL_REQUIREMENT` (deny-by-default).
        """
        if permission not in self.permissions:
            raise KeyError(permission)
        return self.approval_policy.get(permission, DEFAULT_APPROVAL_REQUIREMENT)


# --- Entity (03 §6) ----------------------------------------------------------------


class Tool(ContractModel):
    """Tool entity (03 §6, field-for-field).

    ``approval_policy`` is typed as the 14 §4 map (permission →
    :class:`ApprovalRequirement`) rather than open JSON: 03 §6 types the
    field ``json`` and 14 §4 defines that JSON's only specified shape —
    same narrowing the Skill contract applied to its manifest field.
    """

    id: UUID
    name: BoundedStr
    version: BoundedStr
    location: ToolLocation
    permissions: list[BoundedStr] = Field(default_factory=list)
    input_schema: JsonObject = Field(default_factory=dict)
    output_schema: JsonObject = Field(default_factory=dict)
    sandbox_policy: JsonObject = Field(default_factory=dict)
    approval_policy: dict[str, ApprovalRequirement] = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.DISABLED
