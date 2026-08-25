"""Async engine/session factory (ADR-0002).

Composition-root helper: apps/ builds the engine once from configuration and
injects sessions into repositories. The URL is provided by the caller (from
DATABASE_URL or a secret manager) — never read from committed files (20 §5).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the process-wide async engine (postgresql+asyncpg URL)."""
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory; ``expire_on_commit=False`` keeps returned contract
    data usable after commit (rows are converted to Pydantic at the boundary,
    not held as live ORM state)."""
    return async_sessionmaker(engine, expire_on_commit=False)
