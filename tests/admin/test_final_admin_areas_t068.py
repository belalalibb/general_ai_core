"""FINAL Phase 19 admin widening — Skills/Tools areas (T-IMPL-068).

Contract authority: 41 §22 (Phase 19 module list + config lifecycle +
security invariant), 21 §4 control matrix rows "Skills: import, approve,
disable / Cannot Break: scan/review requirement" and "Tools: enable,
permissions, approval rules / Cannot Break: capability firewall",
21 §9 required admin tests, 14 §3 (import pipeline order), 14 §1 (tool
never trusted by default), 41 §50 FINAL column "all modules + config
lifecycle".

Recorded scope (module docstrings in core/contracts/admin.py +
core/admin/service.py): active areas widen to Skills + Tools (the two
areas whose CONTROLLED machinery exists — Phase 13/14 registries);
Learning/Security/Evaluation/Observability rows stay INERT (their 21 §4
verbs have no bindable machinery — activating them would fake control,
41 §49). ``active_areas`` is injectable DATA (T-IMPL-064 pattern);
default stays MVP so every pre-existing composition is untouched.

21 §9 exit mapping for the new areas:

    config draft validation      -> TestValidationNewAreas
    publish creates version      -> test_skill_publish_creates_area_version
    rollback restores previous   -> TestRollbackNewAreas
    invalid policy rejected      -> unknown-id + pipeline-skip tests
    security invariant cannot be
        disabled                 -> test_enable_cannot_skip_import_pipeline
                                    (scan/review requirement structural)
    admin action audited         -> test_skill_publish_lands_audit_event

Hermetic: in-memory registries/audit only.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.admin import AdminConfigService, InactiveAdminArea
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    ACTION_AREA,
    FINAL_ACTIVE_ADMIN_AREAS,
    MVP_ACTIVE_ADMIN_AREAS,
    AdminAction,
    AdminArea,
    ConfigChange,
    ConfigLifecycleState,
)
from core.contracts.audit import AuditEventType
from core.contracts.routing import ScoringWeights
from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillSource,
    SkillStatus,
    SkillType,
)
from core.contracts.tools import ApprovalRequirement, Tool, ToolLocation, ToolStatus
from core.providers import ModelRegistry, ProviderRegistry
from core.roles.registry import SkillRegistry
from core.tools.registry import ToolRegistry
from core.usage import InMemoryUsageAccounting

TENANT = uuid4()
ACTOR = uuid4()


def make_skill(status: SkillStatus = SkillStatus.ACTIVE) -> Skill:
    name = f"skill_{uuid4().hex[:8]}"
    return Skill(
        id=uuid4(),
        name=name,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        manifest=SkillManifest(
            id=name,
            name=name,
            version="1.0.0",
            type=SkillType.INSTRUCTION,
            source=SkillSource.LOCAL,
            status=status,
        ),
        status=status,
    )


def make_tool(status: ToolStatus = ToolStatus.ACTIVE) -> Tool:
    return Tool(
        id=uuid4(),
        name=f"tool_{uuid4().hex[:8]}",
        version="1.0.0",
        location=ToolLocation.SERVER,
        permissions=["repo.read"],
        approval_policy={"repo.read": ApprovalRequirement.NONE},
        status=status,
    )


class _Weights:
    def __init__(self) -> None:
        self._weights = ScoringWeights()

    @property
    def default_weights(self) -> ScoringWeights:
        return self._weights

    def set_default_weights(self, weights: ScoringWeights) -> None:
        self._weights = weights


class World:
    def __init__(
        self,
        *,
        active_areas: frozenset[AdminArea] = FINAL_ACTIVE_ADMIN_AREAS,
        bind_skills: bool = True,
        bind_tools: bool = True,
    ) -> None:
        self.skills = SkillRegistry()
        self.tools = ToolRegistry()
        self.audit = InMemoryAuditLog()
        self.service = AdminConfigService(
            providers=ProviderRegistry(),
            models=ModelRegistry(),
            usage=InMemoryUsageAccounting(),
            routing=_Weights(),
            audit_log=self.audit,
            skills=self.skills if bind_skills else None,
            tools=self.tools if bind_tools else None,
            active_areas=active_areas,
        )

    def publish(self, action: AdminAction, payload: dict[str, object]) -> ConfigChange:
        change = self.service.draft(
            tenant_id=TENANT, actor_id=ACTOR, action=action, payload=payload
        )
        self.service.validate(TENANT, change.id)
        self.service.preview(TENANT, change.id)
        return self.service.publish(TENANT, change.id)


# --- activation boundary (T-IMPL-064 pattern) ---------------------------------------


class TestActivationBoundary:
    def test_final_set_is_mvp_plus_skills_tools(self) -> None:
        assert FINAL_ACTIVE_ADMIN_AREAS == MVP_ACTIVE_ADMIN_AREAS | {
            AdminArea.SKILLS,
            AdminArea.TOOLS,
        }

    def test_default_service_still_denies_skill_and_tool_areas(self) -> None:
        """MVP default unchanged: pre-existing compositions untouched."""
        world = World(active_areas=MVP_ACTIVE_ADMIN_AREAS)
        for action in (AdminAction.ENABLE_SKILL, AdminAction.DISABLE_TOOL):
            with pytest.raises(InactiveAdminArea):
                world.service.draft(tenant_id=TENANT, actor_id=ACTOR, action=action, payload={})

    def test_inert_areas_stay_inert_under_final_set(self) -> None:
        """Learning/Security/etc have NO actions — structurally inert."""
        final_action_areas = {ACTION_AREA[a] for a in AdminAction}
        assert final_action_areas == FINAL_ACTIVE_ADMIN_AREAS
        for area in (
            AdminArea.LEARNING,
            AdminArea.SECURITY,
            AdminArea.EVALUATION,
            AdminArea.OBSERVABILITY,
        ):
            assert area not in final_action_areas


# --- config draft validation (21 §9) ---------------------------------------------------


class TestValidationNewAreas:
    def test_unknown_skill_rejected(self) -> None:
        world = World()
        change = world.service.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_SKILL,
            payload={"skill_id": str(uuid4())},
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED
        assert "not registered" in (result.validation_result or "")

    def test_unknown_tool_rejected(self) -> None:
        world = World()
        change = world.service.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.ENABLE_TOOL,
            payload={"tool_id": str(uuid4())},
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED

    def test_non_uuid_payload_rejected(self) -> None:
        world = World()
        change = world.service.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_TOOL,
            payload={"tool_id": "not-a-uuid"},
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED
        assert "not a UUID" in (result.validation_result or "")

    def test_unbound_registry_seam_fails_validation_loudly(self) -> None:
        """An active area whose machinery is absent cannot publish (41 §49)."""
        world = World(bind_skills=False)
        change = world.service.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.ENABLE_SKILL,
            payload={"skill_id": str(uuid4())},
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED
        assert "seam is not bound" in (result.validation_result or "")

    def test_enable_cannot_skip_import_pipeline(self) -> None:
        """21 §4 'Cannot Break: scan/review requirement' — structural."""
        world = World()
        for status in (
            SkillStatus.IMPORTED,
            SkillStatus.SCANNED,
            SkillStatus.VALIDATED,
            SkillStatus.REVIEWED,
        ):
            skill = make_skill(status)
            world.skills.register(skill)
            change = world.service.draft(
                tenant_id=TENANT,
                actor_id=ACTOR,
                action=AdminAction.ENABLE_SKILL,
                payload={"skill_id": str(skill.id)},
            )
            result = world.service.validate(TENANT, change.id)
            assert result.state is ConfigLifecycleState.REJECTED
            assert "cannot skip" in (result.validation_result or "")

    def test_approved_skill_may_be_enabled(self) -> None:
        world = World()
        skill = make_skill(SkillStatus.APPROVED)
        world.skills.register(skill)
        world.publish(AdminAction.ENABLE_SKILL, {"skill_id": str(skill.id)})
        assert world.skills.get(skill.id).status is SkillStatus.ACTIVE


# --- publish reaches the live registries (no parallel state) ----------------------------


class TestPublishNewAreas:
    def test_disable_skill_removes_from_selectable_set(self) -> None:
        world = World()
        skill = make_skill(SkillStatus.ACTIVE)
        world.skills.register(skill)
        assert world.skills.list_selectable()
        world.publish(AdminAction.DISABLE_SKILL, {"skill_id": str(skill.id)})
        assert world.skills.list_selectable() == []
        # Entity + manifest advanced together (registry agreement rule).
        stored = world.skills.get(skill.id)
        assert stored.status is SkillStatus.DISABLED
        assert stored.manifest.status is SkillStatus.DISABLED

    def test_disable_tool_refused_by_selection(self) -> None:
        world = World()
        tool = make_tool(ToolStatus.ACTIVE)
        world.tools.register(tool)
        world.publish(AdminAction.DISABLE_TOOL, {"tool_id": str(tool.id)})
        assert world.tools.get(tool.id).status is ToolStatus.DISABLED
        assert world.tools.list_selectable() == []

    def test_enable_tool_restores_admissibility(self) -> None:
        world = World()
        tool = make_tool(ToolStatus.DISABLED)
        world.tools.register(tool)
        world.publish(AdminAction.ENABLE_TOOL, {"tool_id": str(tool.id)})
        assert world.tools.select(tool.id).status is ToolStatus.ACTIVE

    def test_skill_publish_creates_area_version(self) -> None:
        world = World()
        skill = make_skill(SkillStatus.ACTIVE)
        world.skills.register(skill)
        published = world.publish(AdminAction.DISABLE_SKILL, {"skill_id": str(skill.id)})
        assert published.published_version == "skills-v1"

    def test_skill_publish_lands_audit_event(self) -> None:
        world = World()
        skill = make_skill(SkillStatus.ACTIVE)
        world.skills.register(skill)
        world.publish(AdminAction.DISABLE_SKILL, {"skill_id": str(skill.id)})
        events = world.audit.read(TENANT)
        assert any(e.event_type is AuditEventType.ADMIN_CONFIG_PUBLISHED for e in events)


# --- rollback restores previous version (21 §9) -----------------------------------------


class TestRollbackNewAreas:
    def test_rollback_restores_skill_status(self) -> None:
        world = World()
        skill = make_skill(SkillStatus.ACTIVE)
        world.skills.register(skill)
        published = world.publish(AdminAction.DISABLE_SKILL, {"skill_id": str(skill.id)})
        assert world.skills.get(skill.id).status is SkillStatus.DISABLED
        world.service.rollback(TENANT, published.id)
        restored = world.skills.get(skill.id)
        assert restored.status is SkillStatus.ACTIVE
        assert restored.manifest.status is SkillStatus.ACTIVE

    def test_rollback_restores_tool_status(self) -> None:
        world = World()
        tool = make_tool(ToolStatus.ACTIVE)
        world.tools.register(tool)
        published = world.publish(AdminAction.DISABLE_TOOL, {"tool_id": str(tool.id)})
        world.service.rollback(TENANT, published.id)
        assert world.tools.get(tool.id).status is ToolStatus.ACTIVE


# --- registry replace guards -------------------------------------------------------------


class TestRegistryReplace:
    def test_skill_replace_unknown_id_refuses(self) -> None:
        from core.roles.errors import SkillNotRegistered

        registry = SkillRegistry()
        with pytest.raises(SkillNotRegistered):
            registry.replace(make_skill())

    def test_skill_replace_rechecks_manifest_agreement(self) -> None:
        from core.roles.errors import ManifestMismatch

        registry = SkillRegistry()
        skill = make_skill(SkillStatus.ACTIVE)
        registry.register(skill)
        divergent = skill.model_copy(update={"status": SkillStatus.DISABLED})
        with pytest.raises(ManifestMismatch):
            registry.replace(divergent)  # manifest still says active

    def test_tool_replace_unknown_id_refuses(self) -> None:
        from core.tools.errors import ToolNotRegistered

        registry = ToolRegistry()
        with pytest.raises(ToolNotRegistered):
            registry.replace(make_tool())
