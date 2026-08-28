"""Plan contract tests (FINAL Phase 3 gap-fix: first missing Postgres entity).

Verifies core/contracts/plan.py against its recorded authorities:
21 §5/§10 plan-configuration shapes, 10 §8 usage-surface names,
41 §1 rule 9 deny-by-default encoded in defaults, and the 41 §4
contracts-first rule (no implementation imports).
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.base import ContractModel
from core.contracts.plan import Plan, PlanLimits

MODULE_PATH = Path("core/contracts/plan.py")


class TestDenyByDefault:
    """41 §1 rule 9: an unconfigured plan grants NOTHING."""

    def test_default_limits_grant_zero_task_units(self) -> None:
        plan = Plan(id=uuid4(), name="bare")
        assert plan.limits.task_units == 0

    def test_default_entitlements_are_empty(self) -> None:
        plan = Plan(id=uuid4(), name="bare")
        assert plan.entitlements == {}

    def test_default_model_control_is_empty(self) -> None:
        plan = Plan(id=uuid4(), name="bare")
        assert plan.model_control == {}

    def test_default_modality_limits_are_empty(self) -> None:
        assert PlanLimits().modality_limits == {}

    def test_max_parallel_executions_default_is_unset_not_invented(self) -> None:
        # The contract must not invent a parallelism number the spec
        # does not state — None means "resolve via policy defaults".
        assert PlanLimits().max_parallel_executions is None


class TestSpecExampleShapes:
    """The 21 §5 'pro' example must be expressible field-for-field."""

    def test_21_s5_pro_plan_example(self) -> None:
        plan = Plan(
            id=uuid4(),
            name="pro",
            limits=PlanLimits(
                task_units=100,
                max_parallel_executions=3,
                modality_limits={"image_generations": 20},
            ),
            entitlements={
                "models": {"max": False, "medium": True},
                "tools": {"github_read": True, "github_write": False},
                "agent_mode": True,
            },
        )
        assert plan.limits.task_units == 100
        assert plan.entitlements["tools"]["github_write"] is False

    def test_21_s10_enterprise_model_control_example(self) -> None:
        plan = Plan(
            id=uuid4(),
            name="enterprise",
            model_control={
                "auto": True,
                "tier_selection": True,
                "explicit_model": True,
                "explicit_models": True,
                "agent_node_mapping": True,
                "provider_selection": True,
                "max_parallel_models": 5,
                "allowed_strategies": [
                    "fallback_chain",
                    "parallel_compare",
                    "debate",
                    "specialist_roles",
                ],
            },
        )
        assert plan.model_control["max_parallel_models"] == 5


class TestValidationPosture:
    def test_frozen_and_extra_forbid(self) -> None:
        plan = Plan(id=uuid4(), name="pro")
        assert isinstance(plan, ContractModel)
        with pytest.raises(ValidationError):
            plan.name = "changed"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            Plan(id=uuid4(), name="pro", invented_field=True)  # type: ignore[call-arg]

    def test_negative_task_units_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlanLimits(task_units=-1)

    def test_negative_parallel_executions_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlanLimits(max_parallel_executions=-1)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Plan(id=uuid4(), name="")

    def test_plan_is_not_tenant_scoped(self) -> None:
        # Recorded derivation: plans are a PLATFORM catalog — the tenant
        # side of the relation is tenants.plan_id, not a tenant_id here.
        assert "tenant_id" not in Plan.model_fields


class TestContractsFirstRule:
    """41 §4: no Contract imports a specific Implementation."""

    def test_no_implementation_imports(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
        allowed = {"__future__", "typing", "uuid", "pydantic", "core"}
        assert imported <= allowed, f"unexpected imports: {imported - allowed}"
        # And within core: only contracts modules.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core"):
                assert node.module.startswith("core.contracts."), node.module
