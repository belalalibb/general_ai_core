"""T-IMPL-064 tests: specialty graders (FINAL Phase 15, 41 §18).

Exit-list mapping (41 §18 build list — the four items MVP left inactive;
the other five — Deterministic / Model / Aggregator / Verification /
Evidence — are pre-existing T-IMPL-029/030 machinery, verified by the
pre-existing test names, never redone):

- "Skill Graders"      -> TestSkillFormatGrader (14 §2 outputs.format vs
  10 §3 result ``type`` agreement; absent declaration passes — no
  fabricated rule).
- "Role Graders"       -> TestRoleContractGrader (key PRESENCE of the
  41 §15 effective output contract, incl. runtime-override effect).
- "Pairwise"           -> TestPairwise (judge seam; ``passed`` means
  PREFERRED; a tie REFUSES — never a fabricated winner).
- "Counter Evaluation" -> TestCounterEvaluator (independent re-judgment;
  passed = agreement within tolerance; score-less record refused).
- Activation boundary  -> TestActivationBoundary (FINAL set = MVP + the
  four; policy service admits them ONLY via injectable ``active_types``;
  MVP default posture unchanged; the remaining four 22 §5 types —
  security/regression/human_calibrated/production_signal — stay DENIED).
- 22 §4 facet separation -> every row asserted below keeps score /
  confidence / passed as separate facets (never merged).

22 §12 learning-side items (feedback-not-truth, training eligibility,
sanitization, shadow/canary promotion, rollback) belong to the doc 22
§8–§11 learning lifecycle, mapped at the Phase 15 exit evaluation
against core/contracts/learning.py — not this grading task.

Hermetic: no network, no I/O — judges are scripted fakes (41 §49).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.contracts.base import JsonObject
from core.contracts.evaluation import (
    MVP_ACTIVE_GRADER_TYPES,
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.role_profile import RoleProfile, RoleRuntimeOverride
from core.contracts.roles import Role
from core.contracts.skills import Skill
from core.evaluation import (
    FINAL_ACTIVE_GRADER_TYPES,
    CounterEvaluator,
    EvaluationPolicyService,
    InactiveGraderType,
    InMemoryEvaluationStore,
    NothingToChallenge,
    PairwiseEvaluator,
    PairwiseTie,
    RoleContractGrader,
    SkillFormatGrader,
)

TENANT = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- builders --------------------------------------------------------------------------


def make_skill(*, outputs_format: str | None = "markdown") -> Skill:
    return Skill.model_validate(
        {
            "id": uuid4(),
            "name": "Code Review",
            "version": "1.0.0",
            "type": "instruction",
            "source": "local",
            "manifest": {
                "id": "code_review",
                "name": "Code Review",
                "version": "1.0.0",
                "type": "instruction",
                "source": "local",
                "status": "active",
                "outputs_format": outputs_format,
            },
            "status": "active",
        }
    )


def make_profile(
    *,
    output_contract: dict[str, Any] | None = None,
    override: RoleRuntimeOverride | None = None,
) -> RoleProfile:
    role = Role.model_validate(
        {
            "id": uuid4(),
            "scope": "system",
            "name": "software_engineer",
            "version": "1.0.0",
            "objective": "Deliver correct, reviewed code changes.",
            "status": "active",
            "output_contract": output_contract if output_contract is not None else {},
        }
    )
    return RoleProfile(role=role, runtime_override=override)


def make_record(
    *,
    score: float | None = 0.8,
    confidence: float | None = 0.7,
) -> EvaluationRecord:
    """A pre-existing judgment to challenge (above-RAW needs >=1 grader)."""
    graders: tuple[GraderResult, ...]
    if score is None and confidence is None:
        graders = (GraderResult(type=GraderType.DETERMINISTIC, name="check", passed=True),)
    else:
        graders = (
            GraderResult(
                type=GraderType.MODEL_BASED,
                name="judge",
                score=score,
                confidence=confidence,
            ),
        )
    return EvaluationRecord(
        tenant_id=TENANT,
        execution_id=uuid4(),
        level=VerificationLevel.EVALUATED,
        score=score,
        confidence=confidence,
        graders=graders,
    )


class FakePairwiseJudge:
    """Scripted PairwiseJudgePort: returns (winner, confidence) or raises."""

    def __init__(
        self,
        *,
        winner: int = 0,
        confidence: float = 0.9,
        tie: bool = False,
    ) -> None:
        self.winner = winner
        self.confidence = confidence
        self.tie = tie
        self.calls: list[tuple[UUID, JsonObject, JsonObject]] = []

    async def prefer(
        self, tenant_id: UUID, output_a: JsonObject, output_b: JsonObject
    ) -> tuple[int, float]:
        self.calls.append((tenant_id, output_a, output_b))
        if self.tie:
            raise PairwiseTie("scripted tie")
        return self.winner, self.confidence


class FakeCounterJudge:
    """Scripted ModelJudgePort for counter evaluation."""

    def __init__(self, *, score: float | None = 0.8, confidence: float | None = 0.9) -> None:
        self.score = score
        self.confidence = confidence
        self.calls: list[tuple[UUID, UUID]] = []

    async def judge(self, tenant_id: UUID, execution_id: UUID, output: JsonObject) -> GraderResult:
        self.calls.append((tenant_id, execution_id))
        if self.score is None and self.confidence is None:
            return GraderResult(type=GraderType.MODEL_BASED, name="counter_judge", passed=True)
        return GraderResult(
            type=GraderType.MODEL_BASED,
            name="counter_judge",
            score=self.score,
            confidence=self.confidence,
        )


# --- skill grader (41 §18 "Skill Graders") ---------------------------------------------


class TestSkillFormatGrader:
    def test_agreement_passes(self) -> None:
        row = SkillFormatGrader(make_skill(outputs_format="markdown")).row(
            {"type": "markdown", "content": "# ok"}
        )
        assert row.type is GraderType.SKILL_SPECIFIC
        assert row.passed is True

    def test_disagreement_fails(self) -> None:
        row = SkillFormatGrader(make_skill(outputs_format="markdown")).row(
            {"type": "json", "content": "{}"}
        )
        assert row.passed is False

    def test_missing_type_field_fails_when_format_declared(self) -> None:
        row = SkillFormatGrader(make_skill(outputs_format="markdown")).row(
            {"content": "no type key"}
        )
        assert row.passed is False

    def test_no_declared_format_passes(self) -> None:
        """A skill that declares no format has no requirement to violate."""
        row = SkillFormatGrader(make_skill(outputs_format=None)).row({"type": "anything"})
        assert row.passed is True

    def test_row_names_the_manifest_id(self) -> None:
        row = SkillFormatGrader(make_skill()).row({"type": "markdown"})
        assert row.name == "skill_output_format:code_review"

    def test_row_is_a_pure_check_facet(self) -> None:
        """22 §4: a format check is pass/fail — no fabricated score/confidence."""
        row = SkillFormatGrader(make_skill()).row({"type": "markdown"})
        assert row.score is None
        assert row.confidence is None


# --- role grader (41 §18 "Role Graders") ------------------------------------------------


class TestRoleContractGrader:
    def test_all_contract_keys_present_passes(self) -> None:
        profile = make_profile(output_contract={"summary": "required", "diff": {}})
        row = RoleContractGrader(profile).row({"summary": "s", "diff": "d", "x": 1})
        assert row.type is GraderType.ROLE_SPECIFIC
        assert row.passed is True

    def test_missing_contract_key_fails(self) -> None:
        profile = make_profile(output_contract={"summary": "required", "diff": {}})
        row = RoleContractGrader(profile).row({"summary": "s"})
        assert row.passed is False

    def test_empty_contract_requires_nothing(self) -> None:
        row = RoleContractGrader(make_profile()).row({})
        assert row.passed is True

    def test_runtime_override_extends_the_checked_contract(self) -> None:
        """The grader checks the EFFECTIVE contract — override keys count."""
        profile = make_profile(
            output_contract={"summary": "required"},
            override=RoleRuntimeOverride(output_contract={"risk_note": "required"}),
        )
        without_override_key = RoleContractGrader(profile).row({"summary": "s"})
        assert without_override_key.passed is False
        with_both = RoleContractGrader(profile).row({"summary": "s", "risk_note": "low"})
        assert with_both.passed is True

    def test_row_names_the_role(self) -> None:
        row = RoleContractGrader(make_profile()).row({})
        assert row.name == "role_output_contract:software_engineer"

    def test_row_is_a_pure_check_facet(self) -> None:
        row = RoleContractGrader(make_profile()).row({})
        assert row.score is None
        assert row.confidence is None


# --- pairwise (41 §18 "Pairwise") --------------------------------------------------------


class TestPairwise:
    def test_winner_zero_marks_first_candidate_preferred(self) -> None:
        decision = run(
            PairwiseEvaluator(FakePairwiseJudge(winner=0)).compare(TENANT, {"a": 1}, {"b": 2})
        )
        assert decision.winner_index == 0
        assert decision.rows[0].passed is True
        assert decision.rows[1].passed is False

    def test_winner_one_marks_second_candidate_preferred(self) -> None:
        decision = run(
            PairwiseEvaluator(FakePairwiseJudge(winner=1)).compare(TENANT, {"a": 1}, {"b": 2})
        )
        assert decision.winner_index == 1
        assert decision.rows[0].passed is False
        assert decision.rows[1].passed is True

    def test_confidence_rides_both_rows(self) -> None:
        """The judge's trust facet applies to the COMPARISON — both rows."""
        decision = run(
            PairwiseEvaluator(FakePairwiseJudge(winner=0, confidence=0.65)).compare(TENANT, {}, {})
        )
        assert decision.rows[0].confidence == 0.65
        assert decision.rows[1].confidence == 0.65

    def test_rows_carry_no_fabricated_score(self) -> None:
        """22 §4: preference is a check facet; no score is invented."""
        decision = run(PairwiseEvaluator(FakePairwiseJudge()).compare(TENANT, {}, {}))
        assert decision.rows[0].score is None
        assert decision.rows[1].score is None

    def test_rows_are_pairwise_typed_and_named_per_candidate(self) -> None:
        decision = run(PairwiseEvaluator(FakePairwiseJudge()).compare(TENANT, {}, {}))
        assert all(row.type is GraderType.PAIRWISE for row in decision.rows)
        assert decision.rows[0].name == "pairwise:candidate_0"
        assert decision.rows[1].name == "pairwise:candidate_1"

    def test_tie_refuses_loudly(self) -> None:
        """A tie is a refusal, never a fabricated winner."""
        with pytest.raises(PairwiseTie):
            run(PairwiseEvaluator(FakePairwiseJudge(tie=True)).compare(TENANT, {}, {}))

    @pytest.mark.parametrize("bad_winner", [-1, 2, 7])
    def test_invalid_winner_index_is_a_judge_error(self, bad_winner: int) -> None:
        with pytest.raises(ValueError, match="invalid winner index"):
            run(PairwiseEvaluator(FakePairwiseJudge(winner=bad_winner)).compare(TENANT, {}, {}))

    def test_judge_receives_both_candidates(self) -> None:
        judge = FakePairwiseJudge()
        run(PairwiseEvaluator(judge).compare(TENANT, {"a": 1}, {"b": 2}))
        assert judge.calls == [(TENANT, {"a": 1}, {"b": 2})]


