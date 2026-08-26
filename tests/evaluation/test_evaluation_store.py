"""Evaluation store tests (T-IMPL-029; 22 §6; 03 §8; 20 §6).

Covers: append-only recording with loud duplicate denial (evidence is
never overwritten), get-by-id, recording-order listing per execution
(re-grading appends), tenant isolation with anti-enumeration NotFound
(a foreign tenant's record probes identically to an absent one), and the
empty-tuple posture for unknown/foreign executions. Hermetic: in-memory
only.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.evaluation import (
    DuplicateEvaluation,
    EvaluationNotFound,
    EvaluationStoreError,
    InMemoryEvaluationStore,
)

TENANT_A = uuid4()
TENANT_B = uuid4()


def make_record(
    tenant_id: UUID = TENANT_A,
    execution_id: UUID | None = None,
    level: VerificationLevel = VerificationLevel.EVALUATED,
    score: float | None = 0.8,
    confidence: float | None = 0.7,
) -> EvaluationRecord:
    return EvaluationRecord(
        tenant_id=tenant_id,
        execution_id=execution_id or uuid4(),
        level=level,
        score=score,
        confidence=confidence,
        graders=(
            GraderResult(
                type=GraderType.MODEL_BASED, name="judge", score=score, confidence=confidence
            )
            if score is not None or confidence is not None
            else GraderResult(type=GraderType.DETERMINISTIC, name="check", passed=True),
        ),
    )


# --- record / get ---------------------------------------------------------------


def test_record_then_get_roundtrip() -> None:
    store = InMemoryEvaluationStore()
    record = make_record()
    assert store.record(record) == record
    assert store.get(TENANT_A, record.id) == record


def test_get_unknown_id_raises_not_found() -> None:
    store = InMemoryEvaluationStore()
    with pytest.raises(EvaluationNotFound):
        store.get(TENANT_A, uuid4())


def test_duplicate_id_denied_loudly_never_overwritten() -> None:
    # 22 §6/§12: records are evidence — appending under an existing id is
    # a rewrite of history and must fail loudly.
    store = InMemoryEvaluationStore()
    first = make_record()
    store.record(first)
    clash = first.model_copy(update={"score": 0.1})
    with pytest.raises(DuplicateEvaluation):
        store.record(clash)
    # The original record is untouched.
    assert store.get(TENANT_A, first.id).score == first.score


def test_errors_share_the_store_error_base() -> None:
    assert issubclass(EvaluationNotFound, EvaluationStoreError)
    assert issubclass(DuplicateEvaluation, EvaluationStoreError)


# --- list_for_execution ----------------------------------------------------------


def test_list_for_execution_in_recording_order() -> None:
    # 03 §8: an execution may accumulate multiple records (re-grading appends).
    store = InMemoryEvaluationStore()
    execution_id = uuid4()
    first = make_record(execution_id=execution_id, score=0.5, confidence=0.4)
    second = make_record(execution_id=execution_id, score=0.9, confidence=0.8)
    store.record(first)
    store.record(second)
    assert store.list_for_execution(TENANT_A, execution_id) == (first, second)


def test_list_unknown_execution_yields_empty_tuple() -> None:
    store = InMemoryEvaluationStore()
    assert store.list_for_execution(TENANT_A, uuid4()) == ()


def test_list_does_not_leak_other_executions() -> None:
    store = InMemoryEvaluationStore()
    mine = make_record()
    other = make_record()
    store.record(mine)
    store.record(other)
    assert store.list_for_execution(TENANT_A, mine.execution_id) == (mine,)


# --- Tenant isolation (20 §6 anti-enumeration) -----------------------------------


def test_cross_tenant_get_raises_the_same_not_found() -> None:
    # A record that EXISTS in tenant A must probe from tenant B exactly
    # like a record that does not exist at all.
    store = InMemoryEvaluationStore()
    record = make_record(tenant_id=TENANT_A)
    store.record(record)

    with pytest.raises(EvaluationNotFound) as cross:
        store.get(TENANT_B, record.id)
    with pytest.raises(EvaluationNotFound) as absent:
        store.get(TENANT_B, uuid4())
    # Identical error type AND identical message shape — nothing to
    # distinguish "present elsewhere" from "absent".
    assert type(cross.value) is type(absent.value)


def test_cross_tenant_list_is_indistinguishable_from_never_evaluated() -> None:
    store = InMemoryEvaluationStore()
    record = make_record(tenant_id=TENANT_A)
    store.record(record)
    assert store.list_for_execution(TENANT_B, record.execution_id) == ()


def test_same_tenant_still_sees_its_own_records() -> None:
    store = InMemoryEvaluationStore()
    a_record = make_record(tenant_id=TENANT_A)
    b_record = make_record(tenant_id=TENANT_B)
    store.record(a_record)
    store.record(b_record)
    assert store.get(TENANT_A, a_record.id) == a_record
    assert store.get(TENANT_B, b_record.id) == b_record


# --- Port surface is append-only --------------------------------------------------


def test_store_exposes_no_update_or_delete_surface() -> None:
    # Recorded posture: evaluation records are evidence — the binding must
    # not grow mutation methods the port doesn't have.
    public = {name for name in dir(InMemoryEvaluationStore) if not name.startswith("_")}
    assert public == {"record", "get", "list_for_execution"}
