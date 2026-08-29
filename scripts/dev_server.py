"""Dev-only smoke server — composes the API app with a scripted fake provider.

NOT production wiring (41 §49: real-provider execution stays
PENDING_REAL_PROVIDERS). This exists purely so a human can poke the HTTP
surface (POST /v1/execute, GET /v1/executions/{id}, /v1/skills, /v1/models,
/v1/usage) without any network provider, DB, or secret backend.

Run:  python scripts/dev_server.py  (serves on 0.0.0.0:8000)
"""

from __future__ import annotations

from uuid import UUID, uuid4

import uvicorn

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


class EchoAdapter:
    """Fake ProviderAdapterPort — always succeeds, echoing the ask back."""

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(
            credential_ref=credential_ref, status=CredentialStatus.ACTIVE
        )

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        ask = request.payload.get("ask", "")
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output={"content": f"echo: {ask}"},
            usage={"units": 1},
            latency_ms=3,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="fake non_retryable_error",
        )


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


def build_dev_app():  # noqa: ANN201 - FastAPI return kept implicit for dev script
    providers = ProviderRegistry()
    models = ModelRegistry()
    bindings = BindingRegistry()

    provider = Provider(
        id=uuid4(),
        provider_key="dev_echo",
        display_name="Dev Echo Provider",
        status=ProviderStatus.ACTIVE,
        auth_types=["api_key"],
        supports_account_pool=False,
    )
    providers.register(provider, _manifest("dev_echo"))

    model = Model(
        id=uuid4(),
        model_key="echo-1",
        display_name="Echo 1",
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )
    models.register(model)
    bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name="dev/echo-1",
            availability=BindingAvailability.AVAILABLE,
        )
    )

    principal = Principal(tenant_id=uuid4(), user_id=uuid4())
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(principal.tenant_id, plan="pro", task_units_limit=10_000)

    service = ExecutionService(
        adapters={provider.id: EchoAdapter()},
        credential_refs={provider.id: f"secret-ref://{provider.id}"},
        bindings=bindings,
        max_retries_per_candidate=0,
        usage=usage,
    )
    router = SimpleScoringRouter(providers, models, bindings)

    return create_app(
        router=router,
        execution_service=service,
        store=InMemoryExecutionStore(),
        principal=principal,
        models=models,
        bindings=bindings,
        usage=usage,
    )


app = build_dev_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
