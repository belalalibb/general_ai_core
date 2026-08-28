"""Role profile layer — 41 §15 (FINAL Phase 12), distinct from the 03 §6 entity.

Contract authority and layering (recorded):

- 03 §6 defines the Role ENTITY (persisted record, migration 0003) —
  carried verbatim in :mod:`core.contracts.roles` and NOT modified here.
- 41 §15 defines the role PROFILE — a seven-item view: identity /
  objective / required capabilities / preferred skills / behavior
  policies / output contract / runtime override. Five of the seven map
  onto entity fields; ``preferred skills`` and ``runtime override``
  appear ONLY in 41 §15 (and the 41 §50 matrix places "custom roles +
  runtime override" in the FINAL column — this phase). Per the standing
  per-authority rule the two layers are kept side by side, never merged:
  the entity stays field-for-field, the profile WRAPS it (same posture
  as the Phase 9 graph-spec vs record-entity split).

Recorded derivations (the docs name the items but define no shapes):

- ``preferred_skills`` — skill NAME references (strings), mirroring how
  14 §2 references roles from the other direction
  (``runtime.compatible_roles`` is a list of role-name strings). A
  preference is advisory ranking input for the Phase 13 skill resolver
  ("Role" is a resolver input, 41 §16); it never grants or activates a
  skill by itself.
- ``runtime_override`` — an override applied AT INVOCATION TIME, never
  persisted (that is the literal reading of "runtime"). Its surface is
  restricted to the entity's two opaque policy knobs —
  ``behavior_policies`` and ``output_contract`` — because they are the
  only behavior surfaces the entity defines. An override deliberately
  CANNOT touch scope, status, or ``capabilities_requested``: 41 §15
  "a Custom Role never grants permissions" extends to runtime — an
  override that could add capability requests would be a runtime
  escalation channel. The restriction is structural (fields simply do
  not exist on the override contract; ``extra="forbid"`` rejects them).
- Merge semantics — key-level shallow overlay (override key wins,
  otherwise base). The policy fields are opaque JSON (03 §6); a deep
  merge would invent structure inside values no spec defines.
"""

from __future__ import annotations

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject, JsonValue
from core.contracts.roles import Role


class RoleRuntimeOverride(ContractModel):
    """41 §15 ``runtime override`` — invocation-scoped, never persisted.

    Only the two opaque policy surfaces may be overlaid; capability
    requests, scope, and status are structurally out of reach.
    """

    behavior_policies: JsonObject = Field(default_factory=dict)
    output_contract: JsonObject = Field(default_factory=dict)


class RoleProfile(ContractModel):
    """41 §15 role profile — the seven items over the 03 §6 entity.

    ``role`` carries identity / objective / required capabilities /
    behavior policies / output contract; ``preferred_skills`` and
    ``runtime_override`` are the two profile-only items.
    """

    role: Role
    preferred_skills: list[BoundedStr] = Field(default_factory=list)
    runtime_override: RoleRuntimeOverride | None = None

    # --- the five entity-backed profile items (41 §15 names, derived) -----

    @property
    def identity(self) -> str:
        """41 §15 ``identity`` — the entity's name@version (scope-qualified)."""
        return f"{self.role.scope.value}:{self.role.name}@{self.role.version}"

    @property
    def objective(self) -> str:
        return self.role.objective

    @property
    def required_capabilities(self) -> list[str]:
        """41 §15 ``required capabilities`` = the entity's REQUESTS (03 §8).

        Never a grant — grants live only in the Capability Firewall.
        """
        return list(self.role.capabilities_requested)

    # --- effective policies (base overlaid by the runtime override) -------

    def effective_behavior_policies(self) -> dict[str, JsonValue]:
        """Key-level overlay: override wins per key, base otherwise."""
        merged: dict[str, JsonValue] = dict(self.role.behavior_policies)
        if self.runtime_override is not None:
            merged.update(self.runtime_override.behavior_policies)
        return merged

    def effective_output_contract(self) -> dict[str, JsonValue]:
        """Key-level overlay: override wins per key, base otherwise."""
        merged: dict[str, JsonValue] = dict(self.role.output_contract)
        if self.runtime_override is not None:
            merged.update(self.runtime_override.output_contract)
        return merged
