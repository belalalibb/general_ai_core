"""Contract tests: composed context (13 §5) — T-IMPL-027 slice.

Verifies the 13 §5 output contract shape verbatim (context_blocks +
excluded), the closed block-type and exclusion-reason sets, the input
contract's safe defaults (deny high sensitivity by default), and the
deny-by-default validation posture (unknown fields rejected, frozen).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.context import (
    ComposedContext,
    ContextBlock,
    ContextBlockType,
    ContextComposeRequest,
    ContextExclusionReason,
    ExcludedMemory,
)

# --- Closed sets --------------------------------------------------------------


def test_block_types_closed_set() -> None:
    assert {t.value for t in ContextBlockType} == {
        "role",
        "preference",
        "history",
        "ask",
    }


def test_exclusion_reasons_closed_set() -> None:
    assert {r.value for r in ContextExclusionReason} == {
        "irrelevant",
        "low_confidence",
        "high_sensitivity",
        "scope_conflict",
        "over_budget",
    }


def test_spec_example_reason_irrelevant_is_verbatim() -> None:
    # 13 §5 output example uses "irrelevant" — carried verbatim.
    assert ContextExclusionReason.IRRELEVANT.value == "irrelevant"


# --- 13 §5 output example -------------------------------------------------------


def test_spec_output_example_validates() -> None:
    """The 13 §5 output example shape validates field-for-field."""
    memory_id = uuid4()
    composed = ComposedContext.model_validate(
        {
            "context_blocks": [
                {
                    "type": "preference",
                    "content": "User prefers Arabic.",
                    "source": "memory:123",
                    "confidence": 0.92,
                }
            ],
            "excluded": [{"reason": "irrelevant", "memory_id": str(memory_id)}],
        }
    )
    block = composed.context_blocks[0]
    assert block.type is ContextBlockType.PREFERENCE
    assert block.confidence == 0.92
    assert composed.excluded[0].memory_id == memory_id


def test_block_confidence_optional_and_bounded() -> None:
    block = ContextBlock(type=ContextBlockType.ROLE, content="x", source="role:1")
    assert block.confidence is None
    with pytest.raises(ValidationError):
        ContextBlock(
            type=ContextBlockType.PREFERENCE,
            content="x",
            source="memory:1",
            confidence=1.5,
        )


def test_unknown_block_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ContextBlock.model_validate({"type": "skill", "content": "x", "source": "skill:1"})


def test_unknown_exclusion_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        ExcludedMemory.model_validate({"reason": "vibes", "memory_id": str(uuid4())})


def test_empty_context_defaults() -> None:
    composed = ComposedContext()
    assert composed.context_blocks == []
    assert composed.excluded == []


# --- Input contract --------------------------------------------------------------


def test_request_safe_defaults() -> None:
    """Security-policy default is DENY high sensitivity (20 §4 posture)."""
    request = ContextComposeRequest(tenant_id=uuid4(), user_id=uuid4(), ask="hi")
    assert request.allow_high_sensitivity is False
    assert request.role_id is None
    assert request.conversation_id is None
    assert request.relevant_keys is None
    assert request.context_budget > 0


def test_request_rejects_empty_ask_and_zero_budget() -> None:
    with pytest.raises(ValidationError):
        ContextComposeRequest(tenant_id=uuid4(), user_id=uuid4(), ask="")
    with pytest.raises(ValidationError):
        ContextComposeRequest(tenant_id=uuid4(), user_id=uuid4(), ask="hi", context_budget=0)


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ContextComposeRequest.model_validate(
            {
                "tenant_id": str(uuid4()),
                "user_id": str(uuid4()),
                "ask": "hi",
                "semantic_query": "not in this slice",
            }
        )


def test_contract_instances_frozen() -> None:
    block = ContextBlock(type=ContextBlockType.ASK, content="x", source="request")
    with pytest.raises(ValidationError):
        block.content = "y"  # type: ignore[misc]
