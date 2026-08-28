"""Contract tests: provider contract (30 §5, §7, §11, §12, §14).

Validates the documented provider manifest example verbatim, the closed
operation/health/rate-limit/error-category sets, the documented normalized
error example, and deny-by-default behavior (unknown fields/values rejected;
undeclared capabilities default to False).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from core.contracts.provider import (
    AccountHealthCheckState,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderHealth,
    ProviderHealthState,
    ProviderManifest,
    ProviderOperation,
    RateLimitState,
    RateLimitStatus,
)

# --- §5 capability-specific operations ------------------------------------------

DOCUMENTED_OPERATIONS = {
    "generate_text",
    "generate_image",
    "transcribe_audio",
    "synthesize_speech",
    "create_embeddings",
    "rerank_documents",
    "moderate_content",
    "analyze_vision",
    "run_provider_agent",
    "upload_asset",
    "download_asset",
}


def test_operations_match_spec_exactly() -> None:
    assert {o.value for o in ProviderOperation} == DOCUMENTED_OPERATIONS


# --- §7 provider manifest (documented example, verbatim) --------------------------


def _manifest_payload(**overrides: Any) -> dict[str, Any]:
    # The literal manifest example from 30 §7.
    payload: dict[str, Any] = {
        "id": "provider_x",
        "name": "Provider X",
        "version": "1.0.0",
        "status": "active",
        "auth": {
            "types": ["api_key", "session_cookie"],
            "supports_refresh": True,
        },
        "account_pool": {
            "supported": True,
            "lease_required": True,
            "fencing_required": True,
        },
        "capabilities": {
            "chat": True,
            "reasoning": True,
            "code": True,
            "vision_input": True,
            "image_generation": False,
            "audio_input": False,
            "audio_output": False,
            "file_upload": True,
            "browser": False,
            "agent_module": False,
        },
        "models": {"discovery": "dynamic", "static_models": []},
        "rate_limits": {
            "strategy": "provider_defined",
            "dimensions": ["account", "model", "endpoint", "time_window"],
        },
        "health": {"checks": ["auth_valid", "endpoint_available", "quota_available"]},
        "errors": {"mapping": "provider_x_error_map"},
    }
    payload.update(overrides)
    return payload


def test_documented_manifest_example_validates() -> None:
    manifest = ProviderManifest.model_validate(_manifest_payload())
    assert manifest.id == "provider_x"
    assert manifest.auth.supports_refresh is True
    assert manifest.account_pool.fencing_required is True
    assert manifest.capabilities.chat is True
    assert manifest.capabilities.image_generation is False
    assert manifest.models.discovery == "dynamic"
    assert manifest.models.static_models == []
    assert manifest.rate_limits.dimensions == [
        "account",
        "model",
        "endpoint",
        "time_window",
    ]
    assert manifest.errors.mapping == "provider_x_error_map"


def test_manifest_operations_declaration() -> None:
    # 30 §5: a provider implements only the operations it declares.
    manifest = ProviderManifest.model_validate(
        _manifest_payload(operations=["generate_text", "analyze_vision"])
    )
    assert ProviderOperation.GENERATE_TEXT in manifest.operations
    assert ProviderOperation.GENERATE_IMAGE not in manifest.operations


def test_manifest_rejects_unknown_operation() -> None:
    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(_manifest_payload(operations=["mine_bitcoin"]))


def test_manifest_rejects_unknown_capability_key() -> None:
    # Capability key set is closed — a new key is a contract change.
    caps = dict(_manifest_payload()["capabilities"])
    caps["telepathy"] = True
    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(_manifest_payload(capabilities=caps))


def test_manifest_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(_manifest_payload(billing="prepaid"))


def test_capabilities_default_to_deny() -> None:
    # 30 §4.3: never assume undeclared capabilities => all default False.
    caps = ProviderCapabilities()
    assert not any(getattr(caps, field) for field in ProviderCapabilities.model_fields)


def test_manifest_without_account_pool_is_valid() -> None:
    # 30 §10.1: account pools are optional per provider.
    manifest = ProviderManifest.model_validate(
        _manifest_payload(
            account_pool={"supported": False},
            models={"discovery": "none", "static_models": []},
        )
    )
    assert manifest.account_pool.supported is False
    assert manifest.account_pool.lease_required is False


def test_manifest_auth_requires_at_least_one_type() -> None:
    # 30 §7: a REAL (functional, non-template) provider must declare auth.
    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(
            _manifest_payload(auth={"types": [], "supports_refresh": False})
        )


def test_template_manifest_allows_empty_auth_types() -> None:
    # 31 §7 verbatim: template manifests declare ``auth: types: []``.
    manifest = ProviderManifest.model_validate(
        _manifest_payload(
            status="template_disabled",
            is_template=True,
            is_functional=False,
            real_provider_required=True,
            auth={"types": [], "supports_refresh": False},
            notes=["TEMPLATE ONLY", "replace before enabling"],
        )
    )
    assert manifest.is_template is True
    assert manifest.auth.types == []
    assert manifest.notes == ["TEMPLATE ONLY", "replace before enabling"]


def test_capabilities_include_diversity_categories() -> None:
    # 31 §6 categories 8-10 + §8: embeddings/rerank/moderation/tool_use are
    # declarable capability keys (still deny-by-default).
    caps = ProviderCapabilities(
        embeddings=True, rerank=True, moderation=True, tool_use=True
    )
    assert caps.embeddings and caps.rerank and caps.moderation and caps.tool_use
    assert ProviderCapabilities().embeddings is False


def test_agent_module_and_security_blocks() -> None:
    # 31 §8: provider-native agent template declares agent_module + security.
    manifest = ProviderManifest.model_validate(
        _manifest_payload(
            status="template_disabled",
            is_template=True,
            is_functional=False,
            real_provider_required=True,
            auth={"types": []},
            agent_module={
                "supported": True,
                "type": "provider_native_agent",
                "state_model": "unknown",
                "supports_provider_tools": "unknown",
                "supports_platform_tools": False,
                "provider_managed_state": "unknown",
            },
            security={
                "provider_side_tools_allowed_by_default": False,
                "requires_capability_firewall": True,
                "requires_evaluation": True,
                "requires_audit": True,
            },
        )
    )
    assert manifest.agent_module is not None
    assert manifest.agent_module.supported is True
    # 11 §5: unknown is a legal declared value, never treated as supported.
    assert manifest.agent_module.supports_provider_tools == "unknown"
    assert manifest.security is not None
    assert manifest.security.provider_side_tools_allowed_by_default is False


def test_agent_module_absent_on_ordinary_manifest() -> None:
    manifest = ProviderManifest.model_validate(_manifest_payload())
    assert manifest.agent_module is None
    assert manifest.security is None
    assert manifest.notes == []


# --- §11 health --------------------------------------------------------------------


def test_provider_health_states_match_spec() -> None:
    assert {s.value for s in ProviderHealthState} == {
        "HEALTHY",
        "DEGRADED",
        "UNAVAILABLE",
        "SUSPENDED",
    }


def test_account_health_check_states_match_spec() -> None:
    assert {s.value for s in AccountHealthCheckState} == {
        "READY",
        "COOLDOWN",
        "AUTH_EXPIRED",
        "INVALID",
    }


def test_provider_health_separates_provider_and_account_state() -> None:
    # 30 §11: one failed account must not read as "provider down".
    health = ProviderHealth.model_validate(
        {
            "provider_id": "provider_x",
            "state": "HEALTHY",
            "accounts": {"acct-1": "READY", "acct-2": "AUTH_EXPIRED"},
        }
    )
    assert health.state is ProviderHealthState.HEALTHY
    assert health.accounts["acct-2"] is AccountHealthCheckState.AUTH_EXPIRED


def test_provider_health_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth.model_validate({"provider_id": "provider_x", "state": "DOWN"})


# --- §12 normalized rate-limit state ---------------------------------------------------


def test_rate_limit_states_match_spec() -> None:
    assert {s.value for s in RateLimitState} == {
        "available",
        "limited",
        "cooldown_until",
        "unknown",
    }


def test_rate_limit_status_with_cooldown() -> None:
    status = RateLimitStatus.model_validate(
        {"state": "cooldown_until", "cooldown_until": "2026-08-25T12:30:00Z"}
    )
    assert status.state is RateLimitState.COOLDOWN_UNTIL
    assert status.cooldown_until is not None


def test_rate_limit_status_unknown_is_valid_state() -> None:
    # 30 §12: unknown is an explicit normalized state, not an error.
    status = RateLimitStatus.model_validate({"state": "unknown"})
    assert status.cooldown_until is None


def test_cooldown_state_without_timestamp_is_rejected() -> None:
    """T-IMPL-034: a cooldown with no end time cannot drive behavior —
    incoherent rate-limit state must not be constructible (30 §12)."""
    with pytest.raises(ValidationError):
        RateLimitStatus.model_validate({"state": "cooldown_until"})


def test_available_state_with_cooldown_timestamp_is_rejected() -> None:
    """T-IMPL-034: "available but cooling down" is contradictory data —
    the state that consumers act on must be honest (30 §12)."""
    with pytest.raises(ValidationError):
        RateLimitStatus.model_validate(
            {"state": "available", "cooldown_until": "2026-08-25T12:30:00Z"}
        )


def test_limited_and_unknown_may_carry_advisory_timestamp() -> None:
    """Advisory hints stay legal: limited/unknown may carry a timestamp."""
    for state in ("limited", "unknown"):
        status = RateLimitStatus.model_validate(
            {"state": state, "cooldown_until": "2026-08-25T12:30:00Z"}
        )
        assert status.cooldown_until is not None


# --- §14 error normalization ------------------------------------------------------------

DOCUMENTED_ERROR_CATEGORIES = {
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
}


def test_error_categories_match_spec_exactly() -> None:
    assert {c.value for c in ProviderErrorCategory} == DOCUMENTED_ERROR_CATEGORIES


def test_documented_normalized_error_example_validates() -> None:
    # The literal example from 30 §14.
    payload = {
        "category": "rate_limited",
        "retryable": True,
        "retry_after_ms": 30000,
        "provider_code": "raw-code",
        "safe_message": "Provider rate limit reached.",
    }
    err = ProviderError.model_validate(payload)
    assert err.category is ProviderErrorCategory.RATE_LIMITED
    assert err.retryable is True
    assert err.retry_after_ms == 30000
    # Round-trip: serialization reproduces the documented wire shape.
    assert err.model_dump(mode="json", exclude_none=True) == payload


def test_normalized_error_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        ProviderError.model_validate(
            {
                "category": "mystery_error",
                "retryable": False,
                "safe_message": "x",
            }
        )


def test_normalized_error_requires_safe_message() -> None:
    with pytest.raises(ValidationError):
        ProviderError.model_validate({"category": "timeout", "retryable": True})


def test_normalized_error_rejects_negative_retry_after() -> None:
    with pytest.raises(ValidationError):
        ProviderError.model_validate(
            {
                "category": "rate_limited",
                "retryable": True,
                "retry_after_ms": -1,
                "safe_message": "x",
            }
        )


def test_json_schema_export_is_closed() -> None:
    for entity in (ProviderManifest, ProviderHealth, RateLimitStatus, ProviderError):
        schema = entity.model_json_schema()
        assert schema["additionalProperties"] is False
