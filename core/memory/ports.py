"""Conversation-history and memory store ports (MVP Phase 6, 41 §45).

Spec anchors:

- 41 §45 deliverables: "conversation history" + "basic user preferences".
- 03 §3 entities: Conversation / Message / MemoryItem (contract layer).
- 13 §7 memory safety (binds at this boundary): no cross-tenant leakage,
  no using one user's memory for another, NO SECRETS AS MEMORY.
- 13 §8 memory visibility: view/edit/delete preferences — the CRUD surface
  below is what makes that possible later.
- 20 §6 tenant isolation: every operation is tenant-scoped; ``tenant_id``
  is an explicit parameter on every method, not ambient state (the
  core/storage pattern carried verbatim).

Design decisions (recorded here, mirroring the storage-port pattern):

- Append-only history: messages are appended, never edited or deleted in
  the MVP — history is an audit-grade record of what the model actually
  saw (12 §10 idempotency posture leans on stable history).
- Reads return immutable contract objects; ordering is guaranteed
  (messages by created_at then insertion order; deterministic, testable).
- Memory writes are UPSERTS keyed by (tenant, user, scope, key): a
  preference has one current value per owner+scope; the store bumps
  evidence_count/last_seen on repeat writes instead of duplicating rows
  (13 §6 "repeated evidence exists" needs that count).
- Secret-like keys/values are REJECTED at this boundary
  (SecretLikeMemoryRejected, 13 §7) — an explicit design duty recorded in
  the Phase 6 slicing decision (R044).
- No semantic-similarity retrieval on this port: MVP retrieval filters are
  scope/recency/confidence (R044 scope boundary (c)); the vector-backed
  search arrives with the pgvector binding behind the same port surface.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.contracts.conversation import Conversation, ConversationStatus, Message
from core.contracts.memory import MemoryItem, MemoryScope


class ConversationStorePort(Protocol):
    """Tenant-scoped conversation + message history seam (03 §3; 41 §45)."""

    def create_conversation(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation (id supplied by the caller)."""
        ...

    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        """Fetch a conversation; raises ``ConversationNotFound`` (also for
        cross-tenant probes — anti-enumeration, 20 §6)."""
        ...

    def set_status(
        self, tenant_id: UUID, conversation_id: UUID, status: ConversationStatus
    ) -> Conversation:
        """Transition active|archived (03 §3 closed set)."""
        ...

    def list_conversations(self, tenant_id: UUID, user_id: UUID) -> tuple[Conversation, ...]:
        """List the user's conversations within the tenant (newest first)."""
        ...

    def append_message(self, tenant_id: UUID, message: Message) -> Message:
        """Append a message to history (append-only; no edit/delete in MVP).

        Raises ``ConversationNotFound`` for absent/foreign conversations and
        ``EmptyMessage`` when neither content nor attachments are present.
        """
        ...

    def get_history(
        self, tenant_id: UUID, conversation_id: UUID, limit: int | None = None
    ) -> tuple[Message, ...]:
        """Return messages oldest-first; ``limit`` keeps the NEWEST ``limit``
        messages (context windows want the tail, not the head)."""
        ...


class MemoryStorePort(Protocol):
    """Tenant-scoped memory / preference seam (03 §3 MemoryItem; 13 §3/§7/§8)."""

    def upsert(self, item: MemoryItem) -> MemoryItem:
        """Write a memory item, keyed by (tenant, user, scope, key).

        Repeat writes to the same logical key update value/confidence,
        increment evidence_count, and refresh last_seen — preserving the
        original item id. Raises ``SecretLikeMemoryRejected`` when the key
        or value looks like secret material (13 §7).
        """
        ...

    def get(self, tenant_id: UUID, memory_id: UUID) -> MemoryItem:
        """Fetch by id; raises ``MemoryItemNotFound`` (also cross-tenant)."""
        ...

    def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: MemoryScope | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]:
        """Filtered retrieval (13 §9 scope/recency/confidence subset).

        Returns tenant-shared items (user_id=None) plus — when ``user_id``
        is given — that user's items; NEVER another user's items (13 §7).
        Expired items are excluded unless explicitly requested. Ordering:
        most recently seen first (recency, 13 §9).
        """
        ...

    def delete(self, tenant_id: UUID, memory_id: UUID) -> None:
        """Delete a memory item (13 §8 'memory deletion respected')."""
        ...
