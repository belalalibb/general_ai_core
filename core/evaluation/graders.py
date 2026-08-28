"""Specialty graders — FINAL Phase 15 (41 §18, T-IMPL-064).

Spec anchors:

- 41 §18 build list: "Pairwise / Skill Graders / Role Graders / Counter
  Evaluation" (the four 22 §5 grader types the MVP left representable-
  but-inactive, R049 boundary (c) — this phase activates them).
- 22 §4: score/confidence never merged — every row here keeps them as
  separate facets (or uses ``passed``, the check facet).
- 22 §5 names the types without interfaces — every mechanism below is
  DERIVED from existing contracts, with the derivation recorded:

Recorded derivations (nothing invented silently):

- SKILL GRADER (``skill_specific``): the only output requirement a Skill
  DECLARES anywhere is the 14 §2 manifest's ``outputs.format`` hint
  (e.g. ``markdown``), and the only output shape carrying a format is the
  10 §3 result object's ``type`` field. The grader checks they AGREE —
  a pure cross-contract data check. A skill that declares no format has
  no requirement to violate: passed=True (grading an absent requirement
  as failure would fabricate a rule).
- ROLE GRADER (``role_specific``): the Role's output requirement is the
  41 §15 profile's effective output contract — OPAQUE JSON no spec gives
  structure to. The only structure-free check possible is key PRESENCE:
  every key the contract names must exist in the output. Deeper
  semantics are policy data for a later authority; inventing them here
  would fabricate contract structure. An empty contract requires nothing.
- PAIRWISE (``pairwise``): comparing two candidate outputs is inherently
  a judgment, so the comparator is a SEAM (PairwiseJudgePort, same
  posture as ModelJudgePort — no real model integration claimed, 41 §49).
  The decision carries one row per candidate: ``passed`` means PREFERRED
  (the check facet is the honest carrier for a binary preference);
  judge confidence rides both rows as the trust facet. The judge must
  pick a side — a tie is a refusal (PairwiseTie), never a fabricated
  winner (same posture as the preference-learning tie rule).
- COUNTER EVALUATION (``counter_evaluation``): 22 §5 names the type; the
  purpose derivable from doc 22's trust ladder is to CHALLENGE an
  existing judgment with an INDEPENDENT one. The only structure-free
  challenge over two judgments is agreement-within-tolerance:
  passed = |counter_score − original_score| <= tolerance. Challenging a
  record that carries no score is a caller error (nothing exists to
  challenge) — refused loudly, never graded.

Activation: FINAL_ACTIVE_GRADER_TYPES widens the admitted set; the
EvaluationPolicyService takes it via its (new, injectable) ``active_types``
— MVP_ACTIVE_GRADER_TYPES stays the default so every recorded MVP posture
and test keeps holding. security/regression/human_calibrated/
production_signal remain representable-but-inactive: 41 §18 does not list
them, and no doc defines their mechanism (recorded, not skipped silently —
naming one still raises InactiveGraderType).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from core.contracts.base import JsonObject
from core.contracts.evaluation import (
    MVP_ACTIVE_GRADER_TYPES,
    EvaluationRecord,
    GraderResult,
    GraderType,
)
from core.contracts.role_profile import RoleProfile
from core.contracts.skills import Skill
from core.evaluation.policy import ModelJudgePort

#: The FINAL Phase 15 admitted set (41 §18): MVP pair + the four named
#: build items. The remaining four 22 §5 types stay inactive (see module
#: docstring — no documented mechanism; never silently run).
FINAL_ACTIVE_GRADER_TYPES: frozenset[GraderType] = MVP_ACTIVE_GRADER_TYPES | frozenset(
    {
        GraderType.PAIRWISE,
        GraderType.SKILL_SPECIFIC,
        GraderType.ROLE_SPECIFIC,
        GraderType.COUNTER_EVALUATION,
    }
)


class OutputGraderPort(Protocol):
    """A pure single-output specialty grader the policy service can run."""

    @property
    def grader_type(self) -> GraderType:
        """Which 22 §5 family this grader belongs to."""
        ...

    def row(self, output: JsonObject) -> GraderResult:
        """Grade one execution output; always returns an explicit row."""
        ...


# --- skill grader (22 §5 skill_specific) ---------------------------------------------


class SkillFormatGrader:
    """Checks the 10 §3 result ``type`` against the 14 §2 ``outputs.format``."""

    grader_type: GraderType = GraderType.SKILL_SPECIFIC

    def __init__(self, skill: Skill) -> None:
        self._skill = skill

    def row(self, output: JsonObject) -> GraderResult:
        declared = self._skill.manifest.outputs_format
        passed = True if declared is None else output.get("type") == declared
        return GraderResult(
            type=self.grader_type,
            name=f"skill_output_format:{self._skill.manifest.id}",
            passed=passed,
        )


# --- role grader (22 §5 role_specific) -----------------------------------------------


class RoleContractGrader:
    """Checks key PRESENCE of the role's effective output contract."""

    grader_type: GraderType = GraderType.ROLE_SPECIFIC

    def __init__(self, profile: RoleProfile) -> None:
        self._profile = profile

    def row(self, output: JsonObject) -> GraderResult:
        contract = self._profile.effective_output_contract()
        missing = [key for key in contract if key not in output]
        return GraderResult(
            type=self.grader_type,
            name=f"role_output_contract:{self._profile.role.name}",
            passed=not missing,
        )


