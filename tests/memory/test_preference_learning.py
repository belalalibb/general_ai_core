"""T-IMPL-060 — Preference learning gate (13 §6; 41 §14 Phase 11).

13 §10 exit-test mapping across the Phase 11 suites (honest, 41 §49):

- scope conflict resolution → test_context_composer.py (pre-existing)
- tenant isolation → test_memory_stores.py + test_context_composer.py
- preference confidence update → test_memory_stores.py::
  test_repeat_write_updates_in_place_and_accumulates_evidence
  (pre-existing) + the confidence-ratio tests below
- irrelevant memory excluded → test_context_composer.py (pre-existing)
- secret not stored → test_memory_stores.py (pre-existing)
- memory deletion respected → test_memory_stores.py (pre-existing)
- context budget respected → test_context_composer.py (pre-existing)
- project memory overrides user memory → test_context_composer.py::
  test_scope_conflict_more_specific_wins (pre-existing)

This file adds the 13 §6 learning conditions, each individually.
"""

from __future__ import annotations

import pytest

from core.contracts.memory import MemoryScope, MemorySensitivity
from core.memory import LearningDecision, PreferenceLearningGate, PreferenceObservation


def obs(
    value: object = "ar",
    *,
    key: str = "preferred_language",
    scope: MemoryScope = MemoryScope.CONVERSATION,
) -> PreferenceObservation:
    return PreferenceObservation.model_validate({"key": key, "value": value, "scope": scope})


def evaluate(
    observations: list[PreferenceObservation],
    *,
    value: object = "ar",
    sensitivity: MemorySensitivity = MemorySensitivity.LOW,
    policy_allows_memory: bool = True,
    min_evidence: int = 2,
) -> LearningDecision:
    return PreferenceLearningGate(min_evidence=min_evidence).evaluate(
        key="preferred_language",
        value=value,
        sensitivity=sensitivity,
        observations=observations,
        policy_allows_memory=policy_allows_memory,
    )


# --- condition 1: repeated evidence exists -------------------------------------


def test_single_observation_is_not_repeated_evidence() -> None:
    decision = evaluate([obs()])
    assert not decision.learnable
    assert decision.reason == "insufficient_evidence:1<2"


def test_two_agreeing_observations_admit() -> None:
    decision = evaluate([obs(), obs()])
    assert decision.learnable
    assert decision.reason is None


def test_caller_may_raise_the_evidence_bar() -> None:
    decision = evaluate([obs(), obs()], min_evidence=3)
    assert not decision.learnable
    assert decision.reason == "insufficient_evidence:2<3"


def test_evidence_bar_below_two_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        PreferenceLearningGate(min_evidence=1)


def test_other_keys_do_not_count_as_evidence() -> None:
    decision = evaluate([obs(), obs(key="theme")])
    assert not decision.learnable
    assert decision.reason == "insufficient_evidence:1<2"


# --- condition 2: no contradiction dominates -----------------------------------


def test_contradiction_tie_refuses() -> None:
    """A tie means no value dominates — learning would fabricate certainty."""
    decision = evaluate([obs("ar"), obs("ar"), obs("en"), obs("en")])
    assert not decision.learnable
    assert decision.reason == "contradiction_dominates:2vs2"


def test_contradiction_majority_refuses() -> None:
    decision = evaluate([obs("ar"), obs("ar"), obs("en"), obs("en"), obs("en")])
    assert not decision.learnable
    assert decision.reason == "contradiction_dominates:3vs2"


def test_strict_supporting_majority_admits() -> None:
    decision = evaluate([obs("ar"), obs("ar"), obs("ar"), obs("en")])
    assert decision.learnable


# --- condition 3: scope is clear -----------------------------------------------


def test_mixed_scope_evidence_refuses_with_named_scopes() -> None:
    decision = evaluate([obs(scope=MemoryScope.CONVERSATION), obs(scope=MemoryScope.PROJECT)])
    assert not decision.learnable
    assert decision.reason == "scope_unclear:conversation,project"


def test_contradicting_scope_does_not_muddy_supporting_scope() -> None:
    """Scope clarity is judged over SUPPORTING evidence only."""
    decision = evaluate(
        [
            obs("ar", scope=MemoryScope.PROJECT),
            obs("ar", scope=MemoryScope.PROJECT),
            obs("en", scope=MemoryScope.CONVERSATION),
        ]
    )
    assert decision.learnable


# --- condition 4: sensitivity is acceptable ------------------------------------


def test_high_sensitivity_never_learnable() -> None:
    """13 §6: 'Do not infer sensitive attributes unnecessarily.'"""
    decision = evaluate([obs(), obs()], sensitivity=MemorySensitivity.HIGH)
    assert not decision.learnable
    assert decision.reason == "sensitivity_unacceptable:high"


def test_medium_sensitivity_admits() -> None:
    decision = evaluate([obs(), obs()], sensitivity=MemorySensitivity.MEDIUM)
    assert decision.learnable


# --- condition 5: user/admin policy allows memory ------------------------------


def test_policy_denies_by_default() -> None:
    """Deny-by-default (41 §1 rule 9): absent permission refuses."""
    gate = PreferenceLearningGate()
    decision = gate.evaluate(
        key="preferred_language",
        value="ar",
        sensitivity=MemorySensitivity.LOW,
        observations=[obs(), obs()],
    )
    assert not decision.learnable
    assert decision.reason == "memory_policy_denies"


def test_policy_permission_admits() -> None:
    decision = evaluate([obs(), obs()], policy_allows_memory=True)
    assert decision.learnable


# --- evidence-based confidence (13 §1) ------------------------------------------


def test_unanimous_evidence_yields_full_confidence() -> None:
    decision = evaluate([obs(), obs(), obs()])
    assert decision.learnable
    assert decision.confidence == 1.0


def test_confidence_is_the_supporting_ratio() -> None:
    decision = evaluate([obs("ar"), obs("ar"), obs("ar"), obs("en")])
    assert decision.learnable
    assert decision.confidence == 0.75


def test_refusals_carry_no_confidence() -> None:
    decision = evaluate([obs()])
    assert decision.confidence is None


# --- gate order and purity -------------------------------------------------------


def test_conditions_checked_in_documented_order() -> None:
    """Evidence failure is reported even when later conditions also fail."""
    decision = evaluate([obs()], sensitivity=MemorySensitivity.HIGH, policy_allows_memory=False)
    assert decision.reason == "insufficient_evidence:1<2"


def test_gate_is_pure_and_does_not_write_memory() -> None:
    """The gate answers only; the write path stays MemoryStorePort.upsert."""
    import core.memory.preferences as preferences

    source = open(preferences.__file__).read()  # noqa: SIM115
    assert ".upsert(" not in source  # docstring may NAME the write path; never call it
    assert "MemoryStorePort" not in source.replace(
        "MemoryStorePort.upsert", ""
    )  # no store dependency beyond the docstring reference
    for banned in ("httpx", "redis", "asyncpg", "sqlalchemy", "socket"):
        assert banned not in source
