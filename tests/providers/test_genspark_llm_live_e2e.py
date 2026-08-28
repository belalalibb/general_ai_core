"""LIVE full-stack end-to-end through the REAL Genspark LLM proxy (T-IMPL-037).

Same 41 §49 proof shape as the groq reference e2e: the path exercised is
the PRODUCTION composition — no fakes anywhere in the chain:

    POST /v1/execute (httpx-ASGI)
      -> SimpleScoringRouter (real registries, genspark_llm registered ACTIVE)
      -> ExecutionService (usage reservation + settlement)
      -> GensparkLLMAdapter (real HTTPS call to www.genspark.ai llm_proxy)
      -> normalized response -> API result + usage block

Env-gated like tests/providers/test_genspark_llm_live.py: SKIPPED without
``GSK_API_KEY``; the hermetic gates never touch the network. The key rides
the SecretManagerPort -> opaque ref path (20 §5) — never in any artifact.

Enable-after-verification posture (31 §19 step 14): the composition below
registers genspark_llm with domain status ACTIVE deliberately — this test
IS the verification gate, and the registration is scoped to this test world.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest

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
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.secrets.memory import InMemorySecretManager
from core.usage import InMemoryUsageAccounting
from providers.real.genspark_llm import MANIFEST, GensparkLLMAdapter

requires_live_key = pytest.mark.skipif(
    not os.environ.get("GSK_API_KEY"),
    reason="GSK_API_KEY not set — live e2e runs manually only (41 §49)",
)

LIVE_MODEL = "gpt-5-nano"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _live_world() -> tuple[Any, InMemoryUsageAccounting, Principal]:
    """Compose the production stack with the REAL Genspark LLM adapter."""
    tenant_id = uuid4()
    principal = Principal(tenant_id=tenant_id, user_id=uuid4())

    secrets = InMemorySecretManager()
    ref = secrets.store(tenant_id, os.environ["GSK_API_KEY"])
    adapter = GensparkLLMAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant_id, r),
        health_credential_ref=ref,
    )

    providers = ProviderRegistry()
    provider = Provider(
        id=uuid4(),
        provider_key="genspark_llm",
        display_name="Genspark LLM Proxy",
        status=ProviderStatus.ACTIVE,  # enabled AFTER verification (31 §19 step 14)
        auth_types=["api_key"],
        supports_account_pool=False,
    )
    # The registry checks manifest flags: real+functional passes; the shipped
    # "disabled" manifest status is a lifecycle word, not a template marker.
    providers.register(provider, MANIFEST)

    models = ModelRegistry()
    model = Model(
        id=uuid4(),
        model_key="gpt-5-nano",
        display_name="GPT-5 Nano (Genspark LLM Proxy)",
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
        credential_refs={provider.id: ref},
        bindings=bindings,
        max_retries_per_candidate=1,
        usage=usage,
    )
    app = create_app(
        router=SimpleScoringRouter(providers, models, bindings),
        execution_service=service,
        store=InMemoryExecutionStore(),
        principal=principal,
    )
    return app, usage, principal


@requires_live_key
class TestLiveEndToEnd:
    def test_execute_end_to_end_through_real_genspark_llm(self) -> None:
        app, usage, principal = _live_world()

        async def call() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/execute",
                    json={"ask": "Reply with exactly the word: OK"},
                    timeout=120.0,
                )

        response = run(call())
        assert response.status_code == 200, response.text
        body = response.json()
        # 10 §3 result shape with REAL model output
        assert body["status"] == "succeeded"
        assert isinstance(body["result"]["content"], str)
        assert body["result"]["content"].strip()
        # usage settled: reservation resolved to exactly one stage unit
        summary = usage.summary(principal.tenant_id)
        assert summary.task_units.used == 1.0
        assert summary.task_units.remaining == 9.0
        # the live key never appears in the API response
        assert os.environ["GSK_API_KEY"] not in response.text
