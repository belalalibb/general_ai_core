"""R179 4.5 — durable memory + conversation bindings (F-R179-01 / F-R179-03).

Measured first (evidence/r179/durability_measured.json): memory died with
the process and ``execute`` with ``conversation_id`` failed 500 in the
durable profile. Correction = composition seam only: the EXISTING Postgres
repositories are adapted onto the ports the runtime already speaks.

Hermetic proof in three parts (same shape as test_durable_sourcechange_pa3):

1. FAKE async repositories (dict-backed, mirroring the Postgres semantics
   that matter for the ports: logical-key upsert, tenant scoping, named
   refusals) drive the adapters over a REAL AsyncBridge — the adapters
   forward every port method verbatim and re-raise refusals unchanged.
2. Port parity: both adapters satisfy ``MemoryStorePort`` /
   ``ConversationStorePort`` structurally (the runtime's consumers —
   ContextComposer, PreferenceLearner, RepoMapper, create_app — are typed
   against the ports, never the in-memory classes).
3. Composition truth: ``apps/composition/runtime.py`` binds the durable
   stores ONLY in the ``DATABASE_URL`` branch and keeps the in-memory
   classes otherwise (the hermetic in-memory profile is byte-identical).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from apps.composition.memory import (
    DurableConversationStore,
    DurableMemoryStore,
    build_durable_memory_stores,
)
from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import MemoryItem, MemoryScope
from core.memory.errors import (
    ConversationNotFound,
    EmptyMessage,
    MemoryItemNotFound,
    SecretLikeMemoryRejected,
)
from core.memory.memory import (
    InMemoryConversationStore,
    InMemoryMemoryStore,
    _screen_secret_like,
)
from core.memory.ports import ConversationStorePort, MemoryStorePort

RUNTIME_PY = Path(__file__).resolve().parents[2] / "apps" / "composition" / "runtime.py"

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()


# --- fakes: the Postgres repository semantics the ports depend on -------------


class FakeMemoryRepository:
    """Mirrors PostgresMemoryRepository: secret screen BEFORE I/O, logical-key
    upsert preserving the ORIGINAL id + evidence increment, tenant scoping."""

    def __init__(self) -> None:
        self.rows: dict[UUID, MemoryItem] = {}

    async def upsert(self, item: MemoryItem) -> MemoryItem:
        _screen_secret_like(item.key, item.value)
        for existing in self.rows.values():
            if (existing.tenant_id, existing.user_id, existing.scope, existing.key) == (
                item.tenant_id,
                item.user_id,
                item.scope,
                item.key,
            ):
                merged = existing.model_copy(
                    update={
                        "value": item.value,
                        "confidence": item.confidence,
                        "evidence_count": existing.evidence_count + 1,
                        "last_seen": item.last_seen,
                    }
                )
                self.rows[existing.id] = merged
                return merged
        self.rows[item.id] = item
        return item

    async def get(self, tenant_id: UUID, memory_id: UUID) -> MemoryItem:
        row = self.rows.get(memory_id)
        if row is None or row.tenant_id != tenant_id:
            raise MemoryItemNotFound(memory_id)
        return row

    async def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: MemoryScope | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]:
        rows = [
            r
            for r in self.rows.values()
            if r.tenant_id == tenant_id
            and (r.user_id is None or r.user_id == user_id)
            and (scope is None or r.scope is scope)
            and (key is None or r.key == key)
            and r.confidence >= min_confidence
        ]
        rows.sort(key=lambda r: r.last_seen, reverse=True)
        return tuple(rows)

    async def delete(self, tenant_id: UUID, memory_id: UUID) -> None:
        row = self.rows.get(memory_id)
        if row is None or row.tenant_id != tenant_id:
            raise MemoryItemNotFound(memory_id)
        del self.rows[memory_id]


class FakeConversationRepository:
    """Mirrors PostgresConversationRepository's port-visible behaviour."""

    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, list[Message]] = {}

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        self.messages[conversation.id] = []
        return conversation

    def _scoped(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        row = self.conversations.get(conversation_id)
        if row is None or row.tenant_id != tenant_id:
            raise ConversationNotFound(conversation_id)
        return row

    async def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        return self._scoped(tenant_id, conversation_id)

    async def set_status(
        self, tenant_id: UUID, conversation_id: UUID, status: ConversationStatus
    ) -> Conversation:
        row = self._scoped(tenant_id, conversation_id).model_copy(update={"status": status})
        self.conversations[conversation_id] = row
        return row

    async def list_conversations(self, tenant_id: UUID, user_id: UUID) -> tuple[Conversation, ...]:
        return tuple(
            c
            for c in self.conversations.values()
            if c.tenant_id == tenant_id and c.user_id == user_id
        )

    async def append_message(self, tenant_id: UUID, message: Message) -> Message:
        self._scoped(tenant_id, message.conversation_id)
        if not message.content and not message.attachments:
            raise EmptyMessage()
        self.messages[message.conversation_id].append(message)
        return message

    async def get_history(
        self, tenant_id: UUID, conversation_id: UUID, limit: int | None = None
    ) -> tuple[Message, ...]:
        self._scoped(tenant_id, conversation_id)
        rows = self.messages[conversation_id]
        if limit is not None:
            rows = rows[-limit:]
        return tuple(rows)


class ExplodingMemoryRepository(FakeMemoryRepository):
    async def upsert(self, item: MemoryItem) -> MemoryItem:
        raise RuntimeError("database unavailable")


# --- fixtures ---------------------------------------------------------------------


@pytest.fixture
def bridge() -> Iterator[AsyncBridge]:
    b = AsyncBridge()
    try:
        yield b
    finally:
        b.close()


@pytest.fixture
def memory_repo() -> FakeMemoryRepository:
    return FakeMemoryRepository()


@pytest.fixture
def conversation_repo() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def memory(bridge: AsyncBridge, memory_repo: FakeMemoryRepository) -> DurableMemoryStore:
    return DurableMemoryStore(repository=memory_repo, bridge=bridge)  # type: ignore[arg-type]


@pytest.fixture
def conversations(
    bridge: AsyncBridge, conversation_repo: FakeConversationRepository
) -> DurableConversationStore:
    return DurableConversationStore(repository=conversation_repo, bridge=bridge)  # type: ignore[arg-type]


def _item(key: str = "lang", value: Any = "ar", **overrides: Any) -> MemoryItem:
    base: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "user_id": USER,
        "scope": MemoryScope.TENANT,
        "key": key,
        "value": value,
        "source": "test",
        "confidence": 0.9,
        "evidence_count": 1,
        "last_seen": datetime.now(UTC),
    }
    base.update(overrides)
    return MemoryItem(**base)


