"""Contract tests: evaluation contracts (03 §7; 22 §3/§4/§5/§6).

Verifies the verification-level and grader-type closed sets match the
specs verbatim, the level ladder order is encoded as data, score and
confidence are SEPARATE independently-nullable [0,1] fields (22 §4 —
never merged), the 22 §6 grader-row shapes (check-style and
judgment-style) both validate, RAW records carry no judgment while
above-RAW records require graders, unknown fields are rejected
(deny-by-default), and instances are frozen value objects.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.evaluation import (
    MVP_ACTIVE_GRADER_TYPES,
    VERIFICATION_LEVEL_ORDER,
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)

# --- Closed sets exactly as written in 22 §3 / 22 §5 ---------------------------


def test_verification_level_set_matches_spec() -> None:
    # 22 §3 / 03 §7: RAW|EVALUATED|VALIDATED|VERIFIED|GOLD
    assert {v.value for v in VerificationLevel} == {
        "RAW",
        "EVALUATED",
        "VALIDATED",
        "VERIFIED",
        "GOLD",
    }


def test_verification_level_order_is_the_full_ladder_ascending() -> None:
    # 22 §3 lists levels in ascending trust order — encoded as data.
    assert VERIFICATION_LEVEL_ORDER == (
        VerificationLevel.RAW,
        VerificationLevel.EVALUATED,
        VerificationLevel.VALIDATED,
        VerificationLevel.VERIFIED,
        VerificationLevel.GOLD,
    )
    # The ladder covers the closed set exactly once.
    assert len(VERIFICATION_LEVEL_ORDER) == len(set(VERIFICATION_LEVEL_ORDER))
    assert set(VERIFICATION_LEVEL_ORDER) == set(VerificationLevel)


def test_grader_type_set_matches_spec_all_ten() -> None:
    # 22 §5: all ten grader types, verbatim.
    assert {g.value for g in GraderType} == {
        "deterministic",
        "model_based",
        "pairwise",
        "counter_evaluation",
        "skill_specific",
        "role_specific",
        "security",
        "regression",
        "human_calibrated",
        "production_signal",
    }


def test_mvp_active_grader_types_is_the_r049_boundary() -> None:
    # R049 boundary (c): only deterministic + model_based RUN in MVP.
    assert MVP_ACTIVE_GRADER_TYPES == frozenset({GraderType.DETERMINISTIC, GraderType.MODEL_BASED})
    assert MVP_ACTIVE_GRADER_TYPES < set(GraderType)  # strictly narrower


# --- GraderResult: both 22 §6 row shapes ---------------------------------------


def test_check_style_grader_row_validates() -> None:
    # 22 §6 example: {"type": "deterministic", "name": ..., "passed": true}
    row = GraderResult(type=GraderType.DETERMINISTIC, name="schema_check", passed=True)
    assert row.passed is True
    assert row.score is None
    assert row.confidence is None


def test_judgment_style_grader_row_validates() -> None:
    # 22 §6 example: {"type": "model_based", "name": ..., "score": .., "confidence": ..}
    row = GraderResult(type=GraderType.MODEL_BASED, name="judge", score=0.86, confidence=0.7)
    assert row.passed is None
    assert row.score == 0.86
    assert row.confidence == 0.7


def test_grader_row_must_grade_something() -> None:
    with pytest.raises(ValidationError):
        GraderResult(type=GraderType.DETERMINISTIC, name="empty")


@pytest.mark.parametrize("field", ["score", "confidence"])
@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_grader_judgment_fields_bounded_unit_interval(field: str, bad: float) -> None:
    kwargs: dict[str, Any] = {"type": GraderType.MODEL_BASED, "name": "judge", field: bad}
    with pytest.raises(ValidationError):
        GraderResult(**kwargs)


def test_score_and_confidence_are_independent_fields_never_merged() -> None:
    # 22 §4: two independent facets — one may be present without the other.
    only_score = GraderResult(type=GraderType.MODEL_BASED, name="j", score=0.5)
    only_conf = GraderResult(type=GraderType.MODEL_BASED, name="j", confidence=0.5)
    assert only_score.score == 0.5 and only_score.confidence is None
    assert only_conf.confidence == 0.5 and only_conf.score is None
    # Structural guarantee: no combined "quality" field exists on the shape.
    assert "quality" not in GraderResult.model_fields
    assert {"score", "confidence"} <= set(GraderResult.model_fields)


# --- EvaluationRecord: 03 §7 entity + 22 §6 record -----------------------------


def _judged_row() -> GraderResult:
    return GraderResult(type=GraderType.MODEL_BASED, name="judge", score=0.9, confidence=0.8)


def test_evaluation_record_validates_field_for_field() -> None:
    # 03 §7: id / execution_id / level / score|null / confidence|null /
    # evidence_ref|null / graders (+ tenant_id storage addition, recorded).
    record = EvaluationRecord(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        level=VerificationLevel.EVALUATED,
        score=0.9,
        confidence=0.8,
        evidence_ref="s3://evidence/abc",
        graders=(_judged_row(),),
    )
    assert record.level is VerificationLevel.EVALUATED
    assert record.score == 0.9
    assert record.confidence == 0.8
    assert record.evidence_ref == "s3://evidence/abc"
    assert len(record.graders) == 1


def test_raw_record_carries_no_judgment() -> None:
    # 22 §3: RAW = generated but NOT evaluated.
    record = EvaluationRecord(tenant_id=uuid4(), execution_id=uuid4(), level=VerificationLevel.RAW)
    assert record.score is None
    assert record.confidence is None
    assert record.graders == ()


@pytest.mark.parametrize(
    "extra",
    [
        {"graders": (GraderResult(type=GraderType.DETERMINISTIC, name="c", passed=True),)},
        {"score": 0.5},
        {"confidence": 0.5},
    ],
)
def test_raw_record_rejects_any_judgment_facet(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EvaluationRecord(
            tenant_id=uuid4(),
            execution_id=uuid4(),
            level=VerificationLevel.RAW,
            **extra,
        )


@pytest.mark.parametrize(
    "level",
    [
        VerificationLevel.EVALUATED,
        VerificationLevel.VALIDATED,
        VerificationLevel.VERIFIED,
        VerificationLevel.GOLD,
    ],
)
def test_above_raw_requires_at_least_one_grader(level: VerificationLevel) -> None:
    # 22 §3: EVALUATED means "scored by one or more graders" — an above-RAW
    # record without grader rows claims an evaluation that never happened.
    with pytest.raises(ValidationError):
        EvaluationRecord(tenant_id=uuid4(), execution_id=uuid4(), level=level)


def test_record_score_and_confidence_independently_nullable() -> None:
    # 22 §4 embodied at type level: either facet may be absent.
    record = EvaluationRecord(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        level=VerificationLevel.EVALUATED,
        score=0.7,
        graders=(_judged_row(),),
    )
    assert record.score == 0.7
    assert record.confidence is None
    assert "quality" not in EvaluationRecord.model_fields


@pytest.mark.parametrize("field", ["score", "confidence"])
@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_record_judgment_fields_bounded_unit_interval(field: str, bad: float) -> None:
    kwargs: dict[str, Any] = {
        "tenant_id": uuid4(),
        "execution_id": uuid4(),
        "level": VerificationLevel.EVALUATED,
        "graders": (_judged_row(),),
        field: bad,
    }
    with pytest.raises(ValidationError):
        EvaluationRecord(**kwargs)


# --- Deny-by-default + frozen value objects ------------------------------------


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluationRecord(
            tenant_id=uuid4(),
            execution_id=uuid4(),
            level=VerificationLevel.RAW,
            surprise="nope",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        GraderResult(
            type=GraderType.DETERMINISTIC,
            name="c",
            passed=True,
            surprise="nope",  # type: ignore[call-arg]
        )


def test_instances_are_frozen() -> None:
    record = EvaluationRecord(tenant_id=uuid4(), execution_id=uuid4(), level=VerificationLevel.RAW)
    with pytest.raises(ValidationError):
        record.level = VerificationLevel.GOLD  # type: ignore[misc]
