"""T-IMPL-066 tests: learning-lifecycle gates (FINAL Phase 17, 41 §20).

Exit mapping (22 §12 learning-side items):

- "training eligibility enforcement" -> TestTrainingEligibilityGate
  (the eight verbatim 22 §9 conditions as DATA; ALL must hold; refusal
  names EVERY failed condition; sanitized/quality/source-trace resolved
  from the LearningSample contract — single source of truth).
- "shadow/canary promotion gate" -> TestPromotionGate (the seven
  verbatim 22 §11 conditions; shadow/canary are two of them; admin
  approval conditional on policy).
- "rollback model version" -> rollback_plan_exists condition here + the
  pre-existing admin rollback machinery (T-IMPL-031, verified by name:
  tests/admin — recorded, not redone).
- 41 §20 "Training eligibility: separate from Feedback" ->
  test_no_feedback_input_exists (structural: no signals field mentions
  feedback; same posture as the tool gate's missing skill parameter).
- "feedback not treated as truth" -> pre-existing preference-learning
  suite (19 tests, verified by name — recorded, not redone).

Deny-by-default: every signal defaults False (approval_required defaults
True); a default-constructed signals object fails every gate.

Hermetic: pure gates, no I/O.
"""

from __future__ import annotations

from dataclasses import fields
from uuid import uuid4

import pytest

from core.contracts.evaluation import VerificationLevel
from core.contracts.learning import (
    LearningEligibility,
    LearningSample,
    SanitizationState,
)
from core.learning import (
    PROMOTION_CONDITIONS,
    TRAINING_ELIGIBILITY_CONDITIONS,
    EligibilitySignals,
    LearningError,
    NotEligibleForTraining,
    PromotionDenied,
    PromotionGate,
    PromotionSignals,
    TrainingEligibilityGate,
)


def make_sample(
    *,
    level: VerificationLevel = VerificationLevel.VERIFIED,
    sanitization: SanitizationState = SanitizationState.PASSED,
) -> LearningSample:
    return LearningSample(
        id=uuid4(),
        source_execution_id=uuid4(),
        tenant_id=uuid4(),
        eligibility=LearningEligibility.PENDING,
        sanitization_state=sanitization,
        verification_level=level,
    )


def passing_signals() -> EligibilitySignals:
    return EligibilitySignals(
        privacy_policy_allows=True,
        tenant_user_policy_allows=True,
        sensitive_data_handled=True,
        deduplicated=True,
        not_poisoned=True,
    )


def passing_promotion() -> PromotionSignals:
    return PromotionSignals(
        offline_eval_pass=True,
        regression_pass=True,
        security_eval_pass=True,
        shadow_performance_acceptable=True,
        canary_performance_acceptable=True,
        rollback_plan_exists=True,
        approval_required=True,
        admin_approved=True,
    )


# --- 22 §9 training eligibility ---------------------------------------------------------


