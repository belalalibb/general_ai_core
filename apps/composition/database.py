"""Database composition wiring (ADR-0002 binding at the root; Vision V1).

Environment contract (deployment surface — Lane C):

- ``DATABASE_URL``       — REQUIRED to bind. postgresql+asyncpg URL
                           (same variable alembic env.py and the live
                           test suites already read — ONE name, one
                           meaning). The value carries credentials and
                           is NEVER logged (20 §5).
- ``DATABASE_ECHO``      — optional; "1"/"true" enables SQLAlchemy
                           statement echo (dev diagnostics only).

"Not configured ⇒ absent": without DATABASE_URL there is nothing to
bind and ``database_settings_from_env`` returns None — callers keep the
in-memory profile (the ADR-0002 dev/test posture). This module is the
ONLY place the process-wide engine is constructed for the platform;
repositories receive the session FACTORY (never construct engines —
the recorded posture of all seven bindings).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    PostgresAuditLogRepository,
    PostgresBindingCatalog,
    PostgresConversationRepository,
    PostgresExecutionRepository,
    PostgresGatewayRegistrationCatalog,
    PostgresIdempotencyStore,
    PostgresMemoryRepository,
    PostgresModelCatalog,
    PostgresOutbox,
    PostgresProjectRepository,
    PostgresProviderCatalog,
    PostgresRoleCatalog,
    PostgresSkillCatalog,
    PostgresUsageRepository,
    PostgresWorkspaceRepository,
)

_ENV_URL = "DATABASE_URL"
_ENV_ECHO = "DATABASE_ECHO"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated database deployment settings (no credentials in repr)."""

    url: str
    echo: bool = False

    def __repr__(self) -> str:  # 20 §5: the URL carries credentials
        return f"DatabaseSettings(url='***', echo={self.echo!r})"


def database_settings_from_env(
    environ: dict[str, str] | None = None,
) -> DatabaseSettings | None:
    """Read settings from the environment; None when not configured.

    ``environ`` is injectable for hermetic tests; production callers pass
    nothing and get ``os.environ``.
    """
    env = os.environ if environ is None else environ
    url = env.get(_ENV_URL, "").strip()
    if not url:
        return None  # not configured ⇒ binding absent (recorded posture)
    echo = env.get(_ENV_ECHO, "").strip().lower() in _TRUTHY
    return DatabaseSettings(url=url, echo=echo)


@dataclass(frozen=True, slots=True)
class DatabaseBindings:
    """The full V1 repository set over ONE shared engine/session factory.

    The engine is exposed for lifecycle management (``await
    engine.dispose()`` at shutdown) — repositories themselves never
    own it.
    """

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    executions: PostgresExecutionRepository
    conversations: PostgresConversationRepository
    memory: PostgresMemoryRepository
    audit: PostgresAuditLogRepository
    usage: PostgresUsageRepository
    idempotency: PostgresIdempotencyStore
    # Vision V2: durable transactional outbox (40 §4.2) — the async
    # execute path stages messages here; the relay drains onto the bus.
    outbox: PostgresOutbox
    # PRV-4 catalogs: durable truth the composition root HYDRATES the
    # existing in-memory registries from (admission authority unchanged).
    role_catalog: PostgresRoleCatalog
    skill_catalog: PostgresSkillCatalog
    model_catalog: PostgresModelCatalog
    provider_catalog: PostgresProviderCatalog
    # Gap 1 (migration 0018): durable provider-model bindings — the
    # write-through + hydration seam the onboarding surface persists
    # through so an onboarded provider survives restart.
    binding_catalog: PostgresBindingCatalog
    # ADR-0011: per-provider gateway registration records — the operator
    # data (refs only, 20 §5) the root rebuilds gateway adapters from.
    gateway_registrations: PostgresGatewayRegistrationCatalog
    # Vision V5: durable workspace/project entities (existing tables from
    # migration 0002; core/workspace/ owns the FILE area separately).
    workspaces: PostgresWorkspaceRepository
    projects: PostgresProjectRepository


def build_database_bindings(settings: DatabaseSettings) -> DatabaseBindings:
    """Construct the production bindings from validated settings.

    The ONLY place the platform's async engine is created. All
    repositories share the same session factory (one pool, one truth).
    """
    engine = create_engine(settings.url, echo=settings.echo)
    factory = create_session_factory(engine)
    return DatabaseBindings(
        engine=engine,
        session_factory=factory,
        executions=PostgresExecutionRepository(factory),
        conversations=PostgresConversationRepository(factory),
        memory=PostgresMemoryRepository(factory),
        audit=PostgresAuditLogRepository(factory),
        usage=PostgresUsageRepository(factory),
        idempotency=PostgresIdempotencyStore(factory),
        outbox=PostgresOutbox(factory),
        role_catalog=PostgresRoleCatalog(factory),
        skill_catalog=PostgresSkillCatalog(factory),
        model_catalog=PostgresModelCatalog(factory),
        provider_catalog=PostgresProviderCatalog(factory),
        binding_catalog=PostgresBindingCatalog(factory),
        gateway_registrations=PostgresGatewayRegistrationCatalog(factory),
        workspaces=PostgresWorkspaceRepository(factory),
        projects=PostgresProjectRepository(factory),
    )
