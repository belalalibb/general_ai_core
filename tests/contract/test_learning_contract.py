"""LearningSample contract tests (03 §7 verbatim + deny-by-default posture)."""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.evaluation import VerificationLevel
from core.contracts.learning import (
    LearningEligibility,
    LearningSample,
    SanitizationState,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "core/contracts/learning.py"
)


class TestClosedSets:
    def test_eligibility_values_verbatim(self) -> None:
        # 03 §7: eligible|ineligible|pending — closed set, verbatim.
        assert {m.value for m in LearningEligibility} == {
            "eligible",
            "ineligible",
            "pending",
        }

    def test_sanitization_values_verbatim(self) -> None:
        # 03 §7: pending|passed|failed — closed set, verbatim.
        assert {m.value for m in SanitizationState} == {
            "pending",
            "passed",
            "failed",
        }

    def test_verification_level_is_reused_not_duplicated(self) -> None:
        # 03 §7 lists the identical RAW..GOLD set for LearningSample and
        # Evaluation — one source of truth (core.contracts.evaluation).
        assert LearningSample.model_fields["verification_level"].annotation is (
            VerificationLevel
        )
        source = MODULE_PATH.read_text(encoding="utf-8")
        assert "class VerificationLevel" not in source

    def test_unknown_enum_values_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LearningSample(
                id=uuid4(),
                source_execution_id=uuid4(),
                eligibility="approved",  # type: ignore[arg-type]
            )
        with pytest.raises(ValidationError):
            LearningSample(
                id=uuid4(),
                source_execution_id=uuid4(),
                sanitization_state="clean",  # type: ignore[arg-type]
            )


class TestDenyByDefault:
    def test_new_sample_grants_nothing_toward_training(self) -> None:
        # 41 §1 rule 9 / 22 §9: every default must grant NOTHING toward
        # the training-eligibility gate.
        sample = LearningSample(id=uuid4(), source_execution_id=uuid4())
        assert sample.eligibility is LearningEligibility.PENDING
        assert sample.sanitization_state is SanitizationState.PENDING
        assert sample.verification_level is VerificationLevel.RAW
        assert sample.dataset_id is None
        assert sample.tenant_id is None

    def test_field_set_is_exactly_the_03_yaml(self) -> None:
        # Field-for-field vs 03 §7 — nothing added, renamed, or dropped.
        assert set(LearningSample.model_fields) == {
            "id",
            "source_execution_id",
            "tenant_id",
            "eligibility",
            "sanitization_state",
            "verification_level",
            "dataset_id",
        }

    def test_tenant_id_nullable_by_spec(self) -> None:
        # 03 §7: tenant_id uuid|null — both attributed and unattributed
        # samples are expressible.
        tenant = uuid4()
        attributed = LearningSample(
            id=uuid4(), source_execution_id=uuid4(), tenant_id=tenant
        )
        assert attributed.tenant_id == tenant

    def test_gold_eligible_sanitized_sample_expressible(self) -> None:
        # The far end of the 22 §8 lifecycle must be representable.
        dataset = uuid4()
        sample = LearningSample(
            id=uuid4(),
            source_execution_id=uuid4(),
            tenant_id=uuid4(),
            eligibility=LearningEligibility.ELIGIBLE,
            sanitization_state=SanitizationState.PASSED,
            verification_level=VerificationLevel.GOLD,
            dataset_id=dataset,
        )
        assert sample.dataset_id == dataset


class TestContractRigidity:
    def test_frozen(self) -> None:
        sample = LearningSample(id=uuid4(), source_execution_id=uuid4())
        with pytest.raises(ValidationError):
            sample.eligibility = LearningEligibility.ELIGIBLE  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            LearningSample(
                id=uuid4(),
                source_execution_id=uuid4(),
                dataset_name="x",  # type: ignore[call-arg]
            )

    def test_no_implementation_imports(self) -> None:
        # 41 §4 — contracts import contracts only.
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("core."):
                    assert node.module.startswith("core.contracts."), node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(
                        ("core.memory", "core.execution", "infrastructure")
                    ), alias.name
