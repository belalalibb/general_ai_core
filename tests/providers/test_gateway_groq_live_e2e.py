"""LIVE full-stack E2E through the GATEWAY-backed Groq provider (G3).

The proof ADR-0008 G3 demands — the full diagrammed chain, no fakes in the
path except transport plumbing (in-process ASGI instead of a TCP socket):

    Platform HTTP API  POST /v1/execute {"ask": ...}
      -> decision-A canonicalization (ask -> canonical messages)
      -> RemoteGatewayAdapter (wire envelope, secret+route-token headers)
      -> REAL gateway app (build_app + groq registered, route_map)
      -> providers/groq facade -> REAL HTTPS call to api.groq.com
      -> canonical response -> platform result + EXISTING settlement path

Decision D: BOTH entry points are asserted in this single test — the
platform HTTP API entry (platform payload convention) AND the
Router/ExecutionService entry (canonical messages payload).

Env-gated (41 §49 never-fake rule): SKIPPED unless ``GW_GROQ_API_KEY`` is
set — the same variable the gateway's Groq Layer 1 resolves internally
(platform credential mode: the key never crosses the platform boundary).

Reproduce:  GW_GROQ_API_KEY=<key> python3 -m pytest \
                tests/providers/test_gateway_groq_live_e2e.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Coroutine
from pathlib import Path
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
from providers.real.gateway import CREDENTIAL_MODE_PLATFORM, build_gateway_manifest

GROQ_KEY_ENV = "GW_GROQ_API_KEY"

requires_live_key = pytest.mark.skipif(
    not os.environ.get(GROQ_KEY_ENV),
    reason=f"{GROQ_KEY_ENV} not set — live e2e runs manually only (41 §49)",
)

LIVE_MODEL = "allam-2-7b"
GATEWAY_SECRET = "gwsecret_live_e2e_ephemeral_test_only_value"
ROUTE_TOKEN = "routetok_live_e2e_ephemeral_test_only"
INTERNAL_SLUG = "groq"  # gateway-private; asserted to NEVER cross


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _real_gateway_app() -> Any:
    """Build the REAL gateway app with the REAL groq provider registered.

    Test-only path wiring: both roots ship a top-level ``providers``
    package. The platform's is already imported in this process, so the
    gateway's ``providers.groq`` is made resolvable by extending the
    imported package's ``__path__`` — pure test plumbing; nothing in either
    codebase changes.
    """
    gateway_root = Path(__file__).resolve().parents[2] / "gateway-service"
    if str(gateway_root) not in sys.path:
        sys.path.insert(0, str(gateway_root))
    import providers as _platform_providers

    gateway_providers_dir = str(gateway_root / "providers")
    if gateway_providers_dir not in _platform_providers.__path__:
        _platform_providers.__path__.append(gateway_providers_dir)
    from app import build_app, register_live_providers  # gateway-service/app.py
    from gateway.config import GatewayConfig
    from gateway.provider_registry import ProviderRegistry as GwProviderRegistry

    registry = GwProviderRegistry()
    register_live_providers(registry)
    registry.eager_verify_all()
    config = GatewayConfig(
        secrets_by_version={1: GATEWAY_SECRET},
        current_secret_version=1,
        route_map={ROUTE_TOKEN: INTERNAL_SLUG},
    )
    return build_app(config, registry)


def _live_world() -> dict[str, Any]:
    """Compose the platform against the REAL in-process gateway app.

    ZERO provider-specific platform code: manifest + adapter builder are
    generic; the ONLY Groq-specific artifact lives inside the gateway.
    """
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, user_id=uuid4())

    gateway_app = _real_gateway_app()
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
        transport=httpx.ASGITransport(app=gateway_app),
    )

    providers = ProviderRegistry()
    provider = Provider(
        id=uuid4(),
        provider_key="groq-remote",
        display_name="Groq (Remote)",
        status=ProviderStatus.ACTIVE,  # this test IS the verification gate
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
            provider_model_name=LIVE_MODEL,
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
        "usage": usage,
        "service": service,
        "router": router,
        "app": create_app(
            router=router,
            execution_service=service,
            store=InMemoryExecutionStore(),
            principal=principal,
        ),
    }


@requires_live_key
class TestLiveGatewayEndToEnd:
    def test_both_entry_points_through_real_gateway_and_real_groq(self) -> None:
        world = _live_world()
        principal: Principal = world["principal"]
        usage: InMemoryUsageAccounting = world["usage"]
        live_key = os.environ[GROQ_KEY_ENV]

        # ---- Entry point 1 (decision D): platform HTTP API, {"ask": ...} ----
        async def api_call() -> httpx.Response:
            transport = httpx.ASGITransport(app=world["app"])
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/execute",
                    json={"ask": "Reply with exactly the word: OK"},
                    timeout=60.0,
                )

        response = run(api_call())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "succeeded", body
        assert isinstance(body["result"]["content"], str)
        assert body["result"]["content"].strip()
        # no-leak: key / slug / route token / upstream URL never surface
        assert live_key not in response.text
        assert ROUTE_TOKEN not in response.text
        assert "api.groq.com" not in response.text
        summary = usage.summary(principal.tenant_id)
        assert summary.task_units.used == 1.0

        # ---- Entry point 2 (decision D): Router + ExecutionService direct,
        # caller-supplied CANONICAL messages payload (idempotent pass-through)
        decision = world["router"].route(
            RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
        )
        service: ExecutionService = world["service"]
        report = run(
            service.execute_single(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={
                    "messages": [
                        {"role": "user", "content": "Reply with exactly the word: YES"}
                    ],
                    "max_tokens": 16,
                },
                request_hash="live-e2e-router-entry",
            )
        )
        assert report.execution.status.value == "succeeded"
        ledger = usage.get(report.execution.id)
        assert ledger.status is UsageLedgerStatus.SETTLED
        assert ledger.units_settled == 1.0
        assert usage.summary(principal.tenant_id).task_units.used == 2.0
        dumped = report.execution.model_dump_json()
        assert live_key not in dumped
        assert ROUTE_TOKEN not in dumped
        assert INTERNAL_SLUG + '"' not in dumped  # slug never crosses
