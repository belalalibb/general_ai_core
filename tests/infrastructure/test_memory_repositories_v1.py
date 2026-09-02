"""Conversation + memory repositories — hermetic + live gates (V1 chunk 2).

Same two-layer posture as test_execution_repository_v1: hermetic
conversion/compile/guard tests always run; live round-trips are gated on
DATABASE_URL (skip-when-absent, 41 §49).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import MemoryItem, MemoryScope, MemorySensitivity
from core.memory.errors import (
    ConversationNotFound,
    EmptyMessage,
    MemoryItemNotFound,
    SecretLikeMemoryRejected,
)
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    PostgresConversationRepository,
    PostgresMemoryRepository,
)
from infrastructure.db.repositories.conversations import (
    _row_to_conversation,
    _row_to_message,
)
from infrastructure.db.repositories.memory import _row_to_item
from infrastructure.db.tables import conversations, memory_items, messages, metadata

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()
OTHER_USER = uuid4()
PLAN_ID = uuid4()
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


def make_conversation(
    *,
    conversation_id: UUID | None = None,
    tenant_id: UUID = TENANT,
    user_id: UUID = USER,
) -> Conversation:
    return Conversation(
        id=conversation_id or uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        project_id=None,
        title="Test conversation",
        status=ConversationStatus.ACTIVE,
    )


def make_message(
    conversation_id: UUID,
    *,
    content: str = "hello",
    created_at: datetime = NOW,
    attachments: list[dict[str, Any]] | None = None,
) -> Message:
    return Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=content,
        attachments=attachments or [],
        created_at=created_at,
    )


def make_item(
    *,
    tenant_id: UUID = TENANT,
    user_id: UUID | None = USER,
    scope: MemoryScope = MemoryScope.TENANT,
    key: str = "preferred_language",
    value: Any = "ar",
    confidence: float = 0.92,
    last_seen: datetime = NOW,
    expires_at: datetime | None = None,
) -> MemoryItem:
    return MemoryItem(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        scope=scope,
        key=key,
        value=value,
        source="conversation",
        confidence=confidence,
        evidence_count=1,
        last_seen=last_seen,
        expires_at=expires_at,
        sensitivity=MemorySensitivity.LOW,
    )


# --- Hermetic layer -----------------------------------------------------------


class _Row:
    def __init__(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(self, key, value)


class TestHermetic:
    def test_conversation_row_conversion(self) -> None:
        conv = make_conversation()
        row = _Row(
            {
                "id": conv.id,
                "tenant_id": conv.tenant_id,
                "user_id": conv.user_id,
                "project_id": conv.project_id,
                "title": conv.title,
                "status": conv.status.value,
            }
        )
        assert _row_to_conversation(row) == conv

    def test_message_row_conversion_preserves_attachments(self) -> None:
        msg = make_message(uuid4(), attachments=[{"kind": "image", "ref": "x"}])
        row = _Row(
            {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "role": msg.role.value,
                "content": msg.content,
                "attachments": msg.attachments,
                "created_at": msg.created_at,
            }
        )
        assert _row_to_message(row) == msg

    def test_memory_row_conversion_bare_string_value(self) -> None:
        # 03 §3 value: json — a bare string is a valid JSON value (13 §3 "ar").
        item = make_item(value="ar")
        row = _Row(
            {
                "id": item.id,
                "tenant_id": item.tenant_id,
                "user_id": item.user_id,
                "scope": item.scope.value,
                "key": item.key,
                "value": item.value,
                "source": item.source,
                "confidence": item.confidence,
                "evidence_count": item.evidence_count,
                "last_seen": item.last_seen,
                "expires_at": item.expires_at,
                "sensitivity": item.sensitivity.value,
            }
        )
        assert _row_to_item(row) == item

    @pytest.mark.asyncio
    async def test_secret_like_memory_refused_before_any_io(self) -> None:
        def exploding_factory() -> Any:  # pragma: no cover - must not run
            raise AssertionError("no session for refused input")

        repo = PostgresMemoryRepository(exploding_factory)
        with pytest.raises(SecretLikeMemoryRejected):
            await repo.upsert(make_item(key="api_key", value="sk-123"))

    @pytest.mark.asyncio
    async def test_empty_message_refused_before_any_io(self) -> None:
        def exploding_factory() -> Any:  # pragma: no cover - must not run
            raise AssertionError("no session for refused input")

        repo = PostgresConversationRepository(exploding_factory)
        with pytest.raises(EmptyMessage):
            await repo.append_message(TENANT, make_message(uuid4(), content=""))

    def test_upsert_statement_compiles_for_postgresql(self) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        item = make_item()
        stmt = pg_insert(memory_items).values(
            id=item.id,
            tenant_id=item.tenant_id,
            user_id=item.user_id,
            scope=item.scope.value,
            key=item.key,
            value=item.value,
            source=item.source,
            confidence=item.confidence,
            evidence_count=item.evidence_count,
            last_seen=item.last_seen,
            expires_at=item.expires_at,
            sensitivity=item.sensitivity.value,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_memory_items_logical_key",
            set_={"evidence_count": memory_items.c.evidence_count + 1},
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT ON CONSTRAINT uq_memory_items_logical_key" in compiled


# --- Live layer (env-gated) ---------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    eng: AsyncEngine = create_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.execute(delete(messages))
        await conn.execute(delete(conversations))
        await conn.execute(delete(memory_items))
    await eng.dispose()


@pytest_asyncio.fixture()
async def seeded(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO plans (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"),
            {"id": PLAN_ID, "name": f"plan-{PLAN_ID}"},
        )
        for tenant_id in (TENANT, OTHER_TENANT):
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, name, type, status, plan_id)"
                    " VALUES (:id, :name, 'personal', 'active', :plan_id)"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {"id": tenant_id, "name": f"t-{tenant_id}", "plan_id": PLAN_ID},
            )
        for tenant_id, user_id in ((TENANT, USER), (TENANT, OTHER_USER)):
            await conn.execute(
                text(
                    "INSERT INTO users (id, tenant_id, email, preferred_language,"
                    " status, created_at, updated_at)"
                    " VALUES (:id, :tenant_id, :email, 'en', 'active', :now, :now)"
                    " ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": user_id,
                    "tenant_id": tenant_id,
                    "email": f"{user_id}@example.test",
                    "now": NOW,
                },
            )
    return engine


@requires_live_postgres
class TestLiveConversations:
    @pytest.mark.asyncio
    async def test_create_get_status_history_round_trip(self, seeded: AsyncEngine) -> None:
        repo = PostgresConversationRepository(create_session_factory(seeded))
        conv = make_conversation()
        await repo.create_conversation(conv)
        assert await repo.get_conversation(TENANT, conv.id) == conv

        m1 = make_message(conv.id, content="first", created_at=NOW)
        m2 = make_message(conv.id, content="second", created_at=NOW + timedelta(seconds=1))
        m3 = make_message(conv.id, content="third", created_at=NOW + timedelta(seconds=2))
        for m in (m1, m2, m3):
            await repo.append_message(TENANT, m)

        history = await repo.get_history(TENANT, conv.id)
        assert [m.content for m in history] == ["first", "second", "third"]
        tail = await repo.get_history(TENANT, conv.id, limit=2)
        assert [m.content for m in tail] == ["second", "third"]  # newest, in order

        archived = await repo.set_status(TENANT, conv.id, ConversationStatus.ARCHIVED)
        assert archived.status is ConversationStatus.ARCHIVED
        assert (await repo.get_conversation(TENANT, conv.id)).status is ConversationStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_anti_enumeration_and_duplicate_create(self, seeded: AsyncEngine) -> None:
        repo = PostgresConversationRepository(create_session_factory(seeded))
        conv = make_conversation()
        await repo.create_conversation(conv)
        with pytest.raises(ConversationNotFound):
            await repo.get_conversation(OTHER_TENANT, conv.id)  # foreign
        with pytest.raises(ConversationNotFound):
            await repo.get_conversation(TENANT, uuid4())  # absent
        with pytest.raises(ValueError, match="already exists"):
            await repo.create_conversation(conv)
        # Appending through a foreign tenant is refused identically.
        with pytest.raises(ConversationNotFound):
            await repo.append_message(OTHER_TENANT, make_message(conv.id))

    @pytest.mark.asyncio
    async def test_list_is_user_scoped_newest_first(self, seeded: AsyncEngine) -> None:
        repo = PostgresConversationRepository(create_session_factory(seeded))
        old = make_conversation()
        new = make_conversation()
        foreign_user = make_conversation(user_id=OTHER_USER)
        for c in (old, new, foreign_user):
            await repo.create_conversation(c)
        await repo.append_message(TENANT, make_message(old.id, created_at=NOW))
        await repo.append_message(
            TENANT, make_message(new.id, created_at=NOW + timedelta(minutes=5))
        )
        rows = await repo.list_conversations(TENANT, USER)
        assert [c.id for c in rows[:2]] == [new.id, old.id]
        assert all(c.user_id == USER for c in rows)


@requires_live_postgres
class TestLiveMemory:
    @pytest.mark.asyncio
    async def test_upsert_preserves_id_and_accumulates_evidence(self, seeded: AsyncEngine) -> None:
        repo = PostgresMemoryRepository(create_session_factory(seeded))
        first = await repo.upsert(make_item(value="ar"))
        assert first.evidence_count == 1
        second = await repo.upsert(
            make_item(value="en", confidence=0.95, last_seen=NOW + timedelta(hours=1))
        )
        assert second.id == first.id  # original id survives
        assert second.evidence_count == 2
        assert second.value == "en"
        assert second.confidence == 0.95

    @pytest.mark.asyncio
    async def test_query_user_scoping_and_recency(self, seeded: AsyncEngine) -> None:
        repo = PostgresMemoryRepository(create_session_factory(seeded))
        shared = await repo.upsert(make_item(user_id=None, key="tz", value="UTC", last_seen=NOW))
        mine = await repo.upsert(
            make_item(key="lang", value="ar", last_seen=NOW + timedelta(minutes=1))
        )
        await repo.upsert(
            make_item(user_id=OTHER_USER, key="theme", value="dark")
        )  # never visible to USER
        rows = await repo.query(TENANT, user_id=USER)
        assert [r.id for r in rows] == [mine.id, shared.id]  # recency order
        # user_id=None sees only shared items.
        only_shared = await repo.query(TENANT)
        assert {r.id for r in only_shared} == {shared.id}

    @pytest.mark.asyncio
    async def test_expiry_confidence_filters_and_delete(self, seeded: AsyncEngine) -> None:
        repo = PostgresMemoryRepository(create_session_factory(seeded))
        expired = await repo.upsert(make_item(key="stale", expires_at=NOW - timedelta(days=1)))
        low = await repo.upsert(make_item(key="weak", confidence=0.2))
        live = await repo.upsert(make_item(key="fresh", confidence=0.9))
        default = await repo.query(TENANT, user_id=USER)
        assert expired.id not in {r.id for r in default}
        with_expired = await repo.query(TENANT, user_id=USER, include_expired=True)
        assert expired.id in {r.id for r in with_expired}
        confident = await repo.query(TENANT, user_id=USER, min_confidence=0.5)
        assert {r.id for r in confident} == {live.id}
        assert low.id not in {r.id for r in confident}

        await repo.delete(TENANT, live.id)
        with pytest.raises(MemoryItemNotFound):
            await repo.get(TENANT, live.id)
        with pytest.raises(MemoryItemNotFound):
            await repo.delete(OTHER_TENANT, low.id)  # foreign == absent
