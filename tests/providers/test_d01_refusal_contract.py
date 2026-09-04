"""R168 D-01 — in-band (HTTP 200) plan refusal is a FAILED provider call, not a success.

HERMETIC (httpx.MockTransport). The captured live shape
``evidence/failure_shapes/genspark_llm_200_plan_refusal.json`` (LC-1) is an
HTTP 200 whose assistant content is a plan-refusal sentence and whose usage
reports ZERO tokens: no inference happened. Before R168 the genspark_llm
adapter booked it ``succeeded=True`` and the execution settled 1.0 unit.

Contract under test (adapter-level, providers/ — no core change):

- the adapter returns ``succeeded=False`` with a ``ProviderError`` whose
  category indicts the ACCOUNT/route (``quota_exceeded``: plan/credit
  exhaustion) — failover-permitting, never request-indicting;
- the refusal text never crosses into the error (30 §14);
- a genuine completion that merely QUOTES the refusal wording (tokens > 0)
  stays a success — the detector needs both signals;
- zero usage alone is not a refusal;
- through ExecutionService: run FAILED, 0 units settled, hold released;
- a second candidate is tried (failover-permitting) and charged exactly once.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    ProviderModelBinding,
)
from core.contracts.execute import ExecutionStatus
from core.contracts.model_policy import AutoModelPolicy
from core.contracts.provider import (
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderOperation,
)
from core.contracts.routing import CandidateScore, RoutingDecision, ScoringWeights
from core.contracts.usage import UsageLedgerStatus
from core.execution import ExecutionService
from core.providers import BindingRegistry
from core.usage.memory import InMemoryUsageAccounting
from providers.real.genspark_llm import MANIFEST, GensparkLLMAdapter

REPO = Path(__file__).resolve().parents[2]
SHAPE = REPO / "evidence" / "failure_shapes" / "genspark_llm_200_plan_refusal.json"
API_KEY = "gsk-TEST_ONLY_fake_key_for_mock_transport"
CRED_REF = "credref_test_opaque_handle"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _refusal_body() -> dict[str, Any]:
    doc = json.loads(SHAPE.read_text())
    assert doc["_meta"]["http_status"] == 200
    body: dict[str, Any] = doc["body"]
    return body


def _adapter(body: dict[str, Any], status: int = 200) -> GensparkLLMAdapter:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return GensparkLLMAdapter(
        MANIFEST,
        secret_resolver=lambda ref: API_KEY,
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(responder),
    )


def _request() -> ProviderGenerateRequest:
    return ProviderGenerateRequest.model_validate(
        {
            "request_id": uuid4(),
            "tenant_id": uuid4(),
            "operation": ProviderOperation.GENERATE_TEXT,
            "provider_model_name": "gpt-5-nano",
            "credential_ref": CRED_REF,
            "payload": {"ask": "hello"},
        }
    )


# --- adapter contract ------------------------------------------------------------------


def test_200_plan_refusal_is_a_failed_call_not_a_success() -> None:
    response = run(_adapter(_refusal_body()).generate(_request()))
    assert response.succeeded is False
    assert response.output == {}
    assert response.error is not None
    # Account/plan-indicting: the ROUTE (this credential's plan) is exhausted;
    # another account or provider can serve the request ⇒ failover-permitting.
    assert response.error.category is ProviderErrorCategory.QUOTA_EXCEEDED
    assert response.error.retryable is False
    assert response.error.provider_code == "plan_refusal_200"


def test_refusal_text_never_crosses_into_the_error() -> None:
    response = run(_adapter(_refusal_body()).generate(_request()))
    assert response.error is not None
    serialized = response.error.model_dump_json()
    assert "Free-plan" not in serialized
    assert "pricing" not in serialized


def test_genuine_completion_quoting_the_refusal_wording_stays_a_success() -> None:
    body = _refusal_body()
    # Same sentence, but inference DID happen (tokens consumed) — not a refusal.
    body["usage"] = {"prompt_tokens": 12, "completion_tokens": 40, "total_tokens": 52}
    response = run(_adapter(body).generate(_request()))
    assert response.succeeded is True
    assert response.error is None


def test_zero_usage_alone_is_not_a_refusal() -> None:
    body = _refusal_body()
    body["choices"][0]["message"]["content"] = "hi there"
    response = run(_adapter(body).generate(_request()))
    assert response.succeeded is True


# --- execution + settlement --------------------------------------------------------------


def _model() -> Model:
    return Model(
        id=uuid4(),
        model_key="m-alpha",
        display_name="m-alpha",
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        status=ModelStatus.ACTIVE,
    )


def _world(
    *bodies: dict[str, Any],
) -> tuple[ExecutionService, RoutingDecision, InMemoryUsageAccounting, UUID]:
    model = _model()
    bindings = BindingRegistry()
    adapters: dict[UUID, GensparkLLMAdapter] = {}
    refs: dict[UUID, str] = {}
    candidates: list[CandidateScore] = []
    for body in bodies:
        pid = uuid4()
        adapters[pid] = _adapter(body)
        refs[pid] = CRED_REF
        bindings.register(
            ProviderModelBinding(
                provider_id=pid,
                model_id=model.id,
                provider_model_name="gpt-5-nano",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        candidates.append(CandidateScore(model_id=model.id, provider_id=pid, score=0.9))
    decision = RoutingDecision(
        selected=candidates[0],
        ranked=candidates,
        fallback_candidates=candidates[1:],
        policy_snapshot=AutoModelPolicy(type="auto"),
        weights=ScoringWeights(),
    )
    accounting = InMemoryUsageAccounting()
    tenant = uuid4()
    accounting.configure_tenant(tenant, plan="pro", task_units_limit=10.0)

    async def _no_sleep(_: float) -> None:
        return None

    service = ExecutionService(
        adapters=adapters,
        credential_refs=refs,
        bindings=bindings,
        max_retries_per_candidate=1,
        usage=accounting,
        sleeper=_no_sleep,
    )
    return service, decision, accounting, tenant


def _ok_body() -> dict[str, Any]:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": "real answer"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        "model": "gpt-5-nano",
    }


def _execute(service: ExecutionService, decision: RoutingDecision, tenant: UUID) -> Any:
    return run(
        service.execute_single(
            tenant_id=tenant,
            user_id=uuid4(),
            decision=decision,
            operation=ProviderOperation.GENERATE_TEXT,
            payload={"ask": "hello"},
            request_hash="h",
        )
    )


def test_refusal_run_is_failed_and_settles_zero_units() -> None:
    service, decision, accounting, tenant = _world(_refusal_body())
    report = _execute(service, decision, tenant)
    assert report.execution.status is ExecutionStatus.FAILED
    assert report.final_output is None
    node = report.nodes[0].node
    assert node.error is not None
    assert node.error["category"] == "quota_exceeded"
    assert report.usage is not None
    assert report.usage.status is UsageLedgerStatus.FAILED
    assert report.usage.units_settled == 0.0
    assert accounting.summary(tenant).task_units.used == 0.0
    assert accounting.summary(tenant).task_units.remaining == 10.0


def test_refusal_is_failover_permitting() -> None:
    service, decision, accounting, tenant = _world(_refusal_body(), _ok_body())
    report = _execute(service, decision, tenant)
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.final_output is not None
    assert report.final_output["content"] == "real answer"
    tried = [a.candidate.provider_id for a in report.nodes[0].attempts]
    assert len(tried) == 2 and tried[0] != tried[1]
    assert report.usage is not None
    assert report.usage.units_settled == 1.0  # ONE succeeded stage, charged once
    assert accounting.summary(tenant).task_units.used == 1.0