class TestTrainingEligibilityGate:
    def test_condition_list_is_the_verbatim_22s9_set(self) -> None:
        assert TRAINING_ELIGIBILITY_CONDITIONS == (
            "privacy_policy_allows",
            "tenant_user_policy_allows",
            "sensitive_data_handled",
            "quality_level_sufficient",
            "deduplicated",
            "sanitized",
            "source_trace_exists",
            "not_poisoned",
        )

    def test_verdicts_cover_exactly_the_condition_set(self) -> None:
        verdicts = TrainingEligibilityGate().evaluate(make_sample(), passing_signals())
        assert tuple(verdicts) == TRAINING_ELIGIBILITY_CONDITIONS

    def test_all_conditions_held_admits(self) -> None:
        verdicts = TrainingEligibilityGate().admit(make_sample(), passing_signals())
        assert all(verdicts.values())

    def test_default_signals_fail_everything_deniable(self) -> None:
        """Deny-by-default: an unresolved condition is a failed condition."""
        with pytest.raises(NotEligibleForTraining) as exc:
            TrainingEligibilityGate().admit(make_sample(), EligibilitySignals())
        assert exc.value.failed == [
            "privacy_policy_allows",
            "tenant_user_policy_allows",
            "sensitive_data_handled",
            "deduplicated",
            "not_poisoned",
        ]

    def test_refusal_names_every_failed_condition_not_just_first(self) -> None:
        signals = EligibilitySignals(
            privacy_policy_allows=True,
            tenant_user_policy_allows=True,
            sensitive_data_handled=True,
            deduplicated=False,  # fails
            not_poisoned=False,  # fails too
        )
        with pytest.raises(NotEligibleForTraining) as exc:
            TrainingEligibilityGate().admit(make_sample(), signals)
        assert exc.value.failed == ["deduplicated", "not_poisoned"]

    def test_unsanitized_sample_fails_the_sanitized_condition(self) -> None:
        """Single source of truth: the contract's SanitizationState decides."""
        sample = make_sample(sanitization=SanitizationState.PENDING)
        with pytest.raises(NotEligibleForTraining) as exc:
            TrainingEligibilityGate().admit(sample, passing_signals())
        assert exc.value.failed == ["sanitized"]

    def test_failed_sanitization_also_fails(self) -> None:
        sample = make_sample(sanitization=SanitizationState.FAILED)
        with pytest.raises(NotEligibleForTraining):
            TrainingEligibilityGate().admit(sample, passing_signals())

    @pytest.mark.parametrize(
        "level",
        [VerificationLevel.RAW, VerificationLevel.EVALUATED, VerificationLevel.VALIDATED],
    )
    def test_below_verified_fails_quality_by_default(self, level: VerificationLevel) -> None:
        sample = make_sample(level=level)
        with pytest.raises(NotEligibleForTraining) as exc:
            TrainingEligibilityGate().admit(sample, passing_signals())
        assert exc.value.failed == ["quality_level_sufficient"]

    @pytest.mark.parametrize("level", [VerificationLevel.VERIFIED, VerificationLevel.GOLD])
    def test_verified_and_gold_pass_quality(self, level: VerificationLevel) -> None:
        verdicts = TrainingEligibilityGate().admit(make_sample(level=level), passing_signals())
        assert verdicts["quality_level_sufficient"] is True

    def test_minimum_level_is_injectable_configuration(self) -> None:
        gate = TrainingEligibilityGate(minimum_level=VerificationLevel.GOLD)
        with pytest.raises(NotEligibleForTraining) as exc:
            gate.admit(make_sample(level=VerificationLevel.VERIFIED), passing_signals())
        assert exc.value.failed == ["quality_level_sufficient"]

    def test_broken_external_trace_fails_source_trace(self) -> None:
        signals = EligibilitySignals(
            privacy_policy_allows=True,
            tenant_user_policy_allows=True,
            sensitive_data_handled=True,
            deduplicated=True,
            not_poisoned=True,
            source_trace_intact=False,
        )
        with pytest.raises(NotEligibleForTraining) as exc:
            TrainingEligibilityGate().admit(make_sample(), signals)
        assert exc.value.failed == ["source_trace_exists"]

    def test_gate_is_pure_and_never_mutates_the_sample(self) -> None:
        sample = make_sample()
        TrainingEligibilityGate().admit(sample, passing_signals())
        assert sample.eligibility is LearningEligibility.PENDING  # untouched

    def test_no_feedback_input_exists(self) -> None:
        """41 §20: eligibility SEPARATE from feedback — structural."""
        names = [f.name for f in fields(EligibilitySignals)]
        assert not any("feedback" in name for name in names)

    def test_error_is_a_learning_error(self) -> None:
        assert issubclass(NotEligibleForTraining, LearningError)


# --- 22 §11 promotion gates -------------------------------------------------------------


