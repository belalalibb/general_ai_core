"""R188 §B — Learning / Evaluation closure pins (verification, not new engine).

The directive asks for closure of the learning loop as it EXISTS: the same
gates, the same custody, the same isolated retrieval path. These pins verify
the claims a caller relies on and would catch any regression that opened a
silent path:

B1  gate-before-answer: ``ask_learned`` answers ONLY from GOLD; a sample that
    is captured, sanitized, evaluated and even training-eligible is still NOT
    an answer until promotion passes ALL 22 §11 gates.
B2  feedback is signal-only, structurally: neither gate's signals dataclass
    has a feedback field; passing one is a TypeError (not a soft ignore).
B3  poisoned input never reaches GOLD: ``not_poisoned=False`` denies training
    eligibility by name; a later promotion attempt on the same sample is
    refused (no promotion without eligibility).
B4  GOLD custody + provenance: the promoted memory item carries the GOLD
    source, the promotion audit event binds sample -> memory item, and the
    lifecycle report exposes both verdict sets as data.
B5  tenant isolation on the retrieval path: another tenant asking the SAME
    key gets an explicit not-found (never the neighbour's knowledge).
B6  measurement, not assertion: ``capability_delta`` reports gained / lost /
    still-missing keys from before/after snapshots of the isolated path.

Hermetic: production in-memory stores, no network.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any
from uuid import uuid4

import pytest

from core.audit import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.evaluation import VerificationLevel
from core.contracts.learning import LearningEligibility
from core.evaluation import InMemoryEvaluationStore
from core.evaluation.policy import EvaluationPolicyService
from core.learning import (
    GOLD_KNOWLEDGE_SOURCE,
    EligibilitySignals,
    LearningLifecycleService,
    NotEligibleForTraining,
    PromotionDenied,
    PromotionSignals,
    TrainingEligibilityGate,
)
from core.memory.memory import InMemoryMemoryStore

TENANT = uuid4()
NEIGHBOUR = uuid4()
ADMIN = uuid4()
KEY = "incident.rollback"
VALUE = {"answer": "drain, flip alias, verify"}

ALL_ELIGIBLE = EligibilitySignals(
    privacy_policy_allows=True,
    tenant_user_policy_allows=True,
    sensitive_data_handled=True,
    deduplicated=True,
    not_poisoned=True,
)
ALL_PROMOTABLE = PromotionSignals(
    offline_eval_pass=True,
    regression_pass=True,
    security_eval_pass=True,
    shadow_performance_acceptable=True,
    canary_performance_acceptable=True,
    rollback_plan_exists=True,
    approval_required=True,
    admin_approved=True,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture()
def world() -> dict[str, Any]:
    audit = InMemoryAuditLog()
    knowledge = InMemoryMemoryStore()
    service = LearningLifecycleService(
        evaluation=EvaluationPolicyService(store=InMemoryEvaluationStore()),
        knowledge=knowledge,
        audit=audit,
        eligibility_gate=TrainingEligibilityGate(minimum_level=VerificationLevel.RAW),
    )
    return {"service": service, "audit": audit, "knowledge": knowledge}


def _captured_and_evaluated(service: LearningLifecycleService) -> Any:
    sample = service.capture_from_execution(
        TENANT, uuid4(), knowledge_key=KEY, knowledge_value=VALUE
    )
    sample = service.mark_sanitized(TENANT, sample.id, passed=True)
    return run(service.evaluate(TENANT, sample.id, {"content": VALUE["answer"]}))


class TestGateBeforeAnswer:
    def test_eligible_but_unpromoted_sample_is_not_an_answer(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = _captured_and_evaluated(service)
        sample = service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        assert sample.eligibility is LearningEligibility.ELIGIBLE
        assert service.ask_learned(TENANT, KEY)["found"] is False
        assert service.learned_keys(TENANT) == ()

    def test_one_failed_promotion_gate_keeps_the_answer_closed(
        self, world: dict[str, Any]
    ) -> None:
        service: LearningLifecycleService = world["service"]
        sample = _captured_and_evaluated(service)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        almost = dataclasses.replace(ALL_PROMOTABLE, security_eval_pass=False)
        with pytest.raises(PromotionDenied) as denied:
            service.promote_to_gold(TENANT, sample.id, almost, actor_id=ADMIN)
        assert "security_eval_pass" in str(denied.value)
        assert service.ask_learned(TENANT, KEY)["found"] is False
        assert service.learned_keys(TENANT) == ()


class TestFeedbackIsSignalOnly:
    @pytest.mark.parametrize("signals_type", [EligibilitySignals, PromotionSignals])
    def test_no_feedback_field_and_no_soft_acceptance(self, signals_type: type) -> None:
        names = {f.name for f in dataclasses.fields(signals_type)}
        assert not any("feedback" in name or "rating" in name for name in names)
        with pytest.raises(TypeError):
            signals_type(feedback_score=1.0)


class TestPoisonedInputRegression:
    def test_poisoned_sample_is_denied_by_name_and_cannot_be_promoted(
        self, world: dict[str, Any]
    ) -> None:
        service: LearningLifecycleService = world["service"]
        sample = _captured_and_evaluated(service)
        poisoned = dataclasses.replace(ALL_ELIGIBLE, not_poisoned=False)
        with pytest.raises(NotEligibleForTraining) as refused:
            service.admit_to_training(TENANT, sample.id, poisoned)
        assert "not_poisoned" in str(refused.value)
        after = service.get(TENANT, sample.id)
        assert after.eligibility is not LearningEligibility.ELIGIBLE
        assert after.dataset_id is None
        with pytest.raises((PromotionDenied, NotEligibleForTraining)):
            service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE, actor_id=ADMIN)
        assert service.ask_learned(TENANT, KEY)["found"] is False


class TestGoldCustodyAndProvenance:
    def test_promoted_item_carries_source_audit_binding_and_verdicts(
        self, world: dict[str, Any]
    ) -> None:
        service: LearningLifecycleService = world["service"]
        sample = _captured_and_evaluated(service)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        item = service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE, actor_id=ADMIN)
        assert item.source == GOLD_KNOWLEDGE_SOURCE
        assert service.get(TENANT, sample.id).verification_level is VerificationLevel.GOLD
        events = [
            e
            for e in world["audit"].read(TENANT)
            if e.event_type is AuditEventType.TRAINING_DATASET_PROMOTED
        ]
        assert len(events) == 1
        assert events[0].details["sample_id"] == str(sample.id)
        assert events[0].actor_id == ADMIN
        answer = service.ask_learned(TENANT, KEY)
        assert answer["found"] is True
        assert answer["evidence"] == {
            "memory_item_id": str(item.id),
            "source": GOLD_KNOWLEDGE_SOURCE,
        }
        report = service.sample_report(TENANT, sample.id)
        assert set(report["eligibility_verdicts"]) >= {"not_poisoned", "sanitized"}
        assert set(report["promotion_verdicts"]) >= {"security_eval_pass", "rollback_plan_exists"}


class TestTenantIsolationOnRetrieval:
    def test_neighbour_asking_same_key_gets_explicit_not_found(
        self, world: dict[str, Any]
    ) -> None:
        service: LearningLifecycleService = world["service"]
        sample = _captured_and_evaluated(service)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE, actor_id=ADMIN)
        assert service.ask_learned(TENANT, KEY)["found"] is True
        assert service.ask_learned(NEIGHBOUR, KEY) == {
            "found": False,
            "key": KEY,
            "answer": None,
            "evidence": None,
        }
        assert service.learned_keys(NEIGHBOUR) == ()


class TestMeasuredNotAsserted:
    def test_capability_delta_reports_gained_and_still_missing(
        self, world: dict[str, Any]
    ) -> None:
        service: LearningLifecycleService = world["service"]
        probes = [KEY, "never.learned"]
        before = service.capability_snapshot(TENANT, probes)
        assert before.found == () and set(before.missing) == set(probes)
        sample = _captured_and_evaluated(service)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE, actor_id=ADMIN)
        after = service.capability_snapshot(TENANT, probes)
        delta = LearningLifecycleService.capability_delta(before, after)
        assert delta["gained"] == [KEY]
        assert delta["lost"] == []
        assert delta["still_missing"] == ["never.learned"]
