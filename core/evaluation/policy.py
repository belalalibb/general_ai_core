"""Evaluation policy service (MVP Phase 7 slice 2, 41 §46, T-IMPL-030).

Implements the 22 §2 pipeline IN ORDER::

    Execution Trace
    ↓
    Evaluation Policy
    ↓
    Deterministic Graders        (step 1 — cheap checks, always first)
    + Model Graders              (step 2 — OPTIONAL model judge seam)
    ↓
    Aggregator                   (step 3 — score + confidence + evidence)
    ↓
    Score + Confidence + Evidence
    ↓
    Verification Level           (step 4 — positions in VERIFICATION_LEVEL_ORDER)

Recorded MVP deterministic checks (concrete, consuming execution output
as DATA — chosen for this slice and recorded here per the task ruling):

- ``output_present``    — the execution produced a NON-EMPTY output
  object. An empty output cannot satisfy any request, so it fails the
  cheapest possible check before any model is consulted.
- ``error_free_output`` — the output does not self-report failure via an
  ``"error"`` key. An output that carries its own error marker is not a
  clean result regardless of how a judge might score its prose.

Model judge is OPTIONAL (41 §46 "basic evaluation policy (deterministic
checks + optional model judge)" — verbatim): evaluation MUST complete on
deterministic graders alone, and a BROKEN judge degrades the evaluation
to deterministic-only rather than crashing the caller. The judge seam
consumes the EXISTING :class:`~core.providers.ports.ProviderAdapterPort`
(30 §8.1) — tests use fakes per the 41 §49 NOT-CLAIMED rule (no real
provider integration exists yet).

Level assignment is STRUCTURAL (22 §3 definitions + 22 §12 test rule):
the service computes an ACHIEVED rung and a CAP rung as indices into
``VERIFICATION_LEVEL_ORDER`` and takes the minimum — "a failed
deterministic check prevents the VERIFIED level" (22 §12) falls out of
the cap being EVALUATED, which sits BELOW VERIFIED in the ladder; it is
never an ad-hoc ``if`` on the final answer. A judge-absent evaluation is
capped below VERIFIED because 22 §3 defines VERIFIED as "has sufficient
evidence/confidence" and confidence is a judgment-trust number (22 §4)
that only judgment-style graders produce. GOLD is NEVER assigned by this
pipeline: 22 §3 defines it as "APPROVED as high-quality reference
sample" — approval is a human/admin act, not a pipeline outcome.

Grader-type boundary (R049 boundary (c)): the ADMITTED set is DATA —
the injectable ``active_types`` (default ``MVP_ACTIVE_GRADER_TYPES``, so
every recorded MVP posture keeps holding; FINAL Phase 15 / T-IMPL-064
widens it via ``core.evaluation.graders.FINAL_ACTIVE_GRADER_TYPES``).
A request naming any type OUTSIDE the admitted set is DENIED loudly with
:class:`InactiveGraderType` — never silently skipped (silent skipping
would fake coverage that never ran).

22 §7 user visibility (scores never in user-facing responses) binds at
the API surface in T-IMPL-032, not here — this service is admin-side
machinery producing evidence records.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import fmean
from typing import Protocol
from uuid import UUID, uuid4

from core.contracts.base import JsonObject
from core.contracts.evaluation import (
    MVP_ACTIVE_GRADER_TYPES,
    VERIFICATION_LEVEL_ORDER,
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.provider import ProviderGenerateRequest, ProviderOperation
from core.evaluation.errors import InactiveGraderType, JudgeFailure
from core.evaluation.ports import EvaluationStorePort
from core.providers.ports import ProviderAdapterPort

# --- deterministic graders (step 1) ------------------------------------------------


@dataclass(frozen=True)
class DeterministicCheck:
    """One named, pure, cheap check over execution output (22 §5 deterministic).

    The predicate consumes the execution output as DATA and returns
    pass/fail — a check either holds or it doesn't (22 §6 row shape).
    """

    name: str
    predicate: Callable[[JsonObject], bool]


def _output_present(output: JsonObject) -> bool:
    return bool(output)


def _error_free_output(output: JsonObject) -> bool:
    return "error" not in output


#: The recorded MVP check set (module docstring) — injectable for tests,
#: but this tuple is the default policy shipped by this slice.
MVP_DETERMINISTIC_CHECKS: tuple[DeterministicCheck, ...] = (
    DeterministicCheck(name="output_present", predicate=_output_present),
    DeterministicCheck(name="error_free_output", predicate=_error_free_output),
)


# --- model judge seam (step 2, optional) --------------------------------------------


class ModelJudgePort(Protocol):
    """Optional judgment-style grader seam (22 §5 model_based).

    Returns ONE judgment-style :class:`GraderResult` (score + confidence,
    kept separate per 22 §4). Any failure raises :class:`JudgeFailure`;
    the policy service CONTAINS that failure (degrade, never crash).
    """

    async def judge(
        self, tenant_id: UUID, execution_id: UUID, output: JsonObject
    ) -> GraderResult:
        """Judge one execution output; raise ``JudgeFailure`` on any problem."""
        ...


class AdapterModelJudge:
    """Model judge over the EXISTING ProviderAdapterPort (30 §8.1).

    Builds a normalized :class:`ProviderGenerateRequest` carrying the
    execution output as payload data, and expects the judge model to
    answer with ``{"score": <0..1>, "confidence": <0..1>}`` — two numbers,
    never one (22 §4). ``credential_ref`` stays an opaque reference
    end-to-end (20 §5): this class never logs, echoes, or resolves it.

    EVERY failure mode — adapter raise, normalized provider error,
    missing/out-of-range judgment fields — becomes :class:`JudgeFailure`
    so the policy service has exactly ONE containment point.
    """

    def __init__(
        self,
        adapter: ProviderAdapterPort,
        *,
        provider_model_name: str,
        credential_ref: str,
        judge_name: str = "model_judge",
        timeout_ms: int | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._adapter = adapter
        self._provider_model_name = provider_model_name
        self._credential_ref = credential_ref
        self._judge_name = judge_name
        self._timeout_ms = timeout_ms
        self._id_factory = id_factory

    async def judge(
        self, tenant_id: UUID, execution_id: UUID, output: JsonObject
    ) -> GraderResult:
        request = ProviderGenerateRequest(
            request_id=self._id_factory(),
            tenant_id=tenant_id,
            operation=ProviderOperation.GENERATE_TEXT,
            provider_model_name=self._provider_model_name,
            credential_ref=self._credential_ref,
            payload={
                "task": "evaluation_judgment",
                "execution_id": str(execution_id),
                "output": output,
            },
            timeout_ms=self._timeout_ms,
        )
        try:
            response = await self._adapter.generate(request)
        except Exception as exc:  # noqa: BLE001 — boundary containment (30 §14)
            raise JudgeFailure("judge adapter raised") from exc
        if not response.succeeded:
            raise JudgeFailure("judge call failed")
        score = _unit_interval(response.output.get("score"))
        confidence = _unit_interval(response.output.get("confidence"))
        if score is None or confidence is None:
            raise JudgeFailure("judge returned no usable score/confidence")
        return GraderResult(
            type=GraderType.MODEL_BASED,
            name=self._judge_name,
            score=score,
            confidence=confidence,
        )


def _unit_interval(value: object) -> float | None:
    """Accept only a real number in [0, 1]; anything else is unusable."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if 0.0 <= number <= 1.0:
        return number
    return None


