"""General Agent — capability discovery → skill composition → strategy → ONE executor (R191).

Authority: R191-DEC-01 (Parts 2–4, 7–9, 12–13, 20).

Recorded decisions:
- The General Agent is an ORCHESTRATOR over existing Core machinery: it
  produces an :class:`AgentPlan` (data) and hands the plan's
  :class:`ExecutionStrategySpec` to the EXISTING :class:`StrategyExecutor`,
  which routes every stage through the ONE router and runs it through the
  ONE execution service. No second engine, router, registry or memory.
- Extensibility pattern (Part 3): Define → Contract → Register → Discover →
  Compose → Execute. A *capability* is a registered contributor that turns a
  request into a :class:`CapabilityContribution` (a strategy and/or skills
  and/or capability requirements). App Factory is ONE such entry. There is
  no fixed task-type enum and no provider-name branching here.
- Exactly one HOW per request: ``strategy`` XOR ``template_ref`` XOR
  ``capability``; nothing ⇒ bounded AUTO. Two at once is refused loudly.
- Skills (Part 7/8): admitted against the ONE ``SkillRegistry`` with the
  SAME rule ``/v1/execute`` uses (``list_selectable`` by manifest id; unknown
  and non-selectable are indistinguishable). Skill ``manifest.capabilities``
  flow into the plan's ``required_capabilities`` (union with template /
  request / capability requirements) and ride into EVERY stage's
  ``RoutingRequest`` through the executor's ``required_capabilities`` seam.
- Provider-native agents (Part 13) are Models with agent capability
  metadata that the Router may select for a stage; the platform authority
  (:data:`GeneralAgent.PLATFORM_AUTHORITY`) never moves to them.
- Security (Part 20): nothing here grants anything — the firewall, tool
  approval, tenant policy, usage and audit remain where they are (inside the
  execution service / tool gate). Templates and skills are data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pydantic import Field

from core.contracts.agent_template import AgentPlan, OverrideRecord, TemplateOverride
from core.contracts.base import ContractModel, JsonObject
from core.contracts.execution_strategy import ExecutionStrategySpec
from core.contracts.model_policy import NodeModelPolicy
from core.contracts.provider import ProviderOperation
from core.execution.strategy import StrategyExecutor, StrategyReport
from core.execution.templates import TemplateError, TemplateRegistry, apply_override
from core.roles.registry import SkillRegistry


class PlanRefused(Exception):
    """The request cannot become a plan without guessing — refused loudly."""


class GeneralAgentRequest(ContractModel):
    """What the caller asks the General Agent to do — declarative input."""

    ask: str
    capability: str | None = None
    template_ref: str | None = None
    strategy: ExecutionStrategySpec | None = None
    override: TemplateOverride | None = None
    skills: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    model_policy: NodeModelPolicy | None = None
    auto_review: bool = False
    context: JsonObject = Field(default_factory=dict)


class CapabilityContribution(ContractModel):
    """What a registered capability contributes to a plan (data only)."""

    strategy: ExecutionStrategySpec | None = None
    template_ref: str | None = None
    skills: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


Contributor = Callable[[GeneralAgentRequest], CapabilityContribution]


@dataclass(frozen=True)
class AgentCapability:
    """Define → Contract → Register: a named, versioned contributor."""

    name: str
    version: str
    description: str
    contribute: Contributor

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


class AgentCapabilityRegistry:
    """Discover: the ONE place capabilities are registered and listed."""

    def __init__(self) -> None:
        self._by_name: dict[str, AgentCapability] = {}

    def register(self, capability: AgentCapability) -> AgentCapability:
        if capability.name in self._by_name:
            msg = f"capability already registered: {capability.name}"
            raise ValueError(msg)
        self._by_name[capability.name] = capability
        return capability

    def get(self, name: str) -> AgentCapability | None:
        return self._by_name.get(name)

    def list(self) -> list[AgentCapability]:
        return [self._by_name[k] for k in sorted(self._by_name)]


class GeneralAgent:
    """Plan (data) → the ONE StrategyExecutor. Reusable for any capability."""

    #: What the platform agent owns and never delegates (Part 13).
    PLATFORM_AUTHORITY: tuple[str, ...] = (
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

    def __init__(
        self,
        *,
        executor: StrategyExecutor,
        templates: TemplateRegistry,
        skills: SkillRegistry,
        capabilities: AgentCapabilityRegistry,
    ) -> None:
        self._executor = executor
        self._templates = templates
        self._skills = skills
        self._capabilities = capabilities

    # -- compose -------------------------------------------------------------------

    def plan(self, request: GeneralAgentRequest) -> AgentPlan:
        hows = [
            name
            for name, present in (
                ("strategy", request.strategy is not None),
                ("template_ref", request.template_ref is not None),
                ("capability", request.capability is not None),
            )
            if present
        ]
        if len(hows) > 1:
            msg = f"exactly one of strategy / template_ref / capability may be given; got {hows}"
            raise PlanRefused(msg)

        notes: list[str] = []
        skills: list[str] = list(request.skills)
        required: set[str] = set(request.required_capabilities)
        template_ref: str | None = None
        capability_ref: str | None = None
        overrides: list[OverrideRecord] = []
        spec: ExecutionStrategySpec | None = request.strategy
        wanted_template = request.template_ref

        if request.capability is not None:
            capability = self._capabilities.get(request.capability)
            if capability is None:
                msg = f"unknown capability {request.capability!r}"
                raise PlanRefused(msg)
            contribution = capability.contribute(request)
            capability_ref = capability.ref
            notes.extend(contribution.notes)
            skills.extend(s for s in contribution.skills if s not in skills)
            required.update(contribution.required_capabilities)
            if contribution.strategy is not None and contribution.template_ref is not None:
                msg = f"capability {capability.ref} contributed both a strategy and a template"
                raise PlanRefused(msg)
            spec = contribution.strategy
            wanted_template = contribution.template_ref

        if wanted_template is not None:
            template = self._templates.resolve_ref(wanted_template)
            if template is None:
                msg = f"unknown or inactive template {wanted_template!r}"
                raise PlanRefused(msg)
            template_ref = template.ref
            skills.extend(s for s in template.skills if s not in skills)
            required.update(template.required_capabilities)
            spec = template.strategy

        if request.override is not None and not request.override.is_empty:
            if spec is None:
                msg = "an override requires a template_ref, a capability, or a custom strategy"
                raise PlanRefused(msg)
            try:
                spec, overrides = apply_override(spec, request.override)
            except TemplateError as exc:
                raise PlanRefused(str(exc)) from exc
            skills.extend(s for s in request.override.add_skills if s not in skills)
            required.update(request.override.add_required_capabilities)

        # Skills: the ONE registry, the SAME admission rule as /v1/execute.
        selectable = {skill.manifest.id: skill for skill in self._skills.list_selectable()}
        for skill_id in skills:
            skill = selectable.get(skill_id)
            if skill is None:
                msg = f"skill is not selectable: {skill_id}"
                raise PlanRefused(msg)
            required.update(skill.manifest.capabilities)

        if spec is None:
            spec = ExecutionStrategySpec(mode="auto")
        # auto / template modes → concrete plan through the EXISTING resolver.
        try:
            spec = self._executor.resolve(
                spec, request_model_policy=request.model_policy, auto_review=request.auto_review
            )
        except Exception as exc:  # UnknownTemplate from the executor's own view
            raise PlanRefused(str(exc)) from exc

        return AgentPlan(
            strategy=spec,
            template_ref=template_ref,
            capability=capability_ref,
            skills=skills,
            required_capabilities=sorted(required),
            overrides_applied=overrides,
            notes=notes,
        )

    # -- execute (the ONE executor) -------------------------------------------------

    async def execute(
        self,
        plan: AgentPlan,
        *,
        tenant_id: UUID,
        user_id: UUID,
        ask: str,
        request_hash: str,
        base_payload: JsonObject | None = None,
        operation: ProviderOperation = ProviderOperation.GENERATE_TEXT,
        timeout_ms: int | None = None,
        idempotency_key: str | None = None,
        conversation_id: UUID | None = None,
    ) -> StrategyReport:
        payload: JsonObject = dict(base_payload or {})
        if plan.skills:
            payload["skills"] = list(plan.skills)
        return await self._executor.execute(
            spec=plan.strategy,
            tenant_id=tenant_id,
            user_id=user_id,
            ask=ask,
            request_hash=request_hash,
            base_payload=payload,
            operation=operation,
            required_capabilities=list(plan.required_capabilities),
            timeout_ms=timeout_ms,
            idempotency_key=idempotency_key,
            conversation_id=conversation_id,
        )