class TestPromotionGate:
    def test_condition_list_is_the_verbatim_22s11_set(self) -> None:
        assert PROMOTION_CONDITIONS == (
            "offline_eval_pass",
            "regression_pass",
            "security_eval_pass",
            "shadow_performance_acceptable",
            "canary_performance_acceptable",
            "rollback_plan_exists",
            "admin_approval_where_required",
        )

    def test_verdicts_cover_exactly_the_condition_set(self) -> None:
        verdicts = PromotionGate().evaluate(passing_promotion())
        assert tuple(verdicts) == PROMOTION_CONDITIONS

    def test_all_gates_passed_promotes(self) -> None:
        verdicts = PromotionGate().admit("specialist-v2", passing_promotion())
        assert all(verdicts.values())

    def test_default_signals_deny_everything(self) -> None:
        """Deny-by-default: a fresh candidate promotes nothing."""
        with pytest.raises(PromotionDenied) as exc:
            PromotionGate().admit("specialist-v2", PromotionSignals())
        assert exc.value.failed == list(PROMOTION_CONDITIONS)

    @pytest.mark.parametrize(
        "broken",
        ["shadow_performance_acceptable", "canary_performance_acceptable"],
    )
    def test_shadow_or_canary_failure_blocks_promotion(self, broken: str) -> None:
        """The 22 §12 'shadow/canary promotion gate' item, both arms."""
        signals = PromotionSignals(
            **{
                **{f.name: True for f in fields(PromotionSignals)},
                broken: False,
            }
        )
        with pytest.raises(PromotionDenied) as exc:
            PromotionGate().admit("specialist-v2", signals)
        assert exc.value.failed == [broken]

    def test_missing_rollback_plan_blocks_promotion(self) -> None:
        """The 22 §12 'rollback model version' precondition."""
        signals = PromotionSignals(
            **{
                **{f.name: True for f in fields(PromotionSignals)},
                "rollback_plan_exists": False,
            }
        )
        with pytest.raises(PromotionDenied) as exc:
            PromotionGate().admit("specialist-v2", signals)
        assert exc.value.failed == ["rollback_plan_exists"]

    def test_approval_required_and_absent_blocks(self) -> None:
        signals = PromotionSignals(
            **{
                **{f.name: True for f in fields(PromotionSignals)},
                "admin_approved": False,
            }
        )
        with pytest.raises(PromotionDenied) as exc:
            PromotionGate().admit("specialist-v2", signals)
        assert exc.value.failed == ["admin_approval_where_required"]

    def test_approval_not_required_holds_vacuously(self) -> None:
        """22 §11 'where required' — the only conditional item."""
        signals = PromotionSignals(
            **{
                **{f.name: True for f in fields(PromotionSignals)},
                "approval_required": False,
                "admin_approved": False,
            }
        )
        verdicts = PromotionGate().admit("specialist-v2", signals)
        assert verdicts["admin_approval_where_required"] is True

    def test_approval_requirement_defaults_to_required(self) -> None:
        """Requiring approval is the safe default (deny-by-default)."""
        assert PromotionSignals().approval_required is True

    def test_refusal_names_the_candidate(self) -> None:
        with pytest.raises(PromotionDenied) as exc:
            PromotionGate().admit("specialist-v2", PromotionSignals())
        assert exc.value.candidate == "specialist-v2"

    def test_no_feedback_input_exists(self) -> None:
        names = [f.name for f in fields(PromotionSignals)]
        assert not any("feedback" in name for name in names)


# --- hermeticity ------------------------------------------------------------------------


def test_learning_package_performs_no_io() -> None:
    import inspect

    import core.learning.errors as errors_module
    import core.learning.gates as gates_module

    for module in (gates_module, errors_module):
        source = inspect.getsource(module)
        for forbidden in ("httpx", "requests", "urllib", "socket", "aiohttp", "subprocess"):
            assert forbidden not in source
