"""R191 — General Agent over the EXISTING engine (RED first).

Proof areas (Part 23): A (agent consumes an ExecutionStrategy), E (skills
compose into a strategy), F (skill requirements → capability requirements),
K (per-stage model), L (AUTO), M (provider-native agent stays distinct),
N (a capability is consumed by the General Agent, not a second engine),
O (skills/templates cannot bypass the registry admission rule), plus G/I/J
re-driven THROUGH the agent on the unchanged router/executor/board.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from core.agent.general import (
    AgentCapability,
    AgentCapabilityRegistry,
    CapabilityContribution,
    GeneralAgent,
    GeneralAgentRequest,
    PlanRefused,
)
from core.contracts.agent_template import (
    AgentPlan,
    StrategyTemplate,
    TemplateOrigin,
    TemplateOverride,
)
from core.contracts.domain import AgentCapabilityType
from core.contracts.execution_strategy import ExecutionStrategySpec, StageKind, StrategyStage
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.provider import ProviderErrorCategory
from core.contracts.skills import SkillStatus
from core.execution.strategy import StrategyExecutor
from core.execution.templates import TemplateRegistry
from core.roles.registry import SkillRegistry
from tests.api.test_node_mapping_and_auto_skills import make_skill
from tests.routing.test_r188_capacity_signals import World, _err, _run


def _skills(*ids: str, caps: dict[str, list[str]] | None = None) -> SkillRegistry:
    registry = SkillRegistry()
    for sid in ids:
        skill = make_skill(manifest_id=sid)
        if caps and sid in caps:
            manifest = skill.manifest.model_copy(update={"capabilities": caps[sid]})
            skill = skill.model_copy(update={"manifest": manifest})
        registry.register(skill)
    return registry


def _template(strategy: ExecutionStrategySpec | None = None) -> StrategyTemplate:
    return StrategyTemplate(
        id="coding.default",
        version="1",
        name="plan/code/review",
        origin=TemplateOrigin.SYSTEM,
        strategy=strategy
        or ExecutionStrategySpec(
            mode="custom",
            stages=[
                StrategyStage(key="plan", role="planner"),
                StrategyStage(key="code", role="coder", depends_on=["plan"]),
                StrategyStage(
                    key="review", kind=StageKind.REVIEW, role="reviewer", depends_on=["code"]
                ),
            ],
        ),
        skills=["testing"],
    )


def _world(*providers: str) -> World:
    """R188 capacity World (N providers, ONE shared model, ONE signal board)."""
    return World(list(providers))


def _agent(
    world: World,
    *,
    skills: SkillRegistry | None = None,
    templates: TemplateRegistry | None = None,
    capabilities: AgentCapabilityRegistry | None = None,
) -> GeneralAgent:
    templates = templates or TemplateRegistry()
    executor = StrategyExecutor(
        router=world.router,
        execution=world.service,
        templates=templates.as_strategy_mapping(),
        clock=lambda: world.now,
    )
    return GeneralAgent(
        executor=executor,
        templates=templates,
        skills=skills or SkillRegistry(),
        capabilities=capabilities or AgentCapabilityRegistry(),
    )


def _execute(agent: GeneralAgent, plan: AgentPlan) -> Any:
    return _run(
        agent.execute(plan, tenant_id=uuid4(), user_id=uuid4(), ask="go", request_hash="h")
    )


def _model_only() -> ExplicitModelPolicy:
    return ExplicitModelPolicy(type="explicit_model", model_id="shared-model")


class TestPlanning:
    def test_a_agent_consumes_a_custom_execution_strategy_verbatim(self) -> None:
        spec = ExecutionStrategySpec(mode="custom", stages=[StrategyStage(key="only")])
        plan = _agent(_world("alpha")).plan(GeneralAgentRequest(ask="do", strategy=spec))
        assert plan.strategy == spec
        assert plan.template_ref is None and plan.capability is None

    def test_l_auto_when_nothing_is_specified(self) -> None:
        plan = _agent(_world("alpha")).plan(GeneralAgentRequest(ask="hello"))
        assert plan.strategy.mode == "custom"  # resolved bounded AUTO plan
        assert [s.key for s in plan.strategy.stages] == ["generate"]
        assert plan.strategy.stages[0].model_policy is None  # Router AUTO

    def test_b_template_ref_produces_the_template_strategy(self) -> None:
        templates = TemplateRegistry()
        templates.register(_template())
        plan = _agent(_world("alpha"), templates=templates, skills=_skills("testing")).plan(
            GeneralAgentRequest(ask="build", template_ref="coding.default")
        )
        assert plan.template_ref == "coding.default@1"
        assert [s.key for s in plan.strategy.stages] == ["plan", "code", "review"]
        assert plan.skills == ["testing"]

    def test_k_per_stage_model_override_is_recorded(self) -> None:
        templates = TemplateRegistry()
        templates.register(_template())
        a = ExplicitModelPolicy(type="explicit_model", model_id="model-a")
        b = ExplicitModelPolicy(type="explicit_model", model_id="model-b")
        plan = _agent(_world("alpha"), templates=templates, skills=_skills("testing")).plan(
            GeneralAgentRequest(
                ask="build",
                template_ref="coding.default",
                override=TemplateOverride(stage_model_policies={"plan": a, "code": b}),
            )
        )
        assert plan.strategy.stages[0].model_policy == a
        assert plan.strategy.stages[1].model_policy == b
        assert plan.strategy.stages[2].model_policy is None
        assert sorted(r.stage_key or "" for r in plan.overrides_applied) == ["code", "plan"]

    def test_e_f_skills_compose_and_their_requirements_flow_into_capabilities(self) -> None:
        skills = _skills(
            "security", "fastapi", caps={"security": ["chat", "audit"], "fastapi": ["chat"]}
        )
        plan = _agent(_world("alpha"), skills=skills).plan(
            GeneralAgentRequest(ask="harden the api", skills=["security", "fastapi"])
        )
        assert plan.skills == ["security", "fastapi"]
        assert plan.required_capabilities == ["audit", "chat"]  # union, sorted, deduplicated

    def test_o_unknown_or_non_selectable_skill_is_refused_like_v1_execute(self) -> None:
        skills = SkillRegistry()
        skills.register(make_skill(manifest_id="draft", status=SkillStatus.IMPORTED))
        with pytest.raises(PlanRefused, match="not selectable: ghost"):
            _agent(_world("alpha"), skills=skills).plan(
                GeneralAgentRequest(ask="x", skills=["ghost"])
            )
        with pytest.raises(PlanRefused, match="not selectable: draft"):
            _agent(_world("alpha"), skills=skills).plan(
                GeneralAgentRequest(ask="x", skills=["draft"])
            )
        templates = TemplateRegistry()
        templates.register(_template().model_copy(update={"skills": ["ghost"]}))
        with pytest.raises(PlanRefused, match="not selectable: ghost"):
            _agent(_world("alpha"), templates=templates, skills=skills).plan(
                GeneralAgentRequest(ask="x", template_ref="coding.default")
            )

    def test_two_structures_at_once_is_refused(self) -> None:
        with pytest.raises(PlanRefused, match="exactly one"):
            _agent(_world("alpha")).plan(
                GeneralAgentRequest(
                    ask="x",
                    template_ref="coding.default",
                    strategy=ExecutionStrategySpec(mode="custom", stages=[StrategyStage(key="s")]),
                )
            )


class TestCapabilities:
    def test_n_capability_is_discovered_and_composed_not_a_second_engine(self) -> None:
        world = _world("alpha")
        seen: list[GeneralAgentRequest] = []

        def contribute(request: GeneralAgentRequest) -> CapabilityContribution:
            seen.append(request)
            return CapabilityContribution(
                strategy=ExecutionStrategySpec(
                    mode="custom", stages=[StrategyStage(key="inventory", role="inspector")]
                ),
                skills=["fastapi"],
                # "reasoning" is what the R188 World model declares; the requirement
                # therefore flows into routing AND is satisfiable (Part 10 posture).
                required_capabilities=["reasoning"],
                notes=["capability chose a one-stage plan"],
            )

        caps = AgentCapabilityRegistry()
        caps.register(
            AgentCapability(name="demo", version="1", description="demo", contribute=contribute)
        )
        assert [c.name for c in caps.list()] == ["demo"]
        agent = _agent(world, capabilities=caps, skills=_skills("fastapi"))
        plan = agent.plan(GeneralAgentRequest(ask="inspect", capability="demo"))
        assert plan.capability == "demo@1"
        assert [s.key for s in plan.strategy.stages] == ["inventory"]
        assert plan.skills == ["fastapi"] and seen and seen[0].ask == "inspect"
        assert plan.required_capabilities == ["reasoning"]  # contribution -> routing filter
        report = _execute(agent, plan)  # through the ONE executor
        assert report.succeeded and len(report.outcomes) == 1
        with pytest.raises(PlanRefused, match="unknown capability"):
            agent.plan(GeneralAgentRequest(ask="x", capability="nope"))


class TestRoutingThroughTheAgent:
    def test_g_i_same_model_many_providers_and_same_model_fallback(self) -> None:
        world = _world("alpha", "beta")
        agent = _agent(world)
        plan = agent.plan(
            GeneralAgentRequest(
                ask="go",
                strategy=ExecutionStrategySpec(
                    mode="custom", stages=[StrategyStage(key="s", model_policy=_model_only())]
                ),
            )
        )
        first = world.route(_model_only())
        world.adapters[first.selected.provider_id].script = [
            _err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=30_000)
        ]
        report = _execute(agent, plan)
        assert report.succeeded
        attempts = report.outcomes[0].report.nodes[0].attempts
        assert len(attempts) == 2
        assert attempts[0].candidate.provider_id != attempts[1].candidate.provider_id
        assert {a.candidate.model_id for a in attempts} == {world.model.id}  # SAME model
        # H: the cooling provider is excluded on the next decision — per-binding signal.
        second = world.route(_model_only())
        assert second.selected.provider_id == attempts[1].candidate.provider_id
        assert second.fallback_candidates == []

    def test_j_explicit_provider_plus_model_stays_precise(self) -> None:
        world = _world("alpha", "beta")
        agent = _agent(world)
        plan = agent.plan(
            GeneralAgentRequest(
                ask="go",
                strategy=ExecutionStrategySpec(
                    mode="custom",
                    stages=[
                        StrategyStage(
                            key="s",
                            model_policy=ExplicitModelPolicy(
                                type="explicit_model", model_id="shared-model", provider_id="beta"
                            ),
                        )
                    ],
                ),
            )
        )
        report = _execute(agent, plan)
        attempt = report.outcomes[0].report.nodes[0].attempts[0]
        assert attempt.candidate.provider_id == world.by_key["beta"].id


class TestProviderNativeAgentStaysDistinct:
    def test_m_general_agent_is_not_a_provider_agent_type(self) -> None:
        assert "general" not in {t.value for t in AgentCapabilityType}
        assert GeneralAgent.PLATFORM_AUTHORITY == (
            "authorization",
            "capability_firewall",
            "tool_approval",
            "tenant_isolation",
            "usage",
            "routing",
            "evaluation",
            "audit",
            "final_response_policy",
        )
