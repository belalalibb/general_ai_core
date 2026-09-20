"""App Factory — a *capability* of the General Agent (R191-B, first vertical slice).

What this module IS
-------------------
* ``AppFactoryCapability`` — a contributor registered in the ONE
  ``AgentCapabilityRegistry``. Given a request, it obtains a project inventory
  (from ``request.context["project_inventory"]`` or by asking an injected
  ``ProjectInspectorPort``) and contributes the DATA template
  ``app_factory.plan@1`` plus inspectable notes. It owns no execution.
* ``APP_FACTORY_TEMPLATE`` — a system-origin ``StrategyTemplate`` (data):
  ``inventory-summary → architecture-plan → review``. It is registered in the
  ONE ``TemplateRegistry`` by whoever composes the runtime and is executed by
  the ONE ``StrategyExecutor`` exactly like any other template.
* ``ProjectInventory`` / ``QevionInventory`` / ``ApplicationPlan`` — records.
  ``qevion_inventory`` reads the EXISTING registries (models, skills,
  capabilities); it never keeps a copy.
* ``build_application_plan`` — assembles the inspectable plan record with the
  model policy and provider routing posture stated explicitly (Part 9/10):
  Model identity ≠ Provider capacity; same-model fallback preferred.

What this module is NOT (R191 directive Part 22, non-negotiable)
----------------------------------------------------------------
No engine, no router, no model/provider manager, no second registry, no
``TemplateExecutor``, no code generation. ``ApplicationPlan.generation_deferred``
is always ``True`` in this round.

Credential posture: this module never sees a token. Inspection over the
network lives in ``apps/agent_dev/project_inspector.py`` and the token rides
only the request header there; the ``ProjectInspectorPort`` used here is
token-free by construction (the composition layer binds credentials).
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from core.agent.general import (
    AgentCapability,
    AgentCapabilityRegistry,
    CapabilityContribution,
    GeneralAgentRequest,
    PlanRefused,
)
from core.contracts.agent_template import AgentPlan, StrategyTemplate, TemplateOrigin
from core.contracts.base import BoundedStr, ContractModel
from core.contracts.execution_strategy import ExecutionStrategySpec, StageKind, StrategyStage
from core.providers.registry import ModelRegistry
from core.roles.registry import SkillRegistry

APP_FACTORY_CAPABILITY_NAME = "app_factory"
APP_FACTORY_CAPABILITY_VERSION = "1"
APP_FACTORY_TEMPLATE_ID = "app_factory.plan"
APP_FACTORY_TEMPLATE_VERSION = "1"


# --------------------------------------------------------------------------- records


class ProjectInventory(ContractModel):
    """Bounded, read-only description of a target repository at one commit."""

    remote_url: BoundedStr
    branch: BoundedStr
    head_sha: BoundedStr
    file_count: int = Field(ge=0)
    paths: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    manifests: list[str] = Field(default_factory=list)
    truncated: bool = False


class QevionInventory(ContractModel):
    """What QEVION can bring to bear — read through the existing registries."""

    models: list[str] = Field(default_factory=list)
    model_capabilities: dict[str, list[str]] = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class ApplicationPlan(ContractModel):
    """The slice's terminal artefact: everything decided, nothing generated."""

    ask: BoundedStr
    project: ProjectInventory
    qevion: QevionInventory
    strategy_template: BoundedStr | None
    stages: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    model_policy: BoundedStr
    provider_routing: Literal["same-model-fallback-preferred"] = "same-model-fallback-preferred"
    generation_deferred: Literal[True] = True
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- ports


class ProjectInspectorPort(Protocol):
    """Token-free inspection port bound by the composition layer."""

    def inspect(self, remote_url: str, branch: str) -> ProjectInventory: ...


# --------------------------------------------------------------------------- template (data)


