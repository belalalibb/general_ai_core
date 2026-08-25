"""Alembic environment — async engine (ADR-0002).

Rules:

- DATABASE_URL comes from the environment only; never from committed config
  (20 §5 secrets rules). Offline mode (--sql) uses a credential-free
  placeholder so SQL review needs no live database (hermetic gates).
- target_metadata is infrastructure/db/tables.py — the single metadata
  object that maps core contracts. Autogenerate output is a reviewed draft,
  never committed blind (ADR-0002).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from infrastructure.db.tables import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

_OFFLINE_PLACEHOLDER_URL = "postgresql+asyncpg://localhost/offline_placeholder"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if context.is_offline_mode():
        return _OFFLINE_PLACEHOLDER_URL
    raise RuntimeError(
        "DATABASE_URL is not set. Online migrations require it; "
        "for SQL review without a database use: alembic ... upgrade head --sql"
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection (hermetic review path)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.")
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
