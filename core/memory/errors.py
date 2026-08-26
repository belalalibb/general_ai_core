"""Conversation/memory store errors (closed, minimal set for the MVP ports).

Anti-enumeration posture carried from core/storage (20 §6): a conversation
or memory item that is absent and one that exists in ANOTHER tenant raise
the SAME NotFound error — cross-tenant probes must not distinguish
"absent" from "present elsewhere".
"""

from __future__ import annotations


class MemoryStoreError(Exception):
    """Base class for conversation/memory store failures."""


class ConversationNotFound(MemoryStoreError):
    """No conversation with this id within the caller's tenant scope.

    Deliberately also raised for conversations owned by ANOTHER tenant
    (anti-enumeration, 20 §6).
    """

    def __init__(self, conversation_id: object) -> None:
        super().__init__(f"conversation not found: {conversation_id}")


class MemoryItemNotFound(MemoryStoreError):
    """No memory item with this id within the caller's tenant scope.

    Deliberately also raised for items owned by ANOTHER tenant
    (anti-enumeration, 20 §6).
    """

    def __init__(self, memory_id: object) -> None:
        super().__init__(f"memory item not found: {memory_id}")


class EmptyMessage(MemoryStoreError):
    """Message carries neither content nor attachments (meaningless turn)."""

    def __init__(self) -> None:
        super().__init__("message must carry content or attachments")


class SecretLikeMemoryRejected(MemoryStoreError):
    """Memory write rejected: key or value looks like secret material.

    13 §7 (verbatim forbidden list): "storing secrets as memory". This is
    enforced AT THE PORT boundary — a secret that reaches the memory store
    is already a policy failure, so the store denies loudly instead of
    persisting it. The error message carries the matched INDICATOR only,
    never the offending value (no secrets in logs, 20 §5).
    """

    def __init__(self, indicator: str) -> None:
        super().__init__(
            f"memory write rejected: secret-like material detected ({indicator}); "
            "secrets must never be stored as memory (13 §7)"
        )
        self.indicator = indicator
