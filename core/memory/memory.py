"""In-memory conversation + memory stores (MVP Phase 6 bindings, 41 §45).

Satisfy :class:`~core.memory.ports.ConversationStorePort` and
:class:`~core.memory.ports.MemoryStorePort` against process memory — the
same skeleton discipline as ``InMemoryObjectStorage`` / ``InMemoryUsage-
Accounting``: durable persistence arrives later behind the same ports.

Isolation mechanics (20 §6): physical keying by ``(tenant_id, id)``; a
foreign tenant's record can never be addressed, and probing it raises the
same NotFound as a truly absent record.

Secret rejection (13 §7): key/value screening uses the indicator list
below. This is a BOUNDARY GUARD, not a scanner — its job is to refuse the
obvious ("api_key", "password", bearer tokens, PEM blocks), loudly, so a
policy failure upstream cannot silently become persisted secret material.
"""

from __future__ import annotations

import re
from uuid import UUID

from core.contracts.base import utc_now
from core.contracts.conversation import Conversation, ConversationStatus, Message
from core.contracts.memory import MemoryItem, MemoryScope
from core.memory.errors import (
    ConversationNotFound,
    EmptyMessage,
    MemoryItemNotFound,
    SecretLikeMemoryRejected,
)

# --- 13 §7 secret screening ----------------------------------------------------

# Key substrings that indicate credential material (case-insensitive).
_SECRET_KEY_INDICATORS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "credential",
    "client_secret",
)

# Value patterns that indicate credential material.
_SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9\-_.~+/]{16,}", re.IGNORECASE)),
    ("PEM block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT-like token", re.compile(r"\beyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.")),
    ("long opaque token", re.compile(r"\b(?:sk|pk|ghp|gho|xoxb)-[A-Za-z0-9\-_]{16,}\b")),
)


def _screen_secret_like(key: str, value: object) -> None:
    """Raise :class:`SecretLikeMemoryRejected` on secret-looking key/value."""
    key_lower = key.lower()
    for indicator in _SECRET_KEY_INDICATORS:
        if indicator in key_lower:
            raise SecretLikeMemoryRejected(f"key contains '{indicator}'")
    text = value if isinstance(value, str) else repr(value)
    for label, pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            raise SecretLikeMemoryRejected(f"value matches {label}")


# --- Conversation store ----------------------------------------------------------


class InMemoryConversationStore:
    """Process-memory implementation of ``ConversationStorePort``."""

    def __init__(self) -> None:
        self._conversations: dict[tuple[UUID, UUID], Conversation] = {}
        # Insertion-ordered message log per conversation (append-only).
        self._messages: dict[tuple[UUID, UUID], list[Message]] = {}
        self._insert_seq = 0  # creation order for newest-first listing
        self._creation_order: dict[tuple[UUID, UUID], int] = {}

    def create_conversation(self, conversation: Conversation) -> Conversation:
        key = (conversation.tenant_id, conversation.id)
        if key in self._conversations:
            raise ValueError(f"conversation already exists: {conversation.id}")
        self._conversations[key] = conversation
        self._messages[key] = []
        self._insert_seq += 1
        self._creation_order[key] = self._insert_seq
        return conversation

    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        conv = self._conversations.get((tenant_id, conversation_id))
        if conv is None:
            raise ConversationNotFound(conversation_id)
        return conv

    def set_status(
        self, tenant_id: UUID, conversation_id: UUID, status: ConversationStatus
    ) -> Conversation:
        key = (tenant_id, conversation_id)
        conv = self._conversations.get(key)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        updated = conv.model_copy(update={"status": status})
        self._conversations[key] = updated
        return updated

    def list_conversations(self, tenant_id: UUID, user_id: UUID) -> tuple[Conversation, ...]:
        matches = [
            (self._creation_order[key], conv)
            for key, conv in self._conversations.items()
            if key[0] == tenant_id and conv.user_id == user_id
        ]
        matches.sort(key=lambda pair: pair[0], reverse=True)  # newest first
        return tuple(conv for _, conv in matches)

    def append_message(self, tenant_id: UUID, message: Message) -> Message:
        key = (tenant_id, message.conversation_id)
        if key not in self._conversations:
            raise ConversationNotFound(message.conversation_id)
        if not message.content and not message.attachments:
            raise EmptyMessage()
        self._messages[key].append(message)
        return message

    def get_history(
        self, tenant_id: UUID, conversation_id: UUID, limit: int | None = None
    ) -> tuple[Message, ...]:
        key = (tenant_id, conversation_id)
        if key not in self._conversations:
            raise ConversationNotFound(conversation_id)
        log = self._messages[key]
        if limit is not None and limit >= 0:
            log = log[len(log) - min(limit, len(log)) :]  # newest `limit`, in order
        return tuple(log)


# --- Memory store -----------------------------------------------------------------


class InMemoryMemoryStore:
    """Process-memory implementation of ``MemoryStorePort``.

    Upsert identity: one current value per logical key
    ``(tenant_id, user_id, scope, key)`` — repeat writes update in place,
    bump evidence_count, refresh last_seen, and keep the original item id
    (13 §6 needs the accumulated evidence count).
    """

    def __init__(self) -> None:
        self._items: dict[tuple[UUID, UUID], MemoryItem] = {}
        self._logical: dict[tuple[UUID, UUID | None, MemoryScope, str], UUID] = {}

    def upsert(self, item: MemoryItem) -> MemoryItem:
        _screen_secret_like(item.key, item.value)
        logical = (item.tenant_id, item.user_id, item.scope, item.key)
        existing_id = self._logical.get(logical)
        if existing_id is None:
            self._items[(item.tenant_id, item.id)] = item
            self._logical[logical] = item.id
            return item
        current = self._items[(item.tenant_id, existing_id)]
        updated = current.model_copy(
            update={
                "value": item.value,
                "source": item.source,
                "confidence": item.confidence,
                "evidence_count": current.evidence_count + 1,
                "last_seen": item.last_seen,
                "expires_at": item.expires_at,
                "sensitivity": item.sensitivity,
            }
        )
        self._items[(item.tenant_id, existing_id)] = updated
        return updated

    def get(self, tenant_id: UUID, memory_id: UUID) -> MemoryItem:
        item = self._items.get((tenant_id, memory_id))
        if item is None:
            raise MemoryItemNotFound(memory_id)
        return item

    def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: MemoryScope | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]:
        now = utc_now()
        results: list[MemoryItem] = []
        for (item_tenant, _), item in self._items.items():
            if item_tenant != tenant_id:
                continue
            # 13 §7: never another user's memory. Tenant-shared (None) always
            # eligible; user-owned only for that same user.
            if item.user_id is not None and item.user_id != user_id:
                continue
            if scope is not None and item.scope != scope:
                continue
            if key is not None and item.key != key:
                continue
            if item.confidence < min_confidence:
                continue
            if not include_expired and item.expires_at is not None and item.expires_at <= now:
                continue
            results.append(item)
        results.sort(key=lambda m: m.last_seen, reverse=True)  # recency, 13 §9
        return tuple(results)

    def delete(self, tenant_id: UUID, memory_id: UUID) -> None:
        item = self._items.pop((tenant_id, memory_id), None)
        if item is None:
            raise MemoryItemNotFound(memory_id)
        self._logical.pop((item.tenant_id, item.user_id, item.scope, item.key), None)
