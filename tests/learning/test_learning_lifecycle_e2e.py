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


# DEC03: port double only, not live database verification.
class _Custody:
    def __init__(self):
        from core.learning.storage import recover_capture
        from tests.learning.test_storage_policy_r178 import NOW, custody_row

        row, policy = custody_row()
        self.current = recover_capture(row, tenant_id=policy.tenant_id, policy=policy, now=NOW)
        self.calls = []
        self.fail_save = False

    def get(self, tenant_id, sample_id):
        from copy import deepcopy

        from core.learning.storage import LearningStorageError

        if tenant_id != self.current.sample.tenant_id or sample_id != self.current.sample.id:
            raise LearningStorageError("unknown learning sample")
        return deepcopy(self.current)

    def list(self, tenant_id):
        return (self.get(tenant_id, self.current.sample.id),)

    def capture_external(self, tenant_id, **kwargs):
        self.calls.append(("external", kwargs))
        return self.get(tenant_id, self.current.sample.id)

    def capture_from_execution(self, tenant_id, source_execution_id, **kwargs):
        self.calls.append(("execution", source_execution_id, kwargs))
        return self.get(tenant_id, self.current.sample.id)

    def save(self, sample, state, *, expected_revision):
        from copy import deepcopy
        from dataclasses import replace

        from core.learning.storage import LearningStorageConflict, validate_custody_state

        if self.fail_save or expected_revision != self.current.revision:
            raise LearningStorageConflict("stale or unavailable learning sample")
        self.calls.append(("save", expected_revision, validate_custody_state(state)))
        self.current = replace(
            self.current, sample=sample, state=deepcopy(state), revision=expected_revision + 1
        )
        return self.current.revision


def _durable_lifecycle(custody, **kwargs):
    return LearningLifecycleService(knowledge=InMemoryMemoryStore(), custody=custody, **kwargs)


@pytest.mark.parametrize("kind", ["external", "execution"])
def test_custody_lifecycle_capture_delegates_without_local_snapshot(kind):
    custody = _Custody()
    service = _durable_lifecycle(custody)
    args = dict(
        knowledge_key="fact",
        knowledge_value={"nested": ["benign"]},
        policy_id=uuid4(),
        rights_ref=uuid4(),
        idempotency_key=uuid4(),
    )
    tenant, source = custody.current.sample.tenant_id, custody.current.sample.source_execution_id
    if kind == "external":
        args["actor_id"] = uuid4()
        sample = service.capture_external(tenant, **args)
    else:
        sample = service.capture_from_execution(tenant, source, **args)
    assert sample == custody.current.sample and service._samples == {}
    assert custody.calls[0][-1] == args
    fresh = _durable_lifecycle(custody)
    assert fresh.get(tenant, sample.id) == sample
    assert fresh.list_samples(tenant) == (sample,)
    assert fresh.sample_report(tenant, sample.id)["knowledge_key"] == "fact"


@pytest.mark.parametrize("fail", [False, True])
def test_custody_lifecycle_review_is_revision_checked_and_not_cached(fail):
    from core.learning.storage import LearningStorageConflict

    custody = _Custody()
    service = _durable_lifecycle(custody)
    sample = custody.current.sample
    custody.fail_save = fail
    if fail:
        with pytest.raises(LearningStorageConflict):
            service.mark_sanitized(sample.tenant_id, sample.id, passed=True)
        assert (
            service.get(sample.tenant_id, sample.id).sanitization_state is SanitizationState.PENDING
        )
    else:
        changed = service.mark_sanitized(sample.tenant_id, sample.id, passed=True)
        assert changed.sanitization_state is SanitizationState.PASSED
        assert _durable_lifecycle(custody).get(sample.tenant_id, sample.id) == changed
        assert custody.calls[-1][0:2] == ("save", 0)
        assert set(custody.current.state) <= {
            "version",
            "eligibility_verdicts",
            "promotion_verdicts",
            "evaluation_id",
            "memory_id",
        }


@pytest.mark.parametrize("operation", ["scan", "review", "level", "evaluate", "admit", "promote"])
def test_custody_lifecycle_unavailable_payload_refuses_content_operations(operation):
    from dataclasses import replace

    custody = _Custody()
    custody.current = replace(custody.current, payload=None)
    service = _durable_lifecycle(custody)
    sample = custody.current.sample
    t, s = sample.tenant_id, sample.id
    actions = {
        "scan": lambda: service.sanitize(t, s),
        "review": lambda: service.mark_sanitized(t, s, passed=True),
        "level": lambda: service.set_verification_level(t, s, VerificationLevel.VERIFIED),
        "evaluate": lambda: run(service.evaluate(t, s, {"answer": "fact"})),
        "admit": lambda: service.admit_to_training(t, s, ALL_ELIGIBLE),
        "promote": lambda: service.promote_to_gold(t, s, ALL_PROMOTABLE),
    }
    assert service.get(t, s) == sample
    report = service.sample_report(t, s)
    assert report["knowledge_key"] is None and report["sanitization_report"] is None
    assert report["derived_signals"] == {"deduplicated": False, "scan_clean": False}
    with pytest.raises(LearningError):
        actions[operation]()
    assert custody.calls == []


