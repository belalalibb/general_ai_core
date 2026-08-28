"""In-memory role + skill registries (MVP Phase 6 slice 2, T-IMPL-026).

Spec anchors:

- 41 §45: Phase 6 delivers "system roles" and "local skills".
- 03 §6: Role / Skill entities (the registered records ARE the contracts).
- 03 §8 (verbatim, binds here): "Role can request capabilities but cannot
  grant permissions. Skill can require Tools but cannot bypass Tool
  permissions." — the registries expose requested capabilities/tools as
  DATA ONLY; nothing here grants, authorizes, or executes anything.
- 14 §1: "Skill is not automatically a Tool. Tool is never trusted by
  default." — a tool_enabled skill is selectable, but its tools remain
  inert manifest data in Phase 6 (R044 boundary (a)).
- 31 §10 posture mirrored: registries may LOAD non-active roles/skills
  (drafts, pipeline states, disabled) for inspection, but selection admits
  ONLY status=active — and for skills, ONLY source=local (R044 boundary
  (b): imported skills are representable, not selectable, until the import
  machinery lands in a later phase).

LOADABLE-NOT-EXECUTABLE / LOADABLE-NOT-SELECTABLE is the whole point:
``get_*`` answers "what is registered" (inspection); ``select_*`` answers
"may this be used" (admission) and denies with a NAMED reason (11 §14
explainability posture — same as router exclusions).

Everything here is in-memory and hermetic: durable persistence binds these
registries through infrastructure/ (ADR-0002) in a later task.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.roles import Role, RoleStatus
from core.contracts.skills import Skill, SkillSource, SkillStatus
from core.roles.errors import (
    DuplicateRegistration,
    ManifestMismatch,
    RoleNotRegistered,
    RoleNotSelectable,
    SkillNotRegistered,
    SkillNotSelectable,
)


class RoleRegistry:
    """System-role registry: load anything valid, select only active."""

    def __init__(self) -> None:
        self._roles: dict[UUID, Role] = {}

    def register(self, role: Role) -> None:
        """Register a role. Duplicate ids are rejected, never overwritten."""
        if role.id in self._roles:
            raise DuplicateRegistration("role", role.id)
        self._roles[role.id] = role

    def get(self, role_id: UUID) -> Role:
        """Inspection: return the registered role regardless of status."""
        role = self._roles.get(role_id)
        if role is None:
            raise RoleNotRegistered(role_id)
        return role

    def select(self, role_id: UUID) -> Role:
        """Admission: return the role ONLY if it is selectable (active).

        Draft/disabled roles deny with a named reason (loadable-but-not-
        selectable). Unknown ids raise RoleNotRegistered — absent and
        not-selectable are DIFFERENT answers, both explainable.
        """
        role = self.get(role_id)
        if role.status is not RoleStatus.ACTIVE:
            raise RoleNotSelectable(role_id, role.status.value)
        return role

    def list_selectable(self) -> list[Role]:
        """All roles that would pass :meth:`select`, name-ordered."""
        return sorted(
            (r for r in self._roles.values() if r.status is RoleStatus.ACTIVE),
            key=lambda r: r.name,
        )

    def list_all(self) -> list[Role]:
        """Inspection view: every registered role, name-ordered."""
        return sorted(self._roles.values(), key=lambda r: r.name)


#: Entity/manifest fields that must agree (Skill contract consistency rule).
_MANIFEST_AGREEMENT_FIELDS = ("name", "version", "type", "source", "status")


class SkillRegistry:
    """Local-skill registry: load anything consistent, select active+local."""

    def __init__(self) -> None:
        self._skills: dict[UUID, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill after entity/manifest consistency validation.

        The Skill contract records the rule: entity fields are authoritative
        and the embedded manifest must AGREE — a divergent pair is rejected
        (ManifestMismatch names the first divergent field) rather than
        silently preferring one side.
        """
        for field in _MANIFEST_AGREEMENT_FIELDS:
            if getattr(skill, field) != getattr(skill.manifest, field):
                raise ManifestMismatch(skill.id, field)
        if skill.id in self._skills:
            raise DuplicateRegistration("skill", skill.id)
        self._skills[skill.id] = skill

    def get(self, skill_id: UUID) -> Skill:
        """Inspection: return the registered skill regardless of status."""
        skill = self._skills.get(skill_id)
        if skill is None:
            raise SkillNotRegistered(skill_id)
        return skill

    def replace(self, skill: Skill) -> None:
        """Explicit re-registration (admin update path, 21 §4 Skills row).

        Mirrors ``ModelRegistry.replace`` (T-IMPL-068): the admin control
        plane publishes status changes (enable/disable) by replacing the
        stored frozen record — selection sees the change immediately
        through ``select``/``list_selectable``; no parallel admin copy.
        The unknown-id case refuses loudly (an admin cannot 'replace' a
        skill that was never registered); manifest agreement is re-checked
        exactly as on first registration.
        """
        if skill.id not in self._skills:
            raise SkillNotRegistered(skill.id)
        for field in _MANIFEST_AGREEMENT_FIELDS:
            if getattr(skill, field) != getattr(skill.manifest, field):
                raise ManifestMismatch(skill.id, field)
        self._skills[skill.id] = skill

    def select(self, skill_id: UUID) -> Skill:
        """Admission: return the skill ONLY if selectable.

        Two named denial reasons (checked in this order):

        - status != active — the 14 §3 pipeline states and ``disabled`` are
          loadable-but-not-selectable (31 §10 mirror).
        - source != local — R044 boundary (b): Phase 6 activates LOCAL
          skills only; an imported skill (even status=active) is
          representable data, not a selectable capability, until the import
          machinery (scan/validate/review) exists to have vouched for it.
        """
        skill = self.get(skill_id)
        if skill.status is not SkillStatus.ACTIVE:
            raise SkillNotSelectable(skill_id, f"status={skill.status.value}")
        if skill.source is not SkillSource.LOCAL:
            raise SkillNotSelectable(skill_id, f"source={skill.source.value}")
        return skill

    def list_selectable(self) -> list[Skill]:
        """All skills that would pass :meth:`select`, name-ordered."""
        return sorted(
            (
                s
                for s in self._skills.values()
                if s.status is SkillStatus.ACTIVE and s.source is SkillSource.LOCAL
            ),
            key=lambda s: s.name,
        )

    def list_all(self) -> list[Skill]:
        """Inspection view: every registered skill, name-ordered."""
        return sorted(self._skills.values(), key=lambda s: s.name)
