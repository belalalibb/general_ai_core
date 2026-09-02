"""R161 Phase 3 — Real Learning Improvement, part 1: sanitization is MEASURED.

22 §12 names the test verbatim: "sanitization removes secrets". Before
R161 the lifecycle's sanitization step was a reviewer toggle with no
machine check; a secret-bearing sample travelled the whole pipeline and
failed only at the memory write (GOLD promotion — the LAST step).

Pins (hermetic, pure):
- the sanitizer is deterministic and NEVER echoes the matched text;
- findings name path + label from the closed SECRET_LABELS set;
- ``mark_sanitized(passed=True)`` over findings is REFUSED (and the
  sample is marked FAILED, never silently PASSED);
- ``passed=False`` is always accepted (a reviewer may fail for reasons
  the scanner cannot see);
- derived signals: byte-identical duplicates are detected; the scan
  verdict lowers ``not_poisoned``; assertions cannot raise either;
- over HTTP: POST .../scan reports; POST .../sanitize refusal is an
  honest 200 with ``sanitized: false`` + report; admit of a duplicate is
  refused naming ``deduplicated`` even when the caller asserted True.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import pytest

from core.contracts.learning import SanitizationState
from core.learning import (
    SECRET_LABELS,
    EligibilitySignals,
    LearningLifecycleService,
    NotEligibleForTraining,
    SanitizationRefused,
    sanitize_knowledge,
)
from core.memory.memory import InMemoryMemoryStore

TENANT = uuid4()
FAKE_PAT = "ghp_" + "A" * 36
FAKE_AWS = "AKIA" + "Z" * 16

ALL_TRUE = EligibilitySignals(
    privacy_policy_allows=True,
    tenant_user_policy_allows=True,
    sensitive_data_handled=True,
    deduplicated=True,
    not_poisoned=True,
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _service() -> LearningLifecycleService:
    return LearningLifecycleService(knowledge=InMemoryMemoryStore())


class TestSanitizerIsPureAndNonRevealing:
    def test_clean_knowledge_reports_clean(self) -> None:
        report = sanitize_knowledge("ops.rollback", {"answer": "drain, flip alias, verify"})
        assert report.clean is True
        assert report.findings == ()
        assert report.scanned_paths >= 2

    def test_findings_name_path_and_label_never_content(self) -> None:
        report = sanitize_knowledge(
            "deploy.notes",
            {"steps": ["export TOKEN", f"use {FAKE_PAT} to push"], "aws": {"id": FAKE_AWS}},
        )
        assert report.clean is False
        labels = {f.label for f in report.findings}
        assert {"github_pat", "aws_access_key_id"} <= labels
        assert labels <= set(SECRET_LABELS)
        paths = {f.path for f in report.findings}
        assert "steps[1]" in paths and "aws.id" in paths
        dumped = str(report.as_json())
        assert FAKE_PAT not in dumped and FAKE_AWS not in dumped  # never echoed
        for finding in report.findings:
            assert len(finding.fingerprint) == 12

    def test_credential_like_keys_are_findings(self) -> None:
        report = sanitize_knowledge("service.api_key", {"value": "not-a-real-token"})
        assert any(f.label == "credential_key" and f.path == "$key" for f in report.findings)
        nested = sanitize_knowledge("ok", {"config": {"client_secret": "x"}})
        assert any(f.path == "config.client_secret#key" for f in nested.findings)

    def test_deterministic(self) -> None:
        payload = {"a": [f"Bearer {'q' * 20}", 1, None, True], "b": {"c": "plain"}}
        assert sanitize_knowledge("k", payload) == sanitize_knowledge("k", payload)


class TestReviewedActIsGatedByTheScan:
    def test_passed_true_over_findings_is_refused_and_marks_failed(self) -> None:
        svc = _service()
        sample = svc.capture_external(
            TENANT, knowledge_key="k", knowledge_value={"note": f"token {FAKE_PAT}"}
        )
        with pytest.raises(SanitizationRefused) as exc:
            svc.mark_sanitized(TENANT, sample.id, passed=True)
        assert svc.get(TENANT, sample.id).sanitization_state is SanitizationState.FAILED
        assert FAKE_PAT not in str(exc.value)
        report = svc.sample_report(TENANT, sample.id)
        assert report["sanitization_report"]["clean"] is False

    def test_passed_false_always_accepted(self) -> None:
        svc = _service()
        dirty = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": FAKE_AWS})
        clean = svc.capture_external(TENANT, knowledge_key="k2", knowledge_value={"v": "fine"})
        for sample in (dirty, clean):
            state = svc.mark_sanitized(TENANT, sample.id, passed=False).sanitization_state
            assert state is SanitizationState.FAILED

    def test_clean_sample_passes_and_scan_runs_implicitly(self) -> None:
        svc = _service()
        sample = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": "fine"})
        assert svc.sample_report(TENANT, sample.id)["sanitization_report"] is None
        state = svc.mark_sanitized(TENANT, sample.id, passed=True).sanitization_state
        assert state is SanitizationState.PASSED
        assert svc.sample_report(TENANT, sample.id)["sanitization_report"]["clean"] is True


class TestDerivedSignals:
    def test_byte_identical_duplicate_is_detected_per_tenant(self) -> None:
        svc = _service()
        first = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"a": 1, "b": 2})
        assert svc.derived_signals(TENANT, first.id)["deduplicated"] is True
        # same content, different key order → still a duplicate (canonical)
        second = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"b": 2, "a": 1})
        assert svc.derived_signals(TENANT, second.id)["deduplicated"] is False
        assert svc.derived_signals(TENANT, first.id)["deduplicated"] is False
        # another tenant's identical sample is invisible (tenant isolation)
        other_tenant = uuid4()
        other = svc.capture_external(
            other_tenant, knowledge_key="k", knowledge_value={"a": 1, "b": 2}
        )
        assert svc.derived_signals(other_tenant, other.id)["deduplicated"] is True

    def test_assertions_cannot_raise_derived_facts(self) -> None:
        svc = _service()
        a = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": FAKE_PAT})
        svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": FAKE_PAT})
        resolved = svc.resolve_signals(TENANT, a.id, ALL_TRUE)
        assert resolved.deduplicated is False
        assert resolved.not_poisoned is False
        assert resolved.privacy_policy_allows is True  # untouched

    def test_admit_refuses_duplicate_naming_the_condition(self) -> None:
        svc = _service()
        a = svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": "same"})
        svc.capture_external(TENANT, knowledge_key="k", knowledge_value={"v": "same"})
        svc.mark_sanitized(TENANT, a.id, passed=True)
        with pytest.raises(NotEligibleForTraining) as exc:
            svc.admit_to_training(TENANT, a.id, ALL_TRUE)
        assert "deduplicated" in exc.value.failed
        assert "not_poisoned" not in exc.value.failed  # clean content stays trusted
        report = svc.sample_report(TENANT, a.id)
        assert report["eligibility_verdicts"]["deduplicated"] is False
        assert report["derived_signals"] == {"deduplicated": False, "scan_clean": True}


class TestOverHttp:
    def test_scan_and_refusal_ride_the_admin_routes(self) -> None:
        from tests.api.test_admin_api import World
        from tests.api.test_learning_lifecycle_routes import SAMPLES, _app, _get, _post

        world = World()
        app = _app(world)
        service = app.state.learning_lifecycle_service
        dirty = service.capture_external(
            world.principal.tenant_id, knowledge_key="k", knowledge_value={"v": FAKE_PAT}
        )
        scan = run(_post(app, f"{SAMPLES}/{dirty.id}/scan"))
        assert scan.status_code == 200
        assert scan.json()["clean"] is False
        assert FAKE_PAT not in scan.text
        refused = run(_post(app, f"{SAMPLES}/{dirty.id}/sanitize", {"passed": True}))
        assert refused.status_code == 200
        assert refused.json()["sanitized"] is False
        assert {f["label"] for f in refused.json()["report"]["findings"]} == {"github_pat"}
        report = run(_get(app, f"{SAMPLES}/{dirty.id}"))
        assert report.json()["sample"]["sanitization_state"] == "failed"
        assert report.json()["derived_signals"] == {"deduplicated": True, "scan_clean": False}
        # unknown id → 404 (anti-enumeration parity with the other verbs)
        assert run(_post(app, f"{SAMPLES}/{uuid4()}/scan")).status_code == 404


class TestPromotionIsTheKnowledgeWrite:
    """R161 self-audit: GOLD is stamped only AFTER the memory substrate accepted
    the item. A refused write (backend failure, 13 §7 secret screen) leaves the
    sample unpromoted — never GOLD-on-paper with nothing retrievable."""

    @staticmethod
    def _eligible(service: LearningLifecycleService, tenant: Any) -> Any:
        from core.contracts.evaluation import VerificationLevel

        sample = service.capture_external(
            tenant, knowledge_key="ops.k", knowledge_value={"answer": "drain then flip"}
        )
        service.mark_sanitized(tenant, sample.id, passed=True)
        service.set_verification_level(tenant, sample.id, VerificationLevel.VERIFIED)
        service.admit_to_training(tenant, sample.id, ALL_TRUE)
        return sample

    def test_refused_write_leaves_level_and_audit_untouched(self) -> None:
        from core.audit.memory import InMemoryAuditLog
        from core.contracts.audit import AuditEventType
        from core.contracts.evaluation import VerificationLevel
        from core.contracts.memory import MemoryItem
        from core.learning import PromotionSignals
        from core.memory.errors import MemoryStoreError

        class RefusingStore(InMemoryMemoryStore):
            def upsert(self, item: MemoryItem) -> MemoryItem:
                raise MemoryStoreError("backend unavailable")

        audit = InMemoryAuditLog()
        service = LearningLifecycleService(knowledge=RefusingStore(), audit=audit)
        tenant = uuid4()
        sample = self._eligible(service, tenant)
        signals = PromotionSignals(
            offline_eval_pass=True,
            regression_pass=True,
            security_eval_pass=True,
            shadow_performance_acceptable=True,
            canary_performance_acceptable=True,
            rollback_plan_exists=True,
            approval_required=True,
            admin_approved=True,
        )
        with pytest.raises(MemoryStoreError):
            service.promote_to_gold(tenant, sample.id, signals)
        report = service.sample_report(tenant, sample.id)
        assert report["sample"]["verification_level"] == VerificationLevel.VERIFIED.value
        assert audit.read(tenant, AuditEventType.TRAINING_DATASET_PROMOTED) == ()
        assert service.ask_learned(tenant, "ops.k")["found"] is False

    def test_route_reports_refused_write_honestly(self) -> None:
        from core.contracts.memory import MemoryItem
        from core.memory.errors import MemoryStoreError
        from tests.api.test_admin_api import World
        from tests.api.test_learning_lifecycle_routes import ALL_PROMOTE, SAMPLES, _app, _post

        world = World()
        app = _app(world)
        service = app.state.learning_lifecycle_service
        tenant = world.principal.tenant_id
        sample = self._eligible(service, tenant)

        def refuse(item: MemoryItem) -> MemoryItem:
            raise MemoryStoreError("backend unavailable")

        service._knowledge.upsert = refuse  # type: ignore[method-assign]
        response = run(_post(app, f"{SAMPLES}/{sample.id}/promote", ALL_PROMOTE))
        assert response.status_code == 200
        body = response.json()
        assert body["promoted"] is False
        assert body["stage"] == "knowledge_write"
        assert "backend unavailable" in body["reason"]
