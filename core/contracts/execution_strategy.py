"""Execution strategy contracts — caller-defined HOW of a task (R188 C1, additive).

Authority: R188-DEC-01 §C. This is Core infrastructure for *execution
orchestration* (stages, roles, delegation, model assignment, sequencing,
parallelism, review/retest, resource selection) — NOT a workflow template
library and NOT an exposure of private chain-of-thought.

Recorded decisions:

- ONE router, ONE execution service: a stage carries a ``NodeModelPolicy``
  (10 §13.5 union — auto / tier / explicit_model / explicit_models). The
  Router resolves the concrete provider for EVERY stage at execution time;
  a stage never names a provider except through the existing
  ``ExplicitModelPolicy.provider_id`` (agent ↔ provider decoupling).
- Composition primitives, not a methodology: ``StageKind`` names what a
  stage DOES with its inputs (``generate`` produces; ``review`` judges an
  upstream output; ``retest`` re-runs a check against an upstream output).
  Roles are free bounded strings chosen by the caller. Nothing here requires
  an analyst/planner/reviewer/fixer template.
- ``depends_on`` is a DAG: stages with satisfied dependencies run in the
  same wave, concurrently (bounded); a cycle is a validation error. Unlike
  the 12 §3 graph (which permits revisits for agent loops), a *strategy*
  is a finite plan — bounded by construction (S4 flood posture).
- ``mode``: ``custom`` = the caller's stages verbatim; ``auto`` = the Core
  composes a bounded, policy-valid plan (see ``core/execution/strategy.py``);
  ``template`` = a NAMED optional reusable configuration resolved by the
  executor's template registry — absent id ⇒ loud refusal, never a guess.
- Bounds: at most :data:`MAX_STAGES` stages, at most :data:`MAX_PARALLEL`
  stages per wave; deeper needs are an operator decision, not a silent
  widening.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.model_policy import NodeModelPolicy

#: Hard bounds (S4): a strategy is a finite plan the caller cannot inflate.
MAX_STAGES = 16
MAX_PARALLEL = 4


class StageKind(StrEnum):
    """What a stage does with its inputs — closed, minimal, composable."""

    GENERATE = "generate"
    REVIEW = "review"
    RETEST = "retest"


class StrategyStage(ContractModel):
    """One stage of a caller-defined execution strategy."""

    key: BoundedStr
    kind: StageKind = StageKind.GENERATE
    role: BoundedStr | None = None
    instruction: BoundedStr | None = None
    model_policy: NodeModelPolicy | None = None  # None ⇒ Router AUTO for this stage
    depends_on: list[BoundedStr] = Field(default_factory=list)
    payload: JsonObject = Field(default_factory=dict)


class ExecutionStrategySpec(ContractModel):
    """``execution_strategy`` object of POST /v1/execute (additive, optional)."""

    mode: Literal["auto", "custom", "template"] = "custom"
    template_id: BoundedStr | None = None
    stages: list[StrategyStage] = Field(default_factory=list)
    max_parallel: int = Field(default=MAX_PARALLEL, ge=1, le=MAX_PARALLEL)

    @model_validator(mode="after")
    def _well_formed(self) -> ExecutionStrategySpec:
        if self.mode == "custom":
            if not self.stages:
                msg = "custom strategy requires at least one stage"
                raise ValueError(msg)
        if self.mode == "template" and not self.template_id:
            msg = "template strategy requires template_id"
            raise ValueError(msg)
        if self.mode == "auto" and self.stages:
            msg = "auto strategy composes its own stages; pass none"
            raise ValueError(msg)
        if len(self.stages) > MAX_STAGES:
            msg = f"strategy exceeds {MAX_STAGES} stages"
            raise ValueError(msg)
        keys = [stage.key for stage in self.stages]
        if len(set(keys)) != len(keys):
            msg = f"duplicate stage keys: {keys}"
            raise ValueError(msg)
        known = set(keys)
        for stage in self.stages:
            for dep in stage.depends_on:
                if dep not in known:
                    msg = f"stage {stage.key!r} depends on unknown stage {dep!r}"
                    raise ValueError(msg)
                if dep == stage.key:
                    msg = f"stage {stage.key!r} depends on itself"
                    raise ValueError(msg)
            if stage.kind in (StageKind.REVIEW, StageKind.RETEST) and not stage.depends_on:
                msg = f"{stage.kind.value} stage {stage.key!r} must depend on the stage it checks"
                raise ValueError(msg)
        self.waves()  # raises on cycles
        return self

    def waves(self) -> list[list[StrategyStage]]:
        """Topological waves (Kahn); raises ``ValueError`` on a cycle."""
        remaining = {stage.key: set(stage.depends_on) for stage in self.stages}
        by_key = {stage.key: stage for stage in self.stages}
        done: set[str] = set()
        waves: list[list[StrategyStage]] = []
        while remaining:
            ready = sorted(key for key, deps in remaining.items() if deps <= done)
            if not ready:
                msg = f"strategy has a dependency cycle among {sorted(remaining)}"
                raise ValueError(msg)
            waves.append([by_key[key] for key in ready])
            for key in ready:
                done.add(key)
                del remaining[key]
        return waves
