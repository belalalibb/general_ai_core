"""PostgreSQL catalog repositories — durable truth for the platform catalogs.

PRV-4 RESOLUTION (the AA-3 STOP: "registry persistence design — ties to the
repositories primitive"). Recorded design decision:

- The in-memory registries (core/roles/registry.py, core/providers/
  registry.py) REMAIN the runtime admission authority — their selection
  semantics (ACTIVE-only, local-only skills, template exclusion) are
  proven by the largest test suites in the repo and are NOT rebuilt here
  (P1 REUSE; P2 consumers unchanged).
- These catalog repositories make the EXISTING tables (roles/skills/
  models/providers — migrations 0003/0004/0005) the durable source of
  truth: ``load_all`` feeds registry HYDRATION at the composition root
  (startup: rows -> contracts -> registry.register), ``upsert`` is the
  write-through seam a future runtime-registration surface (PRV-4's
  admin routes — V7/AA territory, NOT V1) calls BEFORE registering
  in-memory. Durable row first, process state second — a crash between
  the two loses nothing (the next hydration replays the row).
- ProviderManifest is DELIBERATELY NOT persisted: the manifest is the
  provider's code self-declaration (30 §7) describing what the shipped
  adapter can actually do — a DB row claiming capabilities the code does
  not have would fabricate architecture. Manifests stay composition-time
  data next to the provider implementations; the catalog persists the
  Provider ENTITY (03 §4) only.
- No provider_model_bindings table exists and none is invented here:
  ProviderModelBinding persistence arrives WITH the runtime binding-
  registration surface that needs it (a justified migration then, not a
  speculative one now — same posture as the deferred conversations
  created_at column).

Shared repository posture (all four): session FACTORY injected; rows <->
frozen contracts at the boundary (nested contracts round-trip as JSONB
via their own ``model_dump(mode="json")``/``model_validate`` — no
hand-rolled field mapping to drift); these are PLATFORM catalogs (03 §4/
§6 — deliberately NOT tenant-scoped, matching the schema and the parity
suite); ``load_all`` orders deterministically by the human key.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.domain import AgentCapability, Model, Provider
from core.contracts.roles import Role
from core.contracts.skills import Skill, SkillManifest, SkillProvenance
from infrastructure.db.tables import models, providers, roles, skills


def _row_to_role(row: Any) -> Role:
    return Role(
        id=row.id,
        scope=row.scope,
        name=row.name,
        version=row.version,
        objective=row.objective,
        behavior_policies=row.behavior_policies,
        output_contract=row.output_contract,
        status=row.status,
        capabilities_requested=row.capabilities_requested,
    )


def _row_to_skill(row: Any) -> Skill:
    return Skill(
        id=row.id,
        name=row.name,
        version=row.version,
        type=row.type,
        source=row.source,
        provenance=SkillProvenance.model_validate(row.provenance),
        manifest=SkillManifest.model_validate(row.manifest),
        status=row.status,
    )


def _row_to_model(row: Any) -> Model:
    return Model(
        id=row.id,
        model_key=row.model_key,
        display_name=row.display_name,
        tier=row.tier,
        modalities=row.modalities,
        capabilities=row.capabilities,
        context_window=row.context_window,
        quality_score=row.quality_score,
        speed_score=row.speed_score,
        cost_score=row.cost_score,
        reliability_score=row.reliability_score,
        status=row.status,
        agent_capability=(
            AgentCapability.model_validate(row.agent_capability)
            if row.agent_capability is not None
            else None
        ),
    )


def _row_to_provider(row: Any) -> Provider:
    return Provider(
        id=row.id,
        provider_key=row.provider_key,
        display_name=row.display_name,
        status=row.status,
        auth_types=row.auth_types,
        supports_account_pool=row.supports_account_pool,
    )


def _role_values(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "scope": role.scope.value,
        "name": role.name,
        "version": role.version,
        "objective": role.objective,
        "behavior_policies": role.behavior_policies,
        "output_contract": role.output_contract,
        "status": role.status.value,
        "capabilities_requested": list(role.capabilities_requested),
    }


def _skill_values(skill: Skill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "version": skill.version,
        "type": skill.type.value,
        "source": skill.source.value,
        "provenance": skill.provenance.model_dump(mode="json"),
        "manifest": skill.manifest.model_dump(mode="json"),
        "status": skill.status.value,
    }


def _model_values(model: Model) -> dict[str, Any]:
    return {
        "id": model.id,
        "model_key": model.model_key,
        "display_name": model.display_name,
        "tier": model.tier.value,
        "modalities": [m.value for m in model.modalities],
        "capabilities": list(model.capabilities),
        "context_window": model.context_window,
        "quality_score": model.quality_score,
        "speed_score": model.speed_score,
        "cost_score": model.cost_score,
        "reliability_score": model.reliability_score,
        "status": model.status.value,
        "agent_capability": (
            model.agent_capability.model_dump(mode="json")
            if model.agent_capability is not None
            else None
        ),
    }


def _provider_values(provider: Provider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "provider_key": provider.provider_key,
        "display_name": provider.display_name,
        "status": provider.status.value,
        "auth_types": [a.value for a in provider.auth_types],
        "supports_account_pool": provider.supports_account_pool,
    }


class _CatalogBase:
    """Shared load_all/upsert over one catalog table (id PK upsert).

    ``upsert`` is keyed on the id PRIMARY KEY (ON CONFLICT (id) DO
    UPDATE): the same entity id updates in place; a DIFFERENT id
    colliding with a secondary unique key (e.g. uq_roles_name_version,
    models.model_key) surfaces the IntegrityError LOUDLY — two distinct
    ids claiming one human key is a catalog corruption, never absorbed.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory


class PostgresRoleCatalog(_CatalogBase):
    """Durable role catalog over the ``roles`` table (migration 0003)."""

    async def load_all(self) -> list[Role]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(roles).order_by(roles.c.name, roles.c.version)
            )
        return [_row_to_role(row) for row in rows]

    async def upsert(self, role: Role) -> None:
        values = _role_values(role)
        stmt = pg_insert(roles).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
                )


class PostgresSkillCatalog(_CatalogBase):
    """Durable skill catalog over the ``skills`` table (migration 0004)."""

    async def load_all(self) -> list[Skill]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(skills).order_by(skills.c.name, skills.c.version)
            )
        return [_row_to_skill(row) for row in rows]

    async def upsert(self, skill: Skill) -> None:
        values = _skill_values(skill)
        stmt = pg_insert(skills).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
                )


class PostgresModelCatalog(_CatalogBase):
    """Durable model catalog over the ``models`` table (migration 0005)."""

    async def load_all(self) -> list[Model]:
        async with self._sessions() as session:
            rows = await session.execute(select(models).order_by(models.c.model_key))
        return [_row_to_model(row) for row in rows]

    async def upsert(self, model: Model) -> None:
        values = _model_values(model)
        stmt = pg_insert(models).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
                )


class PostgresProviderCatalog(_CatalogBase):
    """Durable provider ENTITY catalog over ``providers`` (migration 0005).

    The ProviderManifest is NOT here by decision (module docstring): the
    composition root pairs loaded entities with the code-shipped
    manifests when hydrating the ProviderRegistry.
    """

    async def load_all(self) -> list[Provider]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(providers).order_by(providers.c.provider_key)
            )
        return [_row_to_provider(row) for row in rows]

    async def upsert(self, provider: Provider) -> None:
        values = _provider_values(provider)
        stmt = pg_insert(providers).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
                )
