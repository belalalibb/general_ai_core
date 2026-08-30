"""Composition-root wiring tests for the V1 database bindings (Vision V1).

Hermetic: ``environ`` is injected as a plain dict — no real environment
variables are read, no connection is opened (SQLAlchemy engine creation
is lazy: no I/O until first use). What is verified is the WIRING policy,
same posture as test_composition_bindings_t075:

- "not configured ⇒ binding absent": missing DATABASE_URL returns None,
  callers keep the in-memory profile (ADR-0002 dev/test posture).
- settings repr never leaks the URL (it carries credentials, 20 §5).
- the builder produces the real repository types over ONE shared
  engine/session factory (one pool, one truth).
"""

from __future__ import annotations

import pytest

from apps.composition import (
    DatabaseBindings,
    DatabaseSettings,
    build_database_bindings,
    database_settings_from_env,
)
from infrastructure.db.repositories import (
    PostgresAuditLogRepository,
    PostgresConversationRepository,
    PostgresExecutionRepository,
    PostgresIdempotencyStore,
    PostgresMemoryRepository,
    PostgresUsageRepository,
)

URL = "postgresql+asyncpg://svc:credential-value@db.internal:5432/platform"


class TestDatabaseSettings:
    def test_not_configured_returns_none(self) -> None:
        assert database_settings_from_env({}) is None

    def test_blank_url_is_not_configured(self) -> None:
        assert database_settings_from_env({"DATABASE_URL": "   "}) is None

    def test_full_configuration_parsed(self) -> None:
        settings = database_settings_from_env({"DATABASE_URL": URL})
        assert settings == DatabaseSettings(url=URL, echo=False)

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_echo_truthy_values(self, value: str) -> None:
        settings = database_settings_from_env(
            {"DATABASE_URL": URL, "DATABASE_ECHO": value}
        )
        assert settings is not None and settings.echo is True

    def test_echo_defaults_off_and_unknown_values_off(self) -> None:
        for env in ({"DATABASE_URL": URL}, {"DATABASE_URL": URL, "DATABASE_ECHO": "0"}):
            settings = database_settings_from_env(env)
            assert settings is not None and settings.echo is False

    def test_repr_never_contains_the_url(self) -> None:
        # The URL carries credentials — reprs get logged (20 §5).
        settings = DatabaseSettings(url=URL)
        assert URL not in repr(settings)
        assert "credential-value" not in repr(settings)

    def test_builder_returns_all_repositories_over_one_factory(self) -> None:
        bindings = build_database_bindings(DatabaseSettings(url=URL))
        assert isinstance(bindings, DatabaseBindings)
        assert isinstance(bindings.executions, PostgresExecutionRepository)
        assert isinstance(bindings.conversations, PostgresConversationRepository)
        assert isinstance(bindings.memory, PostgresMemoryRepository)
        assert isinstance(bindings.audit, PostgresAuditLogRepository)
        assert isinstance(bindings.usage, PostgresUsageRepository)
        assert isinstance(bindings.idempotency, PostgresIdempotencyStore)
        # ONE shared session factory (one pool, one truth) — every
        # repository holds the same object the bindings expose.
        for repo in (
            bindings.executions,
            bindings.conversations,
            bindings.memory,
            bindings.audit,
            bindings.usage,
            bindings.idempotency,
        ):
            assert repo._sessions is bindings.session_factory  # noqa: SLF001
