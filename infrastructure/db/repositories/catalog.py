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
- provider_model_bindings (migration 0018) arrived WITH the runtime
  binding-registration surface this docstring originally reserved it
  for: the admin provider-onboarding path (31 §19, core/providers/
  onboarding.py) persists providers/models/bindings write-through so an
  onboarded provider survives restart — exactly the "justified
  migration then, not a speculative one now" this record promised.
  PostgresBindingCatalog below mirrors the shared catalog posture.

Shared repository posture (all four): session FACTORY injected; rows <->
frozen contracts at the boundary (nested contracts round-trip as JSONB
via their own ``model_dump(mode="json")``/``model_validate`` — no
hand-rolled field mapping to drift); these are PLATFORM catalogs (03 §4/
§6 — deliberately NOT tenant-scoped, matching the schema and the parity
suite); ``load_all`` orders deterministically by the human key.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.domain import (
    AgentCapability,
    AgentRuntimeBinding,
    Model,
    Provider,
    ProviderModelBinding,
)
from core.contracts.roles import Role
from core.contracts.skills import Skill, SkillManifest, SkillProvenance
from infrastructure.db.tables import (
    models,
    provider_gateway_registrations,
    provider_model_bindings,
    providers,
    roles,
    skills,
)


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


def _row_to_binding(row: Any) -> ProviderModelBinding:
    return ProviderModelBinding(
        provider_id=row.provider_id,
        model_id=row.model_id,
        provider_model_name=row.provider_model_name,
        endpoint_ref=row.endpoint_ref,
        availability=row.availability,
        limits_metadata=row.limits_metadata,
        capabilities=row.capabilities,
        agent_runtime=(
            AgentRuntimeBinding.model_validate(row.agent_runtime)
            if row.agent_runtime is not None
            else None
        ),
    )


def _binding_values(binding: ProviderModelBinding) -> dict[str, Any]:
    return {
        "provider_id": binding.provider_id,
        "model_id": binding.model_id,
        "provider_model_name": binding.provider_model_name,
        "endpoint_ref": binding.endpoint_ref,
        "availability": binding.availability.value,
        "limits_metadata": dict(binding.limits_metadata),
        "capabilities": dict(binding.capabilities),
        "agent_runtime": (
            binding.agent_runtime.model_dump(mode="json")
            if binding.agent_runtime is not None
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
        """Insert-or-update keyed on the NATURAL key ``model_key`` (Gap 2).

        The durable row's id is FIRST-WRITER-WINS: a later upsert for the
        same key updates every column EXCEPT id, so FK references (bindings)
        stay valid. This serves both consumers — onboarding (stable ids ⇒
        same row either way) and admin status write-through for code-shipped
        entities whose in-memory ids are per-boot (the id-keyed conflict
        would violate the model_key UNIQUE constraint across boots).
        """
        values = _model_values(model)
        stmt = pg_insert(models).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["model_key"], set_=update_cols
                    )
                )

    async def delete(self, model_id: Any) -> None:
        """Remove one model row (Gap 2: REGISTER_MODEL rollback).

        Absent id is a no-op DELETE (idempotent rollback — restoring
        pre-publish ABSENCE twice is still absence). FK RESTRICT from
        provider_model_bindings guards ordering: bindings first.
        """
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(delete(models).where(models.c.id == model_id))


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
        """Insert-or-update keyed on the NATURAL key ``provider_key`` (Gap 2).

        Same first-writer-wins id posture as the model catalog: the id
        column never changes on conflict, so bindings/gateway-registration
        FKs stay valid across per-boot in-memory id churn.
        """
        values = _provider_values(provider)
        stmt = pg_insert(providers).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "id"}
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["provider_key"], set_=update_cols
                    )
                )

    async def delete(self, provider_id: Any) -> None:
        """Remove one provider row (Gap 2: REGISTER_PROVIDER rollback).

        Idempotent (absent id ⇒ no-op). FK RESTRICT from bindings and
        gateway registrations refuses loudly if dependents still exist —
        the caller must remove those first (memory-order mirrored).
        """
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    delete(providers).where(providers.c.id == provider_id)
                )


class PostgresBindingCatalog(_CatalogBase):
    """Durable binding catalog over ``provider_model_bindings`` (0018).

    Upsert is keyed on the COMPOSITE primary key (provider_id, model_id)
    — the natural key the contract defines (one model bound once per
    provider) — so re-onboarding the same pair updates in place. Rows
    hydrate the BindingRegistry at startup exactly like the other four
    catalogs; ordering is deterministic by the composite key.
    """

    async def load_all(self) -> list[ProviderModelBinding]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(provider_model_bindings).order_by(
                    provider_model_bindings.c.provider_id,
                    provider_model_bindings.c.model_id,
                )
            )
        return [_row_to_binding(row) for row in rows]

    async def upsert(self, binding: ProviderModelBinding) -> None:
        values = _binding_values(binding)
        stmt = pg_insert(provider_model_bindings).values(**values)
        update_cols = {
            k: v for k, v in values.items() if k not in ("provider_id", "model_id")
        }
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["provider_id", "model_id"],
                        set_=update_cols,
                    )
                )

    async def delete(self, provider_id: Any, model_id: Any) -> None:
        """Remove one binding row by its composite key (Gap 2 rollback)."""
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    delete(provider_model_bindings).where(
                        (provider_model_bindings.c.provider_id == provider_id)
                        & (provider_model_bindings.c.model_id == model_id)
                    )
                )


class PostgresGatewayRegistrationCatalog(_CatalogBase):
    """Durable gateway registration records (0018; ADR-0011).

    One JSONB ``definition`` row per gateway-backed provider: the
    OPERATOR's registration data (declared operations/capabilities/
    static models + the OPAQUE route_token_ref/credential_ref +
    credential_mode) from which the composition root re-derives the
    manifest (build_gateway_manifest) and rebuilds the adapter
    (build_gateway_adapter) at startup — executability across restart.
    REFS ONLY (20 §5): no secret value is ever a column or a JSON value
    here; the refs resolve through the SecretManagerPort at the last
    moment. The definition SHAPE is validated by the composition layer's
    contract at the boundary (same JSONB posture as manifests in skills
    rows). DECISION 2: canonical-gateway providers only — foreign/
    native-API providers still require an adapter/shim.
    """

    async def load_all(self) -> list[tuple[Any, dict[str, Any]]]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(provider_gateway_registrations).order_by(
                    provider_gateway_registrations.c.provider_id
                )
            )
        return [(row.provider_id, dict(row.definition)) for row in rows]

    async def upsert(self, provider_id: Any, definition: dict[str, Any]) -> None:
        values = {"provider_id": provider_id, "definition": definition}
        stmt = pg_insert(provider_gateway_registrations).values(**values)
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["provider_id"],
                        set_={"definition": definition},
                    )
                )
