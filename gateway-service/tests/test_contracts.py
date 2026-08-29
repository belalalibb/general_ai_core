"""Contract shape tests — Layer 3 is closed and exact."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.contracts import (
    EXCLUDED_OPERATIONS,
    EnvelopeCredential,
    ErrorCategory,
    FacadeResult,
    GatewayError,
    GatewayOperation,
    ProviderDefinition,
    RequestEnvelope,
    ResponseEnvelope,
    Usage,
    reject_excluded_operations,
)

# The 12 categories, verbatim from core/contracts/provider.py (platform-led).
PLATFORM_ERROR_CATEGORIES = [
    "auth_expired",
    "invalid_credential",
    "rate_limited",
    "quota_exceeded",
    "model_unavailable",
    "provider_unavailable",
    "unsupported_capability",
    "bad_request",
    "content_rejected",
    "timeout",
    "retryable_server_error",
    "non_retryable_error",
]


def test_error_categories_verbatim_12() -> None:
    assert [c.value for c in ErrorCategory] == PLATFORM_ERROR_CATEGORIES
    assert len(ErrorCategory) == 12


def test_v1_operations_are_8_and_exclusions_are_3() -> None:
    assert len(GatewayOperation) == 8
    assert EXCLUDED_OPERATIONS == {"run_provider_agent", "upload_asset", "download_asset"}
    assert not ({op.value for op in GatewayOperation} & EXCLUDED_OPERATIONS)


def test_excluded_operation_rejected_at_load_time() -> None:
    with pytest.raises(ValueError, match="OPEN-2"):
        reject_excluded_operations(["generate_text", "upload_asset"])


def test_request_envelope_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RequestEnvelope.model_validate(
            {
                "operation": "generate_text",
                "model": "m",
                "request_id": "r",
                "tenant_id": "t",
                "credential": {"mode": "platform"},
                "payload": {},
                "timeout_ms": 1000,
                "provider_slug": "sneaky",  # forbidden by construction
            }
        )


def test_credential_user_key_requires_value() -> None:
    with pytest.raises(ValidationError):
        EnvelopeCredential.model_validate({"mode": "user_key"})


def test_credential_platform_forbids_value() -> None:
    with pytest.raises(ValidationError):
        EnvelopeCredential.model_validate({"mode": "platform", "value": "x"})


def test_response_envelope_one_of_output_error() -> None:
    with pytest.raises(ValidationError):
        ResponseEnvelope(succeeded=False, latency_ms=1, error=None)
    with pytest.raises(ValidationError):
        ResponseEnvelope(
            succeeded=True,
            output={},
            latency_ms=1,
            error=GatewayError(
                category=ErrorCategory.TIMEOUT, retryable=True, message="x"
            ),
        )


def test_facade_result_one_of() -> None:
    with pytest.raises(ValidationError):
        FacadeResult(succeeded=True, output=None)
    with pytest.raises(ValidationError):
        FacadeResult(succeeded=False, error=None)
    ok = FacadeResult(succeeded=True, output={"text": "x"}, usage=Usage(units=1))
    assert ok.output == {"text": "x"}


def test_definition_semver_enforced() -> None:
    base: dict[str, object] = {
        "display_name": "X",
        "credential_mode": "platform",
        "operations": ["generate_text"],
    }
    with pytest.raises(ValidationError):
        ProviderDefinition.model_validate({**base, "definition_version": "1.0"})
    ok = ProviderDefinition.model_validate({**base, "definition_version": "1.0.0"})
    assert ok.definition_version == "1.0.0"


def test_definition_unknown_capability_key_rejected() -> None:
    with pytest.raises(ValidationError, match="closed set"):
        ProviderDefinition.model_validate(
            {
                "display_name": "X",
                "definition_version": "1.0.0",
                "credential_mode": "platform",
                "capabilities": {"telepathy": True},
                "operations": ["generate_text"],
            }
        )
