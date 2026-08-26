"""Conversation history + memory/preferences module (MVP Phase 6, 41 §45).

Port + in-memory fake pattern (same posture as core/storage, core/secrets,
core/usage): Core defines the seams; durable persistence binds behind the
same ports in a later phase (ADR-0002 toolchain stays in infrastructure).
"""

from core.memory.errors import (
    ConversationNotFound,
    EmptyMessage,
    MemoryStoreError,
    MemoryItemNotFound,
    SecretLikeMemoryRejected,
)
from core.memory.memory import InMemoryConversationStore, InMemoryMemoryStore
from core.memory.ports import ConversationStorePort, MemoryStorePort

__all__ = [
    "ConversationNotFound",
    "ConversationStorePort",
    "EmptyMessage",
    "InMemoryConversationStore",
    "InMemoryMemoryStore",
    "MemoryStoreError",
    "MemoryItemNotFound",
    "MemoryStorePort",
    "SecretLikeMemoryRejected",
]
