"""Skill resolver — 41 §16 chain (T-IMPL-062).

Spec anchor (41 §16, verbatim):

    Task + Role + Context → Candidate Skills → Compatibility → Ranking
    → Selected Skills

Recorded derivations (the chain is named without an interface — every
mapping below is derived from EXISTING contracts, nothing invented silently):

- INPUTS map to existing contracts: Task = TaskAnalysis (11 §3 — carries
  ``capabilities_required``); Role = RoleProfile (41 §15 — carries
  ``preferred_skills``, the profile-only field built for exactly this
  resolver, and the underlying Role name); Context = ComposedContext
  (13 §5 output) accepted as OPTIONAL DATA — no doc defines a context→skill
  rule, so context participates in no gate or rank yet (recorded honestly,
  41 §49; the parameter keeps the §16 seam so a documented rule can bind
  later without changing the chain shape).
- CANDIDATE SKILLS = the registry's selectable set (``list_selectable``:
  active + local). The resolver NEVER widens admission — a pipeline state,
  disabled, or imported skill is not a candidate; the registry rule is the
  single admission authority (deny-by-default preserved).
- COMPATIBILITY is a GATE with named exclusions (11 §14 posture — the same
  explainability the router and composer use). Two documented checks:
  role compatibility (14 §2 ``runtime.compatible_roles``: an EMPTY list
  means unrestricted — the 14 §2 example lists specific roles, no doc says
  empty forbids all, and deny-by-default here would make every listless
  skill dead data; a NON-empty list must contain the role name) and
  capability coverage (a skill is compatible with the task when it
  declares every capability the task requires; task with no required
  capabilities gates nothing). Both refusals are RECORDED per skill, never
  silent skips.
- RANKING is deterministic DATA, not learned scoring: preferred skills
  first (41 §15 ``preferred_skills`` is "advisory ranking input" — its
  recorded purpose), then broader task-capability coverage, then name for
  a stable total order. No doc defines skill scoring weights; inventing a
  scoring model would fabricate architecture.
- SELECTED SKILLS = the ranked list, optionally truncated by caller
  ``limit`` (no doc fixes a selection count). Selection is still DATA —
  a selected skill's tools remain inert (03 §8; enforced upstream).
- The resolver is PURE: reads the registry, computes, returns a decision
  object carrying selections AND named exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts.context import ComposedContext
from core.contracts.role_profile import RoleProfile
from core.contracts.routing import TaskAnalysis
from core.contracts.skills import Skill
from core.roles.registry import SkillRegistry


@dataclass(frozen=True)
class SkillExclusion:
    """One candidate refused by the compatibility gate — reason named."""

    skill_name: str
    reason: str


@dataclass(frozen=True)
class SkillResolution:
    """Resolver output: selected skills + named exclusions (11 §14)."""

    selected: tuple[Skill, ...] = ()
    excluded: tuple[SkillExclusion, ...] = ()


class SkillResolver:
    """The 41 §16 resolver chain over the EXISTING SkillRegistry."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        *,
        task: TaskAnalysis,
        role: RoleProfile,
        context: ComposedContext | None = None,
        limit: int | None = None,
    ) -> SkillResolution:
        """Task + Role + Context → Candidates → Compatibility → Ranking → Selected.

        ``context`` is accepted per the §16 chain but participates in no
        gate or rank yet — no doc defines a context→skill rule (recorded).
        ``limit`` (if given) must be >= 1; it truncates the ranked list.
        """
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1 when given")
        del context  # §16 seam only — no documented rule binds it yet.

        # Candidate Skills: the registry's admission rule, unwidened.
        candidates = self._registry.list_selectable()

        # Compatibility: gate with named exclusions.
        role_name = role.role.name
        required = set(task.capabilities_required)
        compatible: list[Skill] = []
        excluded: list[SkillExclusion] = []
        for skill in candidates:
            compat_roles = skill.manifest.runtime.compatible_roles
            if compat_roles and role_name not in compat_roles:
                excluded.append(
                    SkillExclusion(
                        skill_name=skill.name,
                        reason=f"role_incompatible:{role_name}",
                    )
                )
                continue
            missing = required - set(skill.manifest.capabilities)
            if missing:
                excluded.append(
                    SkillExclusion(
                        skill_name=skill.name,
                        reason="capabilities_missing:" + ",".join(sorted(missing)),
                    )
                )
                continue
            compatible.append(skill)

        # Ranking: preferred first, broader coverage next, name for stability.
        preferred = set(role.preferred_skills)

        def rank_key(skill: Skill) -> tuple[int, int, str]:
            is_preferred = 0 if skill.name in preferred else 1
            coverage = len(set(skill.manifest.capabilities) & required)
            return (is_preferred, -coverage, skill.name)

        ranked = sorted(compatible, key=rank_key)

        # Selected Skills: the ranked list, caller-truncatable.
        selected = tuple(ranked[:limit] if limit is not None else ranked)
        return SkillResolution(selected=selected, excluded=tuple(excluded))
