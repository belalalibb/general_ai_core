"""Strategy templates, overrides and agent plans — declarative configuration (R191).

Authority: R191-DEC-01 (General Agent + extensible Skills/Strategy/Template
foundation). ADDITIVE: a NEW contract module outside the R189 frozen set; it
PRODUCES the frozen :class:`~core.contracts.execution_strategy.ExecutionStrategySpec`
and never redefines it.

Recorded decisions:
- A template DESCRIBES an execution strategy; it is not an engine. The ONE
  ``StrategyExecutor`` runs whatever a template produces (Part 5).
- Templates are versioned and identifiable: ``(id, version)`` is the
  immutable identity; a new version is a new record — older versions never
  mutate (Part 23 Q). ``origin`` distinguishes system / imported / user /
  workspace templates (Part 5/6) as a LABEL over the existing tenancy — no
  new ownership rule is invented (Part 21).
- Overrides are explicit and inspectable (Part 12): the runtime strategy
  carries an ``overrides_applied`` record; there are no hidden priority
  rules. Overrides are ADDITIVE to the template (model policy per stage or
  for all stages, extra skills, tighter parallelism); they cannot remove
  stages or change stage kinds — a different DAG is a different template
  or a ``custom`` strategy.
- A stage never names a provider except through the existing
  ``ExplicitModelPolicy.provider_id`` (Part 9 D). Nothing here carries a
  provider-specific branch.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.execution_strategy import MAX_PARALLEL, ExecutionStrategySpec
from core.contracts.model_policy import NodeModelPolicy


class TemplateOrigin(StrEnum):
    """Where a template came from — a label, not an authority."""

    SYSTEM = "system"
    IMPORTED = "imported"
    USER = "user"
    WORKSPACE = "workspace"


class TemplateStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class StrategyTemplate(ContractModel):
    """A versioned, identifiable, declarative execution-strategy configuration."""

    id: BoundedStr
    version: BoundedStr
    name: BoundedStr
    origin: TemplateOrigin
    status: TemplateStatus = TemplateStatus.ACTIVE
    description: BoundedStr | None = None
    #: The strategy this template produces. ``mode`` must be ``custom`` — a
    #: template is a concrete plan, never a pointer to another template and
    #: never "auto" (that would hide the methodology the template exists to
    #: make explicit).
    strategy: ExecutionStrategySpec
    #: Skill manifest ids the template composes (Part 7). Admission against
    #: the ONE SkillRegistry happens at plan time, not here.
    skills: list[BoundedStr] = Field(default_factory=list)
    #: Explicit capability requirements in addition to what skills declare.
    required_capabilities: list[BoundedStr] = Field(default_factory=list)
    tags: list[BoundedStr] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _concrete(self) -> StrategyTemplate:
        if self.strategy.mode != "custom":
            msg = "a template must carry a concrete custom strategy (mode='custom')"
            raise ValueError(msg)
        return self

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class TemplateOverride(ContractModel):
    """Explicit, inspectable, ADDITIVE overrides applied on top of a template."""

    #: "Use Model X everywhere" (Part 12) — applied to EVERY stage.
    model_policy_all: NodeModelPolicy | None = None
    #: Per-stage model policy (Part 9 C); keys must name stages of the template.
    stage_model_policies: dict[str, NodeModelPolicy] = Field(default_factory=dict)
    #: Extra skills composed into the plan (union with the template's).
    add_skills: list[BoundedStr] = Field(default_factory=list)
    #: Extra capability requirements (union).
    add_required_capabilities: list[BoundedStr] = Field(default_factory=list)
    #: Tighten (never widen beyond the frozen bound) concurrency.
    max_parallel: int | None = Field(default=None, ge=1, le=MAX_PARALLEL)

    @property
    def is_empty(self) -> bool:
        return (
            self.model_policy_all is None
            and not self.stage_model_policies
            and not self.add_skills
            and not self.add_required_capabilities
            and self.max_parallel is None
        )


class OverrideRecord(ContractModel):
    """What an override actually changed — the inspectable trail (Part 12)."""

    field: BoundedStr
    stage_key: BoundedStr | None = None
    detail: BoundedStr


class AgentPlan(ContractModel):
    """The General Agent's resolved plan — data the ONE executor runs."""

    strategy: ExecutionStrategySpec
    template_ref: BoundedStr | None = None
    capability: BoundedStr | None = None
    skills: list[BoundedStr] = Field(default_factory=list)
    required_capabilities: list[BoundedStr] = Field(default_factory=list)
    overrides_applied: list[OverrideRecord] = Field(default_factory=list)
    notes: list[BoundedStr] = Field(default_factory=list)
