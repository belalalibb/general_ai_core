"""ProviderAdapter behavioral port semantics (T-IMPL-018; 30 §8, §11, §14).

Hermetic — a fully in-memory fake adapter implements ProviderAdapterPort and
proves the port's behavioral obligations without any network:

- generate() rejects undeclared operations with unsupported_capability
  (30 §8.1 note) instead of executing or raising raw errors.
- health_check() keeps provider health and account health separate (30 §11).
- validate_credential() sees only opaque references (20 §5).
- normalize_error() maps raw failures into the 12-category shape (30 §14).

Async methods are driven with asyncio.run (no pytest-asyncio; ADR-0001).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
    ProviderOperation,
)
from core.providers import ProviderAdapterPort


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _manifest() -> ProviderManifest:
    # Minimal valid manifest: text-only fake provider declaring ONE operation.
    return ProviderManifest.model_validate(
        {
            "id": "fake_text",
            "name": "Fake Text Provider",
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": ["fake-text-1"]},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


class FakeTextAdapter:
    """In-memory ProviderAdapterPort implementation (text-generation only)."""

    def __init__(self) -> None:
        self._manifest = _manifest()
        self._known_credential_refs = {"cred_ref_ok"}

    def get_manifest(self) -> ProviderManifest:
        return self._manifest

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        status = "active" if credential_ref in self._known_credential_refs else "invalid"
        return CredentialHealth.model_validate({"credential_ref": credential_ref, "status": status})

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return [
            DiscoveredModel.model_validate(
                {"provider_model_name": "fake-text-1", "modalities": ["text"]}
            )
        ]

    async def get_capabilities(self) -> ProviderCapabilities:
        return self._manifest.capabilities

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        if request.operation not in self._manifest.operations:
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=ProviderError(
                    category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                    retryable=False,
                    safe_message="Provider does not declare this operation.",
                ),
            )
        prompt = str(request.payload.get("prompt", ""))
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output={"text": f"echo:{prompt}"},
            usage={"input_tokens": len(prompt.split()), "output_tokens": 1},
            latency_ms=1,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        if scope is HealthScope.ACCOUNT:
            # Account-scope report: per-account states, provider still healthy —
            # one bad account never marks the provider down (30 §11).
            return ProviderHealth.model_validate(
                {
                    "provider_id": "fake_text",
                    "state": "HEALTHY",
                    "accounts": {"acct-1": "READY", "acct-2": "AUTH_EXPIRED"},
                }
            )
        return ProviderHealth.model_validate({"provider_id": "fake_text", "state": "HEALTHY"})

    def normalize_error(self, error: object) -> ProviderError:
        # Raw provider failure objects never cross the boundary (30 §14).
        raw = error if isinstance(error, dict) else {}
        status = raw.get("http_status")
        if status == 429:
            return ProviderError(
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                retry_after_ms=int(raw.get("retry_after_ms", 1000)),
                provider_code=str(status),
                safe_message="Provider rate limit reached.",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code=str(status) if status is not None else None,
            safe_message="Provider request failed.",
        )


def _adapter() -> ProviderAdapterPort:
    # Static-typing proof: FakeTextAdapter satisfies the Protocol.
    adapter: ProviderAdapterPort = FakeTextAdapter()
    return adapter


def _request(**overrides: Any) -> ProviderGenerateRequest:
    base: dict[str, Any] = {
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "operation": ProviderOperation.GENERATE_TEXT,
        "provider_model_name": "fake-text-1",
        "credential_ref": "cred_ref_ok",
        "payload": {"prompt": "hello world"},
    }
    base.update(overrides)
    return ProviderGenerateRequest.model_validate(base)


# --- required interface behaviors (30 §8.1) ----------------------------------------


def test_manifest_is_the_single_source_of_declaration() -> None:
    manifest = _adapter().get_manifest()
    assert manifest.id == "fake_text"
    assert manifest.operations == [ProviderOperation.GENERATE_TEXT]
    # Deny-by-default: undeclared capabilities are False (30 §7).
    assert manifest.capabilities.chat is True
    assert manifest.capabilities.image_generation is False
    assert manifest.capabilities.browser is False


def test_generate_declared_operation_succeeds() -> None:
    resp = run(_adapter().generate(_request()))
    assert resp.succeeded is True
    assert resp.error is None
    assert resp.output == {"text": "echo:hello world"}
    assert resp.usage["input_tokens"] == 2


def test_generate_undeclared_operation_is_unsupported_capability() -> None:
    """30 §8.1 note: undeclared operation → normalized rejection, no raw error."""
    req = _request(operation=ProviderOperation.GENERATE_IMAGE)
    resp = run(_adapter().generate(req))
    assert resp.succeeded is False
    assert resp.error is not None
    assert resp.error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY
    assert resp.error.retryable is False
    assert resp.request_id == req.request_id


def test_validate_credential_uses_opaque_reference_only() -> None:
    adapter = _adapter()
    ok = run(adapter.validate_credential("cred_ref_ok"))
    bad = run(adapter.validate_credential("cred_ref_unknown"))
    assert ok.status == "active"
    assert bad.status == "invalid"
    # The report never contains anything but the reference itself (20 §5).
    assert set(ok.model_dump(exclude_none=True)) <= {
        "credential_ref",
        "status",
        "checked_at",
        "detail",
    }


def test_discover_models_returns_declarations_not_bindings() -> None:
    (model,) = run(_adapter().discover_models())
    assert model.provider_model_name == "fake-text-1"
    assert model.modalities == ["text"]


def test_health_scopes_keep_provider_and_account_health_separate() -> None:
    """30 §11: one AUTH_EXPIRED account does not make the provider unhealthy."""
    adapter = _adapter()
    provider_scope = run(adapter.health_check(HealthScope.PROVIDER))
    account_scope = run(adapter.health_check(HealthScope.ACCOUNT))
    assert provider_scope.state == "HEALTHY"
    assert provider_scope.accounts == {}
    assert account_scope.state == "HEALTHY"
    assert account_scope.accounts["acct-2"] == "AUTH_EXPIRED"


# --- normalize_error (30 §14) ------------------------------------------------------


def test_normalize_error_maps_rate_limit_with_retry_hint() -> None:
    err = _adapter().normalize_error({"http_status": 429, "retry_after_ms": 250})
    assert err.category is ProviderErrorCategory.RATE_LIMITED
    assert err.retryable is True
    assert err.retry_after_ms == 250
    assert err.provider_code == "429"


def test_normalize_error_never_leaks_raw_payload() -> None:
    raw = {"http_status": 500, "body": "stacktrace: secret internals"}
    err = _adapter().normalize_error(raw)
    assert err.category is ProviderErrorCategory.NON_RETRYABLE_ERROR
    dumped = err.model_dump()
    assert "stacktrace" not in str(dumped.values())
    assert err.safe_message == "Provider request failed."
