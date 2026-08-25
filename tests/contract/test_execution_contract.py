"""Contract tests: execution contract (03 §5 Execution / ExecutionNode).

Verifies every closed set matches 03 §5 verbatim, the documented entity
shapes validate, ExecutionStatus is the single shared 6-state lifecycle,
unknown fields/values are rejected (deny-by-default), and instances are
frozen value objects with closed JSON Schema exports.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)

# --- Closed sets exactly as written in 03 §5 ----------------------------------


def test_execution_strategy_set_matches_spec() -> None:
    # 03 §5: single|parallel|pipeline|debate|review_judge|map_reduce|agent|hybrid
    # (identical list in 12 §2)
    assert {s.value for s in ExecutionStrategy} == {
        "single",
        "parallel",
        "pipeline",
        "debate",
        "review_judge",
        "map_reduce",
        "agent",
        "hybrid",
    }


def test_execution_node_type_set_matches_spec() -> None:
    # 03 §5: model_call|tool_call|planner|reviewer|tester|validator|aggregator
    assert {t.value for t in ExecutionNodeType} == {
        "model_call",
        "tool_call",
        "planner",
        "reviewer",
        "tester",
        "validator",
        "aggregator",
    }


def test_execution_node_status_set_matches_spec() -> None:
    # 03 §5: pending|running|succeeded|failed|skipped|cancelled
    assert {s.value for s in ExecutionNodeStatus} == {
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
    }


def test_execution_reuses_shared_execution_status() -> None:
    # Single source of truth: the entity uses the same 6-state lifecycle
    # already carried by the API contract (03 §5 == 10 §5 status values).
    field = Execution.model_fields["status"]
    assert field.annotation is ExecutionStatus
    assert {s.value for s in ExecutionStatus} == {
        "queued",
        "running",
        "waiting_approval",
        "succeeded",
        "failed",
        "cancelled",
    }


# --- Documented entity shapes (03 §5, field-for-field) -------------------------


def _execution_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "conversation_id": None,
        "request_hash": "sha256:1f3a9c",
        "idempotency_key": None,
        "status": "queued",
        "strategy": "single",
        # documented cost_snapshot example shape (11 §10)
        "cost_snapshot": {"estimated_units": 2},
        "created_at": "2026-08-25T12:00:00Z",
        "completed_at": None,
    }
    payload.update(overrides)
    return payload


def _node_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "execution_id": str(uuid4()),
        "node_key": "review_code",
        "type": "model_call",
        "status": "pending",
        "input_ref": "blob://executions/abc/input.json",
        "output_ref": None,
        "retry_count": 0,
        "error": None,
    }
    payload.update(overrides)
    return payload


def test_execution_documented_shape_validates() -> None:
    execution = Execution.model_validate(_execution_payload())
    assert execution.status is ExecutionStatus.QUEUED
    assert execution.strategy is ExecutionStrategy.SINGLE
    assert execution.cost_snapshot == {"estimated_units": 2}
    assert execution.conversation_id is None
    assert execution.completed_at is None


def test_execution_completed_shape_validates() -> None:
    execution = Execution.model_validate(
        _execution_payload(
            conversation_id=str(uuid4()),
            idempotency_key="idem-123",
            status="succeeded",
            strategy="agent",
            completed_at="2026-08-25T12:05:00Z",
        )
    )
    assert execution.status is ExecutionStatus.SUCCEEDED
    assert execution.strategy is ExecutionStrategy.AGENT
    assert execution.completed_at is not None
    assert execution.completed_at > execution.created_at


def test_execution_rejects_unknown_strategy_and_status() -> None:
    with pytest.raises(ValidationError):
        Execution.model_validate(_execution_payload(strategy="swarm"))
    with pytest.raises(ValidationError):
        Execution.model_validate(_execution_payload(status="paused"))


def test_execution_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Execution.model_validate(_execution_payload(priority="high"))


def test_execution_requires_request_hash() -> None:
    payload = _execution_payload()
    del payload["request_hash"]
    with pytest.raises(ValidationError):
        Execution.model_validate(payload)


def test_node_documented_shape_validates() -> None:
    node = ExecutionNode.model_validate(_node_payload())
    assert node.type is ExecutionNodeType.MODEL_CALL
    assert node.status is ExecutionNodeStatus.PENDING
    assert node.retry_count == 0
    assert node.output_ref is None
    assert node.error is None


def test_node_input_ref_accepts_string_or_json() -> None:
    # 03 §5: input_ref is string/json — both representations are valid.
    by_ref = ExecutionNode.model_validate(_node_payload(input_ref="blob://x/in.json"))
    assert by_ref.input_ref == "blob://x/in.json"
    inline = ExecutionNode.model_validate(_node_payload(input_ref={"prompt": "review this diff"}))
    assert inline.input_ref == {"prompt": "review this diff"}


def test_node_output_ref_accepts_string_json_or_null() -> None:
    # 03 §5: output_ref is string/json|null.
    assert (
        ExecutionNode.model_validate(_node_payload(output_ref="blob://x/out.json")).output_ref
        == "blob://x/out.json"
    )
    assert ExecutionNode.model_validate(
        _node_payload(output_ref={"verdict": "approve"})
    ).output_ref == {"verdict": "approve"}
    assert ExecutionNode.model_validate(_node_payload(output_ref=None)).output_ref is None


def test_node_failed_shape_with_error_validates() -> None:
    node = ExecutionNode.model_validate(
        _node_payload(
            status="failed",
            retry_count=2,
            error={"category": "timeout", "message": "provider timed out"},
        )
    )
    assert node.status is ExecutionNodeStatus.FAILED
    assert node.retry_count == 2
    assert node.error is not None and node.error["category"] == "timeout"


def test_node_rejects_unknown_type_and_status() -> None:
    # approval_gate/human_input/finalizer/provider_agent_call are 12 §5
    # *graph-runtime* node types, not 03 §5 domain-entity types.
    with pytest.raises(ValidationError):
        ExecutionNode.model_validate(_node_payload(type="approval_gate"))
    with pytest.raises(ValidationError):
        # "ready" / "waiting_approval" are 12 §6 graph lifecycle states only.
        ExecutionNode.model_validate(_node_payload(status="ready"))


def test_node_rejects_negative_retry_count_and_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ExecutionNode.model_validate(_node_payload(retry_count=-1))
    with pytest.raises(ValidationError):
        ExecutionNode.model_validate(_node_payload(weight=0.5))


def test_node_requires_node_key_non_empty() -> None:
    with pytest.raises(ValidationError):
        ExecutionNode.model_validate(_node_payload(node_key=""))


# --- Contract-layer posture ----------------------------------------------------


def test_entities_are_frozen_value_objects() -> None:
    execution = Execution.model_validate(_execution_payload())
    with pytest.raises(ValidationError):
        execution.status = ExecutionStatus.RUNNING  # type: ignore[misc]
    node = ExecutionNode.model_validate(_node_payload())
    with pytest.raises(ValidationError):
        node.retry_count = 3  # type: ignore[misc]


def test_json_schema_exports_are_closed() -> None:
    for entity in (Execution, ExecutionNode):
        schema = entity.model_json_schema()
        assert schema["additionalProperties"] is False
