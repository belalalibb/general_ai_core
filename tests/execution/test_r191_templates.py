"""R191 — Template abstraction over the EXISTING strategy engine (RED first).

Proof areas (directive Part 23): B (template → runtime strategy), C (override
changes configuration, not engine behavior), D (system vs user templates are
distinguishable), Q (older versions never mutate), and that the EXISTING
``StrategyExecutor(templates=...)`` consumes the registry unchanged.
"""

from __future__ import annotations

import pytest

from core.contracts.agent_template import (
    StrategyTemplate,
    TemplateOrigin,
    TemplateOverride,
    TemplateStatus,
)
from core.contracts.execution_strategy import ExecutionStrategySpec, StageKind, StrategyStage
from core.contracts.model_policy import ExplicitModelPolicy, TierModelPolicy
from core.execution.strategy import StrategyExecutor, UnknownTemplate
from core.execution.templates import (
    DuplicateTemplate,
    OverrideRejected,
    TemplateNotFound,
    TemplateRegistry,
)
from tests.execution.test_r188_strategy_executor import RecordingAdapter, World


def _plan_code_review() -> ExecutionStrategySpec:
    return ExecutionStrategySpec(
        mode="custom",
        stages=[
            StrategyStage(key="plan", role="planner", instruction="Plan the change."),
            StrategyStage(
                key="code",
                role="coder",
                instruction="Implement the plan.",
                depends_on=["plan"],
                model_policy=TierModelPolicy(type="tier", tier="coding"),
            ),
            StrategyStage(
                key="review",
                kind=StageKind.REVIEW,
                role="reviewer",
                instruction="Review the implementation.",
                depends_on=["code"],
            ),
        ],
    )


def _template(
    *,
    tid: str = "coding.default",
    version: str = "1",
    origin: TemplateOrigin = TemplateOrigin.SYSTEM,
) -> StrategyTemplate:
    return StrategyTemplate(
        id=tid,
        version=version,
        name="Plan / code / review",
        origin=origin,
        strategy=_plan_code_review(),
        skills=["testing"],
        required_capabilities=["chat"],
    )


class TestTemplateIsData:
    def test_template_must_be_a_concrete_custom_strategy(self) -> None:
        with pytest.raises(ValueError, match="mode='custom'"):
            StrategyTemplate(
                id="x",
                version="1",
                name="x",
                origin=TemplateOrigin.USER,
                strategy=ExecutionStrategySpec(mode="auto"),
            )

    def test_b_template_produces_runtime_strategy_without_override(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template())
        spec, applied = registry.materialize("coding.default")
        assert spec == _plan_code_review()
        assert applied == []

    def test_c_override_changes_configuration_only(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template())
        everywhere = ExplicitModelPolicy(type="explicit_model", model_id="model-x")
        spec, applied = registry.materialize(
            "coding.default", override=TemplateOverride(model_policy_all=everywhere, max_parallel=1)
        )
        assert [s.key for s in spec.stages] == ["plan", "code", "review"]
        assert [s.kind for s in spec.stages] == [s.kind for s in _plan_code_review().stages]
        assert all(s.model_policy == everywhere for s in spec.stages)
        assert spec.max_parallel == 1
        assert {(r.field, r.stage_key) for r in applied} == {
            ("model_policy", "plan"),
            ("model_policy", "code"),
            ("model_policy", "review"),
            ("max_parallel", None),
        }
        # The registered template itself is untouched (frozen record).
        assert registry.get("coding.default").strategy == _plan_code_review()

    def test_per_stage_override_and_unknown_stage_is_loud(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template())
        strong = ExplicitModelPolicy(type="explicit_model", model_id="model-strong")
        spec, applied = registry.materialize(
            "coding.default", override=TemplateOverride(stage_model_policies={"plan": strong})
        )
        assert spec.stages[0].model_policy == strong
        assert spec.stages[1].model_policy == TierModelPolicy(type="tier", tier="coding")
        assert [r.stage_key for r in applied] == ["plan"]
        with pytest.raises(OverrideRejected, match="unknown stage"):
            registry.materialize(
                "coding.default", override=TemplateOverride(stage_model_policies={"nope": strong})
            )


class TestOriginAndVersions:
    def test_d_system_and_user_templates_are_distinguishable(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template())
        registry.register(_template(tid="mine.review", origin=TemplateOrigin.USER))
        assert [t.id for t in registry.list(origin=TemplateOrigin.SYSTEM)] == ["coding.default"]
        assert [t.id for t in registry.list(origin=TemplateOrigin.USER)] == ["mine.review"]
        assert registry.get("mine.review").origin is TemplateOrigin.USER
        with pytest.raises(DuplicateTemplate, match="system"):
            registry.register(_template(version="2", origin=TemplateOrigin.USER))

    def test_q_new_version_does_not_mutate_the_old_one(self) -> None:
        registry = TemplateRegistry()
        v1 = _template(version="1")
        registry.register(v1)
        v2_strategy = _plan_code_review().model_copy(update={"max_parallel": 1})
        registry.register(v1.model_copy(update={"version": "2", "strategy": v2_strategy}))
        assert registry.get("coding.default").version == "2"  # latest active
        assert registry.get("coding.default", version="1") == v1
        assert registry.get("coding.default", version="1").strategy.max_parallel == 4
        with pytest.raises(DuplicateTemplate):
            registry.register(v1)
        with pytest.raises(TemplateNotFound):
            registry.get("coding.default", version="9")

    def test_disabled_template_is_not_selectable_but_stays_listable(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template().model_copy(update={"status": TemplateStatus.DISABLED}))
        with pytest.raises(TemplateNotFound, match="no active"):
            registry.get("coding.default")
        assert [t.status for t in registry.list(include_inactive=True)] == [
            TemplateStatus.DISABLED
        ]
        assert registry.list() == []


class TestExistingExecutorConsumesTheRegistry:
    def test_strategy_executor_resolves_template_mode_through_the_mapping_view(self) -> None:
        registry = TemplateRegistry()
        registry.register(_template())
        world = World(
            {"alpha": RecordingAdapter("alpha")},
            ["model-x"],
            templates=registry.as_strategy_mapping(),
        )
        assert isinstance(world.executor, StrategyExecutor)
        resolved = world.executor.resolve(
            ExecutionStrategySpec(mode="template", template_id="coding.default")
        )
        assert resolved == _plan_code_review()
        pinned = world.executor.resolve(
            ExecutionStrategySpec(mode="template", template_id="coding.default@1")
        )
        assert pinned == _plan_code_review()
        with pytest.raises(UnknownTemplate):
            world.executor.resolve(ExecutionStrategySpec(mode="template", template_id="ghost"))
        # Live view: a later registration is visible to the SAME executor.
        registry.register(_template(tid="other.plan", origin=TemplateOrigin.IMPORTED))
        assert world.executor.resolve(
            ExecutionStrategySpec(mode="template", template_id="other.plan")
        ) == _plan_code_review()
