"""R179 rulings Q3 (F-R179-02) — promote-to-GOLD completable over HTTP by CAPABILITY.

Before: ``security_eval_pass`` needed an evaluation record carrying a passing
``GraderType.SECURITY`` row, but SECURITY was outside ``FINAL_ACTIVE_GRADER_TYPES``
and no production path emitted such a row, so the shipped (strict) profile could
NEVER complete ``POST /v1/admin/learning/samples/{id}/promote`` over HTTP.

After (operator ruling: resolve by capability, never by relaxing the condition):

- ``SecretMaterialGrader`` is the first REAL ``GraderType.SECURITY`` grader. It is
  non-vacuous: the existing deterministic sanitizer (13 §7 credential vocabulary)
  runs over the graded output; a credential-bearing output FAILS the row.
- ``EvaluationPolicyService`` gains an injectable ``output_graders`` step (default
  empty — every MVP posture byte-identical); the learning-lifecycle composition
  in ``apps/api/app.py`` activates SECURITY through it (graders.py:44 path).
- ``POST …/evaluate`` returns ``evaluation_id`` so the caller can bind the SAME
  record as ``evidence_refs.security_evaluation_id``; ``POST …/promote`` answers
  201 when a GOLD item was really created (200 stays for refusal-as-data).
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.store import InMemoryExecutionStore
from core.contracts.base import JsonObject
from core.contracts.evaluation import GraderType, VerificationLevel
from core.evaluation import (
    FINAL_ACTIVE_GRADER_TYPES,
    EvaluationPolicyService,
    InMemoryEvaluationStore,
    OutputGraderPort,
)
from core.evaluation.errors import InactiveGraderType
from core.evaluation.graders import SecretMaterialGrader
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryMemoryStore
from tests.api.test_admin_api import World, _no_sleep
from tests.api.test_promotion_evidence_r177 import HUMAN_SIGNALS, _evaluation

SAMPLES = "/v1/admin/learning/samples"
ROOT = Path(__file__).resolve().parents[2]
TENANT = uuid4()

# Credential shapes the 13 §7 vocabulary names (never real material).
ANTHROPIC_LIKE = "sk-ant-" + "A1" * 16
GITHUB_PAT_LIKE = "ghp_" + "Q" * 36
PEM_LIKE = "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----"

ADMIT_ALL = {
    "privacy_policy_allows": True,
    "tenant_user_policy_allows": True,
    "sensitive_data_handled": True,
    "deduplicated": True,
    "not_poisoned": True,
}


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- the grader itself -----------------------------------------------------------------


class TestSecretMaterialGrader:
    def test_is_a_security_grader_on_the_output_grader_port(self) -> None:
        grader: OutputGraderPort = SecretMaterialGrader()
        assert grader.grader_type is GraderType.SECURITY

    def test_clean_output_passes(self) -> None:
        row = SecretMaterialGrader().row({"answer": "durable gold", "n": 3})
        assert row.type is GraderType.SECURITY
        assert row.passed is True
        assert row.score is None and row.confidence is None  # a CHECK row (22 §6)

    @pytest.mark.parametrize(
        ("output", "label"),
        [
            ({"answer": f"use {ANTHROPIC_LIKE}"}, "anthropic_api_key"),
            ({"nested": {"deep": [GITHUB_PAT_LIKE]}}, "github_pat"),
            ({"pem": PEM_LIKE}, "pem_private_key"),
            ({"api_key": "x"}, "credential_key"),
        ],
    )
    def test_credential_material_fails_and_is_never_echoed(
        self, output: JsonObject, label: str
    ) -> None:
        row = SecretMaterialGrader().row(output)
        assert row.passed is False
        assert label in row.name
        for secret in (ANTHROPIC_LIKE, GITHUB_PAT_LIKE, "BEGIN RSA"):
            assert secret not in row.name

    def test_deterministic_and_pure(self) -> None:
        grader = SecretMaterialGrader()
        output = {"a": f"token {GITHUB_PAT_LIKE}", "b": "fine"}
        assert grader.row(output) == grader.row(dict(output))
        assert output == {"a": f"token {GITHUB_PAT_LIKE}", "b": "fine"}  # untouched

    def test_row_name_is_bounded_even_for_many_findings(self) -> None:
        output = {f"secret_{i}": f"{ANTHROPIC_LIKE}{i}" for i in range(60)}
        row = SecretMaterialGrader().row(output)
        assert row.passed is False
        assert len(row.name) <= 200


# --- activation boundary + pipeline step ----------------------------------------------


class TestActivation:
    def test_security_is_in_the_final_active_set_with_a_real_grader_behind_it(self) -> None:
        assert GraderType.SECURITY in FINAL_ACTIVE_GRADER_TYPES
        # Still representable-only (no documented mechanism, no implementing grader):
        assert {
            GraderType.REGRESSION,
            GraderType.HUMAN_CALIBRATED,
            GraderType.PRODUCTION_SIGNAL,
        }.isdisjoint(FINAL_ACTIVE_GRADER_TYPES)

    def test_default_service_is_byte_identical_mvp_posture(self) -> None:
        store = InMemoryEvaluationStore()
        service = EvaluationPolicyService(store)
        with pytest.raises(InactiveGraderType):
            run(service.evaluate(TENANT, uuid4(), {"x": 1}, grader_types={GraderType.SECURITY}))
        record = run(service.evaluate(TENANT, uuid4(), {"x": 1}))
        assert all(r.type is GraderType.DETERMINISTIC for r in record.graders)

    def test_output_grader_runs_only_when_its_type_is_admitted(self) -> None:
        store = InMemoryEvaluationStore()
        service = EvaluationPolicyService(
            store,
            active_types=FINAL_ACTIVE_GRADER_TYPES,
            output_graders=(SecretMaterialGrader(),),
        )
        full = run(service.evaluate(TENANT, uuid4(), {"answer": "ok"}))
        assert [r.type for r in full.graders].count(GraderType.SECURITY) == 1
        assert full.level is VerificationLevel.VALIDATED  # all checks passed, no judge
        only_det = run(
            service.evaluate(
                TENANT, uuid4(), {"answer": "ok"}, grader_types={GraderType.DETERMINISTIC}
            )
        )
        assert all(r.type is GraderType.DETERMINISTIC for r in only_det.graders)

    def test_failed_security_row_caps_the_level_like_any_failed_check(self) -> None:
        store = InMemoryEvaluationStore()
        service = EvaluationPolicyService(
            store,
            active_types=FINAL_ACTIVE_GRADER_TYPES,
            output_graders=(SecretMaterialGrader(),),
        )
        record = run(service.evaluate(TENANT, uuid4(), {"answer": ANTHROPIC_LIKE}))
        security = [r for r in record.graders if r.type is GraderType.SECURITY]
        assert len(security) == 1 and security[0].passed is False
        assert record.level is VerificationLevel.EVALUATED  # 22 §12 positional cap

    def test_an_inactive_typed_output_grader_never_runs(self) -> None:
        class Rogue:
            grader_type = GraderType.PRODUCTION_SIGNAL

            def row(self, output: JsonObject) -> Any:  # pragma: no cover — must not run
                raise AssertionError("inactive grader executed")

        store = InMemoryEvaluationStore()
        service = EvaluationPolicyService(
            store, active_types=FINAL_ACTIVE_GRADER_TYPES, output_graders=(Rogue(),)
        )
        record = run(service.evaluate(TENANT, uuid4(), {"answer": "ok"}))
        assert all(r.type is not GraderType.PRODUCTION_SIGNAL for r in record.graders)


class TestShippedComposition:
    def test_learning_lifecycle_composition_activates_security_grader(self) -> None:
        source = (ROOT / "apps" / "api" / "app.py").read_text(encoding="utf-8")
        assert "active_types=FINAL_ACTIVE_GRADER_TYPES" in source
        assert "output_graders=(SecretMaterialGrader(),)" in source
        # Exactly the learning-lifecycle EvaluationPolicyService is widened.
        assert source.count("EvaluationPolicyService(") == 1


# --- HTTP: a real 201 and a real 409 -----------------------------------------------------


def _app(
    world: World, *, store: InMemoryExecutionStore | None = None, governed: bool = False
) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    custody = None
    if governed:
        from tests.learning.test_learning_lifecycle_e2e import _Custody

        custody = _Custody()
        world.principal = dataclasses.replace(
            world.principal, tenant_id=custody.current.sample.tenant_id
        )
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=dataclasses.replace(world.surface(), audit=world.audit),
        memory=InMemoryMemoryStore(),
        store=store,
        learning_custody=custody,
        strict_promotion_evidence=True,
    )


async def _post(app: FastAPI, path: str, body: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body)


def _make_eligible(app: FastAPI, sid: str) -> None:
    assert run(_post(app, f"{SAMPLES}/{sid}/sanitize", {"passed": True})).status_code == 200
    admitted = run(_post(app, f"{SAMPLES}/{sid}/admit", ADMIT_ALL))
    assert admitted.status_code == 200 and admitted.json()["admitted"] is True, admitted.text


def _eligible_sample(app: FastAPI, world: World, key: str, execution_id: UUID) -> str:
    service = app.state.learning_lifecycle_service
    sample = service.capture_from_execution(
        world.principal.tenant_id, execution_id, knowledge_key=key, knowledge_value={"a": 1}
    )
    sid = str(sample.id)
    _make_eligible(app, sid)
    return sid


def _governed_sample(app: FastAPI) -> str:
    """The governed double already holds one captured sample; make it eligible."""
    custody = app.state.learning_lifecycle_service._custody
    sid = str(custody.current.sample.id)
    _make_eligible(app, sid)
    return sid


def _regression_ref(app: FastAPI, world: World) -> str:
    world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=100.0)
    service = app.state.scenario_service
    scenario = service.save(
        world.principal.tenant_id,
        name="verification",
        ask="probe",
        checks=("output_present", "error_free_output"),
    )
    replay = run(service.replay(world.principal.tenant_id, world.principal.user_id, scenario.id))
    assert replay["passed"] is True
    return str(replay["execution_id"])


def _promote_body(app: FastAPI, world: World, sid: str, output: JsonObject) -> dict[str, object]:
    """Evaluate over HTTP and hand the SAME record back as the security ref."""
    graded = run(_post(app, f"{SAMPLES}/{sid}/evaluate", {"output": output}))
    assert graded.status_code == 200 and graded.json()["evaluated"] is True, graded.text
    evaluation_id = graded.json()["evaluation_id"]
    assert re.fullmatch(r"[0-9a-f-]{36}", evaluation_id)
    sample = app.state.learning_lifecycle_service.get(world.principal.tenant_id, UUID(sid))
    offline = _evaluation(world, sample.source_execution_id)
    return {
        **HUMAN_SIGNALS,
        "evidence_refs": {
            "evaluation_id": str(offline.id),
            "security_evaluation_id": evaluation_id,
            "regression_execution_id": _regression_ref(app, world),
        },
    }


class TestPromoteOverHttp:
    def test_clean_output_promotes_with_a_real_201_and_a_gold_item(self) -> None:
        world = World()
        store = InMemoryExecutionStore()
        app = _app(world, store=store)
        sid = _eligible_sample(app, world, "q3.clean", uuid4())
        body = _promote_body(app, world, sid, {"answer": "durable gold"})
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["promoted"] is True
        assert payload["evidence"]["resolved"]["security_eval_pass"]["held"] is True
        assert payload["knowledge_key"] == "q3.clean"
        service = app.state.learning_lifecycle_service
        assert service.get(world.principal.tenant_id, UUID(sid)).verification_level is (
            VerificationLevel.GOLD
        )

    def test_credential_bearing_output_is_refused_naming_security(self) -> None:
        world = World()
        store = InMemoryExecutionStore()
        app = _app(world, store=store)
        sid = _eligible_sample(app, world, "q3.dirty", uuid4())
        body = _promote_body(app, world, sid, {"answer": f"token {GITHUB_PAT_LIKE}"})
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        assert response.status_code == 200  # refusal-as-data in the non-governed profile
        payload = response.json()
        assert payload["promoted"] is False
        assert "security_eval_pass" in payload["reason"]
        assert payload["evidence"]["resolved"]["security_eval_pass"]["held"] is False
        assert GITHUB_PAT_LIKE not in response.text
        service = app.state.learning_lifecycle_service
        assert service.get(world.principal.tenant_id, UUID(sid)).verification_level is not (
            VerificationLevel.GOLD
        )

    def test_governed_profile_answers_409_for_the_failing_sample(self) -> None:
        world = World()
        app = _app(world, store=InMemoryExecutionStore(), governed=True)
        sid = _governed_sample(app)
        body = _promote_body(app, world, sid, {"answer": f"key {ANTHROPIC_LIKE}"})
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        assert response.status_code == 409, response.text
        assert ANTHROPIC_LIKE not in response.text

    def test_governed_profile_promotes_a_clean_sample_with_201(self) -> None:
        world = World()
        app = _app(world, store=InMemoryExecutionStore(), governed=True)
        sid = _governed_sample(app)
        body = _promote_body(app, world, sid, {"answer": "clean fact"})
        response = run(_post(app, f"{SAMPLES}/{sid}/promote", body))
        assert response.status_code == 201, response.text
        assert response.json()["promoted"] is True