# --- counter evaluation (41 §18 "Counter Evaluation") ------------------------------------


class TestCounterEvaluator:
    def test_agreement_within_tolerance_upholds(self) -> None:
        record = make_record(score=0.8)
        row = run(
            CounterEvaluator(FakeCounterJudge(score=0.7), tolerance=0.2).challenge(
                record, {"type": "markdown"}
            )
        )
        assert row.type is GraderType.COUNTER_EVALUATION
        assert row.passed is True

    def test_disagreement_beyond_tolerance_challenges(self) -> None:
        record = make_record(score=0.9)
        row = run(
            CounterEvaluator(FakeCounterJudge(score=0.3), tolerance=0.2).challenge(record, {})
        )
        assert row.passed is False

    def test_boundary_agreement_exactly_at_tolerance_upholds(self) -> None:
        record = make_record(score=0.8)
        row = run(
            CounterEvaluator(FakeCounterJudge(score=0.6), tolerance=0.2).challenge(record, {})
        )
        assert row.passed is True

    def test_counter_row_carries_the_independent_judgment_facets(self) -> None:
        """The row records what the COUNTER judge found — both facets, separate."""
        record = make_record(score=0.8)
        row = run(
            CounterEvaluator(FakeCounterJudge(score=0.75, confidence=0.6)).challenge(record, {})
        )
        assert row.score == 0.75
        assert row.confidence == 0.6

    def test_scoreless_counter_judgment_cannot_uphold(self) -> None:
        """A counter judge that produced no score agrees with nothing."""
        record = make_record(score=0.8)
        row = run(
            CounterEvaluator(FakeCounterJudge(score=None, confidence=None)).challenge(record, {})
        )
        assert row.passed is False

    def test_scoreless_record_is_refused(self) -> None:
        """Nothing exists to challenge — caller error, never graded."""
        record = make_record(score=None, confidence=None)
        with pytest.raises(NothingToChallenge):
            run(CounterEvaluator(FakeCounterJudge()).challenge(record, {}))

    @pytest.mark.parametrize("bad_tolerance", [-0.1, 1.1, 5.0])
    def test_out_of_range_tolerance_is_refused(self, bad_tolerance: float) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            CounterEvaluator(FakeCounterJudge(), tolerance=bad_tolerance)

    def test_judge_is_called_with_the_record_identity(self) -> None:
        judge = FakeCounterJudge()
        record = make_record(score=0.8)
        run(CounterEvaluator(judge).challenge(record, {}))
        assert judge.calls == [(record.tenant_id, record.execution_id)]


