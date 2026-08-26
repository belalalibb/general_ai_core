"""Conversation / Message contracts (MVP Phase 6, 41 §45).

Contract authority: docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md
§3 (Conversation / Memory). Carried exactly — no state value added, renamed,
or dropped.

Notes carried from spec:

- 03 §8 relationship rule: "Execution belongs to Tenant and optionally
  Conversation/Project" — the existing ExecutionRecord.conversation_id
  (core/contracts/execution.py) points at :class:`Conversation` here.
- ``Message.role`` is the CHAT-TURN role (user|assistant|system|tool,
  03 §3 verbatim) — distinct from the 03 §6 Role ENTITY (system roles),
  which lives in its own Phase 6 slice. The name collision comes from the
  spec; the two types never mix.
- ``Message.content`` is "text/json" in 03 §3: modeled as ``str`` for the
  text form with structured payloads carried on ``attachments``
  (array of JSON objects, 03 §3) — the same posture as the execute
  contract's input block (10 §2).

Security posture: message content is user data, never secret material —
credential handling stays in the secret-store port (20 §5). No token,
password, or credential field exists on any conversation contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Closed sets (03 §3, verbatim) --------------------------------------------


class ConversationStatus(StrEnum):
    """Conversation status (03 §3) — closed set, verbatim."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    """Chat-turn role on a message (03 §3) — closed set, verbatim.

    NOT the 03 §6 Role entity (system roles); this is who authored the turn.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# --- Entities (03 §3, field-for-field) ------------------------------------------


class Conversation(ContractModel):
    """Conversation entity (03 §3, field-for-field)."""

    id: UUID
    tenant_id: UUID
    user_id: UUID
    project_id: UUID | None = None
    title: BoundedStr
    status: ConversationStatus


class Message(ContractModel):
    """Message entity (03 §3, field-for-field).

    ``content`` may be empty (a tool turn can carry only attachments), but
    the field itself is required — a message with no content and no
    attachments is meaningless and the store rejects it.
    """

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str = Field(max_length=200_000)
    attachments: list[JsonObject] = Field(default_factory=list)
    created_at: datetime
