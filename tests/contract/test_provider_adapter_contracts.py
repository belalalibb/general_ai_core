"""Contract tests: §8 adapter payload shapes (30 §8.1; T-IMPL-018).

Hermetic. Validates the operation contracts that cross the ProviderAdapter
seam: HealthScope, CredentialHealth, DiscoveredModel,
ProviderGenerateRequest/Response — closed sets, deny-by-default fields,
and the 20 §5 opaque-credential rule (shape carries only a reference).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderError,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderOperation,
)

# --- HealthScope (30 §8.1 / §11 separation) ----------------------------------------


def test_health_scope_is_the_two_documented_scopes() -> None:
    assert {s.value for s in HealthScope} == {"provider", "account"}


# --- CredentialHealth (30 §8.1; 20 §5) ---------------------------------------------


def test_credential_health_roundtrip_carries_only_opaque_reference() -> None:
    health = CredentialHealth.model_validate(
        {"credential_ref": "cred_ref_abc123", "status": "active"}
    )
    assert health.credential_ref == "cred_ref_abc123"
    assert health.status == "active"
    assert health.checked_at is None
    assert health.detail is None


def test_credential_health_rejects_secret_material_fields() -> None:
    # extra="forbid": a field named e.g. "api_key" can never sneak in (20 §5).
    with pytest.raises(ValidationError):
        CredentialHealth.model_validate(
            {"credential_ref": "cred_ref", "status": "active", "api_key": "sk-live"}
        )


def test_credential_health_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        CredentialHealth.model_validate({"credential_ref": "cred_ref", "status": "sort_of_ok"})


# --- DiscoveredModel (30 §8.1; NOT a binding) --------------------------------------


def test_discovered_model_minimal_and_defaults() -> None:
    model = DiscoveredModel.model_validate({"provider_model_name": "x-large-v2"})
    assert model.provider_model_name == "x-large-v2"
    assert model.endpoint_ref is None
    assert model.modalities == []
    assert model.capabilities == {}
    assert model.limits_metadata == {}


def test_discovered_model_rejects_registry_binding_fields() -> None:
    # Binding creation is a Core decision (03 §4): a provider cannot declare
    # binding/registry identifiers through discovery.
    with pytest.raises(ValidationError):
        DiscoveredModel.model_validate({"provider_model_name": "x", "binding_id": str(uuid4())})


# --- ProviderGenerateRequest (30 §8.1) ---------------------------------------------


def _request_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "operation": "generate_text",
        "provider_model_name": "x-large-v2",
        "credential_ref": "cred_ref_abc123",
    }
    payload.update(overrides)
    return payload


def test_generate_request_roundtrip_with_defaults() -> None:
    req = ProviderGenerateRequest.model_validate(_request_payload())
    assert req.operation is ProviderOperation.GENERATE_TEXT
    assert req.account_id is None
    assert req.payload == {}
    assert req.timeout_ms is None


def test_generate_request_operation_must_be_a_documented_operation() -> None:
    with pytest.raises(ValidationError):
        ProviderGenerateRequest.model_validate(_request_payload(operation="do_anything"))


def test_generate_request_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProviderGenerateRequest.model_validate(_request_payload(timeout_ms=0))


def test_generate_request_rejects_inline_secret_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderGenerateRequest.model_validate(_request_payload(api_key="sk-live"))


# --- ProviderGenerateResponse (30 §8.1 / §14) --------------------------------------


def test_generate_response_success_shape() -> None:
    resp = ProviderGenerateResponse.model_validate(
        {
            "request_id": str(uuid4()),
            "succeeded": True,
            "output": {"text": "hello"},
            "usage": {"input_tokens": 3, "output_tokens": 1},
            "latency_ms": 120,
        }
    )
    assert resp.succeeded is True
    assert resp.error is None
    assert resp.output == {"text": "hello"}


def test_generate_response_failure_carries_normalized_error_only() -> None:
    resp = ProviderGenerateResponse.model_validate(
        {
            "request_id": str(uuid4()),
            "succeeded": False,
            "error": {
                "category": "unsupported_capability",
                "retryable": False,
                "safe_message": "Provider does not support this operation.",
            },
        }
    )
    assert resp.succeeded is False
    assert isinstance(resp.error, ProviderError)
    assert resp.error.category == "unsupported_capability"
    assert resp.error.retryable is False


def test_generate_response_rejects_raw_provider_error_shape() -> None:
    # A raw provider error blob (unknown fields) must not validate (30 §14).
    with pytest.raises(ValidationError):
        ProviderGenerateResponse.model_validate(
            {
                "request_id": str(uuid4()),
                "succeeded": False,
                "error": {"http_status": 500, "body": "Internal Server Error"},
            }
        )


def test_generate_response_latency_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        ProviderGenerateResponse.model_validate(
            {"request_id": str(uuid4()), "succeeded": True, "latency_ms": -1}
        )
