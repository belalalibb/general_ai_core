"""PostgreSQL conversation repository — ConversationStorePort binding.

Binds :class:`core.memory.ports.ConversationStorePort` (03 §3; 41 §45)
against the ``conversations``/``messages`` tables (migration 0006).

Design decisions (recorded):

- SAME SEMANTICS as the proven in-memory binding (core/memory/memory.py),
  re-verified against real SQL: tenant-scoped reads with anti-enumeration
  (:class:`ConversationNotFound` identical for absent and foreign, 20 §6);
  append-only messages; ``get_history`` returns oldest-first and ``limit``
  keeps the NEWEST tail; ``list_conversations`` newest-created-first.
- The conversations table has no created_at column (schema fact, 0006) —
  creation order for listing is derived from ``messages.created_at`` where
  possible; since the schema cannot express it exactly, listing orders by
  the primary key insertion via a window on id is NOT honest either.
  RECORDED DERIVATION: the port promises "newest first"; the durable,
  schema-backed ordering available is by first-message time with
  conversation id as deterministic tiebreak — conversations without
  messages sort last in stable id order. This is the honest maximum the
  existing schema supports; adding a created_at column is a schema change
  reserved for a justified migration, not silently invented here.
- Messages are physically keyed by conversation FK; tenant scoping rides
  the conversation row (a message is reachable ONLY through its
  tenant-checked conversation — the same reachability rule as in-memory).
- The port is sync (Protocol methods are ``def``); this binding is async
  (asyncpg). RECORDED: apps compose it behind async routes; the async
  surface mirrors PostgresExecutionRepository. A sync facade would fake
  it; the honest binding is async and the composition root owns the
  bridge. Method names/shapes match the port exactly otherwise.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.conversation import Conversation, ConversationStatus, Message
from core.memory.errors import ConversationNotFound, EmptyMessage
from infrastructure.db.tables import conversations, messages


def _row_to_conversation(row: Any) -> Conversation:
    return Conversation(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        project_id=row.project_id,
        title=row.title,
        status=row.status,
    )


def _row_to_message(row: Any) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        attachments=row.attachments,
        created_at=row.created_at,
    )


class PostgresConversationRepository:
    """Durable ConversationStorePort binding over asyncpg sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        async with self._sessions() as session:
            try:
                async with session.begin():
                    await session.execute(
                        conversations.insert().values(
                            id=conversation.id,
                            tenant_id=conversation.tenant_id,
                            user_id=conversation.user_id,
                            project_id=conversation.project_id,
                            title=conversation.title,
                            status=conversation.status.value,
                        )
                    )
            except IntegrityError as exc:
                if "pk_conversations" in str(exc.orig):
                    msg = f"conversation already exists: {conversation.id}"
                    raise ValueError(msg) from exc
                raise
        return conversation

    async def _get_scoped(
        self, session: AsyncSession, tenant_id: UUID, conversation_id: UUID
    ) -> Any:
        row = (
            await session.execute(
                select(conversations).where(
                    conversations.c.id == conversation_id,
                    conversations.c.tenant_id == tenant_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise ConversationNotFound(conversation_id)
        return row

    async def get_conversation(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> Conversation:
        async with self._sessions() as session:
            row = await self._get_scoped(session, tenant_id, conversation_id)
        return _row_to_conversation(row)

    async def set_status(
        self, tenant_id: UUID, conversation_id: UUID, status: ConversationStatus
    ) -> Conversation:
        async with self._sessions() as session:
            async with session.begin():
                row = await self._get_scoped(session, tenant_id, conversation_id)
                await session.execute(
                    conversations.update()
                    .where(
                        conversations.c.id == conversation_id,
                        conversations.c.tenant_id == tenant_id,
                    )
                    .values(status=status.value)
                )
        return _row_to_conversation(row).model_copy(update={"status": status})

    async def list_conversations(
        self, tenant_id: UUID, user_id: UUID
    ) -> tuple[Conversation, ...]:
        # Newest first by first-message time (schema-honest ordering —
        # see module docstring); conversations without messages last.
        first_message = (
            select(
                messages.c.conversation_id,
                func.min(messages.c.created_at).label("started_at"),
            )
            .group_by(messages.c.conversation_id)
            .subquery()
        )
        stmt = (
            select(conversations)
            .outerjoin(
                first_message,
                conversations.c.id == first_message.c.conversation_id,
            )
            .where(
                conversations.c.tenant_id == tenant_id,
                conversations.c.user_id == user_id,
            )
            .order_by(
                first_message.c.started_at.desc().nulls_last(),
                conversations.c.id,
            )
        )
        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        return tuple(_row_to_conversation(row) for row in rows)

    async def append_message(self, tenant_id: UUID, message: Message) -> Message:
        if not message.content and not message.attachments:
            raise EmptyMessage()
        async with self._sessions() as session:
            async with session.begin():
                await self._get_scoped(session, tenant_id, message.conversation_id)
                await session.execute(
                    messages.insert().values(
                        id=message.id,
                        conversation_id=message.conversation_id,
                        role=message.role.value,
                        content=message.content,
                        attachments=message.attachments,
                        created_at=message.created_at,
                    )
                )
        return message

    async def get_history(
        self, tenant_id: UUID, conversation_id: UUID, limit: int | None = None
    ) -> tuple[Message, ...]:
        async with self._sessions() as session:
            await self._get_scoped(session, tenant_id, conversation_id)
            stmt = select(messages).where(
                messages.c.conversation_id == conversation_id
            )
            if limit is not None and limit >= 0:
                # Newest `limit`, returned oldest-first (port contract):
                # order desc, cap, then reverse in memory.
                newest = (
                    await session.execute(
                        stmt.order_by(
                            messages.c.created_at.desc(), messages.c.id.desc()
                        ).limit(limit)
                    )
                ).all()
                return tuple(_row_to_message(row) for row in reversed(newest))
            rows = (
                await session.execute(
                    stmt.order_by(messages.c.created_at, messages.c.id)
                )
            ).all()
        return tuple(_row_to_message(row) for row in rows)
