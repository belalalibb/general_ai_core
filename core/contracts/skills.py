"""Skill contract + manifest (MVP Phase 6, 41 §45 "local skills").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §6
  (Skill entity, field-for-field).
- docs/ai_orchestration_pack/final_docs_v3/14_SKILLS_AND_TOOLS.md §1
  (definitions: "Skill is not automatically a Tool. Tool is never trusted
  by default."), §2 (skill manifest shape), §3 (import lifecycle states +
  provenance fields).
- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §8
  (relationship rule, verbatim): "Skill can require Tools but cannot bypass
  Tool permissions."

Scope boundaries carried from the R044 slicing decision (recorded, binding):

- (a) LOCAL skills only in Phase 6. Tools a skill requires are representable
  as manifest DATA (``requires_tools``) but are never executed here — tool
  execution and the Capability Firewall are NOT Phase 6.
- (b) The import PIPELINE (scan/validate/review machinery) is not built;
  the lifecycle states and provenance fields exist as contract data so that
  imported skills are representable, but Phase 6 registries only activate
  ``source=local`` skills.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Closed sets ----------------------------------------------------------------


class SkillType(StrEnum):
    """Skill type (03 §6) — closed set, verbatim."""

    INSTRUCTION = "instruction"
    WORKFLOW = "workflow"
    TOOL_ENABLED = "tool_enabled"


class SkillSource(StrEnum):
    """Skill source (03 §6) — closed set, verbatim."""

    LOCAL = "local"
    IMPORTED = "imported"


class SkillStatus(StrEnum):
    """Skill lifecycle status (03 §6 + 14 §3 import lifecycle) — closed set.

    The 14 §3 pipeline order is ``imported → scanned → validated → reviewed
    → approved → active`` (plus ``disabled``). Only ``active`` skills are
    selectable (registry rule); every other state is loadable-but-not-
    selectable, mirroring the 31 §10 template posture.
    """

    IMPORTED = "imported"
    SCANNED = "scanned"
    VALIDATED = "validated"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ACTIVE = "active"
    DISABLED = "disabled"


class SkillInvocation(StrEnum):
    """Who may invoke the skill (14 §2 ``runtime.invocation``) — closed set."""

    USER = "user"
    MODEL = "model"
    USER_OR_MODEL = "user_or_model"


#: 14 §3 pipeline order, encoded as data so review tooling and later import
#: machinery derive ordering from the spec, not ad-hoc comparisons.
#: ``disabled`` is a terminal administrative state outside the pipeline.
IMPORT_LIFECYCLE_ORDER: tuple[SkillStatus, ...] = (
    SkillStatus.IMPORTED,
    SkillStatus.SCANNED,
    SkillStatus.VALIDATED,
    SkillStatus.REVIEWED,
    SkillStatus.APPROVED,
    SkillStatus.ACTIVE,
)


# --- Manifest parts (14 §2) -------------------------------------------------------


class SkillToolRequirements(ContractModel):
    """``requires_tools`` block (14 §2): tool names as DATA, never grants.

    03 §8: "Skill can require Tools but cannot bypass Tool permissions" —
    listing a tool here neither authorizes nor executes it; the (later-phase)
    Capability Firewall decides.
    """

    required: list[BoundedStr] = Field(default_factory=list)
    optional: list[BoundedStr] = Field(default_factory=list)


class SkillRuntime(ContractModel):
    """``runtime`` block (14 §2): invocation mode + compatible roles."""

    invocation: SkillInvocation = SkillInvocation.USER_OR_MODEL
    compatible_roles: list[BoundedStr] = Field(default_factory=list)


class SkillManifest(ContractModel):
    """Skill manifest — 14 §2 shape, field-for-field.

    ``inputs_schema`` is ``None`` for schema-less skills (the 14 §2 example
    shows ``inputs.schema: null``); ``outputs_format`` is a format hint
    (e.g. ``markdown``). ``permissions_requested`` records what the skill
    ASKS for — a request, never a grant (same posture as Role, 03 §8).
    """

    id: BoundedStr
    name: BoundedStr
    version: BoundedStr
    type: SkillType
    source: SkillSource
    status: SkillStatus
    capabilities: list[BoundedStr] = Field(default_factory=list)
    inputs_schema: JsonObject | None = None
    outputs_format: BoundedStr | None = None
    requires_tools: SkillToolRequirements = Field(default_factory=SkillToolRequirements)
    permissions_requested: list[BoundedStr] = Field(default_factory=list)
    runtime: SkillRuntime = Field(default_factory=SkillRuntime)


class SkillProvenance(ContractModel):
    """Import provenance (14 §3): every imported skill records its origin.

    14 §3 verbatim: "External sources are references, not runtime
    dependencies. Every imported skill becomes a local version." All fields
    optional here because LOCAL skills have no import origin; the (later)
    import machinery enforces presence for ``source=imported``.
    """

    source_url: BoundedStr | None = None
    source_version: BoundedStr | None = None
    checksum: BoundedStr | None = None
    imported_at: datetime | None = None
    reviewed_by: BoundedStr | None = None
    local_version: BoundedStr | None = None


# --- Entity ----------------------------------------------------------------------


class Skill(ContractModel):
    """Skill entity — 03 §6 field-for-field.

    03 §6 types ``provenance`` and ``manifest`` as ``json``; this contract
    binds them to the 14 §2/§3 shapes (the spec's own manifest definition)
    so a Skill can never carry a manifest that does not validate.

    Consistency rule (recorded): the entity's name/version/type/source/status
    are the authoritative registry values; the embedded manifest must agree —
    the registry rejects divergent pairs rather than silently preferring one.
    """

    id: UUID
    name: BoundedStr
    version: BoundedStr
    type: SkillType
    source: SkillSource
    provenance: SkillProvenance = Field(default_factory=SkillProvenance)
    manifest: SkillManifest
    status: SkillStatus
