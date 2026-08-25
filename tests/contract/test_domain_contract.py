"""Contract tests: core domain types (03 §4 Models/Providers/Accounts, §9 agent).

Verifies every closed set matches the spec verbatim, that the documented
entity shapes validate, that unknown fields/values are rejected
(deny-by-default), and that agent capability flags default to undeclared.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.domain import (
    AccountHealthState,
    AccountLifecycleState,
    AgentCapability,
    AgentCapabilityType,
    AgentRuntimeBinding,
    AuthType,
    BindingAvailability,
    Credential,
    CredentialStatus,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    OwnerType,
    Provider,
    ProviderAccount,
    ProviderModelBinding,
    ProviderStatus,
)

# --- Closed sets exactly as written in 03 §4 / §9 -----------------------------


def test_model_tier_set_matches_spec() -> None:
    assert {t.value for t in ModelTier} == {"fast", "medium", "max", "custom"}


def test_modality_set_matches_spec() -> None:
    assert {m.value for m in Modality} == {"text", "image", "audio", "video", "code"}


def test_model_status_set_matches_spec() -> None:
    assert {s.value for s in ModelStatus} == {"active", "disabled", "deprecated"}


def test_provider_status_set_matches_spec() -> None:
    assert {s.value for s in ProviderStatus} == {"active", "disabled", "maintenance"}


def test_auth_type_set_matches_spec() -> None:
    assert {a.value for a in AuthType} == {
        "api_key",
        "oauth",
        "session_cookie",
        "custom",
    }


def test_binding_availability_set_matches_spec() -> None:
    assert {a.value for a in BindingAvailability} == {
        "available",
        "unavailable",
        "degraded",
    }


def test_owner_type_set_matches_spec() -> None:
    assert {o.value for o in OwnerType} == {"platform", "tenant", "user"}


def test_credential_status_set_matches_spec() -> None:
    assert {s.value for s in CredentialStatus} == {
        "active",
        "revoked",
        "expired",
        "invalid",
    }


def test_account_lifecycle_state_set_matches_spec() -> None:
    # 03 §4 ProviderAccount.lifecycle_state — 7 values, uppercase, verbatim.
    assert {s.value for s in AccountLifecycleState} == {
        "READY",
        "COOLDOWN",
        "REFRESH_REQUIRED",
        "AUTH_EXPIRED",
        "INVALID",
        "PENDING",
        "DISABLED",
    }


def test_account_health_state_set_matches_spec() -> None:
    assert {s.value for s in AccountHealthState} == {
        "healthy",
        "degraded",
        "failed",
        "unknown",
    }


def test_agent_capability_type_set_matches_spec() -> None:
    # 03 §9.1 — 6 values, verbatim.
    assert {t.value for t in AgentCapabilityType} == {
        "none",
        "tool_using_model",
        "provider_agent",
        "managed_assistant",
        "code_agent",
        "research_agent",
    }


# --- Documented entity shapes (03 §4) -----------------------------------------


def _model_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "model_key": "model-x",
        "display_name": "Model X",
        "tier": "fast",
        "modalities": ["text", "code"],
        "capabilities": ["reasoning", "coding", "vision", "image_generation"],
        "context_window": 128000,
        "quality_score": 0.9,
        "speed_score": 0.8,
        "cost_score": 0.5,
        "reliability_score": 0.95,
        "status": "active",
    }
    payload.update(overrides)
    return payload


def test_model_documented_shape_validates() -> None:
    model = Model.model_validate(_model_payload())
    assert model.tier is ModelTier.FAST
    assert model.status is ModelStatus.ACTIVE
    assert Modality.CODE in model.modalities


def test_model_nullable_scores_accept_null() -> None:
    # 03 §4: context_window and all scores are `|null`.
    model = Model.model_validate(
        _model_payload(
            context_window=None,
            quality_score=None,
            speed_score=None,
            cost_score=None,
            reliability_score=None,
        )
    )
    assert model.context_window is None
    assert model.quality_score is None


def test_model_requires_at_least_one_modality() -> None:
    with pytest.raises(ValidationError):
        Model.model_validate(_model_payload(modalities=[]))


def test_model_rejects_unknown_tier_and_status() -> None:
    with pytest.raises(ValidationError):
        Model.model_validate(_model_payload(tier="ultra"))
    with pytest.raises(ValidationError):
        Model.model_validate(_model_payload(status="archived"))


def test_model_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Model.model_validate(_model_payload(pricing="cheap"))


def test_model_capabilities_are_open_set() -> None:
    # 03 §9.1 — capability keys like tool_use / provider_agent are additive;
    # the Router treats unknown as ineligible, but the contract accepts them.
    model = Model.model_validate(
        _model_payload(capabilities=["reasoning", "tool_use", "provider_agent"])
    )
    assert "provider_agent" in model.capabilities


def test_provider_documented_shape_validates() -> None:
    provider = Provider.model_validate(
        {
            "id": str(uuid4()),
            "provider_key": "provider_x",
            "display_name": "Provider X",
            "status": "active",
            "auth_types": ["api_key", "oauth", "session_cookie", "custom"],
            "supports_account_pool": True,
        }
    )
    assert provider.status is ProviderStatus.ACTIVE
    assert set(provider.auth_types) == set(AuthType)


def test_provider_rejects_unknown_auth_type() -> None:
    with pytest.raises(ValidationError):
        Provider.model_validate(
            {
                "id": str(uuid4()),
                "provider_key": "provider_x",
                "display_name": "Provider X",
                "status": "active",
                "auth_types": ["magic_link"],
                "supports_account_pool": False,
            }
        )


def test_binding_documented_shape_validates() -> None:
    binding = ProviderModelBinding.model_validate(
        {
            "provider_id": str(uuid4()),
            "model_id": str(uuid4()),
            "provider_model_name": "provider-model-name",
            "endpoint_ref": "chat_completions",
            "availability": "available",
            "limits_metadata": {"rpm": 60},
        }
    )
    assert binding.availability is BindingAvailability.AVAILABLE
    assert binding.agent_runtime is None


def test_binding_agent_runtime_extension_validates() -> None:
    # The documented 03 §9.2 binding extension.
    binding = ProviderModelBinding.model_validate(
        {
            "provider_id": str(uuid4()),
            "model_id": str(uuid4()),
            "provider_model_name": "provider-agent-model",
            "availability": "available",
            "capabilities": {"provider_agent": True},
            "agent_runtime": {
                "provider_managed": True,
                "state_model": "thread",
                "tool_policy": "platform_controlled",
                "file_support": True,
                "max_steps": 10,
            },
        }
    )
    assert binding.agent_runtime is not None
    assert binding.agent_runtime.state_model == "thread"
    assert binding.agent_runtime.tool_policy == "platform_controlled"


def test_agent_runtime_rejects_unknown_state_model_and_tool_policy() -> None:
    with pytest.raises(ValidationError):
        AgentRuntimeBinding.model_validate(
            {"provider_managed": True, "state_model": "global", "tool_policy": "hybrid"}
        )
    with pytest.raises(ValidationError):
        AgentRuntimeBinding.model_validate(
            {"provider_managed": True, "state_model": "run", "tool_policy": "open"}
        )


def test_agent_runtime_max_steps_null_allowed_zero_rejected() -> None:
    # 03 §9.2: max_steps: integer|null.
    binding = AgentRuntimeBinding.model_validate(
        {
            "provider_managed": False,
            "state_model": "stateless",
            "tool_policy": "hybrid",
            "max_steps": None,
        }
    )
    assert binding.max_steps is None
    with pytest.raises(ValidationError):
        AgentRuntimeBinding.model_validate(
            {
                "provider_managed": False,
                "state_model": "stateless",
                "tool_policy": "hybrid",
                "max_steps": 0,
            }
        )


def test_agent_capability_documented_shape_validates() -> None:
    # The documented 03 §9.1 agent_capability metadata block.
    cap = AgentCapability.model_validate(
        {
            "type": "provider_agent",
            "supports_threads": True,
            "supports_tools": True,
            "supports_files": True,
            "supports_stateful_runs": True,
            "supports_streaming": True,
            "provider_managed_state": True,
        }
    )
    assert cap.type is AgentCapabilityType.PROVIDER_AGENT


def test_agent_capability_defaults_are_undeclared() -> None:
    # 30 §4.3: never assume undeclared capabilities. Flags default to None
    # (undeclared), not False/True.
    cap = AgentCapability()
    assert cap.type is AgentCapabilityType.NONE
    assert cap.supports_threads is None
    assert cap.supports_tools is None
    assert cap.provider_managed_state is None


def test_credential_documented_shape_validates() -> None:
    cred = Credential.model_validate(
        {
            "id": str(uuid4()),
            "owner_type": "tenant",
            "owner_id": str(uuid4()),
            "provider_id": str(uuid4()),
            "credential_ref": "secret-store://ref/abc",
            "status": "active",
        }
    )
    assert cred.owner_type is OwnerType.TENANT
    assert cred.status is CredentialStatus.ACTIVE


def test_credential_owner_id_nullable_and_ref_required() -> None:
    cred = Credential.model_validate(
        {
            "id": str(uuid4()),
            "owner_type": "platform",
            "owner_id": None,
            "provider_id": str(uuid4()),
            "credential_ref": "secret-store://ref/platform",
            "status": "active",
        }
    )
    assert cred.owner_id is None
    with pytest.raises(ValidationError):
        Credential.model_validate(
            {
                "id": str(uuid4()),
                "owner_type": "platform",
                "provider_id": str(uuid4()),
                "credential_ref": "",  # opaque ref must be non-empty
                "status": "active",
            }
        )


def test_provider_account_documented_shape_validates() -> None:
    account = ProviderAccount.model_validate(
        {
            "id": str(uuid4()),
            "provider_id": str(uuid4()),
            "credential_id": str(uuid4()),
            "owner_type": "platform",
            "lifecycle_state": "COOLDOWN",
            "health_state": "degraded",
            "cooldown_until": "2026-08-25T12:00:00Z",
        }
    )
    assert account.lifecycle_state is AccountLifecycleState.COOLDOWN
    assert account.health_state is AccountHealthState.DEGRADED
    assert account.cooldown_until is not None


def test_provider_account_rejects_lowercase_lifecycle_state() -> None:
    # Lifecycle states are uppercase in 03 §4 — case drift is contract drift.
    with pytest.raises(ValidationError):
        ProviderAccount.model_validate(
            {
                "id": str(uuid4()),
                "provider_id": str(uuid4()),
                "credential_id": str(uuid4()),
                "owner_type": "platform",
                "lifecycle_state": "cooldown",
                "health_state": "degraded",
            }
        )


def test_entities_are_frozen_value_objects() -> None:
    model = Model.model_validate(_model_payload())
    with pytest.raises(ValidationError):
        model.status = ModelStatus.DISABLED


def test_json_schema_export_is_closed() -> None:
    # Contract artifacts export with additionalProperties=false everywhere.
    for entity in (Model, Provider, ProviderModelBinding, Credential, ProviderAccount):
        schema = entity.model_json_schema()
        assert schema["additionalProperties"] is False
