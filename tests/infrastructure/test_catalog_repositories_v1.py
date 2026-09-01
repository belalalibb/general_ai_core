"""Catalog repositories — hermetic + live gates (Vision V1 chunk 6, PRV-4).

Two layers, same posture as the other V1 repository suites:

1. Hermetic (always run): row↔contract conversion fidelity for all four
   catalogs (incl. nested-contract JSONB round-trips), upsert SQL
   compiles for the postgresql dialect, surface pins — no server needed.
2. Live (env-gated, skip-when-absent per 41 §49): full round-trips
   against a REAL PostgreSQL — the hydration path (upsert -> load_all ->
   the EXISTING in-memory registries accept the loaded contracts), id-
   keyed update-in-place, deterministic ordering, secondary-unique-key
   collision surfacing loudly.

Run the live layer with:

    DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/db \\
    python3 -m pytest tests/infrastructure/test_catalog_repositories_v1.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from core.contracts.domain import (
    AgentCapability,
    AgentCapabilityType,
    AuthType,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderStatus,
)
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillProvenance,
    SkillSource,
    SkillStatus,
    SkillType,
)
from core.providers.registry import ModelRegistry
from core.roles.registry import RoleRegistry, SkillRegistry
from infrastructure.db.engine import create_engine, create_session_factory
from infrastructure.db.repositories import (
    PostgresModelCatalog,
    PostgresProviderCatalog,
    PostgresRoleCatalog,
    PostgresSkillCatalog,
)
from infrastructure.db.repositories.catalog import (
    _model_values,
    _provider_values,
    _role_values,
    _row_to_model,
    _row_to_provider,
    _row_to_role,
    _row_to_skill,
    _skill_values,
)
from infrastructure.db.tables import metadata, models, providers, roles, skills

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


class _Row:
    """Bare attribute carrier standing in for a SQLAlchemy Row."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def make_role(*, name: str = "analyst", version: str = "v1") -> Role:
    return Role(
        id=uuid4(),
        scope=RoleScope.SYSTEM,
        name=name,
        version=version,
        objective="analyze things carefully",
        behavior_policies={"tone": "precise"},
        output_contract={"format": "markdown"},
        status=RoleStatus.ACTIVE,
        capabilities_requested=["reasoning"],
    )


def make_skill(*, name: str = "code_review", version: str = "1.0") -> Skill:
    return Skill(
        id=uuid4(),
        name=name,
        version=version,
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        provenance=SkillProvenance(
            source_url="https://github.com/anthropics/skills",
            checksum="a" * 64,
            imported_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
            reviewed_by="admin@example.test",
            local_version="1.0-local",
        ),
        manifest=SkillManifest(
            id=name,
            name=name,
            version=version,
            type=SkillType.INSTRUCTION,
            source=SkillSource.LOCAL,
            status=SkillStatus.ACTIVE,
            capabilities=["review"],
        ),
        status=SkillStatus.ACTIVE,
    )


def make_model(*, model_key: str = "fast-model") -> Model:
    return Model(
        id=uuid4(),
        model_key=model_key,
        display_name="Fast Model",
        tier=ModelTier.FAST,
        modalities=[Modality.TEXT, Modality.CODE],
        capabilities=["reasoning", "coding"],
        context_window=128_000,
        quality_score=0.8,
        status=ModelStatus.ACTIVE,
        agent_capability=AgentCapability(
            type=AgentCapabilityType.TOOL_USING_MODEL,
            supports_tools=True,
        ),
    )


def make_provider(*, provider_key: str = "groq") -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=provider_key,
        display_name="Groq",
        status=ProviderStatus.ACTIVE,
        auth_types=[AuthType.API_KEY],
        supports_account_pool=True,
    )


