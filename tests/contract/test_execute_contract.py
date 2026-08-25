"""Contract tests: /v1/execute API (10 §2-§5), streaming (10 §11), webhooks (10 §12).

Every documented example from 10_API_CONTRACTS.md is validated verbatim;
invalid payloads (unknown fields, unknown enum values, missing required
fields) must be rejected.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from core.contracts.execute import (
    ExecuteAsyncAccepted,
    ExecuteRequest,
    ExecuteSyncResponse,
    ExecutionStatus,
    ExecutionStatusResponse,
    StreamEvent,
    WebhookEventType,
    WebhookPayload,
)

# --- §2 request ---------------------------------------------------------------

# The literal request example from 10 §2.
DOCUMENTED_REQUEST = {
    "ask": "راجع الكود ده أو ابنِ بوست تسويقي لمنتج كذا",
    "mode": "auto",
    "conversation_id": "optional-uuid",
    "project_id": "optional-uuid",
    "role": {"type": "system", "id": "senior_software_architect"},
    "model_policy": {
        "type": "auto",
        "tier": "medium",
        "explicit_model_id": None,
        "allow_fallback": True,
        "fallback_scope": "same_tier",
    },
    "execution_policy": {
        "strategy": "auto",
        "async": False,
        "stream": False,
        "max_cost_units": 3,
        "approval_required_for_tools": True,
    },
    "tools": {"allowed": ["github", "browser"], "denied": [], "approval_mode": "before_write"},
    "context": {"attachments": [], "metadata": {}, "language": "ar"},
    "output": {"format": "markdown", "language": "ar", "schema": None},
    "webhook_url": None,
}


def test_documented_request_example_validates() -> None:
    req = ExecuteRequest.model_validate(DOCUMENTED_REQUEST)
    assert req.mode == "auto"
    assert req.model_policy is not None and req.model_policy.type == "auto"
    assert req.execution_policy is not None
    assert req.execution_policy.async_ is False
    assert req.execution_policy.max_cost_units == 3
    assert req.tools is not None and req.tools.allowed == ["github", "browser"]
    assert req.output is not None and req.output.schema_ is None


def test_documented_request_round_trip_wire_shape() -> None:
    # Serialization by alias reproduces the documented wire keys
    # ("async", "schema") — not the Python-safe attribute names.
    req = ExecuteRequest.model_validate(DOCUMENTED_REQUEST)
    wire = req.model_dump(mode="json", by_alias=True)
    assert wire == DOCUMENTED_REQUEST


def test_only_ask_is_required() -> None:
    # 10 §2: "Required Fields: ask. Everything else has policy-driven defaults."
    req = ExecuteRequest.model_validate({"ask": "hello"})
    assert req.model_policy is None
    assert req.execution_policy is None
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate({})


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate({"ask": "x", "smuggled": True})
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(
            {"ask": "x", "execution_policy": {"strategy": "auto", "bogus": 1}}
        )


# --- §3 sync success response ---------------------------------------------------


def test_documented_sync_response_validates() -> None:
    # The literal example from 10 §3 (with concrete execution_id).
    payload = {
        "execution_id": "uuid",
        "status": "succeeded",
        "result": {
            "type": "message",
            "content": "final answer",
            "format": "markdown",
            "artifacts": [],
        },
        "usage": {"units_reserved": 2, "units_settled": 2, "details": {}},
        "evaluation": {"visible": False, "level": "EVALUATED", "summary": None},
    }
    resp = ExecuteSyncResponse.model_validate(payload)
    assert resp.status is ExecutionStatus.SUCCEEDED
    assert resp.result.content == "final answer"
    assert resp.usage is not None and resp.usage.units_settled == 2
    assert resp.evaluation is not None and resp.evaluation.level == "EVALUATED"
    assert resp.model_dump(mode="json") == payload


def test_negative_usage_units_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecuteSyncResponse.model_validate(
            {
                "execution_id": "uuid",
                "status": "succeeded",
                "result": {"type": "message", "content": "x"},
                "usage": {"units_reserved": -1, "units_settled": 0},
            }
        )


# --- §4 async accepted -----------------------------------------------------------


def test_documented_async_accepted_validates() -> None:
    payload = {"execution_id": "uuid", "status": "queued", "poll_url": "/v1/executions/uuid"}
    resp = ExecuteAsyncAccepted.model_validate(payload)
    assert resp.status is ExecutionStatus.QUEUED
    assert resp.model_dump(mode="json") == payload


def test_async_accepted_requires_queued_status() -> None:
    # The accepted response is specifically status=queued (10 §4).
    with pytest.raises(ValidationError):
        ExecuteAsyncAccepted.model_validate(
            {"execution_id": "uuid", "status": "running", "poll_url": "/v1/executions/uuid"}
        )


# --- §5 execution status ----------------------------------------------------------


def test_documented_status_response_validates() -> None:
    payload = {
        "execution_id": "uuid",
        "status": "running",
        "progress": {"current_stage": "review", "percent": 65},
        "result": None,
        "error": None,
    }
    resp = ExecutionStatusResponse.model_validate(payload)
    assert resp.status is ExecutionStatus.RUNNING
    assert resp.progress is not None and resp.progress.percent == 65
    assert resp.model_dump(mode="json") == payload


def test_execution_status_set_matches_domain_model() -> None:
    # 03 Domain Model, Execution entity — verbatim, closed set.
    assert {s.value for s in ExecutionStatus} == {
        "queued",
        "running",
        "waiting_approval",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_status_response_with_unified_error() -> None:
    resp = ExecutionStatusResponse.model_validate(
        {
            "execution_id": "uuid",
            "status": "failed",
            "error": {
                "code": "execution_failed",
                "message": "node timed out",
                "retryable": True,
            },
        }
    )
    assert resp.error is not None and resp.error.code == "execution_failed"


def test_progress_percent_bounds() -> None:
    with pytest.raises(ValidationError):
        ExecutionStatusResponse.model_validate(
            {"execution_id": "uuid", "status": "running", "progress": {"percent": 101}}
        )


# --- §11 streaming events -----------------------------------------------------------

STREAM_ADAPTER: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)

# The literal event lines from 10 §11.
DOCUMENTED_STREAM_EVENTS = [
    {"type": "execution_started", "execution_id": "uuid"},
    {"type": "node_started", "node": "planner"},
    {"type": "delta", "content": "partial text"},
    {"type": "node_completed", "node": "reviewer"},
    {"type": "final", "result": {}},
    {"type": "error", "error": {}},
]


def test_all_documented_stream_events_validate_and_round_trip() -> None:
    for payload in DOCUMENTED_STREAM_EVENTS:
        event = STREAM_ADAPTER.validate_python(payload)
        assert STREAM_ADAPTER.dump_python(event, mode="json") == payload


def test_unknown_stream_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        STREAM_ADAPTER.validate_python({"type": "made_up_event"})


def test_stream_event_field_mismatch_rejected() -> None:
    # A delta event must carry "content", not "node".
    with pytest.raises(ValidationError):
        STREAM_ADAPTER.validate_python({"type": "delta", "node": "planner"})


# --- §12 webhooks --------------------------------------------------------------------


def test_webhook_event_types_match_spec_exactly() -> None:
    assert {e.value for e in WebhookEventType} == {
        "execution.queued",
        "execution.started",
        "execution.waiting_approval",
        "execution.succeeded",
        "execution.failed",
        "execution.cancelled",
    }


def test_documented_webhook_payload_validates() -> None:
    # The literal example from 10 §12 (with a concrete ISO timestamp).
    payload = {
        "event": "execution.succeeded",
        "execution_id": "uuid",
        "tenant_id": "uuid",
        "timestamp": "2026-08-25T12:00:00Z",
        "data": {},
    }
    wh = WebhookPayload.model_validate(payload)
    assert wh.event is WebhookEventType.EXECUTION_SUCCEEDED
    assert wh.timestamp.tzinfo is not None


def test_unknown_webhook_event_rejected() -> None:
    with pytest.raises(ValidationError):
        WebhookPayload.model_validate(
            {
                "event": "execution.exploded",
                "execution_id": "uuid",
                "tenant_id": "uuid",
                "timestamp": "2026-08-25T12:00:00Z",
            }
        )


# --- JSON Schema export (language-neutral contract artifact) --------------------------


def test_execute_request_json_schema_export() -> None:
    schema = ExecuteRequest.model_json_schema()
    assert schema["required"] == ["ask"]
    assert schema["additionalProperties"] is False
    # Wire aliases survive in the schema.
    exec_policy = schema["$defs"]["ExecutionPolicy"]["properties"]
    assert "async" in exec_policy and "async_" not in exec_policy
    output_spec = schema["$defs"]["OutputSpec"]["properties"]
    assert "schema" in output_spec and "schema_" not in output_spec
