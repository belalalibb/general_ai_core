"""Role/skill registry errors (closed, minimal set for the MVP registries).

Same explainable-denial posture as core/providers (30 §7 / 11 §14): a
selection that fails does so with a NAMED reason, never a silent skip.
"""

from __future__ import annotations


class RegistryError(Exception):
    """Base class for role/skill registry failures."""


class RoleNotRegistered(RegistryError):
    """No role with this id in the registry."""

    def __init__(self, role_id: object) -> None:
        super().__init__(f"role not registered: {role_id}")


class SkillNotRegistered(RegistryError):
    """No skill with this id in the registry."""

    def __init__(self, skill_id: object) -> None:
        super().__init__(f"skill not registered: {skill_id}")


class DuplicateRegistration(RegistryError):
    """An entity with this id is already registered (re-register explicitly)."""

    def __init__(self, kind: str, entity_id: object) -> None:
        super().__init__(f"{kind} already registered: {entity_id}")


class RoleNotSelectable(RegistryError):
    """The role exists but is not selectable (status != active).

    Loadable-but-not-selectable posture (31 §10 mirror): the registry can
    hold drafts and disabled roles, but selection denies them with this
    named reason.
    """

    def __init__(self, role_id: object, status: str) -> None:
        self.status = status
        super().__init__(f"role not selectable: {role_id} (status={status})")


class SkillNotSelectable(RegistryError):
    """The skill exists but is not selectable.

    Raised for status != active AND for source != local in Phase 6
    (R044 boundary (a): local skills only — imported skills are
    representable but not selectable until the import machinery lands).
    """

    def __init__(self, skill_id: object, reason: str) -> None:
        self.reason = reason
        super().__init__(f"skill not selectable: {skill_id} ({reason})")


class ManifestMismatch(RegistryError):
    """Skill entity fields and its embedded manifest disagree.

    Consistency rule from the Skill contract: the registry rejects divergent
    pairs (name/version/type/source/status must agree) rather than silently
    preferring one side.
    """

    def __init__(self, skill_id: object, field: str) -> None:
        self.field = field
        super().__init__(f"skill manifest mismatch: {skill_id} (field={field})")