APP_FACTORY_TEMPLATE = StrategyTemplate(
    id=APP_FACTORY_TEMPLATE_ID,
    version=APP_FACTORY_TEMPLATE_VERSION,
    name="App Factory — application plan",
    origin=TemplateOrigin.SYSTEM,
    description=(
        "Inventory the target project and QEVION's own capabilities, draft an "
        "architecture plan, review it. Generation is a later, separate template."
    ),
    strategy=ExecutionStrategySpec(
        mode="custom",
        max_parallel=1,
        stages=[
            StrategyStage(
                key="inventory-summary",
                kind=StageKind.GENERATE,
                role="analyst",
                instruction=(
                    "Summarise the project inventory (languages, manifests, layout) and "
                    "the QEVION inventory (models, skills, capabilities) as facts only."
                ),
            ),
            StrategyStage(
                key="architecture-plan",
                kind=StageKind.GENERATE,
                role="architect",
                instruction=(
                    "Propose an application plan for the ask on top of the inventory: "
                    "components, boundaries, data flow, risks. Do NOT write code."
                ),
                depends_on=["inventory-summary"],
            ),
            StrategyStage(
                key="review",
                kind=StageKind.REVIEW,
                role="reviewer",
                instruction="Review the plan for gaps and contradictions with the inventory.",
                depends_on=["architecture-plan"],
            ),
        ],
    ),
    tags=["app-factory", "planning"],
)


# --------------------------------------------------------------------------- inventory


def qevion_inventory(
    *, models: ModelRegistry, skills: SkillRegistry, capabilities: AgentCapabilityRegistry
) -> QevionInventory:
    """Read (never copy) what the platform offers, through the existing registries."""
    active = sorted(models.active_models(), key=lambda m: m.model_key)
    return QevionInventory(
        models=[m.model_key for m in active],
        model_capabilities={m.model_key: sorted(m.capabilities) for m in active},
        skills=sorted(s.manifest.id for s in skills.list_selectable()),
        capabilities=[c.ref for c in capabilities.list()],
    )


# --------------------------------------------------------------------------- capability


class AppFactoryCapability:
    """Contributor for the General Agent. Holds an optional inspector port only."""

    def __init__(self, *, inspector: ProjectInspectorPort | None) -> None:
        self._inspector = inspector

    def as_capability(self) -> AgentCapability:
        return AgentCapability(
            name=APP_FACTORY_CAPABILITY_NAME,
            version=APP_FACTORY_CAPABILITY_VERSION,
            description="Plan an application from a repository inventory (generation deferred).",
            contribute=self.contribute,
        )

    def contribute(self, request: GeneralAgentRequest) -> CapabilityContribution:
        inventory = self._resolve_inventory(request)
        notes = [
            f"project {inventory.remote_url}@{inventory.branch} ({inventory.head_sha}): "
            f"{inventory.file_count} files, languages={sorted(inventory.languages)}, "
            f"manifests={inventory.manifests}"
            + (", inventory truncated" if inventory.truncated else ""),
            "strategy: data template app_factory.plan (no generation stage in this round)",
        ]
        return CapabilityContribution(
            template_ref=f"{APP_FACTORY_TEMPLATE_ID}@{APP_FACTORY_TEMPLATE_VERSION}",
            notes=notes,
        )

    def _resolve_inventory(self, request: GeneralAgentRequest) -> ProjectInventory:
        raw = request.context.get("project_inventory")
        if raw is not None:
            try:
                return ProjectInventory.model_validate(raw)
            except ValueError as exc:
                raise PlanRefused(f"context.project_inventory is malformed: {exc}") from exc
        remote = request.context.get("remote_url")
        branch = request.context.get("branch", "main")
        if self._inspector is not None and isinstance(remote, str) and isinstance(branch, str):
            return self._inspector.inspect(remote, branch)
        raise PlanRefused(
            "app_factory needs context.project_inventory, or context.remote_url with a bound "
            "project inspector"
        )


# --------------------------------------------------------------------------- plan record


def build_application_plan(
    *, ask: str, project: ProjectInventory, qevion: QevionInventory, agent_plan: AgentPlan
) -> ApplicationPlan:
    """Assemble the inspectable plan; the model policy is stated, never inferred silently."""
    pinned = [s for s in agent_plan.strategy.stages if s.model_policy is not None]
    if not pinned:
        model_policy = "auto"
    elif len(pinned) == len(agent_plan.strategy.stages):
        model_policy = "explicit-per-stage"
    else:
        model_policy = (
            "mixed (explicit on " + ", ".join(s.key for s in pinned) + "; auto elsewhere)"
        )
    return ApplicationPlan(
        ask=ask,
        project=project,
        qevion=qevion,
        strategy_template=agent_plan.template_ref,
        stages=[s.key for s in agent_plan.strategy.stages],
        skills=list(agent_plan.skills),
        required_capabilities=list(agent_plan.required_capabilities),
        model_policy=model_policy,
        notes=list(agent_plan.notes),
    )
