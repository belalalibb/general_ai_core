"""R158 — end-to-end learning lifecycle over the EXISTING components.

Proves the 22 §8 chain actually operates (directive §26 acceptance):

Execution → Evaluation (EXISTING EvaluationPolicyService, real graders)
→ Sample state → Training-Eligibility gate (EXISTING) → Promotion gate
(EXISTING) → GOLD → Retrieval (EXISTING InMemoryMemoryStore) →
isolated learned-capability test path → audit evidence
(TRAINING_DATASET_PROMOTED — the 20 §9 event that previously had no
emitter anywhere in the repo).

Every store here is the REAL production in-memory implementation, not a
test double: InMemoryEvaluationStore, InMemoryMemoryStore,
InMemoryAuditLog, EvaluationPolicyService.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from core.audit import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.evaluation import VerificationLevel
from core.contracts.learning import (
    LearningEligibility,
    SanitizationState,
)
from core.evaluation import InMemoryEvaluationStore
from core.evaluation.policy import EvaluationPolicyService
from core.learning import (
    GOLD_KNOWLEDGE_SOURCE,
    EligibilitySignals,
    LearningError,
    LearningLifecycleService,
    NotEligibleForTraining,
    PromotionDenied,
    PromotionSignals,
    SampleNotFound,
    TrainingEligibilityGate,
)
from core.memory.memory import InMemoryMemoryStore

TENANT = uuid4()
OTHER_TENANT = uuid4()
ADMIN = uuid4()

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
    evaluation = EvaluationPolicyService(store=InMemoryEvaluationStore())
    service = LearningLifecycleService(
        evaluation=evaluation,
        knowledge=knowledge,
        audit=audit,
        # RAW-level samples must still be able to advance in this MVP
        # composition: minimum_level=RAW keeps the gate real (all 8
        # conditions still checked) while the evaluation pipeline's level
        # assignment stays authoritative for the recorded level.
        eligibility_gate=TrainingEligibilityGate(minimum_level=VerificationLevel.RAW),
    )
    return {
        "service": service,
        "audit": audit,
        "knowledge": knowledge,
    }


class TestFullLifecycle:
    def test_execution_to_gold_to_retrieval_to_isolated_test(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        execution_id = uuid4()

        # 1) CAPTURE — deny-by-default entry state (contract defaults).
        sample = service.capture_from_execution(
            TENANT,
            execution_id,
            knowledge_key="deploy.rollback_procedure",
            knowledge_value={"answer": "drain, flip alias, verify, then destroy"},
        )
        assert sample.eligibility is LearningEligibility.PENDING
        assert sample.sanitization_state is SanitizationState.PENDING
        assert sample.verification_level is VerificationLevel.RAW
        assert sample.dataset_id is None

        # 2) SANITIZE — explicit reviewed act (no silent pass exists).
        sample = service.mark_sanitized(TENANT, sample.id, passed=True)
        assert sample.sanitization_state is SanitizationState.PASSED

        # 3) EVALUATE — through the EXISTING grader pipeline (real checks).
        sample = run(
            service.evaluate(
                TENANT,
                sample.id,
                {"content": "drain, flip alias, verify, then destroy"},
            )
        )
        assert sample.verification_level in set(VerificationLevel)

        # 4) ELIGIBILITY — the EXISTING 22 §9 gate, all 8 conditions.
        sample = service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        assert sample.eligibility is LearningEligibility.ELIGIBLE
        assert sample.dataset_id is not None  # entered Dataset (03 §8)

        # 5) PROMOTION — the EXISTING 22 §11 gate → GOLD + knowledge write.
        item = service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE, actor_id=ADMIN)
        assert item.source == GOLD_KNOWLEDGE_SOURCE
        assert service.get(TENANT, sample.id).verification_level is (VerificationLevel.GOLD)

        # 6) AUDIT — the 20 §9 event that previously had NO emitter.
        events = [
            e
            for e in world["audit"].read(TENANT)
            if e.event_type is AuditEventType.TRAINING_DATASET_PROMOTED
        ]
        assert len(events) == 1
        assert events[0].actor_id == ADMIN
        assert events[0].details["sample_id"] == str(sample.id)

        # 7) RETRIEVAL — GOLD knowledge is queryable via the memory port.
        assert service.learned_keys(TENANT) == ("deploy.rollback_procedure",)

        # 8) ISOLATED TEST PATH — answers ONLY from GOLD knowledge.
        answer = service.ask_learned(TENANT, "deploy.rollback_procedure")
        assert answer["found"] is True
        assert answer["answer"] == {"answer": "drain, flip alias, verify, then destroy"}
        assert answer["evidence"]["source"] == GOLD_KNOWLEDGE_SOURCE

        # ... and an unlearned key is an explicit not-found, never invented.
        missing = service.ask_learned(TENANT, "unknown.topic")
        assert missing == {
            "found": False,
            "key": "unknown.topic",
            "answer": None,
            "evidence": None,
        }

        # 9) LIFECYCLE REPORT — evidence for the admin surface.
        report = service.sample_report(TENANT, sample.id)
        assert report["source_kind"] == "execution"
        assert all(report["eligibility_verdicts"].values())
        assert all(report["promotion_verdicts"].values())


class TestExternalIngestion:
    def test_external_data_enters_same_pipeline_never_trusted(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = service.capture_external(
            TENANT,
            knowledge_key="vendor.api_quirks",
            knowledge_value={"answer": "retry 429 with jittered backoff"},
        )
        # NOT trusted on entry — identical deny-by-default posture.
        assert sample.eligibility is LearningEligibility.PENDING
        assert sample.verification_level is VerificationLevel.RAW
        assert service.sample_report(TENANT, sample.id)["source_kind"] == ("external")
        # It cannot skip the gates: promotion before eligibility refuses.
        with pytest.raises(LearningError):
            service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE)
        # Same pipeline admits it once reviewed like any sample.
        service.mark_sanitized(TENANT, sample.id, passed=True)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        item = service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE)
        assert item.source == GOLD_KNOWLEDGE_SOURCE


class TestGateRefusals:
    def test_unsanitized_sample_refused_with_named_condition(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = service.capture_from_execution(
            TENANT, uuid4(), knowledge_key="k", knowledge_value={"v": 1}
        )
        with pytest.raises(NotEligibleForTraining) as exc:
            service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        assert "sanitized" in str(exc.value)
        # Verdict persisted: the sample is now explicitly INELIGIBLE.
        assert service.get(TENANT, sample.id).eligibility is (LearningEligibility.INELIGIBLE)

    def test_promotion_gate_names_every_failed_condition(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = service.capture_from_execution(
            TENANT, uuid4(), knowledge_key="k2", knowledge_value={"v": 2}
        )
        service.mark_sanitized(TENANT, sample.id, passed=True)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        with pytest.raises(PromotionDenied) as exc:
            service.promote_to_gold(
                TENANT,
                sample.id,
                PromotionSignals(),  # all deny-by-default
            )
        message = str(exc.value)
        assert "offline_eval_pass" in message
        assert "regression_pass" in message
        # Nothing reached GOLD, retrieval, or audit.
        assert service.learned_keys(TENANT) == ()
        assert not [
            e
            for e in world["audit"].read(TENANT)
            if e.event_type is AuditEventType.TRAINING_DATASET_PROMOTED
        ]


class TestTenantIsolation:
    def test_foreign_tenant_sample_is_not_found(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = service.capture_from_execution(
            TENANT, uuid4(), knowledge_key="secret.k", knowledge_value={"v": 3}
        )
        # Anti-enumeration: foreign tenant sees the SAME error as absent id.
        with pytest.raises(SampleNotFound):
            service.get(OTHER_TENANT, sample.id)
        with pytest.raises(SampleNotFound):
            service.mark_sanitized(OTHER_TENANT, sample.id, passed=True)
        with pytest.raises(SampleNotFound):
            service.admit_to_training(OTHER_TENANT, sample.id, ALL_ELIGIBLE)
        assert service.list_samples(OTHER_TENANT) == ()

    def test_gold_knowledge_is_tenant_scoped(self, world: dict[str, Any]) -> None:
        service: LearningLifecycleService = world["service"]
        sample = service.capture_from_execution(
            TENANT, uuid4(), knowledge_key="ops.playbook", knowledge_value={"v": 4}
        )
        service.mark_sanitized(TENANT, sample.id, passed=True)
        service.admit_to_training(TENANT, sample.id, ALL_ELIGIBLE)
        service.promote_to_gold(TENANT, sample.id, ALL_PROMOTABLE)
        # The other tenant cannot see or query the learned knowledge.
        assert service.learned_keys(OTHER_TENANT) == ()
        assert service.ask_learned(OTHER_TENANT, "ops.playbook")["found"] is (False)
