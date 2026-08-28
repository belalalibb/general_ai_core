"""Learning metadata contract — LearningSample entity (FINAL Phase 3, 41 §6).

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §7
  (``LearningSample`` — carried exactly: no field added, renamed, or
  dropped; both 3-state closed sets verbatim) and §8 ("LearningSample can
  only enter Dataset after eligibility + verification").
- final_docs_v3/22_EVALUATION_AND_LEARNING.md §8 (learning lifecycle:
  candidate → privacy/policy check → sanitization → evaluation →
  verification → training eligibility → dataset) and §9 (training
  eligibility conditions — ALL must hold before data enters training).

Recorded derivations (never silent invention):

- ``verification_level`` reuses :class:`VerificationLevel` from
  :mod:`core.contracts.evaluation` — 03 §7 lists the identical 5-value
  set (RAW..GOLD) for both entities; one source of truth, no duplicate
  enum.
- ``tenant_id`` is nullable BY SPEC (03 §7 ``uuid|null``). The specs do
  not define the meaning of NULL; the honest reading recorded here is
  "sample not attributed to a tenant" — this contract does NOT assign
  richer semantics (e.g. "anonymized" or "platform-owned") that no spec
  states. Storage keeps the column nullable verbatim; 20 §6 tenant
  filters apply to tenant-attributed samples.
- ``dataset_id`` is nullable BY SPEC. No Dataset entity exists in the
  41 §6 storage list or 03's inventory as a Phase 3 table — the field
  stays an opaque UUID reference (03 §8: a sample "can only enter
  Dataset after eligibility + verification"; the Dataset entity belongs
  to a later phase and is not invented here).
- Deny-by-default (41 §1 rule 9): ``eligibility`` defaults PENDING and
  ``sanitization_state`` defaults PENDING — a new sample is NEVER
  eligible or sanitized by default; ``verification_level`` defaults RAW
  ("generated but not evaluated", 22 §3) and ``dataset_id`` defaults
  None — an unprocessed sample claims no dataset membership. Every
  default grants NOTHING toward the 22 §9 training-eligibility gate.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from core.contracts.base import ContractModel
from core.contracts.evaluation import VerificationLevel

# --- Closed sets (03 §7, verbatim) --------------------------------------------


class LearningEligibility(StrEnum):
    """LearningSample eligibility states (03 §7) — closed set, verbatim."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    PENDING = "pending"


class SanitizationState(StrEnum):
    """LearningSample sanitization states (03 §7) — closed set, verbatim."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


# --- Entity (03 §7, field-for-field) ------------------------------------------


class LearningSample(ContractModel):
    """LearningSample entity (03 §7) — learning-pipeline metadata for one sample.

    03 §8 rule ("can only enter Dataset after eligibility + verification")
    is a PIPELINE gate enforced by the learning lifecycle, not a field
    invariant — a row may carry ``dataset_id`` only once the gate passed;
    this contract records the states, it does not re-implement the gate.
    """

    id: UUID
    source_execution_id: UUID
    tenant_id: UUID | None = None
    eligibility: LearningEligibility = LearningEligibility.PENDING
    sanitization_state: SanitizationState = SanitizationState.PENDING
    verification_level: VerificationLevel = VerificationLevel.RAW
    dataset_id: UUID | None = None
