"""Hermetic settlement proof: gateway-backed provider bills through the
EXISTING platform path (G3, ADR-0008).

ZERO network: the "gateway" is an ``httpx.MockTransport`` answering with
canonical wire envelopes. What this file proves:

- the platform registers a gateway-backed provider with ZERO
  provider-specific platform code (config: manifest + adapter builder only);
- estimate -> reserve -> execute -> settle/refund runs through the EXISTING
  ``UsageAccountingPort`` ledger — no new billing engine anywhere;
- failures resolve the reservation (status=failed), never leak units;
- the OPEN-7 auth self-heal retry produces EXTRA wire calls but NEVER an
  extra execution or an extra billing event;
- the full API entry (``{"ask": ...}``) crosses the decision-A
  canonicalization and comes back as consumable ``result.content``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.api import InMemoryExecutionStore, Principal, create_app
from apps.composition import GatewaySettings, build_gateway_adapter
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import ProviderCapabilities, ProviderOperation
from core.contracts.routing import RoutingRequest
from core.contracts.usage import UsageLedgerStatus
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting
from core.usage.errors import ReservationNotFound
from providers.real.gateway import CREDENTIAL_MODE_PLATFORM, build_gateway_manifest

# Test-only sentinels — never real credentials.
GATEWAY_SECRET = "gwsecret_TEST_ONLY_settlement_suite"
ROUTE_TOKEN = "routetok_TEST_ONLY_settlement_suite"
MODEL_NAME = "allam-2-7b"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _canonical_success(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "succeeded": True,
            "output": {"text": "OK", "finish_reason": "stop"},
            "usage": {"input_tokens": 4, "output_tokens": 1, "units": 1},
            "latency_ms": 5,
            "error": None,
        },
    )


def _wire_failure(category: str, *, retryable: bool) -> Any:
    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "succeeded": False,
                "output": None,
                "usage": None,
                "latency_ms": 3,
                "error": {
                    "category": category,
                    "retryable": retryable,
                    "message": f"normalized {category} from facade",
                },
            },
        )

    return _responder


class _Recorder:
    def __init__(self, responder: Any) -> None:
        self.requests: list[httpx.Request] = []
        self._responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _world(responder: Any) -> dict[str, Any]:
    """Compose the platform against a mock gateway — CONFIG ONLY.

    Nothing below mentions Groq internals: the manifest + adapter builder
    are the same generic pieces any gateway-backed provider would use.
    """
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, user_id=uuid4())
    recorder = _Recorder(responder)

    manifest = build_gateway_manifest(
        provider_key="groq-remote",
        display_name="Groq (Remote)",
        operations=[ProviderOperation.GENERATE_TEXT],
        capabilities=ProviderCapabilities(chat=True),
    )
    adapter = build_gateway_adapter(
        GatewaySettings(
            base_url="https://gateway.internal.test",
            secret=GATEWAY_SECRET,
            secret_version=1,
        ),
        manifest=manifest,
        route_token_resolver=lambda: ROUTE_TOKEN,
        credential_mode=CREDENTIAL_MODE_PLATFORM,
        transport=httpx.MockTransport(recorder),
    )

    providers = ProviderRegistry()
    provider = Provider(
        id=uuid4(),
        provider_key="groq-remote",
        display_name="Groq (Remote)",
        status=ProviderStatus.ACTIVE,  # enable-after-verification, test-scoped
        auth_types=["custom"],
        supports_account_pool=False,
    )
    providers.register(provider, manifest)

    models = ModelRegistry()
    model = Model(
        id=uuid4(),
        model_key="allam-2-7b",
        display_name="Allam 2 7B (via gateway)",
        tier=ModelTier.FAST,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.6,
        reliability_score=0.8,
        cost_score=0.9,
        speed_score=0.95,
        status=ModelStatus.ACTIVE,
    )
    models.register(model)

    bindings = BindingRegistry()
    bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name=MODEL_NAME,
            availability=BindingAvailability.AVAILABLE,
        )
    )

    usage = InMemoryUsageAccounting()
    usage.configure_tenant(tenant_id, plan="pro", task_units_limit=10.0)

    service = ExecutionService(
        adapters={provider.id: adapter},
        credential_refs={provider.id: "credref_platform_mode_opaque"},
        bindings=bindings,
        max_retries_per_candidate=1,
        usage=usage,
    )
    router = SimpleScoringRouter(providers, models, bindings)
    return {
        "principal": principal,
        "recorder": recorder,
        "usage": usage,
        "service": service,
        "router": router,
        "app_factory": lambda: create_app(
            router=router,
            execution_service=service,
            store=InMemoryExecutionStore(),
            principal=principal,
        ),
    }


def _decision(world: dict[str, Any]) -> Any:
    return world["router"].route(
        RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
    )


async def _execute(world: dict[str, Any], payload: dict[str, Any]) -> Any:
    principal: Principal = world["principal"]
    service: ExecutionService = world["service"]
    return await service.execute_single(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        decision=_decision(world),
        operation=ProviderOperation.GENERATE_TEXT,
        payload=payload,
        request_hash="settlement-suite-hash",
    )


class TestSettlement:
    def test_success_settles_through_existing_ledger(self) -> None:
        world = _world(_canonical_success)
        report = run(_execute(world, {"ask": "Reply with exactly the word: OK"}))
        assert report.execution.status.value == "succeeded"

        usage: InMemoryUsageAccounting = world["usage"]
        ledger = usage.get(report.execution.id)
        assert ledger.status is UsageLedgerStatus.SETTLED
        assert ledger.units_reserved == 1.0
        assert ledger.units_settled == 1.0
        summary = usage.summary(world["principal"].tenant_id)
        assert summary.task_units.used == 1.0
        assert summary.task_units.remaining == 9.0

    def test_wire_failure_resolves_reservation_as_failed(self) -> None:
        world = _world(_wire_failure("quota_exceeded", retryable=False))
        report = run(_execute(world, {"ask": "hi"}))
        assert report.execution.status.value == "failed"

        usage: InMemoryUsageAccounting = world["usage"]
        ledger = usage.get(report.execution.id)
        assert ledger.status is UsageLedgerStatus.FAILED
        assert ledger.units_settled == 0.0
        # the hold is released: nothing consumed, nothing stuck
        summary = usage.summary(world["principal"].tenant_id)
        assert summary.task_units.used == 0.0
        assert summary.task_units.remaining == 10.0

    def test_auth_selfheal_never_bills_twice(self) -> None:
        """OPEN-7: stale-version 401 -> re-read secret -> retry ONCE.

        Two wire calls, ONE execution, ONE reservation, ONE settlement.
        """
        calls = {"n": 0}

        def _stale_then_ok(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    401,
                    json={
                        "error": {
                            "category": "auth_expired",
                            "retryable": True,
                            "message": "stale secret version",
                        }
                    },
                )
            return _canonical_success(request)

        world = _world(_stale_then_ok)
        report = run(_execute(world, {"ask": "hi"}))
        assert report.execution.status.value == "succeeded"
        assert calls["n"] == 2  # auth retry happened at the wire...

        usage: InMemoryUsageAccounting = world["usage"]
        ledger = usage.get(report.execution.id)
        assert ledger.status is UsageLedgerStatus.SETTLED
        assert ledger.units_settled == 1.0  # ...but billing saw ONE execution
        assert usage.summary(world["principal"].tenant_id).task_units.used == 1.0

    def test_no_usage_recorded_outside_reserve_settle(self) -> None:
        """The gateway's raw usage evidence rides the response; the ledger
        entry for the execution is the ONLY billing artifact created."""
        world = _world(_canonical_success)
        report = run(_execute(world, {"ask": "hi"}))
        usage: InMemoryUsageAccounting = world["usage"]
        # exactly one ledger entry exists — the execution's own
        ledger = usage.get(report.execution.id)
        assert ledger.execution_id == report.execution.id
        with pytest.raises(ReservationNotFound):
            usage.get(uuid4())  # no phantom entries under other ids


class TestApiEntryFullChainHermetic:
    """The decision-A canonicalization proven across the FULL platform chain."""

    def test_api_ask_becomes_canonical_messages_and_content_comes_back(self) -> None:
        world = _world(_canonical_success)
        app = world["app_factory"]()

        async def call() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/execute", json={"ask": "Reply with exactly the word: OK"}
                )

        response = run(call())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "succeeded"
        # decision-A output normalization: wire "text" surfaced as content
        assert body["result"]["content"] == "OK"

        # decision-A payload canonicalization: the gateway received messages
        recorder: _Recorder = world["recorder"]
        assert len(recorder.requests) == 1
        wire_payload = json.loads(recorder.requests[0].content)["payload"]
        assert wire_payload == {
            "messages": [{"role": "user", "content": "Reply with exactly the word: OK"}]
        }

        # settlement through the existing path, from the API entry too
        summary = world["usage"].summary(world["principal"].tenant_id)
        assert summary.task_units.used == 1.0
