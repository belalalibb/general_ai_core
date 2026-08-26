"""Conversation + memory store tests (41 §45; 03 §3; 13 §7/§8/§9; 20 §6).

Covers: append-only history with ordering + tail-limit, tenant isolation
with anti-enumeration NotFound, upsert identity with evidence accumulation,
scope/recency/confidence retrieval filters, cross-user memory exclusion
(13 §7), secret-like rejection at the port boundary (13 §7), and deletion
(13 §8). Hermetic: in-memory only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import MemoryItem, MemoryScope, MemorySensitivity
from core.memory import (
    ConversationNotFound,
    EmptyMessage,
    InMemoryConversationStore,
    InMemoryMemoryStore,
    MemoryItemNotFound,
    MemoryStoreError,
    SecretLikeMemoryRejected,
)

TENANT_A = uuid4()
TENANT_B = uuid4()
USER_1 = uuid4()
USER_2 = uuid4()

NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)


def make_conversation(
    tenant_id: UUID = TENANT_A, user_id: UUID = USER_1, title: str = "chat"
) -> Conversation:
    return Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        title=title,
        status=ConversationStatus.ACTIVE,
    )


def make_message(
    conversation_id: UUID,
    content: str = "hello",
    role: MessageRole = MessageRole.USER,
    created_at: datetime = NOW,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=created_at,
    )


def make_memory(
    tenant_id: UUID = TENANT_A,
    user_id: UUID | None = USER_1,
    scope: MemoryScope = MemoryScope.TENANT,
    key: str = "preferred_language",
    value: object = "ar",
    confidence: float = 0.9,
    last_seen: datetime = NOW,
    expires_at: datetime | None = None,
    sensitivity: MemorySensitivity = MemorySensitivity.LOW,
) -> MemoryItem:
    return MemoryItem(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        scope=scope,
        key=key,
        value=value,
        source="test",
        confidence=confidence,
        evidence_count=1,
        last_seen=last_seen,
        expires_at=expires_at,
        sensitivity=sensitivity,
    )


@pytest.fixture()
def conversations() -> InMemoryConversationStore:
    return InMemoryConversationStore()


@pytest.fixture()
def memories() -> InMemoryMemoryStore:
    return InMemoryMemoryStore()


# --- conversation lifecycle -------------------------------------------------------


class TestConversationLifecycle:
    def test_create_and_get(self, conversations: InMemoryConversationStore) -> None:
        conv = make_conversation()
        conversations.create_conversation(conv)
        assert conversations.get_conversation(TENANT_A, conv.id) == conv

    def test_duplicate_create_rejected(self, conversations: InMemoryConversationStore) -> None:
        conv = make_conversation()
        conversations.create_conversation(conv)
        with pytest.raises(ValueError):
            conversations.create_conversation(conv)

    def test_set_status_archives(self, conversations: InMemoryConversationStore) -> None:
        conv = make_conversation()
        conversations.create_conversation(conv)
        updated = conversations.set_status(TENANT_A, conv.id, ConversationStatus.ARCHIVED)
        assert updated.status is ConversationStatus.ARCHIVED
        assert (
            conversations.get_conversation(TENANT_A, conv.id).status is ConversationStatus.ARCHIVED
        )

    def test_list_newest_first_scoped_to_user(
        self, conversations: InMemoryConversationStore
    ) -> None:
        first = make_conversation(user_id=USER_1, title="first")
        second = make_conversation(user_id=USER_1, title="second")
        other_user = make_conversation(user_id=USER_2, title="other")
        conversations.create_conversation(first)
        conversations.create_conversation(other_user)
        conversations.create_conversation(second)
        listed = conversations.list_conversations(TENANT_A, USER_1)
        assert [c.title for c in listed] == ["second", "first"]


# --- append-only history ----------------------------------------------------------


class TestMessageHistory:
    def test_append_and_read_in_order(self, conversations: InMemoryConversationStore) -> None:
        conv = make_conversation()
        conversations.create_conversation(conv)
        msgs = [make_message(conv.id, content=f"m{i}") for i in range(3)]
        for msg in msgs:
            conversations.append_message(TENANT_A, msg)
        history = conversations.get_history(TENANT_A, conv.id)
        assert [m.content for m in history] == ["m0", "m1", "m2"]

    def test_limit_keeps_newest_tail_in_order(
        self, conversations: InMemoryConversationStore
    ) -> None:
        """Context windows want the tail of history, oldest-first within it."""
        conv = make_conversation()
        conversations.create_conversation(conv)
        for i in range(5):
            conversations.append_message(TENANT_A, make_message(conv.id, f"m{i}"))
        tail = conversations.get_history(TENANT_A, conv.id, limit=2)
        assert [m.content for m in tail] == ["m3", "m4"]

    def test_append_to_missing_conversation_raises(
        self, conversations: InMemoryConversationStore
    ) -> None:
        with pytest.raises(ConversationNotFound):
            conversations.append_message(TENANT_A, make_message(uuid4()))

    def test_empty_message_rejected(self, conversations: InMemoryConversationStore) -> None:
        """A message with no content and no attachments is meaningless."""
        conv = make_conversation()
        conversations.create_conversation(conv)
        with pytest.raises(EmptyMessage):
            conversations.append_message(TENANT_A, make_message(conv.id, content=""))

    def test_attachment_only_message_allowed(
        self, conversations: InMemoryConversationStore
    ) -> None:
        """Tool turns may carry only attachments (03 §3 posture)."""
        conv = make_conversation()
        conversations.create_conversation(conv)
        msg = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role=MessageRole.TOOL,
            content="",
            attachments=[{"artifact_id": str(uuid4())}],
            created_at=NOW,
        )
        conversations.append_message(TENANT_A, msg)
        assert len(conversations.get_history(TENANT_A, conv.id)) == 1


# --- tenant isolation (20 §6) -------------------------------------------------------


class TestConversationTenantIsolation:
    def test_cross_tenant_get_raises_same_not_found(
        self, conversations: InMemoryConversationStore
    ) -> None:
        """Anti-enumeration: foreign-tenant probe == absent record."""
        conv = make_conversation(tenant_id=TENANT_A)
        conversations.create_conversation(conv)
        with pytest.raises(ConversationNotFound):
            conversations.get_conversation(TENANT_B, conv.id)
        with pytest.raises(ConversationNotFound):
            conversations.get_conversation(TENANT_B, uuid4())

    def test_cross_tenant_history_and_append_denied(
        self, conversations: InMemoryConversationStore
    ) -> None:
        conv = make_conversation(tenant_id=TENANT_A)
        conversations.create_conversation(conv)
        with pytest.raises(ConversationNotFound):
            conversations.get_history(TENANT_B, conv.id)
        with pytest.raises(ConversationNotFound):
            conversations.append_message(TENANT_B, make_message(conv.id))

    def test_listing_never_crosses_tenants(self, conversations: InMemoryConversationStore) -> None:
        conversations.create_conversation(make_conversation(tenant_id=TENANT_A))
        assert conversations.list_conversations(TENANT_B, USER_1) == ()


# --- memory upsert identity ---------------------------------------------------------


class TestMemoryUpsert:
    def test_first_write_persists_as_is(self, memories: InMemoryMemoryStore) -> None:
        item = make_memory()
        stored = memories.upsert(item)
        assert stored == item
        assert memories.get(TENANT_A, item.id) == item

    def test_repeat_write_updates_in_place_and_accumulates_evidence(
        self, memories: InMemoryMemoryStore
    ) -> None:
        """(tenant, user, scope, key) is the logical identity (13 §6)."""
        first = make_memory(value="ar", confidence=0.7)
        memories.upsert(first)
        second = make_memory(value="en", confidence=0.95, last_seen=NOW + timedelta(hours=1))
        updated = memories.upsert(second)
        assert updated.id == first.id  # original id kept
        assert updated.value == "en"
        assert updated.confidence == 0.95
        assert updated.evidence_count == 2
        assert updated.last_seen == NOW + timedelta(hours=1)

    def test_different_users_are_distinct_identities(self, memories: InMemoryMemoryStore) -> None:
        a = memories.upsert(make_memory(user_id=USER_1))
        b = memories.upsert(make_memory(user_id=USER_2))
        assert a.id != b.id
        assert memories.get(TENANT_A, a.id).user_id == USER_1
        assert memories.get(TENANT_A, b.id).user_id == USER_2


# --- memory retrieval filters (13 §9 subset) ----------------------------------------


class TestMemoryQuery:
    def test_recency_ordering(self, memories: InMemoryMemoryStore) -> None:
        old = memories.upsert(make_memory(key="k_old", last_seen=NOW - timedelta(days=1)))
        new = memories.upsert(make_memory(key="k_new", last_seen=NOW))
        results = memories.query(TENANT_A, user_id=USER_1)
        assert [m.id for m in results] == [new.id, old.id]

    def test_scope_and_key_filters(self, memories: InMemoryMemoryStore) -> None:
        memories.upsert(make_memory(scope=MemoryScope.TENANT, key="lang"))
        target = memories.upsert(make_memory(scope=MemoryScope.PROJECT, key="tone"))
        results = memories.query(TENANT_A, user_id=USER_1, scope=MemoryScope.PROJECT, key="tone")
        assert [m.id for m in results] == [target.id]

    def test_min_confidence_excludes_low(self, memories: InMemoryMemoryStore) -> None:
        """13 §9: low-confidence memory excluded from context."""
        memories.upsert(make_memory(key="weak", confidence=0.2))
        strong = memories.upsert(make_memory(key="strong", confidence=0.9))
        results = memories.query(TENANT_A, user_id=USER_1, min_confidence=0.5)
        assert [m.id for m in results] == [strong.id]

    def test_expired_excluded_by_default(self, memories: InMemoryMemoryStore) -> None:
        expired = memories.upsert(make_memory(key="stale", expires_at=NOW - timedelta(days=1)))
        live = memories.upsert(make_memory(key="fresh"))
        default = memories.query(TENANT_A, user_id=USER_1)
        assert [m.id for m in default] == [live.id]
        with_expired = memories.query(TENANT_A, user_id=USER_1, include_expired=True)
        assert {m.id for m in with_expired} == {live.id, expired.id}

    def test_tenant_shared_visible_user_owned_private(self, memories: InMemoryMemoryStore) -> None:
        """13 §7: never another user's memory; shared (user_id=None) is fine."""
        shared = memories.upsert(make_memory(user_id=None, key="shared"))
        mine = memories.upsert(make_memory(user_id=USER_1, key="mine"))
        memories.upsert(make_memory(user_id=USER_2, key="theirs"))
        results = memories.query(TENANT_A, user_id=USER_1)
        assert {m.id for m in results} == {shared.id, mine.id}

    def test_query_never_crosses_tenants(self, memories: InMemoryMemoryStore) -> None:
        memories.upsert(make_memory(tenant_id=TENANT_A))
        assert memories.query(TENANT_B, user_id=USER_1) == ()