class TestHermetic:
    def test_role_round_trip_fidelity(self) -> None:
        role = make_role()
        restored = _row_to_role(_Row(**_role_values(role)))
        assert restored == role
        assert restored.scope is RoleScope.SYSTEM  # enum, not bare string

    def test_skill_round_trip_with_nested_contracts(self) -> None:
        skill = make_skill()
        values = _skill_values(skill)
        # JSONB carries plain dicts — nested contracts serialize json-mode
        # (datetime becomes an ISO string, exactly what JSONB stores).
        assert isinstance(values["provenance"], dict)
        assert isinstance(values["provenance"]["imported_at"], str)
        assert isinstance(values["manifest"], dict)
        restored = _row_to_skill(_Row(**values))
        assert restored == skill
        assert restored.provenance.imported_at == skill.provenance.imported_at

    def test_model_round_trip_with_agent_capability_and_none(self) -> None:
        model = make_model()
        restored = _row_to_model(_Row(**_model_values(model)))
        assert restored == model
        assert restored.agent_capability is not None
        assert restored.agent_capability.type is AgentCapabilityType.TOOL_USING_MODEL
        bare = make_model(model_key="bare").model_copy(update={"agent_capability": None})
        assert _row_to_model(_Row(**_model_values(bare))).agent_capability is None

    def test_provider_round_trip_fidelity(self) -> None:
        provider = make_provider()
        restored = _row_to_provider(_Row(**_provider_values(provider)))
        assert restored == provider
        assert restored.auth_types == [AuthType.API_KEY]

    def test_upsert_sql_compiles_for_postgresql(self) -> None:
        # Conflict keys mirror what each catalog ACTUALLY upserts on:
        # roles/skills conflict on id; models/providers conflict on their
        # NATURAL key (Gap 2 — admin write-through must update the durable
        # row for code-shipped entities whose in-memory ids are per-boot).
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for table, values, conflict_col in (
            (roles, _role_values(make_role()), "id"),
            (skills, _skill_values(make_skill()), "id"),
            (models, _model_values(make_model()), "model_key"),
            (providers, _provider_values(make_provider()), "provider_key"),
        ):
            stmt = pg_insert(table).values(**values)
            update_cols = {k: v for k, v in values.items() if k != "id"}
            compiled = str(
                stmt.on_conflict_do_update(
                    index_elements=[conflict_col], set_=update_cols
                ).compile(dialect=postgresql.dialect())
            )
            assert f"ON CONFLICT ({conflict_col}) DO UPDATE" in compiled, table.name

    def test_catalog_surfaces_are_exactly_load_all_and_upsert(self) -> None:
        # Hydration + write-through ONLY: admission stays in the in-memory
        # registries (PRV-4 recorded decision) — no select/list here.
        # Gap 2 widening (deliberate): model/provider catalogs additionally
        # carry ``delete`` — the AdminPersistencePort rollback verb for the
        # REGISTER_* actions (a rolled-back registration removes its durable
        # row; restore reality, 21 §8). Role/skill catalogs stay unwidened.
        for cls in (PostgresRoleCatalog, PostgresSkillCatalog):
            public = {n for n in dir(cls) if not n.startswith("_")}
            assert public == {"load_all", "upsert"}, cls.__name__
        for cls in (PostgresModelCatalog, PostgresProviderCatalog):
            public = {n for n in dir(cls) if not n.startswith("_")}
            assert public == {"load_all", "upsert", "delete"}, cls.__name__


# --- Live layer -----------------------------------------------------------------


@pytest_asyncio.fixture()
async def engine() -> Any:
    url = os.environ["DATABASE_URL"]
    eng: AsyncEngine = create_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        for table in (skills, roles, models):
            await conn.execute(delete(table))
        # providers may be FK'd by credentials in other suites' leftovers;
        # this suite only deletes what it inserted by unique keys.
        await conn.execute(
            delete(providers).where(providers.c.provider_key.like("cat-%"))
        )
    await eng.dispose()


@requires_live_postgres
class TestLiveCatalogs:
    @pytest.mark.asyncio
    async def test_hydration_path_feeds_the_existing_registries(
        self, engine: AsyncEngine
    ) -> None:
        factory = create_session_factory(engine)
        role_catalog = PostgresRoleCatalog(factory)
        skill_catalog = PostgresSkillCatalog(factory)
        model_catalog = PostgresModelCatalog(factory)

        role = make_role(name="hydration-role")
        skill = make_skill(name="hydration_skill")
        model = make_model(model_key="hydration-model")
        await role_catalog.upsert(role)
        await skill_catalog.upsert(skill)
        await model_catalog.upsert(model)

        # The composition-root hydration pattern: rows -> contracts ->
        # the EXISTING in-memory registries (admission authority unchanged).
        role_registry = RoleRegistry()
        for loaded in await role_catalog.load_all():
            role_registry.register(loaded)
        assert role_registry.select(role.id) == role

        skill_registry = SkillRegistry()
        for loaded_skill in await skill_catalog.load_all():
            skill_registry.register(loaded_skill)
        assert skill_registry.select(skill.id) == skill

        model_registry = ModelRegistry()
        for loaded_model in await model_catalog.load_all():
            model_registry.register(loaded_model)
        assert model_registry.get(model.model_key) == model

    @pytest.mark.asyncio
    async def test_upsert_updates_in_place_by_id(self, engine: AsyncEngine) -> None:
        factory = create_session_factory(engine)
        catalog = PostgresModelCatalog(factory)
        model = make_model(model_key="update-model")
        await catalog.upsert(model)
        disabled = model.model_copy(update={"status": ModelStatus.DISABLED})
        await catalog.upsert(disabled)
        loaded = [m for m in await catalog.load_all() if m.id == model.id]
        assert len(loaded) == 1  # updated, not duplicated
        assert loaded[0].status is ModelStatus.DISABLED

    @pytest.mark.asyncio
    async def test_provider_round_trip_and_deterministic_order(
        self, engine: AsyncEngine
    ) -> None:
        factory = create_session_factory(engine)
        catalog = PostgresProviderCatalog(factory)
        b = make_provider(provider_key="cat-bbb")
        a = make_provider(provider_key="cat-aaa")
        await catalog.upsert(b)
        await catalog.upsert(a)
        loaded = [p for p in await catalog.load_all() if p.provider_key.startswith("cat-")]
        assert loaded == [a, b]  # ordered by provider_key, full fidelity

    @pytest.mark.asyncio
    async def test_distinct_ids_colliding_on_human_key_surface_loudly(
        self, engine: AsyncEngine
    ) -> None:
        # Two DIFFERENT ids claiming one name+version is catalog corruption:
        # the secondary unique constraint refuses, never absorbed (recorded).
        factory = create_session_factory(engine)
        catalog = PostgresRoleCatalog(factory)
        await catalog.upsert(make_role(name="clash", version="v9"))
        with pytest.raises(IntegrityError):
            await catalog.upsert(make_role(name="clash", version="v9"))
