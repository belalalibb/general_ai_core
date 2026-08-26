"""Contract tests: conversation + memory contracts (03 §3; 13 §3/§4).

Verifies closed sets match 03 §3 verbatim, entity shapes validate
field-for-field, unknown fields are rejected (deny-by-default), the 13 §4
scope-priority chain is encoded exactly (Conversation > Project >
Workspace > Tenant > Global, ROLE deliberately absent), confidence bounds
hold, no secret-bearing field exists on any contract (20 §5), and
instances are frozen value objects.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import (
    SCOPE_PRIORITY,
    MemoryItem,
    MemoryScope,
    MemorySensitivity,
)

# --- Closed sets exactly as written in 03 §3 ----------------------------------


def test_conversation_status_set_matches_spec() -> None:
    # 03 §3: active|archived
    assert {s.value for s in ConversationStatus} == {"active", "archived"}


def test_message_role_set_matches_spec() -> None:
    # 03 §3: user|assistant|system|tool
    assert {r.value for r in MessageRole} == {"user", "assistant", "system", "tool"}


def test_memory_scope_set_matches_spec() -> None:
    # 03 §3: global|tenant|workspace|project|conversation|role
    assert {s.value for s in MemoryScope} == {
        "global",
        "tenant",
        "workspace",
        "project",
        "conversation",
        "role",
    }


def test_memory_sensitivity_set_matches_spec() -> None:
    # 13 §3 sensitivity ladder: low|medium|high
    assert {s.value for s in MemorySensitivity} == {"low", "medium", "high"}


def test_scope_priority_chain_matches_13_s4_verbatim() -> None:
    """13 §4: Conversation > Project > Workspace > Tenant > Global.

    ROLE is deliberately absent from the conflict chain (module docstring
    records the decision); User rank is encoded via user_id ownership.
    """
    assert SCOPE_PRIORITY == (
        MemoryScope.CONVERSATION,
        MemoryScope.PROJECT,
        MemoryScope.WORKSPACE,
        MemoryScope.TENANT,
        MemoryScope.GLOBAL,
    )
    assert MemoryScope.ROLE not in SCOPE_PRIORITY


# --- Documented shapes validate ------------------------------------------------


def _conversation_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "title": "planning chat",
        "status": "active",
    }
    payload.update(overrides)
    return payload


def _message_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "role": "user",
        "content": "hello",
        "created_at": "2026-08-26T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _memory_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "scope": "tenant",
        "key": "preferred_language",
        "value": "ar",
        "source": "explicit_setting",
        "confidence": 0.92,
        "evidence_count": 3,
        "last_seen": "2026-08-26T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_conversation_shape_validates_field_for_field() -> None:
    conv = Conversation.model_validate(_conversation_payload())
    assert conv.status is ConversationStatus.ACTIVE
    assert conv.project_id is None  # optional per 03 §3


def test_message_shape_validates_field_for_field() -> None:
    msg = Message.model_validate(_message_payload())
    assert msg.role is MessageRole.USER
    assert msg.attachments == []
    assert msg.created_at.tzinfo is not None


def test_memory_item_shape_validates_13_s3_example() -> None:
    """13 §3 example: preferred_language="ar", confidence 0.92, low."""
    item = MemoryItem.model_validate(_memory_payload())
    assert item.value == "ar"
    assert item.confidence == 0.92
    assert item.sensitivity is MemorySensitivity.LOW  # default per 13 §3
    assert item.expires_at is None


def test_memory_value_accepts_structured_json() -> None:
    item = MemoryItem.model_validate(_memory_payload(value={"tone": "formal", "emoji": False}))
    assert item.value == {"tone": "formal", "emoji": False}


def test_memory_user_id_none_means_tenant_shared() -> None:
    item = MemoryItem.model_validate(_memory_payload(user_id=None))
    assert item.user_id is None


# --- Deny-by-default: unknown fields / values rejected ---------------------------


@pytest.mark.parametrize(
    ("model", "payload_factory"),
    [
        (Conversation, _conversation_payload),
        (Message, _message_payload),
        (MemoryItem, _memory_payload),
    ],
)
def test_unknown_fields_rejected(model: Any, payload_factory: Any) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload_factory(unexpected_field="x"))


def test_unknown_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Conversation.model_validate(_conversation_payload(status="deleted"))


def test_unknown_role_rejected() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate(_message_payload(role="moderator"))


def test_unknown_scope_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryItem.model_validate(_memory_payload(scope="user"))  # not a 03 §3 scope


def test_confidence_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        MemoryItem.model_validate(_memory_payload(confidence=1.5))
    with pytest.raises(ValidationError):
        MemoryItem.model_validate(_memory_payload(confidence=-0.1))


def test_negative_evidence_count_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryItem.model_validate(_memory_payload(evidence_count=-1))


# --- Security posture (20 §5) ----------------------------------------------------


def test_no_secret_bearing_fields_on_any_contract() -> None:
    """Credential handling stays in the secret-store port — never here."""
    forbidden = {"token", "password", "secret", "credential", "api_key"}
    for model in (Conversation, Message, MemoryItem):
        for field_name in model.model_fields:
            assert not any(bad in field_name.lower() for bad in forbidden), (
                f"{model.__name__}.{field_name} looks secret-bearing"
            )


# --- Frozen value objects ----------------------------------------------------------


def test_instances_are_frozen() -> None:
    conv = Conversation.model_validate(_conversation_payload())
    item = MemoryItem.model_validate(_memory_payload())
    with pytest.raises(ValidationError):
        conv.status = ConversationStatus.ARCHIVED  # type: ignore[misc]
    with pytest.raises(ValidationError):
        item.confidence = 0.1  # type: ignore[misc]
