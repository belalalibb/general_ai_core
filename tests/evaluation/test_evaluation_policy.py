"""Hermetic tests for the evaluation policy service (T-IMPL-030, 41 §46).

Covers the NEXT_TASK matrix recorded at R050: pipeline order, judge-optional
completion, judge-failure containment, aggregation separation (22 §4),
level-assignment matrix including the 22 §12 structural rule, inactive
grader-type denial (R049 boundary (c)), tenant scoping, and append-only
recording. The model judge consumes ProviderAdapterPort FAKES only
(41 §49 NOT-CLAIMED rule — no real provider integration exists).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.contracts.base import JsonObject
from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.evaluation import (
    MVP_DETERMINISTIC_CHECKS,
    AdapterModelJudge,
    DeterministicCheck,
    EvaluationPolicyService,
    InactiveGraderType,
    InMemoryEvaluationStore,
    JudgeFailure,
)

TENANT = uuid4()
EXECUTION = uuid4()

GOOD_OUTPUT: JsonObject = {"result": "done"}
ERROR_OUTPUT: JsonObject = {"result": "partial", "error": "boom"}
EMPTY_OUTPUT: JsonObject = {}


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- fakes ---------------------------------------------------------------------------


class FakeJudge:
    """Scripted ModelJudgePort fake: returns a judgment or raises JudgeFailure."""

    def __init__(
        self,
        *,
        score: float | None = 0.84,
        confidence: float | None = 0.8,
        broken: bool = False,
    ) -> None:
        self.score = score
        self.confidence = confidence
        self.broken = broken
        self.calls: list[tuple[UUID, UUID]] = []

    async def judge(self, tenant_id: UUID, execution_id: UUID, output: JsonObject) -> GraderResult:
        self.calls.append((tenant_id, execution_id))
        if self.broken:
            raise JudgeFailure("scripted judge breakage")
        return GraderResult(
            type=GraderType.MODEL_BASED,
            name="fake_judge",
            score=self.score,
            confidence=self.confidence,
        )


class FakeAdapter:
    """Minimal scripted ProviderAdapterPort fake for AdapterModelJudge tests.

    ``step`` is a dict (success output), a ProviderError (failed call), or
    an Exception instance (adapter raises across the boundary).
    """

    def __init__(self, step: object) -> None:
        self.step = step
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(
            credential_ref=credential_ref, status=CredentialStatus.ACTIVE
        )  # pragma: no cover - unused

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        if isinstance(self.step, Exception):
            raise self.step
        if isinstance(self.step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id, succeeded=False, error=self.step
            )
        assert isinstance(self.step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id, succeeded=True, output=self.step
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="fake",
        )  # pragma: no cover - unused


def _service(
    store: InMemoryEvaluationStore | None = None,
    *,
    judge: FakeJudge | None = None,
    checks: tuple[DeterministicCheck, ...] = MVP_DETERMINISTIC_CHECKS,
) -> tuple[EvaluationPolicyService, InMemoryEvaluationStore]:
    backing = store if store is not None else InMemoryEvaluationStore()
    return (
        EvaluationPolicyService(backing, checks=checks, judge=judge),
        backing,
    )


# --- pipeline order and shape --------------------------------------------------------


class TestPipeline:
    def test_deterministic_rows_come_before_the_judge_row(self) -> None:
        service, _ = _service(judge=FakeJudge())
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        types = [row.type for row in record.graders]
        assert types == [
            GraderType.DETERMINISTIC,
            GraderType.DETERMINISTIC,
            GraderType.MODEL_BASED,
        ]

    def test_recorded_mvp_checks_run_by_name(self) -> None:
        service, _ = _service()
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert [row.name for row in record.graders] == [
            "output_present",
            "error_free_output",
        ]
        assert all(row.passed is True for row in record.graders)

    def test_checks_consume_output_as_data(self) -> None:
        service, _ = _service()
        record = run(service.evaluate(TENANT, EXECUTION, ERROR_OUTPUT))
        by_name = {row.name: row.passed for row in record.graders}
        assert by_name == {"output_present": True, "error_free_output": False}

    def test_record_lands_in_the_store_appended(self) -> None:
        service, store = _service()
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert store.get(TENANT, record.id) == record
        assert store.list_for_execution(TENANT, EXECUTION) == (record,)

    def test_re_evaluation_appends_a_second_record(self) -> None:
        service, store = _service()
        first = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        second = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert first.id != second.id
        assert store.list_for_execution(TENANT, EXECUTION) == (first, second)

    def test_record_is_tenant_scoped(self) -> None:
        service, store = _service()
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.tenant_id == TENANT
        assert store.list_for_execution(uuid4(), EXECUTION) == ()


# --- judge optionality and containment ------------------------------------------------


class TestJudgeOptionality:
    def test_evaluation_completes_without_a_judge(self) -> None:
        service, _ = _service(judge=None)
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.VALIDATED
        assert all(row.type is GraderType.DETERMINISTIC for row in record.graders)

    def test_broken_judge_degrades_to_deterministic_only(self) -> None:
        broken = FakeJudge(broken=True)
        service, _ = _service(judge=broken)
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert broken.calls  # the judge WAS attempted
        assert all(row.type is GraderType.DETERMINISTIC for row in record.graders)
        assert record.level is VerificationLevel.VALIDATED  # never crashes the caller

    def test_judge_receives_tenant_and_execution(self) -> None:
        judge = FakeJudge()
        service, _ = _service(judge=judge)
        run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert judge.calls == [(TENANT, EXECUTION)]


# --- aggregation separation (22 §4) ---------------------------------------------------


class TestAggregation:
    def test_score_and_confidence_come_from_the_judge_untouched(self) -> None:
        service, _ = _service(judge=FakeJudge(score=0.84, confidence=0.74))
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.score == pytest.approx(0.84)
        assert record.confidence == pytest.approx(0.74)

    def test_facets_never_mix_score_aggregates_only_scores(self) -> None:
        # Two judgment rows via a custom check set producing none, plus a
        # judge: only the judge carries judgment facets — aggregation must
        # not blend passed-ness into either number.
        service, _ = _service(judge=FakeJudge(score=1.0, confidence=0.5))
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.score == pytest.approx(1.0)
        assert record.confidence == pytest.approx(0.5)
        assert record.score != record.confidence  # facets remain distinguishable

    def test_deterministic_only_evaluation_has_no_judgment_numbers(self) -> None:
        service, _ = _service()
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.score is None
        assert record.confidence is None
        assert record.evidence_ref is not None  # evidence exists even without a judge


# --- level assignment matrix (22 §3 / 22 §12) -----------------------------------------


class TestLevelAssignment:
    def test_all_checks_pass_plus_confident_judge_reaches_verified(self) -> None:
        service, _ = _service(judge=FakeJudge(score=0.9, confidence=0.9))
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.VERIFIED

    def test_failed_deterministic_check_prevents_verified(self) -> None:
        """22 §12 verbatim rule — enforced positionally via the ladder cap."""
        service, _ = _service(judge=FakeJudge(score=0.99, confidence=0.99))
        record = run(service.evaluate(TENANT, EXECUTION, ERROR_OUTPUT))
        assert record.level is VerificationLevel.EVALUATED
        assert record.level is not VerificationLevel.VERIFIED

    def test_all_checks_pass_without_judge_caps_at_validated(self) -> None:
        service, _ = _service(judge=None)
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.VALIDATED

    def test_low_confidence_judge_stops_below_verified(self) -> None:
        service, _ = _service(judge=FakeJudge(score=0.9, confidence=0.3))
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.VALIDATED

    def test_failed_check_without_judge_is_evaluated(self) -> None:
        service, _ = _service(judge=None)
        record = run(service.evaluate(TENANT, EXECUTION, EMPTY_OUTPUT))
        assert record.level is VerificationLevel.EVALUATED

    def test_gold_is_never_assigned_by_the_pipeline(self) -> None:
        """22 §3: GOLD is APPROVED — an admin act, not a pipeline outcome."""
        service, _ = _service(judge=FakeJudge(score=1.0, confidence=1.0))
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is not VerificationLevel.GOLD
        assert record.level is VerificationLevel.VERIFIED

    def test_no_graders_at_all_yields_honest_raw(self) -> None:
        service, _ = _service(judge=None, checks=())
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.RAW
        assert record.graders == ()
        assert record.score is None and record.confidence is None
        assert record.evidence_ref is None


# --- grader-type boundary (R049 boundary (c)) -----------------------------------------


class TestGraderTypeBoundary:
    @pytest.mark.parametrize(
        "inactive",
        sorted(
            set(GraderType) - {GraderType.DETERMINISTIC, GraderType.MODEL_BASED},
            key=lambda t: t.value,
        ),
    )
    def test_inactive_grader_types_are_denied_loudly(self, inactive: GraderType) -> None:
        service, store = _service(judge=FakeJudge())
        with pytest.raises(InactiveGraderType):
            run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT, grader_types=[inactive]))
        # Denial means NOTHING ran and NOTHING was recorded.
        assert store.list_for_execution(TENANT, EXECUTION) == ()

    def test_mixing_active_and_inactive_is_still_denied(self) -> None:
        service, store = _service()
        with pytest.raises(InactiveGraderType):
            run(
                service.evaluate(
                    TENANT,
                    EXECUTION,
                    GOOD_OUTPUT,
                    grader_types=[GraderType.DETERMINISTIC, GraderType.SECURITY],
                )
            )
        assert store.list_for_execution(TENANT, EXECUTION) == ()

    def test_explicit_deterministic_only_selection_runs(self) -> None:
        judge = FakeJudge()
        service, _ = _service(judge=judge)
        record = run(
            service.evaluate(
                TENANT, EXECUTION, GOOD_OUTPUT, grader_types=[GraderType.DETERMINISTIC]
            )
        )
        assert judge.calls == []  # judge family not selected — not consulted
        assert all(row.type is GraderType.DETERMINISTIC for row in record.graders)


# --- AdapterModelJudge (30 §8.1 seam, fakes only per 41 §49) ---------------------------


class TestAdapterModelJudge:
    def _judge(self, step: object) -> tuple[AdapterModelJudge, FakeAdapter]:
        adapter = FakeAdapter(step)
        return (
            AdapterModelJudge(
                adapter,
                provider_model_name="judge-model",
                credential_ref="cred://opaque",
            ),
            adapter,
        )

    def test_usable_judgment_becomes_a_model_based_row(self) -> None:
        judge, adapter = self._judge({"score": 0.84, "confidence": 0.74})
        row = run(judge.judge(TENANT, EXECUTION, GOOD_OUTPUT))
        assert row.type is GraderType.MODEL_BASED
        assert row.score == pytest.approx(0.84)
        assert row.confidence == pytest.approx(0.74)
        assert row.passed is None
        request = adapter.requests[0]
        assert request.tenant_id == TENANT
        assert request.payload["execution_id"] == str(EXECUTION)
        assert request.payload["output"] == GOOD_OUTPUT

    def test_adapter_raise_becomes_judge_failure(self) -> None:
        judge, _ = self._judge(RuntimeError("socket melted"))
        with pytest.raises(JudgeFailure):
            run(judge.judge(TENANT, EXECUTION, GOOD_OUTPUT))

    def test_failed_call_becomes_judge_failure(self) -> None:
        judge, _ = self._judge(
            ProviderError(
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                safe_message="fake rate limit",
            )
        )
        with pytest.raises(JudgeFailure):
            run(judge.judge(TENANT, EXECUTION, GOOD_OUTPUT))

    @pytest.mark.parametrize(
        "output",
        [
            {},
            {"score": 0.9},
            {"confidence": 0.9},
            {"score": "high", "confidence": 0.9},
            {"score": 1.5, "confidence": 0.9},
            {"score": -0.1, "confidence": 0.9},
            {"score": True, "confidence": 0.9},
        ],
    )
    def test_unusable_judgment_becomes_judge_failure(self, output: JsonObject) -> None:
        judge, _ = self._judge(output)
        with pytest.raises(JudgeFailure):
            run(judge.judge(TENANT, EXECUTION, GOOD_OUTPUT))

    def test_credential_reference_stays_opaque_in_the_request(self) -> None:
        judge, adapter = self._judge({"score": 0.5, "confidence": 0.5})
        run(judge.judge(TENANT, EXECUTION, GOOD_OUTPUT))
        assert adapter.requests[0].credential_ref == "cred://opaque"

    def test_end_to_end_through_the_policy_service(self) -> None:
        adapter = FakeAdapter({"score": 0.9, "confidence": 0.9})
        judge = AdapterModelJudge(
            adapter, provider_model_name="judge-model", credential_ref="cred://opaque"
        )
        store = InMemoryEvaluationStore()
        service = EvaluationPolicyService(store, judge=judge)
        record = run(service.evaluate(TENANT, EXECUTION, GOOD_OUTPUT))
        assert record.level is VerificationLevel.VERIFIED
        assert isinstance(record, EvaluationRecord)
        assert store.list_for_execution(TENANT, EXECUTION) == (record,)
