"""API surface semantics (T-IMPL-023; 41 §44; 10 §2-§5, §9-§10).

Hermetic — httpx ASGI transport against the composed FastAPI app; fake
provider adapters only, no network, no server process (41 §49: end-to-end
AI execution stays PENDING_REAL_PROVIDERS). Async requests are driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers:

- POST /v1/execute happy path -> 200 ExecuteSyncResponse (10 §3).
- GET /v1/executions/{id} for succeeded and failed executions (10 §5).
- Unified error envelope on EVERY non-success body (10 §9): contract
  validation, unsupported policy, no candidates, provider failure mapping.
- Loud slice rejections: async=true / stream=true -> validation_error.
- Idempotency-Key replay returns the SAME execution (10 §10).
- Unknown execution id -> 404 with the recorded mapping decision.
- Provider internals never leak to clients (20 §4 / 30 §14).
- Usage block (T-IMPL-024; 10 §3): settled ledger surfaces on success;
  entitlement denials map to entitlement_exceeded 403 BEFORE provider work.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import InMemoryExecutionStore, Principal, create_app
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- fake adapter (scripted, mirrors tests/execution posture) ------------------------


def _provider_error(
    category: ProviderErrorCategory, *, retryable: bool = False
) -> ProviderError:
    return ProviderError(
        category=category,
        retryable=retryable,
        safe_message=f"fake {category.value}",
        provider_code="RAW-INTERNAL-CODE",  # must never surface to clients
    )


class FakeAdapter:
    """Scripted ProviderAdapterPort fake — replays outcomes in order.

    Script entries: ProviderError (attempt fails), dict (attempt succeeds
    with that output). Exhausted script -> succeed with ``{"ok": True}``.
    """

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(
            credential_ref=credential_ref, status=CredentialStatus.ACTIVE
        )

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"ok": True}
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=step,
                latency_ms=7,
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=5,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return _provider_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)


# --- world: registries + router + execution service + composed app -------------------


def _manifest(provider_key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": provider_key,
            "name": provider_key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )


class World:
    """One hermetic API world: registries, one provider+model, fake adapter."""

    def __init__(self, *, script: list[object] | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4())
        self.store = InMemoryExecutionStore()
        self.usage: InMemoryUsageAccounting | None = None

        self.provider = Provider(
            id=uuid4(),
            provider_key="prov_a",
            display_name="prov_a",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(self.provider, _manifest("prov_a"))
        self.model = _model("model-alpha")
        self.models.register(self.model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=self.provider.id,
                model_id=self.model.id,
                provider_model_name="vendor/model-alpha",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        self.adapter = FakeAdapter(script)

    def grant_budget(self, limit: float) -> InMemoryUsageAccounting:
        """Bind usage accounting with a configured tenant budget (21 §5 seam)."""
        self.usage = InMemoryUsageAccounting()
        self.usage.configure_tenant(
            self.principal.tenant_id, plan="pro", task_units_limit=limit
        )
        return self.usage

    def app(self) -> FastAPI:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        service = ExecutionService(
            adapters={self.provider.id: self.adapter},
            credential_refs={self.provider.id: f"secret-ref://{self.provider.id}"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            usage=self.usage,
            sleeper=_no_sleep,
        )
        return create_app(
            router=router,
            execution_service=service,
            store=self.store,
            principal=self.principal,
        )


async def _no_sleep(seconds: float) -> None:
    return None


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _post(
    app: FastAPI, body: dict[str, Any], headers: dict[str, str] | None = None
) -> httpx.Response:
    async with _client(app) as client:
        return await client.post("/v1/execute", json=body, headers=headers or {})


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


def _assert_unified_error(body: dict[str, Any], code: str) -> None:
    """Every non-success body is the unified envelope (10 §9)."""
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["retryable"], bool)


# --- POST /v1/execute: sync success (10 §2 / §3) --------------------------------------


def test_execute_success_returns_sync_response() -> None:
    world = World(script=[{"content": "hello from fake"}])
    response = run(_post(world.app(), {"ask": "say hello"}))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["result"]["type"] == "message"
    assert body["result"]["content"] == "hello from fake"
    UUID(body["execution_id"])  # a real execution id
    # No usage accounting bound in this world => usage absent, never faked
    # (10 §3; evaluation stays a later slice).
    assert "usage" not in body
    assert "evaluation" not in body


def test_execute_serializes_non_content_output_verbatim() -> None:
    world = World(script=[{"data": [1, 2]}])
    response = run(_post(world.app(), {"ask": "structured"}))
    assert response.status_code == 200
    assert response.json()["result"]["content"] == '{"data": [1, 2]}'


def test_execute_output_format_hint_is_echoed() -> None:
    world = World(script=[{"content": "# md"}])
    body = {"ask": "hi", "output": {"format": "markdown"}}
    response = run(_post(world.app(), body))
    assert response.json()["result"]["format"] == "markdown"


def test_execute_passes_opaque_credential_and_bound_model_name() -> None:
    world = World()
    run(_post(world.app(), {"ask": "hi"}))
    request = world.adapter.requests[0]
    assert request.credential_ref == f"secret-ref://{world.provider.id}"
    assert request.provider_model_name == "vendor/model-alpha"
    assert request.tenant_id == world.principal.tenant_id
    assert request.payload["ask"] == "hi"


# --- POST /v1/execute: contract validation (10 §2 / §9) -------------------------------


def test_missing_ask_is_validation_error() -> None:
    world = World()
    response = run(_post(world.app(), {}))
    assert response.status_code == 422
    _assert_unified_error(response.json(), "validation_error")


def test_unknown_fields_are_rejected() -> None:
    world = World()
    response = run(_post(world.app(), {"ask": "hi", "surprise": True}))
    assert response.status_code == 422
    _assert_unified_error(response.json(), "validation_error")


def test_non_uuid_conversation_id_is_validation_error() -> None:
    world = World()
    response = run(_post(world.app(), {"ask": "hi", "conversation_id": "not-a-uuid"}))
    assert response.status_code == 422
    _assert_unified_error(response.json(), "validation_error")
    assert world.adapter.requests == []  # rejected before any provider work


def test_valid_conversation_id_reaches_execution() -> None:
    world = World()
    conversation_id = str(uuid4())
    response = run(_post(world.app(), {"ask": "hi", "conversation_id": conversation_id}))
    assert response.status_code == 200
    report = world.store.get(UUID(response.json()["execution_id"]))
    assert str(report.execution.conversation_id) == conversation_id


# --- POST /v1/execute: loud slice rejections ------------------------------------------


def test_async_execution_is_rejected_loudly() -> None:
    world = World()
    body = {"ask": "hi", "execution_policy": {"async": True}}
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    payload = response.json()
    _assert_unified_error(payload, "validation_error")
    assert payload["error"]["details"]["field"] == "execution_policy.async"
    assert world.adapter.requests == []


def test_streaming_is_rejected_loudly() -> None:
    world = World()
    body = {"ask": "hi", "execution_policy": {"stream": True}}
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    payload = response.json()
    _assert_unified_error(payload, "validation_error")
    assert payload["error"]["details"]["field"] == "execution_policy.stream"


def test_unsupported_policy_type_is_validation_error() -> None:
    world = World()
    body = {
        "ask": "hi",
        "model_policy": {
            "type": "explicit_models",
            "models": [{"model_id": "model-alpha"}],
        },
    }
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    payload = response.json()
    _assert_unified_error(payload, "validation_error")
    assert payload["error"]["details"]["field"] == "model_policy"


# --- POST /v1/execute: routing failures (11 §14 / 10 §9) ------------------------------


def test_no_eligible_candidates_is_model_unavailable() -> None:
    world = World()
    body = {"ask": "hi", "model_policy": {"type": "explicit_model", "model_id": "ghost"}}
    response = run(_post(world.app(), body))
    assert response.status_code == 503
    payload = response.json()
    _assert_unified_error(payload, "model_unavailable")
    assert payload["error"]["details"]["excluded"]  # explainable exclusions


# --- POST /v1/execute: provider failure mapping (30 §14 / 10 §9) ----------------------


def test_provider_failure_maps_category_and_hides_internals() -> None:
    world = World(script=[_provider_error(ProviderErrorCategory.RATE_LIMITED)])
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 429
    payload = response.json()
    _assert_unified_error(payload, "rate_limited")
    details = payload["error"]["details"]
    assert details["provider_error_category"] == "rate_limited"
    UUID(details["execution_id"])  # diagnosable via GET
    # 20 §4 / 30 §14: raw provider internals never cross to clients.
    assert "RAW-INTERNAL-CODE" not in response.text


def test_generic_provider_failure_is_execution_failed() -> None:
    world = World(script=[_provider_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)])
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 502
    _assert_unified_error(response.json(), "execution_failed")


# --- Idempotency (10 §10) --------------------------------------------------------------


def test_idempotency_key_replays_same_execution() -> None:
    world = World(script=[{"content": "first"}, {"content": "second"}])
    app = world.app()
    headers = {"Idempotency-Key": "key-1"}
    first = run(_post(app, {"ask": "hi"}, headers))
    second = run(_post(app, {"ask": "hi"}, headers))
    assert first.status_code == second.status_code == 200
    assert first.json()["execution_id"] == second.json()["execution_id"]
    assert second.json()["result"]["content"] == "first"  # replay, not re-run
    assert len(world.adapter.requests) == 1
    assert len(world.store) == 1


def test_different_idempotency_keys_create_distinct_executions() -> None:
    world = World()
    app = world.app()
    first = run(_post(app, {"ask": "hi"}, {"Idempotency-Key": "key-a"}))
    second = run(_post(app, {"ask": "hi"}, {"Idempotency-Key": "key-b"}))
    assert first.json()["execution_id"] != second.json()["execution_id"]
    assert len(world.adapter.requests) == 2


def test_no_idempotency_key_never_replays() -> None:
    world = World()
    app = world.app()
    first = run(_post(app, {"ask": "hi"}))
    second = run(_post(app, {"ask": "hi"}))
    assert first.json()["execution_id"] != second.json()["execution_id"]


# --- GET /v1/executions/{id} (10 §5) ----------------------------------------------------


def test_get_succeeded_execution_status() -> None:
    world = World(script=[{"content": "done"}])
    app = world.app()
    execution_id = run(_post(app, {"ask": "hi"})).json()["execution_id"]
    response = run(_get(app, f"/v1/executions/{execution_id}"))
    assert response.status_code == 200
    body = response.json()
    assert body["execution_id"] == execution_id
    assert body["status"] == "succeeded"
    assert body["progress"]["percent"] == 100
    assert body["result"]["content"] == "done"
    assert "error" not in body


def test_get_failed_execution_status_carries_unified_error() -> None:
    world = World(script=[_provider_error(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    app = world.app()
    execution_id = run(_post(app, {"ask": "hi"})).json()["error"]["details"][
        "execution_id"
    ]
    response = run(_get(app, f"/v1/executions/{execution_id}"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "provider_unavailable"
    assert "result" not in body


def test_get_unknown_execution_is_404_unified_error() -> None:
    world = World()
    response = run(_get(world.app(), f"/v1/executions/{uuid4()}"))
    assert response.status_code == 404
    _assert_unified_error(response.json(), "validation_error")


def test_get_malformed_execution_id_is_422() -> None:
    world = World()
    response = run(_get(world.app(), "/v1/executions/not-a-uuid"))
    assert response.status_code == 422
    _assert_unified_error(response.json(), "validation_error")


# --- usage block + entitlement mapping (T-IMPL-024; 10 §3 / §9) -----------------------


def test_success_surfaces_settled_usage_block() -> None:
    world = World(script=[{"content": "ok"}])
    world.grant_budget(10.0)
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 200
    body = response.json()
    assert body["usage"] == {
        "units_reserved": 1,
        "units_settled": 1,
        "details": {"status": "settled"},
    }


def test_budget_exceeded_maps_to_entitlement_exceeded_403() -> None:
    world = World()
    world.grant_budget(0.0)  # configured but empty budget
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 403
    body = response.json()
    _assert_unified_error(body, "entitlement_exceeded")
    assert body["error"]["details"] == {"requested": 1.0, "remaining": 0.0}
    assert len(world.adapter.requests) == 0  # denied BEFORE provider work


def test_unconfigured_tenant_denied_entitlement_exceeded() -> None:
    world = World()
    world.usage = InMemoryUsageAccounting()  # bound, but tenant NOT configured
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 403
    _assert_unified_error(response.json(), "entitlement_exceeded")
    assert len(world.adapter.requests) == 0


def test_budget_depletes_across_requests_then_denies() -> None:
    world = World(script=[{"content": "a"}, {"content": "b"}])
    world.grant_budget(2.0)
    app = world.app()
    assert run(_post(app, {"ask": "one"})).status_code == 200
    assert run(_post(app, {"ask": "two"})).status_code == 200
    denied = run(_post(app, {"ask": "three"}))
    assert denied.status_code == 403
    _assert_unified_error(denied.json(), "entitlement_exceeded")
    assert len(world.adapter.requests) == 2  # third never reached the provider


def test_failed_execution_ledger_recorded_without_usage_in_error_body() -> None:
    """Failure keeps the unified envelope (10 §9) — the ledger is still
    resolved (failed, 0 settled) and the budget hold released."""
    world = World(
        script=[_provider_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)]
    )
    accounting = world.grant_budget(5.0)
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code >= 400
    body = response.json()
    assert set(body.keys()) == {"error"}  # unified envelope, no usage key
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 5.0  # hold released, nothing settled
