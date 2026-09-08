"""R177-FIX-08 — evidence-bound promotion signals (G-A07-1).

Before: ``POST /v1/admin/learning/samples/{id}/promote`` accepted
``offline_eval_pass`` / ``regression_pass`` / ``security_eval_pass`` as bare
booleans from the caller; the 22 §11 gate was a correct policy engine over
unverified inputs. After: the three artefact-backed signals may be RESOLVED
from recorded evidence (``evidence_refs``) and — when the composition sets
``strict_promotion_evidence=True`` — a caller-asserted ``True`` without a ref
is refused, naming the condition. ``shadow_*`` / ``canary_*`` /
``rollback_plan_exists`` / ``admin_approved`` stay human-asserted and are
labelled ``unverified`` in the response. PromotionGate is unchanged.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import create_app
from apps.api.promotion_evidence import PromotionEvidenceResolver
from apps.api.scenarios import SCENARIO_LABEL_KEY
from apps.api.store import InMemoryExecutionStore
from core.contracts.base import utc_now
from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.contracts.provider import ProviderGenerateResponse
from core.execution.service import ExecutionReport, ExecutionService, NodeReport
from core.memory.memory import InMemoryMemoryStore
from tests.api.test_admin_api import World, _no_sleep

SAMPLES = "/v1/admin/learning/samples"

HUMAN_SIGNALS = {
    "shadow_performance_acceptable": True,
    "canary_performance_acceptable": True,
    "rollback_plan_exists": True,
    "approval_required": True,
    "admin_approved": True,
}


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _app(world: World, *, strict: bool, store: InMemoryExecutionStore | None = None) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=dataclasses.replace(world.surface(), audit=world.audit),
        memory=InMemoryMemoryStore(),
        store=store,
        strict_promotion_evidence=strict,
    )


async def _post(app: FastAPI, path: str, body: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body)


def _eligible_sample(app: FastAPI, world: World, key: str, execution_id: UUID) -> str:
    service = app.state.learning_lifecycle_service
    sample = service.capture_from_execution(
        world.principal.tenant_id, execution_id, knowledge_key=key, knowledge_value={"a": 1}
    )
    sid = str(sample.id)
    run(_post(app, f"{SAMPLES}/{sid}/sanitize", {"passed": True}))
    run(
        _post(
            app,
            f"{SAMPLES}/{sid}/admit",
            {
                "privacy_policy_allows": True,
                "tenant_user_policy_allows": True,
                "sensitive_data_handled": True,
                "deduplicated": True,
                "not_poisoned": True,
            },
        )
    )
    return sid


def _evaluation(
    world: World,
    execution_id: UUID,
    *,
    level: VerificationLevel = VerificationLevel.VALIDATED,
    passed: bool = True,
    grader: GraderType = GraderType.DETERMINISTIC,
    tenant_id: UUID | None = None,
) -> EvaluationRecord:
    record = EvaluationRecord(
        tenant_id=tenant_id or world.principal.tenant_id,
        execution_id=execution_id,
        level=level,
        graders=(GraderResult(type=grader, name="output_present", passed=passed),),
    )
    return world.evaluations.record(record)


def _scenario_report(
    world: World, *, status: ExecutionStatus = ExecutionStatus.SUCCEEDED, labelled: bool = True
) -> ExecutionReport:
    now = utc_now()
    exec_id = uuid4()
    metadata = {SCENARIO_LABEL_KEY: {"scenario_id": str(uuid4())}} if labelled else {}
    node = ExecutionNode(
        id=uuid4(),
        execution_id=exec_id,
        node_key="single",
        type=ExecutionNodeType.MODEL_CALL,
        status=ExecutionNodeStatus.SUCCEEDED,
        input_ref={"ask": "x", "context": {"metadata": metadata}},
        retry_count=0,
    )
    return ExecutionReport(
        execution=Execution(
            id=exec_id,
            tenant_id=world.principal.tenant_id,
            user_id=world.principal.user_id,
            request_hash="sha256:scenario",
            status=status,
            strategy=ExecutionStrategy.SINGLE,
            cost_snapshot={"estimated_units": 1},
            created_at=now,
            completed_at=now,
        ),
        nodes=(NodeReport(node=node, attempts=(), response=ProviderGenerateResponse(output={"text": "ok"})),),
        status_history=(status,),
    )


class TestStrictMode:
    def test_asserted_true_without_refs_is_refused_naming_the_condition(self) -> None:
        world = World()
        app = _app(world, strict=True)
        sid = _eligible_sample(app, world, "k.strict", uuid4())
        body = {
            **HUMAN_SIGNALS,
            "offline_eval_pass": True,
            "regression_pass": True,
            "security_eval_pass": True,
        }
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        assert response.status_code == 200
        payload = response.json()
        assert payload["promoted"] is False
        assert "offline_eval_pass" in payload["reason"]
        assert "regression_pass" in payload["reason"]
        assert "security_eval_pass" in payload["reason"]
        assert payload["evidence"]["strict"] is True
        assert payload["evidence"]["refused_unbacked"] == [
            "offline_eval_pass",
            "regression_pass",
            "security_eval_pass",
        ]

    def test_resolved_refs_promote_and_label_human_signals_unverified(self) -> None:
        world = World()
        store = InMemoryExecutionStore()
        app = _app(world, strict=True, store=store)
        source = uuid4()
        sid = _eligible_sample(app, world, "k.backed", source)
        offline = _evaluation(world, source)
        security = _evaluation(world, source, grader=GraderType.SECURITY)
        regression = _scenario_report(world)
        store.put(regression)
        body = {
            **HUMAN_SIGNALS,
            "evidence_refs": {
                "evaluation_id": str(offline.id),
                "security_evaluation_id": str(security.id),
                "regression_execution_id": str(regression.execution.id),
            },
        }
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        payload = response.json()
        assert payload["promoted"] is True, payload
        ev = payload["evidence"]
        assert ev["resolved"]["offline_eval_pass"]["held"] is True
        assert ev["resolved"]["offline_eval_pass"]["level"] == "VALIDATED"
        assert ev["resolved"]["security_eval_pass"]["held"] is True
        assert ev["resolved"]["regression_pass"]["held"] is True
        assert sorted(ev["unverified"]) == [
            "admin_approved",
            "canary_performance_acceptable",
            "rollback_plan_exists",
            "shadow_performance_acceptable",
        ]

    def test_failed_evaluation_resolves_to_false_and_is_refused(self) -> None:
        world = World()
        app = _app(world, strict=True)
        source = uuid4()
        sid = _eligible_sample(app, world, "k.failed", source)
        bad = _evaluation(world, source, level=VerificationLevel.EVALUATED, passed=False)
        body = {
            **HUMAN_SIGNALS,
            "regression_pass": True,
            "security_eval_pass": True,
            "evidence_refs": {"evaluation_id": str(bad.id)},
        }
        payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
        assert payload["promoted"] is False
        assert "offline_eval_pass" in payload["reason"]
        assert payload["evidence"]["resolved"]["offline_eval_pass"]["held"] is False

    def test_evaluation_of_another_execution_does_not_count(self) -> None:
        world = World()
        app = _app(world, strict=True)
        sid = _eligible_sample(app, world, "k.other", uuid4())
        other = _evaluation(world, uuid4())  # correct tenant, wrong execution
        body = {**HUMAN_SIGNALS, "evidence_refs": {"evaluation_id": str(other.id)}}
        payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
        assert payload["promoted"] is False
        resolved = payload["evidence"]["resolved"]["offline_eval_pass"]
        assert resolved["held"] is False
        assert resolved["reason"] == "evaluation is not of the sample's source execution"

    def test_unknown_or_foreign_tenant_refs_are_the_same_not_found(self) -> None:
        world = World()
        app = _app(world, strict=True)
        source = uuid4()
        sid = _eligible_sample(app, world, "k.foreign", source)
        foreign = _evaluation(world, source, tenant_id=uuid4())
        for ref in (str(uuid4()), str(foreign.id)):
            body = {**HUMAN_SIGNALS, "evidence_refs": {"evaluation_id": ref}}
            payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
            assert payload["promoted"] is False
            assert payload["evidence"]["resolved"]["offline_eval_pass"]["reason"] == "not found"

    def test_regression_ref_must_be_a_succeeded_scenario_execution(self) -> None:
        world = World()
        store = InMemoryExecutionStore()
        app = _app(world, strict=True, store=store)
        sid = _eligible_sample(app, world, "k.reg", uuid4())
        unlabelled = _scenario_report(world, labelled=False)
        failed = _scenario_report(world, status=ExecutionStatus.FAILED)
        store.put(unlabelled)
        store.put(failed)
        for report, reason in (
            (unlabelled, "execution is not a scenario replay"),
            (failed, "scenario replay did not succeed"),
        ):
            body = {
                **HUMAN_SIGNALS,
                "evidence_refs": {"regression_execution_id": str(report.execution.id)},
            }
            payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
            assert payload["promoted"] is False
            assert payload["evidence"]["resolved"]["regression_pass"]["reason"] == reason

    def test_malformed_ref_is_a_validation_error(self) -> None:
        world = World()
        app = _app(world, strict=True)
        sid = _eligible_sample(app, world, "k.bad", uuid4())
        body = {**HUMAN_SIGNALS, "evidence_refs": {"evaluation_id": "not-a-uuid"}}
        assert run(_post(app, f"{SAMPLES}/{sid}/promote", body)).status_code == 422
        body = {**HUMAN_SIGNALS, "evidence_refs": {"unknown": "x"}}
        assert run(_post(app, f"{SAMPLES}/{sid}/promote", body)).status_code == 422


class TestCompatibleMode:
    def test_non_strict_keeps_asserted_booleans_but_labels_them(self) -> None:
        world = World()
        app = _app(world, strict=False)
        sid = _eligible_sample(app, world, "k.compat", uuid4())
        body = {
            **HUMAN_SIGNALS,
            "offline_eval_pass": True,
            "regression_pass": True,
            "security_eval_pass": True,
        }
        payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
        assert payload["promoted"] is True
        assert payload["evidence"]["strict"] is False
        assert "offline_eval_pass" in payload["evidence"]["unverified"]

    def test_refs_override_asserted_booleans_even_when_not_strict(self) -> None:
        world = World()
        app = _app(world, strict=False)
        source = uuid4()
        sid = _eligible_sample(app, world, "k.override", source)
        bad = _evaluation(world, source, level=VerificationLevel.EVALUATED, passed=False)
        body = {
            **HUMAN_SIGNALS,
            "offline_eval_pass": True,  # caller says yes …
            "regression_pass": True,
            "security_eval_pass": True,
            "evidence_refs": {"evaluation_id": str(bad.id)},  # … the record says no
        }
        payload = run(_post(app, f"{SAMPLES}/{sid}/promote", body)).json()
        assert payload["promoted"] is False
        assert "offline_eval_pass" in payload["reason"]


class TestResolverUnit:
    def test_raw_record_is_not_a_pass(self) -> None:
        world = World()
        source = uuid4()
        raw = world.evaluations.record(
            EvaluationRecord(
                tenant_id=world.principal.tenant_id,
                execution_id=source,
                level=VerificationLevel.RAW,
            )
        )
        resolver = PromotionEvidenceResolver(evaluations=world.evaluations, executions=None)
        verdict = resolver.evaluation(world.principal.tenant_id, source, raw.id)
        assert verdict.held is False
        assert verdict.reason == "record is RAW (not evaluated)"

    def test_regression_without_execution_store_is_honest(self) -> None:
        world = World()
        resolver = PromotionEvidenceResolver(evaluations=world.evaluations, executions=None)
        verdict = resolver.regression(world.principal.tenant_id, uuid4())
        assert verdict.held is False
        assert verdict.reason == "no execution store composed"


def test_runtime_profile_enables_strict_evidence() -> None:
    from pathlib import Path

    source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "strict_promotion_evidence=True," in source
