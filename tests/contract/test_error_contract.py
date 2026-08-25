"""Contract tests: unified error format (10 §9).

Verifies the Pydantic contract against the documented wire format:
exact category set, envelope shape, validation accept/reject behavior,
and JSON Schema exportability (the language-neutral contract artifact).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.contracts.errors import ErrorCode, ErrorDetail, ErrorEnvelope

# The 11 categories exactly as written in 10 §9 — the contract must not drift.
DOCUMENTED_CATEGORIES = {
    "validation_error",
    "unauthenticated",
    "unauthorized",
    "entitlement_exceeded",
    "capability_denied",
    "provider_unavailable",
    "model_unavailable",
    "tool_approval_required",
    "rate_limited",
    "execution_failed",
    "internal_error",
}


def test_error_categories_match_spec_exactly() -> None:
    assert {c.value for c in ErrorCode} == DOCUMENTED_CATEGORIES


def test_documented_example_validates() -> None:
    # The literal example from 10 §9.
    payload = {
        "error": {
            "code": "capability_denied",
            "message": "This tool is not allowed for the current user or plan.",
            "retryable": False,
            "details": {"capability": "github.pr.merge"},
            "trace_id": "trace-id",
        }
    }
    env = ErrorEnvelope.model_validate(payload)
    assert env.error.code is ErrorCode.CAPABILITY_DENIED
    assert env.error.retryable is False
    assert env.error.details == {"capability": "github.pr.merge"}
    # Round-trip: serialization reproduces the documented wire shape.
    assert env.model_dump(mode="json", exclude_none=True) == payload


def test_minimal_error_defaults() -> None:
    detail = ErrorDetail(
        code=ErrorCode.INTERNAL_ERROR, message="unexpected failure", retryable=True
    )
    assert detail.details == {}
    assert detail.trace_id is None


def test_unknown_error_code_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate({"code": "not_a_real_code", "message": "x", "retryable": False})


def test_unknown_fields_rejected() -> None:
    # extra="forbid": deny-by-default posture at the contract boundary.
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate(
            {
                "error": {
                    "code": "internal_error",
                    "message": "x",
                    "retryable": False,
                    "smuggled": True,
                }
            }
        )


def test_missing_required_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate({"code": "internal_error"})


def test_empty_message_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail.model_validate({"code": "internal_error", "message": "", "retryable": False})


def test_contract_instances_are_immutable() -> None:
    detail = ErrorDetail(code=ErrorCode.RATE_LIMITED, message="slow down", retryable=True)
    with pytest.raises(ValidationError):
        detail.message = "mutated"


def test_json_schema_export() -> None:
    # Language-neutral contract artifact (ADR-0001 rollback guarantee).
    schema = ErrorEnvelope.model_json_schema()
    assert schema["required"] == ["error"]
    code_schema = schema["$defs"]["ErrorCode"]
    assert set(code_schema["enum"]) == DOCUMENTED_CATEGORIES
    detail_schema = schema["$defs"]["ErrorDetail"]
    assert detail_schema["additionalProperties"] is False
    assert set(detail_schema["required"]) == {"code", "message", "retryable"}