# --- pairwise (22 §5 pairwise) ----------------------------------------------------------


class PairwiseTie(Exception):
    """The pairwise judge could not prefer either candidate — refused.

    A fabricated winner would be worse than no answer (same posture as
    the preference-learning tie rule): the caller decides what a tie
    means; this component never invents a preference.
    """


class PairwiseJudgePort(Protocol):
    """Judgment seam comparing two candidate outputs (no model claimed)."""

    async def prefer(
        self, tenant_id: UUID, output_a: JsonObject, output_b: JsonObject
    ) -> tuple[int, float]:
        """Return (winner index 0|1, confidence in [0,1]); raise PairwiseTie."""
        ...


@dataclass(frozen=True)
class PairwiseDecision:
    """Explicit pairwise outcome: the winner named, one row per candidate."""

    winner_index: int
    rows: tuple[GraderResult, GraderResult]


class PairwiseEvaluator:
    """Compares two candidate outputs through the judge seam."""

    def __init__(self, judge: PairwiseJudgePort, *, name: str = "pairwise") -> None:
        self._judge = judge
        self._name = name

    async def compare(
        self, tenant_id: UUID, output_a: JsonObject, output_b: JsonObject
    ) -> PairwiseDecision:
        """One judged comparison; ``passed`` on a row means PREFERRED."""
        winner, confidence = await self._judge.prefer(tenant_id, output_a, output_b)
        if winner not in (0, 1):
            msg = f"pairwise judge returned invalid winner index: {winner}"
            raise ValueError(msg)
        rows = tuple(
            GraderResult(
                type=GraderType.PAIRWISE,
                name=f"{self._name}:candidate_{index}",
                passed=index == winner,
                confidence=confidence,
            )
            for index in (0, 1)
        )
        return PairwiseDecision(winner_index=winner, rows=(rows[0], rows[1]))


# --- counter evaluation (22 §5 counter_evaluation) ---------------------------------------


class NothingToChallenge(Exception):
    """Counter-evaluating a record without a score is a caller error."""

    def __init__(self, record_id: object) -> None:
        super().__init__(f"record carries no score to challenge: {record_id}")


class CounterEvaluator:
    """Challenges an existing judgment with an independent one."""

    def __init__(self, judge: ModelJudgePort, *, tolerance: float = 0.2) -> None:
        if not 0.0 <= tolerance <= 1.0:
            msg = "tolerance must be within [0, 1]"
            raise ValueError(msg)
        self._judge = judge
        self._tolerance = tolerance

    async def challenge(
        self, record: EvaluationRecord, output: JsonObject
    ) -> GraderResult:
        """Independent re-judgment; passed = original upheld within tolerance."""
        if record.score is None:
            raise NothingToChallenge(record.id)
        counter = await self._judge.judge(record.tenant_id, record.execution_id, output)
        # "Within tolerance" is INCLUSIVE at the boundary; math.isclose
        # keeps that inclusiveness under float representation noise
        # (|0.8 - 0.6| is not exactly 0.2 in binary floating point).
        upheld = counter.score is not None and (
            (delta := abs(counter.score - record.score)) <= self._tolerance
            or math.isclose(delta, self._tolerance)
        )
        return GraderResult(
            type=GraderType.COUNTER_EVALUATION,
            name="counter_evaluation",
            passed=upheld,
            score=counter.score,
            confidence=counter.confidence,
        )