def _conversation(**overrides: Any) -> Conversation:
    base: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "user_id": USER,
        "title": "durable",
        "status": ConversationStatus.ACTIVE,
    }
    base.update(overrides)
    return Conversation(**base)


def _message(conversation_id: UUID, content: str = "hello") -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
        created_at=datetime.now(UTC),
    )


# --- 1. adapters forward verbatim over the bridge -----------------------------


class TestDurableMemoryStore:
    def test_upsert_get_query_delete_round_trip(self, memory: DurableMemoryStore) -> None:
        item = memory.upsert(_item())
        assert memory.get(TENANT, item.id) == item
        assert memory.query(TENANT, user_id=USER, key="lang") == (item,)
        memory.delete(TENANT, item.id)
        with pytest.raises(MemoryItemNotFound):
            memory.get(TENANT, item.id)

    def test_logical_key_upsert_keeps_original_id_and_counts_evidence(
        self, memory: DurableMemoryStore
    ) -> None:
        first = memory.upsert(_item(value="ar"))
        second = memory.upsert(_item(value="en"))
        assert second.id == first.id
        assert second.value == "en"
        assert second.evidence_count == 2

    def test_query_forwards_every_filter_keyword(self, bridge: AsyncBridge) -> None:
        seen: dict[str, Any] = {}

        class Recording(FakeMemoryRepository):
            async def query(self, tenant_id: UUID, **kwargs: Any) -> tuple[MemoryItem, ...]:
                seen.update(tenant_id=tenant_id, **kwargs)
                return ()

        store = DurableMemoryStore(repository=Recording(), bridge=bridge)  # type: ignore[arg-type]
        store.query(
            TENANT,
            user_id=USER,
            scope=MemoryScope.PROJECT,
            key="k",
            min_confidence=0.5,
            include_expired=True,
        )
        assert seen == {
            "tenant_id": TENANT,
            "user_id": USER,
            "scope": MemoryScope.PROJECT,
            "key": "k",
            "min_confidence": 0.5,
            "include_expired": True,
        }

    def test_foreign_tenant_is_not_found_same_refusal(self, memory: DurableMemoryStore) -> None:
        item = memory.upsert(_item())
        with pytest.raises(MemoryItemNotFound):
            memory.get(OTHER_TENANT, item.id)
        with pytest.raises(MemoryItemNotFound):
            memory.delete(OTHER_TENANT, item.id)

    def test_secret_like_refusal_crosses_the_bridge_unchanged(
        self, memory: DurableMemoryStore
    ) -> None:
        with pytest.raises(SecretLikeMemoryRejected):
            memory.upsert(_item(key="api_key", value="sk-live-0000000000000000"))

    def test_durable_write_failure_propagates_loudly(self, bridge: AsyncBridge) -> None:
        store = DurableMemoryStore(repository=ExplodingMemoryRepository(), bridge=bridge)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="database unavailable"):
            store.upsert(_item())


