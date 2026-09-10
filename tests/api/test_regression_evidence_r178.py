"""R178-DEC-01: stored, immutable verification evidence, never status-only trust."""

from __future__ import annotations

import dataclasses
from uuid import UUID, uuid4

import pytest

from apps.api.promotion_evidence import PromotionEvidenceResolver
from apps.api.store import InMemoryExecutionStore
from core.contracts.evaluation import EvaluationRecord, GraderResult, GraderType, VerificationLevel
from core.evaluation.errors import DuplicateEvaluation
from core.evaluation.memory import InMemoryEvaluationStore
from evidence.r178.probe_learning_chain import FailedQualityAdapter
from tests.api.test_admin_api import World
from tests.api.test_learning_lifecycle_routes import ALL_ADMIT
from tests.api.test_promotion_evidence_r177 import (
    HUMAN_SIGNALS,
    SAMPLES,
    _app,
    _post,
    _scenario_report,
    run,
)


def replay(*, failed: bool = False):
    world = World()
    if failed:
        world.adapter = FailedQualityAdapter()
    world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=100.0)
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    service = app.state.scenario_service
    scenario = service.save(
        world.principal.tenant_id,
        name="stored evidence",
        ask="probe",
        checks=("output_present", "error_free_output"),
    )
    result = run(service.replay(world.principal.tenant_id, world.principal.user_id, scenario.id))
    return world, store, app, UUID(result["execution_id"]), result


def resolve(world, store, execution_id, evaluations=None):
    return PromotionEvidenceResolver(
        evaluations=evaluations if evaluations is not None else world.evaluations,
        executions=store,
    ).regression(world.principal.tenant_id, execution_id)


def test_real_replay_stores_immutable_results_and_new_reader_resolves_them():
    world, store, app, execution_id, result = replay()
    records = world.evaluations.list_for_execution(world.principal.tenant_id, execution_id)
    assert len(records) == 1
    record = records[0]
    assert result["evaluation_id"] == str(record.id)
    assert record.evidence_ref.startswith("regression:v1:")
    assert {g.name for g in record.graders} == {"output_present", "error_free_output"}
    assert all(g.type is GraderType.REGRESSION and g.passed is True for g in record.graders)
    with pytest.raises(DuplicateEvaluation):
        world.evaluations.record(record.model_copy(update={"level": VerificationLevel.RAW}))
    # Reader does not depend on a mutable current scenario or process-local verdict map.
    app.state.scenario_service._scenarios.clear()
    assert resolve(world, store, execution_id).held is True


def test_successful_execution_with_failed_required_check_is_not_promotion_evidence():
    world, store, _, execution_id, result = replay(failed=True)
    assert result["passed"] is False
    assert resolve(world, store, execution_id).held is False
    records = world.evaluations.list_for_execution(world.principal.tenant_id, execution_id)
    assert len(records) == 1
    assert any(g.passed is False for g in records[0].graders)


def test_legacy_status_and_replay_label_without_stored_evidence_is_refused():
    world = World()
    store = InMemoryExecutionStore()
    report = _scenario_report(world)
    store.put(report)
    assert resolve(world, store, report.execution.id).held is False


@pytest.mark.parametrize("mutation", ["output", "scenario", "version", "checks"])
def test_modified_execution_provenance_cannot_reuse_evidence(mutation):
    world, store, _, execution_id, _ = replay()
    report = store.get(world.principal.tenant_id, execution_id)
    node = report.nodes[-1]
    if mutation == "output":
        changed = dataclasses.replace(
            node, response=node.response.model_copy(update={"output": {"content": "changed"}})
        )
    else:
        import copy

        payload = copy.deepcopy(node.node.input_ref)
        label = payload["context"]["metadata"]["test_scenario"]
        key = {"scenario": "scenario_id", "version": "evidence_version", "checks": "checks"}[
            mutation
        ]
        label[key] = [] if mutation == "checks" else "changed"
        changed = dataclasses.replace(
            node, node=node.node.model_copy(update={"input_ref": payload})
        )
    store.put(dataclasses.replace(report, nodes=(*report.nodes[:-1], changed)))
    assert resolve(world, store, execution_id).held is False


@pytest.mark.parametrize("mutation", ["missing", "foreign", "level", "check", "fingerprint"])
def test_missing_or_invalid_stored_record_denies(mutation):
    world, store, _, execution_id, _ = replay()
    original = world.evaluations.list_for_execution(world.principal.tenant_id, execution_id)
    assert len(original) == 1
    record = original[0]
    changed = InMemoryEvaluationStore()
    updates = {
        "foreign": {"tenant_id": uuid4()},
        "level": {"level": VerificationLevel.EVALUATED},
        "check": {"graders": record.graders[:-1]},
        "fingerprint": {"evidence_ref": "regression:v1:invalid"},
    }
    if mutation != "missing":
        changed.record(record.model_copy(update=updates[mutation]))
    assert resolve(world, store, execution_id, changed).held is False


def test_evidence_write_failure_never_returns_a_successful_replay_verdict():
    world = World()

    class Unavailable(InMemoryEvaluationStore):
        def record(self, evaluation):
            raise ConnectionError("evidence unavailable")

    world.evaluations = Unavailable()
    world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=100.0)
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    service = app.state.scenario_service
    scenario = service.save(
        world.principal.tenant_id, name="probe", ask="probe", checks=("output_present",)
    )
    with pytest.raises(ConnectionError):
        run(service.replay(world.principal.tenant_id, world.principal.user_id, scenario.id))


@pytest.mark.parametrize("strict", [False, True])
def test_unbacked_legacy_booleans_cannot_promote_even_with_compatibility_flag(strict):
    world = World()
    app = _app(world, strict=strict)
    created = run(_post(app, SAMPLES, {"knowledge_key": "probe", "knowledge_value": {"answer": 1}}))
    sid = created.json()["id"]
    run(_post(app, f"{SAMPLES}/{sid}/sanitize", {"passed": True}))
    run(_post(app, f"{SAMPLES}/{sid}/admit", ALL_ADMIT))
    result = run(
        _post(
            app,
            f"{SAMPLES}/{sid}/promote",
            {
                **HUMAN_SIGNALS,
                "offline_eval_pass": True,
                "security_eval_pass": True,
                "regression_pass": True,
            },
        )
    ).json()
    assert result["promoted"] is False
    assert set(result["evidence"]["refused_unbacked"]) == {
        "offline_eval_pass",
        "security_eval_pass",
        "regression_pass",
    }


def test_judgment_without_explicit_passing_checks_is_not_a_verification_pass():
    world = World()
    source = uuid4()
    record = world.evaluations.record(
        EvaluationRecord(
            tenant_id=world.principal.tenant_id,
            execution_id=source,
            level=VerificationLevel.EVALUATED,
            graders=(
                GraderResult(type=GraderType.SECURITY, name="review", score=0.0, confidence=1.0),
            ),
        )
    )
    resolver = PromotionEvidenceResolver(evaluations=world.evaluations, executions=None)
    assert resolver.evaluation(world.principal.tenant_id, source, record.id).held is False
    assert resolver.security_evaluation(world.principal.tenant_id, source, record.id).held is False