def test_custody_lifecycle_level_change_persists_and_foreign_is_not_exposed():
    custody = _Custody()
    sample = custody.current.sample
    service = _durable_lifecycle(custody)
    changed = service.set_verification_level(
        sample.tenant_id, sample.id, VerificationLevel.VERIFIED
    )
    assert _durable_lifecycle(custody).get(sample.tenant_id, sample.id) == changed
    with pytest.raises(LearningError):
        service.get(uuid4(), sample.id)


@pytest.mark.parametrize("race", [False, True])
def test_custody_lifecycle_evaluation_binds_evidence_without_lost_update(race):
    from core.learning.storage import LearningStorageConflict

    custody = _Custody()
    sample = custody.current.sample
    records = []
    pipeline = EvaluationPolicyService(store=InMemoryEvaluationStore())

    class Runner:
        async def evaluate(self, tenant_id, execution_id, output):
            result = await pipeline.evaluate(tenant_id, execution_id, output)
            records.append(result)
            if race:
                _durable_lifecycle(custody).mark_sanitized(tenant_id, sample.id, passed=True)
            return result

    service = _durable_lifecycle(custody, evaluation=Runner())
    if race:
        with pytest.raises(LearningStorageConflict):
            run(service.evaluate(sample.tenant_id, sample.id, {"content": "fact"}))
        assert custody.current.sample.verification_level is VerificationLevel.RAW
        assert custody.current.sample.sanitization_state is SanitizationState.PASSED
        assert "evaluation_id" not in custody.current.state
    else:
        changed = run(service.evaluate(sample.tenant_id, sample.id, {"content": "fact"}))
        assert changed.verification_level == records[0].level
        assert custody.current.state["evaluation_id"] == str(records[0].id)
        assert _durable_lifecycle(custody).get(sample.tenant_id, sample.id) == changed
    assert len(records) == 1  # committed evaluation survives a custody CAS conflict
    assert service._samples == {}


@pytest.mark.parametrize("allowed", [False, True])
def test_custody_lifecycle_eligibility_persists_closed_verdicts(allowed):
    custody = _Custody()
    sample = custody.current.sample
    service = _durable_lifecycle(custody)
    t, s = sample.tenant_id, sample.id
    service.mark_sanitized(t, s, passed=True)
    service.set_verification_level(t, s, VerificationLevel.VERIFIED)
    dataset = uuid4()
    if allowed:
        service.admit_to_training(t, s, ALL_ELIGIBLE, dataset_id=dataset)
        assert custody.current.sample.dataset_id == dataset
        assert custody.current.sample.eligibility is LearningEligibility.ELIGIBLE
        assert all(custody.current.state["eligibility_verdicts"].values())
    else:
        with pytest.raises(NotEligibleForTraining):
            service.admit_to_training(t, s, EligibilitySignals())
        assert custody.current.sample.eligibility is LearningEligibility.INELIGIBLE
        assert custody.current.state["eligibility_verdicts"]["privacy_policy_allows"] is False
    assert custody.current.revision == 3
    assert service._samples == {}


@pytest.mark.parametrize("operation", ["level", "retrieve", "keys"])
def test_custody_lifecycle_gold_bypasses_wait_for_reconciliation(operation):
    custody = _Custody()
    service = _durable_lifecycle(custody)
    t, s = custody.current.sample.tenant_id, custody.current.sample.id
    actions = {
        "level": lambda: service.set_verification_level(t, s, VerificationLevel.GOLD),
        "retrieve": lambda: service.ask_learned(t, "fact"),
        "keys": lambda: service.learned_keys(t),
    }
    with pytest.raises(LearningError, match="reconciliation"):
        actions[operation]()
    assert custody.calls == []


def test_custody_lifecycle_promotion_waits_for_derived_copy_reconciliation():
    from dataclasses import replace

    custody = _Custody()
    custody.current = replace(
        custody.current,
        sample=custody.current.sample.model_copy(
            update={
                "eligibility": LearningEligibility.ELIGIBLE,
            }
        ),
    )
    service = _durable_lifecycle(custody)
    sample = custody.current.sample
    with pytest.raises(LearningError, match="reconciliation"):
        service.promote_to_gold(sample.tenant_id, sample.id, ALL_PROMOTABLE)
    assert custody.calls == []
