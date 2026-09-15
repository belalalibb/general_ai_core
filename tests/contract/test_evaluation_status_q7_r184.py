"""R184 / Q7 option (a) — the closed ``EvaluationStatus`` set.

Operator-accepted direction (R183 closing report, R184-DEC-01): an ADDITIVE
``evaluation_status`` on the execution admin read with exactly the closed
values ``NEVER_EVALUATED | EVALUATED``. Semantics derive from 22 §3 verbatim:
RAW = "Generated but not evaluated", EVALUATED = "Scored by one or more
graders" — so an execution is EVALUATED iff at least one stored record sits
ABOVE RAW on the ladder; otherwise NEVER_EVALUATED. Written RED before the
contract edit (first act of R184).
"""

from __future__ import annotations

from uuid import uuid4

from core.contracts.evaluation import (
    EvaluationRecord,
    EvaluationStatus,
    GraderResult,
    GraderType,
    VerificationLevel,
    evaluation_status_of,
)


def test_evaluation_status_is_the_accepted_closed_set_exactly() -> None:
    assert {s.value for s in EvaluationStatus} == {"NEVER_EVALUATED", "EVALUATED"}
    assert EvaluationStatus.NEVER_EVALUATED.value == "NEVER_EVALUATED"
    assert EvaluationStatus.EVALUATED.value == "EVALUATED"


def test_no_records_means_never_evaluated() -> None:
    assert evaluation_status_of(()) is EvaluationStatus.NEVER_EVALUATED


def test_only_raw_records_means_never_evaluated() -> None:
    """22 §3: RAW = generated but NOT evaluated — a RAW row is not an evaluation."""
    raw = EvaluationRecord(tenant_id=uuid4(), execution_id=uuid4(), level=VerificationLevel.RAW)
    assert evaluation_status_of((raw,)) is EvaluationStatus.NEVER_EVALUATED
    assert evaluation_status_of((raw, raw)) is EvaluationStatus.NEVER_EVALUATED


def test_any_record_above_raw_means_evaluated() -> None:
    """22 §3: EVALUATED = scored by one or more graders (validator enforces >=1 grader)."""
    grader = GraderResult(type=GraderType.DETERMINISTIC, name="schema_check", passed=True)
    tenant, execution = uuid4(), uuid4()
    raw = EvaluationRecord(tenant_id=tenant, execution_id=execution, level=VerificationLevel.RAW)
    for level in (
        VerificationLevel.EVALUATED,
        VerificationLevel.VALIDATED,
        VerificationLevel.VERIFIED,
        VerificationLevel.GOLD,
    ):
        graded = EvaluationRecord(
            tenant_id=tenant, execution_id=execution, level=level, graders=(grader,)
        )
        assert evaluation_status_of((raw, graded)) is EvaluationStatus.EVALUATED
        assert evaluation_status_of((graded,)) is EvaluationStatus.EVALUATED