class TestDurableConversationStore:
    def test_create_get_status_list_round_trip(
        self, conversations: DurableConversationStore
    ) -> None:
        conv = conversations.create_conversation(_conversation())
        assert conversations.get_conversation(TENANT, conv.id) == conv
        archived = conversations.set_status(TENANT, conv.id, ConversationStatus.ARCHIVED)
        assert archived.status is ConversationStatus.ARCHIVED
        assert conversations.list_conversations(TENANT, USER) == (archived,)
        assert conversations.list_conversations(OTHER_TENANT, USER) == ()

    def test_append_and_history_with_limit_keeps_newest(
        self, conversations: DurableConversationStore
    ) -> None:
        conv = conversations.create_conversation(_conversation())
        m1 = conversations.append_message(TENANT, _message(conv.id, "one"))
        m2 = conversations.append_message(TENANT, _message(conv.id, "two"))
        assert conversations.get_history(TENANT, conv.id) == (m1, m2)
        assert conversations.get_history(TENANT, conv.id, limit=1) == (m2,)

    def test_named_refusals_cross_unchanged(self, conversations: DurableConversationStore) -> None:
        conv = conversations.create_conversation(_conversation())
        with pytest.raises(ConversationNotFound):
            conversations.get_conversation(OTHER_TENANT, conv.id)
        with pytest.raises(ConversationNotFound):
            conversations.append_message(TENANT, _message(uuid4()))
        with pytest.raises(EmptyMessage):
            conversations.append_message(TENANT, _message(conv.id, ""))


# --- 2. port parity ----------------------------------------------------------------


class TestPortParity:
    def test_durable_and_in_memory_satisfy_the_same_ports(
        self, memory: DurableMemoryStore, conversations: DurableConversationStore
    ) -> None:
        durable_memory: MemoryStorePort = memory
        durable_conversations: ConversationStorePort = conversations
        local_memory: MemoryStorePort = InMemoryMemoryStore()
        local_conversations: ConversationStorePort = InMemoryConversationStore()
        for port, impls in (
            (MemoryStorePort, (durable_memory, local_memory)),
            (ConversationStorePort, (durable_conversations, local_conversations)),
        ):
            names = [n for n in vars(port) if not n.startswith("_")]
            for impl in impls:
                for name in names:
                    assert callable(getattr(impl, name)), (type(impl).__name__, name)

    def test_builder_wires_bindings_repositories_over_the_shared_bridge(
        self, bridge: AsyncBridge
    ) -> None:
        class Bindings:
            memory = FakeMemoryRepository()
            conversations = FakeConversationRepository()

        m, c = build_durable_memory_stores(Bindings(), bridge)  # type: ignore[arg-type]
        assert isinstance(m, DurableMemoryStore) and m.repository is Bindings.memory
        assert isinstance(c, DurableConversationStore)
        assert c.repository is Bindings.conversations
        assert m.bridge is bridge and c.bridge is bridge


# --- 3. composition truth (runtime.py binding, profile-conditional) ----------------


class TestRuntimeBinding:
    def test_runtime_binds_durable_stores_only_in_the_database_branch(self) -> None:
        source = RUNTIME_PY.read_text(encoding="utf-8")
        assert "from apps.composition.memory import build_durable_memory_stores" in source
        assert "build_durable_memory_stores(bindings, bridge)" in source
        # The durable stores must be born INSIDE the `if settings is not None:`
        # branch, and the in-memory classes must remain the ONLY other choice.
        durable_branch = source.index("if settings is not None:\n        bridge = AsyncBridge()")
        else_branch = source.index("    else:\n        store = InMemoryExecutionStore()")
        bind_at = source.index("build_durable_memory_stores(bindings, bridge)")
        assert durable_branch < bind_at < else_branch
        assert "InMemoryMemoryStore()" in source
        assert "InMemoryConversationStore()" in source

    def test_in_memory_profile_is_unchanged(self) -> None:
        from apps.composition.runtime import build_runtime_profile

        profile = build_runtime_profile(environ={})
        assert profile.durable is False
        assert profile.bindings is None and profile.bridge is None
        # No database ⇒ the app still boots; nothing durable was allocated.
        assert profile.app.title