# --- activation boundary (FINAL_ACTIVE_GRADER_TYPES + injectable active_types) -----------


FINAL_NEW_TYPES = frozenset(
    {
        GraderType.PAIRWISE,
        GraderType.SKILL_SPECIFIC,
        GraderType.ROLE_SPECIFIC,
        GraderType.COUNTER_EVALUATION,
    }
)
STILL_INACTIVE_TYPES = frozenset(
    {
        GraderType.SECURITY,
        GraderType.REGRESSION,
        GraderType.HUMAN_CALIBRATED,
        GraderType.PRODUCTION_SIGNAL,
    }
)


class TestActivationBoundary:
    def test_final_set_is_mvp_plus_the_four_41s18_items(self) -> None:
        assert FINAL_ACTIVE_GRADER_TYPES == MVP_ACTIVE_GRADER_TYPES | FINAL_NEW_TYPES

    def test_final_set_leaves_the_undocumented_four_inactive(self) -> None:
        assert FINAL_ACTIVE_GRADER_TYPES & STILL_INACTIVE_TYPES == frozenset()

    def test_all_ten_22s5_types_are_accounted_for(self) -> None:
        """FINAL-active + still-inactive partitions the whole 22 §5 enum."""
        assert FINAL_ACTIVE_GRADER_TYPES | STILL_INACTIVE_TYPES == frozenset(GraderType)

    @pytest.mark.parametrize("new_type", sorted(FINAL_NEW_TYPES, key=lambda t: t.value))
    def test_final_service_admits_each_newly_active_type(self, new_type: GraderType) -> None:
        service = EvaluationPolicyService(
            InMemoryEvaluationStore(), active_types=FINAL_ACTIVE_GRADER_TYPES
        )
        # Admission must not raise; the pipeline itself runs only its
        # deterministic/model steps, so a specialty-only request lands RAW.
        record = run(service.evaluate(TENANT, uuid4(), {"x": 1}, grader_types={new_type}))
        assert record.level is VerificationLevel.RAW

    @pytest.mark.parametrize("inactive_type", sorted(STILL_INACTIVE_TYPES, key=lambda t: t.value))
    def test_final_service_still_denies_the_undocumented_types(
        self, inactive_type: GraderType
    ) -> None:
        service = EvaluationPolicyService(
            InMemoryEvaluationStore(), active_types=FINAL_ACTIVE_GRADER_TYPES
        )
        with pytest.raises(InactiveGraderType):
            run(service.evaluate(TENANT, uuid4(), {"x": 1}, grader_types={inactive_type}))

    def test_default_service_keeps_the_mvp_posture(self) -> None:
        """No active_types given -> MVP boundary unchanged (R049 (c))."""
        service = EvaluationPolicyService(InMemoryEvaluationStore())
        with pytest.raises(InactiveGraderType):
            run(service.evaluate(TENANT, uuid4(), {"x": 1}, grader_types={GraderType.PAIRWISE}))

    def test_final_default_request_still_runs_the_pipeline(self) -> None:
        """grader_types=None under the FINAL set: deterministic step runs."""
        service = EvaluationPolicyService(
            InMemoryEvaluationStore(), active_types=FINAL_ACTIVE_GRADER_TYPES
        )
        record = run(service.evaluate(TENANT, uuid4(), {"x": 1}))
        names = [row.name for row in record.graders]
        assert names == ["output_present", "error_free_output"]
        assert record.level is VerificationLevel.VALIDATED


# --- hermeticity guard --------------------------------------------------------------------


def test_graders_module_performs_no_io() -> None:
    """41 §49: the graders are pure — no network/process modules anywhere."""
    import inspect

    import core.evaluation.graders as graders_module

    source = inspect.getsource(graders_module)
    for forbidden in ("httpx", "requests", "urllib", "socket", "aiohttp", "subprocess"):
        assert forbidden not in source