# --- memory deletion + anti-enumeration ---------------------------------------------


class TestMemoryDeletion:
    def test_delete_removes_item_and_logical_key(self, memories: InMemoryMemoryStore) -> None:
        """13 §8: deletion respected — and the logical slot is freed."""
        item = memories.upsert(make_memory())
        memories.delete(TENANT_A, item.id)
        with pytest.raises(MemoryItemNotFound):
            memories.get(TENANT_A, item.id)
        # Re-upserting the same logical key starts fresh (evidence_count=1).
        fresh = memories.upsert(make_memory())
        assert fresh.evidence_count == 1

    def test_cross_tenant_delete_and_get_raise_same_not_found(
        self, memories: InMemoryMemoryStore
    ) -> None:
        item = memories.upsert(make_memory(tenant_id=TENANT_A))
        with pytest.raises(MemoryItemNotFound):
            memories.get(TENANT_B, item.id)
        with pytest.raises(MemoryItemNotFound):
            memories.delete(TENANT_B, item.id)
        # Still present for the rightful tenant.
        assert memories.get(TENANT_A, item.id).id == item.id


# --- secret rejection (13 §7) --------------------------------------------------------


class TestSecretRejection:
    @pytest.mark.parametrize(
        "key",
        ["api_key", "MY_PASSWORD", "openai_apikey", "db_credentials", "client_secret"],
    )
    def test_secret_like_keys_rejected(self, memories: InMemoryMemoryStore, key: str) -> None:
        with pytest.raises(SecretLikeMemoryRejected):
            memories.upsert(make_memory(key=key, value="anything"))

    @pytest.mark.parametrize(
        "value",
        [
            "Bearer abcdefghijklmnop1234",
            "-----BEGIN RSA PRIVATE KEY-----",
            "AKIAIOSFODNN7EXAMPLE",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig",
            "sk-abcdefghijklmnop1234",
        ],
    )
    def test_secret_like_values_rejected(self, memories: InMemoryMemoryStore, value: str) -> None:
        with pytest.raises(SecretLikeMemoryRejected):
            memories.upsert(make_memory(key="note", value=value))

    def test_error_message_carries_indicator_not_value(self, memories: InMemoryMemoryStore) -> None:
        """No secrets in logs (20 §5): the offending VALUE never appears."""
        secret_value = "sk-abcdefghijklmnop1234"
        with pytest.raises(SecretLikeMemoryRejected) as exc_info:
            memories.upsert(make_memory(key="note", value=secret_value))
        assert secret_value not in str(exc_info.value)
        assert exc_info.value.indicator

    def test_rejection_is_a_memory_store_error(self, memories: InMemoryMemoryStore) -> None:
        with pytest.raises(MemoryStoreError):
            memories.upsert(make_memory(key="password"))

    def test_benign_preference_accepted(self, memories: InMemoryMemoryStore) -> None:
        item = memories.upsert(make_memory(key="preferred_language", value="ar"))
        assert item.value == "ar"