# --- the policy service --------------------------------------------------------------


class EvaluationPolicyService:
    """The 22 §2 pipeline as a service; every judgment lands as evidence.

    Records always land through :class:`EvaluationStorePort` — append-only
    (re-evaluating an execution APPENDS a new record; history is never
    rewritten). ``verified_confidence_threshold`` is the 22 §3 VERIFIED
    bar ("has sufficient evidence/confidence") made explicit and
    injectable rather than buried in code.
    """

    def __init__(
        self,
        store: EvaluationStorePort,
        *,
        checks: tuple[DeterministicCheck, ...] = MVP_DETERMINISTIC_CHECKS,
        judge: ModelJudgePort | None = None,
        active_types: frozenset[GraderType] = MVP_ACTIVE_GRADER_TYPES,
        verified_confidence_threshold: float = 0.75,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._checks = checks
        self._judge = judge
        self._active_types = active_types
        self._verified_confidence_threshold = verified_confidence_threshold
        self._id_factory = id_factory

    async def evaluate(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        output: JsonObject,
        *,
        grader_types: Iterable[GraderType] | None = None,
    ) -> EvaluationRecord:
        """Run the pipeline over one execution output and record the result.

        ``grader_types`` selects which ACTIVE grader families run
        (default: the service's whole admitted set). Naming any type
        outside the admitted set raises :class:`InactiveGraderType` —
        denied loudly, never silently skipped.
        """
        requested = self._admitted_grader_types(grader_types)

        # Step 1 — deterministic graders FIRST (cheap checks).
        rows: list[GraderResult] = []
        if GraderType.DETERMINISTIC in requested:
            rows.extend(self._run_checks(output))

        # Step 2 — OPTIONAL model judge; a broken judge degrades to
        # deterministic-only (contained here, the single containment point).
        if GraderType.MODEL_BASED in requested and self._judge is not None:
            try:
                rows.append(await self._judge.judge(tenant_id, execution_id, output))
            except JudgeFailure:
                pass  # degrade: evaluation completes on deterministic graders alone

        # Step 3 — aggregation: score and confidence stay SEPARATE (22 §4).
        score, confidence = _aggregate(rows)

        # Step 4 — level assignment via ladder positions (structural).
        level = self._assign_level(rows, confidence)

        record_id = self._id_factory()
        record = EvaluationRecord(
            id=record_id,
            tenant_id=tenant_id,
            execution_id=execution_id,
            level=level,
            score=score if level is not VerificationLevel.RAW else None,
            confidence=confidence if level is not VerificationLevel.RAW else None,
            evidence_ref=(
                f"object://evidence/{record_id}"
                if level is not VerificationLevel.RAW
                else None
            ),
            graders=tuple(rows),
        )
        return self._store.record(record)

    # --- pipeline steps ---------------------------------------------------------------

    def _admitted_grader_types(
        self,
        grader_types: Iterable[GraderType] | None,
    ) -> frozenset[GraderType]:
        if grader_types is None:
            return self._active_types
        requested = frozenset(grader_types)
        inactive = requested - self._active_types
        if inactive:
            raise InactiveGraderType(sorted(t.value for t in inactive))
        return requested

    def _run_checks(self, output: JsonObject) -> list[GraderResult]:
        return [
            GraderResult(
                type=GraderType.DETERMINISTIC,
                name=check.name,
                passed=check.predicate(output),
            )
            for check in self._checks
        ]

    def _assign_level(
        self, rows: list[GraderResult], confidence: float | None
    ) -> VerificationLevel:
        """Ladder-position arithmetic over VERIFICATION_LEVEL_ORDER (22 §3).

        ``achieved`` climbs on evidence; ``cap`` descends on disqualifiers;
        the answer is the lower rung. The 22 §12 rule ("failed
        deterministic check prevents VERIFIED") is the EVALUATED cap —
        EVALUATED < VERIFIED in the ladder, so prevention is positional,
        not a special case.
        """
        order = VERIFICATION_LEVEL_ORDER
        if not rows:
            # Nothing graded anything: honestly RAW (22 §3 — "generated
            # but not evaluated"), never a fabricated EVALUATED.
            return VerificationLevel.RAW

        checks = [row for row in rows if row.passed is not None]
        all_checks_passed = all(row.passed for row in checks)

        # Pipeline ceiling: GOLD requires approval (22 §3) — never assigned here.
        cap = order.index(VerificationLevel.VERIFIED)
        if not all_checks_passed:
            # 22 §12: failed deterministic check prevents VERIFIED (and,
            # positionally, VALIDATED — "passed required checks" is false).
            cap = min(cap, order.index(VerificationLevel.EVALUATED))
        if confidence is None:
            # No judgment-trust evidence: 22 §3 VERIFIED ("sufficient
            # evidence/confidence") is out of reach without a judge.
            cap = min(cap, order.index(VerificationLevel.VALIDATED))

        achieved = order.index(VerificationLevel.EVALUATED)
        if checks and all_checks_passed:
            achieved = order.index(VerificationLevel.VALIDATED)
        if (
            confidence is not None
            and confidence >= self._verified_confidence_threshold
        ):
            achieved = order.index(VerificationLevel.VERIFIED)

        return order[min(achieved, cap)]


def _aggregate(rows: list[GraderResult]) -> tuple[float | None, float | None]:
    """Aggregate judgment facets ACROSS rows — never with each other (22 §4).

    Score aggregates only scores; confidence aggregates only confidences.
    No arithmetic ever mixes the two facets, so "never merge them into
    one number" survives aggregation structurally.
    """
    scores = [row.score for row in rows if row.score is not None]
    confidences = [row.confidence for row in rows if row.confidence is not None]
    score = fmean(scores) if scores else None
    confidence = fmean(confidences) if confidences else None
    return score, confidence
