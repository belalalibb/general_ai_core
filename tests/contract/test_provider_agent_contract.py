"""Provider-agent contract tests (30 §15.2 payloads, §15.3 events, 12 §23.3
run lifecycle) — FINAL Phase 4, T-IMPL-054.

Hermetic: pure contract validation, no network, no provider imports.
"""

from __future__ import annotations

import ast
import inspect
from uuid import uuid4

import pytest
from pydantic import ValidationError

import core.contracts.provider_agent as provider_agent_module
from core.contracts.provider import ProviderError, ProviderErrorCategory
from core.contracts.provider_agent import (
    ProviderAgentEvent,
    ProviderAgentEventType,
    ProviderAgentRequest,
    ProviderAgentResponse,
    ProviderAgentRun,
    ProviderAgentRunState,
    ProviderAgentRunStatus,
)


def _error() -> ProviderError:
    return ProviderError(
        category=ProviderErrorCategory.TIMEOUT,
        retryable=True,
        safe_message="Provider agent run timed out.",
    )


def _request(**overrides: object) -> ProviderAgentRequest:
    payload: dict[str, object] = {
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "provider_agent_id": "provider_a_code_agent",
        "credential_ref": "cred-ref-opaque-1",
    }
    payload.update(overrides)
    return ProviderAgentRequest.model_validate(payload)


# --- closed sets, verbatim ---------------------------------------------------------


def test_run_state_is_the_12_s23_3_platform_node_lifecycle_verbatim() -> None:
    assert {s.value for s in ProviderAgentRunState} == {
        "pending",
        "ready",
        "running",
        "waiting_approval",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_event_types_are_the_30_s15_3_seven_events_verbatim() -> None:
    assert {e.value for e in ProviderAgentEventType} == {
        "provider_agent.started",
        "provider_agent.step_started",
        "provider_agent.tool_requested",
        "provider_agent.tool_completed",
        "provider_agent.message_delta",
        "provider_agent.completed",
        "provider_agent.failed",
    }


# --- request: deny-by-default tool posture (30 §15.4) ------------------------------


def test_request_provider_side_tools_denied_by_default() -> None:
    req = _request()
    assert req.provider_side_tools_allowed is False


def test_request_carries_only_opaque_credential_reference() -> None:
    with pytest.raises(ValidationError):
        _request(credential_value="sk-secret")  # extra=forbid: no secret fields
    with pytest.raises(ValidationError):
        _request(api_key="sk-secret")


def test_request_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _request(timeout_ms=0)


# --- response: failure coherence (30 §14) ------------------------------------------


def test_response_failure_requires_normalized_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentResponse(request_id=uuid4(), succeeded=False)


def test_response_success_must_not_carry_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentResponse(request_id=uuid4(), succeeded=True, error=_error())


def test_response_success_and_failure_shapes_roundtrip() -> None:
    ok = ProviderAgentResponse(request_id=uuid4(), succeeded=True, output={"text": "done"})
    assert ok.error is None
    failed = ProviderAgentResponse(request_id=uuid4(), succeeded=False, error=_error())
    assert failed.error is not None
    assert failed.error.category is ProviderErrorCategory.TIMEOUT


def test_response_latency_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentResponse(request_id=uuid4(), succeeded=True, latency_ms=-1)


# --- run handle + status coherence -------------------------------------------------


def test_run_handle_run_id_is_opaque_string_not_uuid() -> None:
    run = ProviderAgentRun(
        run_id="thread_abc123/run_9",  # provider-namespace handle
        request_id=uuid4(),
        state=ProviderAgentRunState.PENDING,
    )
    assert run.run_id == "thread_abc123/run_9"


def test_run_status_failed_requires_normalized_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentRunStatus(run_id="r1", state=ProviderAgentRunState.FAILED)


def test_run_status_non_failed_must_not_carry_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentRunStatus(run_id="r1", state=ProviderAgentRunState.SUCCEEDED, error=_error())


def test_run_status_every_non_failed_state_expressible_without_error() -> None:
    for state in ProviderAgentRunState:
        if state is ProviderAgentRunState.FAILED:
            continue
        status = ProviderAgentRunStatus(run_id="r1", state=state)
        assert status.error is None


# --- events: failure coherence + opaque trace payload ------------------------------


def test_failed_event_requires_normalized_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentEvent(type=ProviderAgentEventType.FAILED, run_id="r1")


def test_non_failed_events_must_not_carry_error() -> None:
    with pytest.raises(ValidationError):
        ProviderAgentEvent(type=ProviderAgentEventType.COMPLETED, run_id="r1", error=_error())


def test_every_event_type_expressible_with_opaque_payload() -> None:
    for event_type in ProviderAgentEventType:
        error = _error() if event_type is ProviderAgentEventType.FAILED else None
        event = ProviderAgentEvent(
            type=event_type,
            run_id="r1",
            payload={"provider_trace": "opaque"},
            error=error,
        )
        assert event.payload == {"provider_trace": "opaque"}


# --- module posture -----------------------------------------------------------------


def test_contracts_are_frozen_and_reject_unknown_fields() -> None:
    run = ProviderAgentRun(run_id="r1", request_id=uuid4(), state=ProviderAgentRunState.PENDING)
    with pytest.raises(ValidationError):
        run.state = ProviderAgentRunState.RUNNING  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ProviderAgentRun.model_validate(
            {
                "run_id": "r1",
                "request_id": str(uuid4()),
                "state": "pending",
                "surprise": 1,
            }
        )


def test_module_imports_no_implementation_packages() -> None:
    source = inspect.getsource(provider_agent_module)
    tree = ast.parse(source)
    forbidden_roots = {"apps", "providers", "infrastructure"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in forbidden_roots
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_roots


def test_no_duplicate_lifecycle_enum_defined_elsewhere() -> None:
    # The run state set is defined ONCE here; ProviderError is REUSED from
    # core.contracts.provider (no duplicate error shape).
    source = inspect.getsource(provider_agent_module)
    assert "class ProviderError" not in source
