"""Preference learning gate — 13 §6 admission conditions (41 §14 Phase 11).

Design decisions (recorded, per the standing derivation rule):

13 §6 verbatim: "A preference can be learned when: repeated evidence
exists / no contradiction dominates / scope is clear / sensitivity is
acceptable / user/admin policy allows memory" and "Do not infer sensitive
attributes unnecessarily." The doc defines CONDITIONS, not an interface —
minimal derived component: a pure, deterministic gate that evaluates the
five conditions over observation DATA and answers with an explicit
decision naming the first failing condition (same explainability posture
as router exclusions, 11 §14, and AdmissionDecision, 40 §4.5).

Derived readings (each recorded, none silent):

- "repeated evidence exists" — "repeated" literally means more than once:
  supporting observations >= 2. The doc names no threshold; 2 is the
  minimal reading of the word, and the caller may raise it (data, not
  code).
- "no contradiction dominates" — a contradiction is an observation of the
  SAME key with a DIFFERENT value. It "dominates" when contradicting
  observations equal or outnumber supporting ones: the candidate must
  hold a STRICT majority. (A tie means no value dominates — learning a
  preference from a tie would fabricate certainty.)
- "scope is clear" — all supporting observations agree on ONE scope.
  Observations of the same key spread across scopes leave the scope
  ambiguous; the gate refuses rather than guessing a scope.
- "sensitivity is acceptable" — HIGH is refused (mirrors the composer's
  default-deny for high sensitivity, 13 §9 security classification /
  20 §4 posture); LOW/MEDIUM admit. "Do not infer sensitive attributes
  unnecessarily" is thereby encoded as data: a HIGH-classified candidate
  never becomes a learned preference through this gate.
- "user/admin policy allows memory" — an explicit boolean the CALLER must
  supply; it defaults to False (deny-by-default, 41 §1 rule 9). The gate
  does not resolve policy itself — policy resolution belongs to the
  admin/policy layer; the gate only refuses when permission is absent.
- The gate does NOT write memory. It answers "may this be learned?"; the
  write path stays the existing MemoryStorePort.upsert (which already
  screens secrets, 13 §7, and accumulates evidence_count). Confidence
  estimation is NOT invented — the candidate confidence is the ratio of
  supporting to total observations, the only derivable evidence-based
  figure (13 §1 "evidence-based"); callers may replace it.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts.base import ContractModel, JsonValue
from core.contracts.memory import MemoryScope, MemorySensitivity


class PreferenceObservation(ContractModel):
    """One piece of evidence for (or against) a candidate preference."""

    key: str
    value: JsonValue
    scope: MemoryScope


@dataclass(frozen=True)
class LearningDecision:
    """Explicit learn/refuse outcome — refusals name the failing condition."""

    learnable: bool
    reason: str | None = None
    confidence: float | None = None


class PreferenceLearningGate:
    """Evaluate the 13 §6 conditions over observations; pure and hermetic."""

    def __init__(self, min_evidence: int = 2) -> None:
        # "repeated" >= 2 by the minimal literal reading; caller may raise.
        if min_evidence < 2:
            raise ValueError('13 §6 "repeated evidence" requires min_evidence >= 2')
        self._min_evidence = min_evidence

    def evaluate(
        self,
        *,
        key: str,
        value: JsonValue,
        sensitivity: MemorySensitivity,
        observations: list[PreferenceObservation],
        policy_allows_memory: bool = False,
    ) -> LearningDecision:
        """Apply the five 13 §6 conditions in documented order."""
        relevant = [o for o in observations if o.key == key]
        supporting = [o for o in relevant if o.value == value]
        contradicting = [o for o in relevant if o.value != value]

        # 1. repeated evidence exists
        if len(supporting) < self._min_evidence:
            return LearningDecision(
                learnable=False,
                reason=f"insufficient_evidence:{len(supporting)}<{self._min_evidence}",
            )
        # 2. no contradiction dominates (strict majority required)
        if len(contradicting) >= len(supporting):
            return LearningDecision(
                learnable=False,
                reason=f"contradiction_dominates:{len(contradicting)}vs{len(supporting)}",
            )
        # 3. scope is clear (all supporting evidence agrees on one scope)
        scopes = {o.scope for o in supporting}
        if len(scopes) != 1:
            return LearningDecision(
                learnable=False,
                reason="scope_unclear:" + ",".join(sorted(s.value for s in scopes)),
            )
        # 4. sensitivity is acceptable (HIGH refused — default-deny posture)
        if sensitivity is MemorySensitivity.HIGH:
            return LearningDecision(learnable=False, reason="sensitivity_unacceptable:high")
        # 5. user/admin policy allows memory (explicit; deny-by-default)
        if not policy_allows_memory:
            return LearningDecision(learnable=False, reason="memory_policy_denies")

        return LearningDecision(
            learnable=True,
            confidence=len(supporting) / len(relevant),
        )
