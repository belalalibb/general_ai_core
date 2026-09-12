"""Durable memory + conversation bindings — R179 4.5 (F-R179-01 / F-R179-03).

Measured (4.4, ``evidence/r179/durability_measured_before.json``): knowledge
injected into memory died with the process (memory_blocks 1→0) and the
execute path with ``conversation_id`` failed 500 in the durable profile —
the ``executions.conversation_id`` FK points at the ``conversations``
table while the runtime composed an ``InMemoryConversationStore``.

Root cause is a COMPOSITION seam, not a missing capability: the Postgres
repositories (``infrastructure/db/repositories/{memory,conversations}.py``,
tables from migrations 0002 / 0007) have been built by
``DatabaseBindings`` since V1 and never consumed. This module adapts them
onto the SAME structural ports the runtime already speaks
(``core/memory/ports.py``) — verbatim the ``workspaces.py`` posture:

- **Loop affinity**: asyncpg pools are bound to the AsyncBridge loop;
  every call crosses via ``bridge.run`` (the ports are synchronous — the
  composer, the preference learner and the repo_map tool call them from
  worker threads / the request path exactly as they call the in-memory
  binding today).
- **No translation needed**: both repositories raise the core-owned
  refusals (``MemoryItemNotFound``, ``ConversationNotFound``,
  ``EmptyMessage``, ``SecretLikeMemoryRejected``) — the bridge re-raises
  them unchanged, so route mappings are untouched.
- **Profile truth**: bound ONLY in the durable branch (``DATABASE_URL``
  set). The in-memory profile keeps ``InMemory*`` byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.conversation import Conversation, ConversationStatus, Message
from core.contracts.memory import MemoryItem, MemoryScope
from infrastructure.db.repositories.conversations import PostgresConversationRepository
from infrastructure.db.repositories.memory import PostgresMemoryRepository

__all__ = [
    "DurableConversationStore",
    "DurableMemoryStore",
    "build_durable_memory_stores",
]


@dataclass(frozen=True)
class DurableMemoryStore:
    """MemoryStorePort over the EXISTING Postgres repository (bridged)."""

    repository: PostgresMemoryRepository
    bridge: AsyncBridge

    def upsert(self, item: MemoryItem) -> MemoryItem:
        return self.bridge.run(self.repository.upsert(item))

    def get(self, tenant_id: UUID, memory_id: UUID) -> MemoryItem:
        return self.bridge.run(self.repository.get(tenant_id, memory_id))

    def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: MemoryScope | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]:
        return self.bridge.run(
            self.repository.query(
                tenant_id,
                user_id=user_id,
                scope=scope,
                key=key,
                min_confidence=min_confidence,
                include_expired=include_expired,
            )
        )

    def delete(self, tenant_id: UUID, memory_id: UUID) -> None:
        self.bridge.run(self.repository.delete(tenant_id, memory_id))


@dataclass(frozen=True)
class DurableConversationStore:
    """ConversationStorePort over the EXISTING Postgres repository (bridged)."""

    repository: PostgresConversationRepository
    bridge: AsyncBridge

    def create_conversation(self, conversation: Conversation) -> Conversation:
        return self.bridge.run(self.repository.create_conversation(conversation))

    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        return self.bridge.run(self.repository.get_conversation(tenant_id, conversation_id))

    def set_status(
        self, tenant_id: UUID, conversation_id: UUID, status: ConversationStatus
    ) -> Conversation:
        return self.bridge.run(self.repository.set_status(tenant_id, conversation_id, status))

    def list_conversations(self, tenant_id: UUID, user_id: UUID) -> tuple[Conversation, ...]:
        return self.bridge.run(self.repository.list_conversations(tenant_id, user_id))

    def append_message(self, tenant_id: UUID, message: Message) -> Message:
        return self.bridge.run(self.repository.append_message(tenant_id, message))

    def get_history(
        self, tenant_id: UUID, conversation_id: UUID, limit: int | None = None
    ) -> tuple[Message, ...]:
        return self.bridge.run(self.repository.get_history(tenant_id, conversation_id, limit=limit))


def build_durable_memory_stores(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> tuple[DurableMemoryStore, DurableConversationStore]:
    """Adapt the ALREADY-COMPOSED repositories onto the runtime ports —
    same builder shape as ``build_durable_workspace_stores`` (one pattern)."""
    return (
        DurableMemoryStore(repository=bindings.memory, bridge=bridge),
        DurableConversationStore(repository=bindings.conversations, bridge=bridge),
    )
