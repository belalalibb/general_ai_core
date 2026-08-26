"""Evaluation contracts (MVP Phase 7, 41 §46 "basic evaluation policy").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §7
  (Evaluation entity, field-for-field) and §8 ("Evaluation belongs to
  Execution/Node").
- docs/ai_orchestration_pack/final_docs_v3/22_EVALUATION_AND_LEARNING.md
  §3 (verification levels), §4 (score vs confidence), §5 (grader types),
  §6 (evaluation record example).

Score vs confidence (22 §4, verbatim)::

    Score = how good the output appears.
    Confidence = how much we trust that judgment.

"Never merge them into one number." — honored STRUCTURALLY: score and
confidence are two independent, independently-nullable fields on every
shape that carries them; no shape in this module has a single combined
"quality" number.

Grader result shapes (22 §6 example, recorded): the deterministic grader
row carries ``passed`` (a check either holds or it doesn't); the
model-based grader row carries ``score`` + ``confidence`` (a judgment plus
trust in that judgment). :class:`GraderResult` is one shape covering both
honestly — ``passed`` for check-style graders, ``score``/``confidence``
for judgment-style graders; at least one facet must be present (a grader
that reports nothing graded nothing).

Scope decisions (MVP PHASE 7 SLICING DECISION, R049):

- All TEN 22 §5 grader types are representable in the closed set; only
  ``deterministic`` and ``model_based`` RUN in MVP Phase 7 (boundary (c)).
- Evaluation attaches at EXECUTION level in MVP; node-level evaluation is
  representable via 03 §8 but not built this phase (boundary (d)).
- ``tenant_id`` is carried on :class:`EvaluationRecord` even though the
  03 §7 entity omits it: evaluations are stored/queried tenant-scoped
  (20 §6 anti-enumeration) exactly like every other store in this repo.
  Recorded as a storage-shape addition, not an entity redefinition.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel

# --- Closed sets ----------------------------------------------------------------


class VerificationLevel(StrEnum):
    """Verification levels (22 §3 / 03 §7) — closed set, verbatim order.

    | RAW       | Generated but not evaluated                  |
    | EVALUATED | Scored by one or more graders                |
    | VALIDATED | Passed required checks                       |
    | VERIFIED  | Has sufficient evidence/confidence           |
    | GOLD      | Approved as high-quality reference sample    |
    """

    RAW = "RAW"
    EVALUATED = "EVALUATED"
    VALIDATED = "VALIDATED"
    VERIFIED = "VERIFIED"
    GOLD = "GOLD"


# Ladder order as data (22 §3 lists levels in ascending trust order) —
# level-assignment logic compares positions in THIS tuple, never ad-hoc.
VERIFICATION_LEVEL_ORDER: tuple[VerificationLevel, ...] = (
    VerificationLevel.RAW,
    VerificationLevel.EVALUATED,
    VerificationLevel.VALIDATED,
    VerificationLevel.VERIFIED,
    VerificationLevel.GOLD,
)


class GraderType(StrEnum):
    """Grader types (22 §5) — closed set, all ten verbatim.

    R049 boundary (c): only DETERMINISTIC and MODEL_BASED run in MVP
    Phase 7; the remaining eight are representable data for later phases,
    never silently executed.
    """

    DETERMINISTIC = "deterministic"
    MODEL_BASED = "model_based"
    PAIRWISE = "pairwise"
    COUNTER_EVALUATION = "counter_evaluation"
    SKILL_SPECIFIC = "skill_specific"
    ROLE_SPECIFIC = "role_specific"
    SECURITY = "security"
    REGRESSION = "regression"
    HUMAN_CALIBRATED = "human_calibrated"
    PRODUCTION_SIGNAL = "production_signal"


# Grader types that actually RUN in MVP Phase 7 (R049 boundary (c)).
MVP_ACTIVE_GRADER_TYPES: frozenset[GraderType] = frozenset(
    {GraderType.DETERMINISTIC, GraderType.MODEL_BASED}
)

# Bounded [0,1] judgment scalar — used for both score and confidence,
# which remain SEPARATE FIELDS everywhere (22 §4).
_UnitInterval = Field(ge=0.0, le=1.0)


class GraderResult(ContractModel):
    """One grader's row in the evaluation record (22 §6 ``graders[]``).

    The 22 §6 example shows two row shapes; this model covers both:

    - check-style (deterministic): ``{"type","name","passed"}``
    - judgment-style (model_based): ``{"type","name","score","confidence"}``

    ``score`` and ``confidence`` are independent and never merged (22 §4).
    A row must carry at least one facet — ``passed`` or a judgment.
    """

    type: GraderType
    name: BoundedStr
    passed: bool | None = None
    score: float | None = _UnitInterval
    confidence: float | None = _UnitInterval

    @model_validator(mode="after")
    def _graded_something(self) -> GraderResult:
        if self.passed is None and self.score is None and self.confidence is None:
            msg = "grader result must carry passed and/or score/confidence"
            raise ValueError(msg)
        return self


class EvaluationRecord(ContractModel):
    """Evaluation record (22 §6 example + 03 §7 Evaluation entity).

    03 §7 fields verbatim: id / execution_id / level / score|null /
    confidence|null / evidence_ref|null / graders. ``tenant_id`` added for
    tenant-scoped storage (module docstring — recorded decision).

    ``score`` and ``confidence`` are separate nullable fields; a record may
    carry either, both, or neither (RAW has no judgment at all) — 22 §4
    embodied at type level.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    execution_id: UUID
    level: VerificationLevel
    score: float | None = _UnitInterval
    confidence: float | None = _UnitInterval
    evidence_ref: BoundedStr | None = None
    graders: tuple[GraderResult, ...] = ()

    @model_validator(mode="after")
    def _raw_carries_no_judgment(self) -> EvaluationRecord:
        """RAW = "generated but not evaluated" (22 §3): no graders, no numbers.

        Conversely any level ABOVE RAW means "scored by one or more
        graders" (22 §3 EVALUATED definition) — an above-RAW record with an
        empty grader list would claim an evaluation that never happened.
        """
        if self.level is VerificationLevel.RAW:
            if self.graders or self.score is not None or self.confidence is not None:
                msg = "RAW means not evaluated: no graders, score, or confidence"
                raise ValueError(msg)
        elif not self.graders:
            msg = f"level {self.level.value} requires at least one grader result"
            raise ValueError(msg)
        return self
