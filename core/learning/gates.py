"""Learning-lifecycle gates — FINAL Phase 17 (41 §20; 22 §9/§11, T-IMPL-066).

Spec anchors:

- 22 §9 Training Eligibility (verbatim, ALL must hold): "privacy policy
  allows / tenant/user policy allows / sensitive data handled / quality
  level sufficient / deduplicated / sanitized / source trace exists /
  not poisoned".
- 22 §11 Promotion Gates (verbatim, ALL must hold): "offline eval pass /
  regression pass / security eval pass / shadow performance acceptable /
  canary performance acceptable / rollback plan exists / admin approval
  where required".
- 41 §20: "User Feedback: signal only. Training eligibility: separate
  from Feedback." — NEITHER gate consumes feedback: no feedback input
  exists on either signals contract (structural separation, same posture
  as the tool gate's missing skill parameter).
- 22 §12 test items: "training eligibility enforcement" and
  "shadow/canary promotion gate" are these gates; "rollback model
  version" is the rollback-plan condition plus the pre-existing admin
  rollback machinery (T-IMPL-031, recorded).

Recorded derivations (nothing invented silently):

- Both condition lists are ordered DATA (the closed 22 §9/§11 sets
  verbatim, snake_cased) — checked ALL (never short-circuited) so a
  refusal names EVERY failed condition (11 §14), not just the first.
- Each condition arrives as a RESOLVED signal from the subsystem that
  owns it (privacy policy, dedup index, poisoning scan, eval runs, admin
  approval...). No doc defines those mechanisms here; the gates compose
  their VERDICTS as booleans — deny-by-default: every signal defaults
  False, so an unstated condition FAILS (an absent verdict is not a
  passing one).
- Three 22 §9 conditions are NOT free booleans because contracts already
  own them (single source of truth, never duplicated):
  ``sanitized``     <- LearningSample.sanitization_state == PASSED,
  ``quality level sufficient`` <- LearningSample.verification_level
  ranked >= an injectable minimum (default VERIFIED — 22 §8 places
  Verification immediately before Training Eligibility, so the bar is
  the level that step certifies; configurable, recorded),
  ``source trace exists`` <- LearningSample.source_execution_id is a
  required field, so the sample-shaped trace always exists; the signal
  remains overridable for traces broken OUTSIDE the sample (recorded).
- The eligibility gate is PURE: it never mutates the sample. Writing
  ``eligibility=ELIGIBLE`` back is the caller's persistence act over the
  frozen contract (same posture as the skill-import steps).
- "admin approval where required" — the ONLY conditional item in 22 §11:
  ``approval_required`` (policy data) decides whether ``admin_approved``
  is consulted; not-required means the condition holds vacuously.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts.evaluation import VERIFICATION_LEVEL_ORDER, VerificationLevel
from core.contracts.learning import LearningSample, SanitizationState
from core.learning.errors import NotEligibleForTraining, PromotionDenied

#: 22 §9 conditions, verbatim order, snake_cased — the closed set as DATA.
TRAINING_ELIGIBILITY_CONDITIONS: tuple[str, ...] = (
    "privacy_policy_allows",
    "tenant_user_policy_allows",
    "sensitive_data_handled",
    "quality_level_sufficient",
    "deduplicated",
    "sanitized",
    "source_trace_exists",
    "not_poisoned",
)

#: 22 §11 conditions, verbatim order, snake_cased — the closed set as DATA.
PROMOTION_CONDITIONS: tuple[str, ...] = (
    "offline_eval_pass",
    "regression_pass",
    "security_eval_pass",
    "shadow_performance_acceptable",
    "canary_performance_acceptable",
    "rollback_plan_exists",
    "admin_approval_where_required",
)


@dataclass(frozen=True)
class EligibilitySignals:
    """Resolved verdicts for the 22 §9 conditions owned by OTHER subsystems.

    Deny-by-default: every field defaults False — an unresolved condition
    fails. NO feedback field exists (41 §20 separation, structural).
    """

    privacy_policy_allows: bool = False
    tenant_user_policy_allows: bool = False
    sensitive_data_handled: bool = False
    deduplicated: bool = False
    not_poisoned: bool = False
    source_trace_intact: bool = True  # sample-shaped trace exists by contract


class TrainingEligibilityGate:
    """The 22 §9 gate: a sample enters training ONLY if ALL conditions hold."""

    def __init__(self, *, minimum_level: VerificationLevel = VerificationLevel.VERIFIED) -> None:
        self._minimum_index = VERIFICATION_LEVEL_ORDER.index(minimum_level)

    def evaluate(self, sample: LearningSample, signals: EligibilitySignals) -> dict[str, bool]:
        """Every condition's verdict, by its 22 §9 name — always ALL of them."""
        level_index = VERIFICATION_LEVEL_ORDER.index(sample.verification_level)
        return {
            "privacy_policy_allows": signals.privacy_policy_allows,
            "tenant_user_policy_allows": signals.tenant_user_policy_allows,
            "sensitive_data_handled": signals.sensitive_data_handled,
            "quality_level_sufficient": level_index >= self._minimum_index,
            "deduplicated": signals.deduplicated,
            "sanitized": sample.sanitization_state is SanitizationState.PASSED,
            "source_trace_exists": signals.source_trace_intact,
            "not_poisoned": signals.not_poisoned,
        }

    def admit(self, sample: LearningSample, signals: EligibilitySignals) -> dict[str, bool]:
        """Admit or refuse LOUDLY, naming every failed condition (11 §14)."""
        verdicts = self.evaluate(sample, signals)
        failed = [name for name, held in verdicts.items() if not held]
        if failed:
            raise NotEligibleForTraining(sample.id, failed)
        return verdicts


@dataclass(frozen=True)
class PromotionSignals:
    """Resolved verdicts for the 22 §11 conditions (deny-by-default)."""

    offline_eval_pass: bool = False
    regression_pass: bool = False
    security_eval_pass: bool = False
    shadow_performance_acceptable: bool = False
    canary_performance_acceptable: bool = False
    rollback_plan_exists: bool = False
    approval_required: bool = True  # requiring approval is the safe default
    admin_approved: bool = False


class PromotionGate:
    """The 22 §11 gate: a trained model/policy promotes ONLY past ALL gates."""

    def evaluate(self, signals: PromotionSignals) -> dict[str, bool]:
        """Every condition's verdict, by its 22 §11 name — always ALL of them."""
        return {
            "offline_eval_pass": signals.offline_eval_pass,
            "regression_pass": signals.regression_pass,
            "security_eval_pass": signals.security_eval_pass,
            "shadow_performance_acceptable": signals.shadow_performance_acceptable,
            "canary_performance_acceptable": signals.canary_performance_acceptable,
            "rollback_plan_exists": signals.rollback_plan_exists,
            "admin_approval_where_required": (
                signals.admin_approved if signals.approval_required else True
            ),
        }

    def admit(self, candidate: str, signals: PromotionSignals) -> dict[str, bool]:
        """Admit or refuse LOUDLY, naming every failed condition (11 §14)."""
        verdicts = self.evaluate(signals)
        failed = [name for name, held in verdicts.items() if not held]
        if failed:
            raise PromotionDenied(candidate, failed)
        return verdicts
