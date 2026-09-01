"""Gap 1 composition — onboarding surface wiring + startup hydration.

Binds the EXISTING pieces together at the root (P1 reuse, no parallel
state):

- :class:`core.providers.onboarding.ProviderOnboardingService` gets the
  SAME registries and the SAME ``adapters``/``credential_refs`` maps the
  composed ExecutionService reads (instance-agreement duty) — a
  successfully onboarded provider is immediately routable and passes
  ``_validate_route`` the moment an admin enables it.
- Durability (ADR-0011 + migration 0018): providers/models/bindings
  write through the EXISTING Postgres catalogs; the per-provider gateway
  registration definition (refs only, 20 §5) is stored so this module's
  :func:`hydrate_gateway_providers` can rebuild the manifest
  (build_gateway_manifest) and the adapter (build_gateway_adapter) at
  the next startup — executability across restart.
- DECISION 2 (binding): canonical-gateway providers ONLY. A foreign/
  native-API provider still requires its own adapter/shim and never
  reaches this wiring.

Secret custody: route tokens resolve through the SecretManagerPort at the
last moment under the fixed PLATFORM custody scope; no secret value ever
appears in a row, a log, or a repr.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError

from apps.api.provider_onboarding import (
    GatewayOnboardRequest,
    ProviderOnboardingSurface,
)
from apps.composition.bridge import AsyncBridge
from apps.composition.gateway import (
    GatewaySettings,
    build_gateway_adapter,
    route_token_resolver_from_secret_manager,
)
from core.contracts.domain import Model, Provider, ProviderModelBinding
from core.contracts.provider import (
    ProviderCapabilities,
    ProviderManifest,
    ProviderOperation,
)
from core.providers.onboarding import ProviderOnboardingService
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.secrets import SecretManagerPort
from providers.real.gateway import build_gateway_manifest

if TYPE_CHECKING:
    from apps.composition.database import DatabaseBindings

#: Fixed custody scope for PLATFORM-owned gateway secrets (route tokens).
#: Deterministic across restarts so refs stored in a durable secret manager
#: (Vault) stay resolvable — unlike the per-boot uuid4 scope real-provider
#: env keys use (those refs are re-minted every boot from the env value).
PLATFORM_TENANT_ID = UUID("00000000-0000-0000-0000-00000000ada1")


def manifest_from_definition(definition: GatewayOnboardRequest) -> ProviderManifest:
    """Re-derive the manifest from the operator's registration definition.

    Pure and deterministic — the SAME derivation serves the onboarding
    route (fresh request) and startup hydration (persisted definition),
    so the two can never drift (one derivation, two consumers).
    OPEN-2 exclusions and unknown operation/capability keys refuse here.
    """
    try:
        operations = [ProviderOperation(op) for op in definition.operations]
    except ValueError as exc:
        raise ValueError(f"unknown provider operation: {exc}") from None
    try:
        capabilities = ProviderCapabilities(**definition.capabilities)
    except ValidationError as exc:
        raise ValueError(
            f"unknown capability key: {exc.errors()[0].get('loc', ('?',))[0]}"
        ) from None
    return build_gateway_manifest(
        provider_key=definition.provider_key,
        display_name=definition.display_name,
        operations=operations,
        capabilities=capabilities,
        static_models=definition.static_models,
        definition_version=definition.definition_version,
    )


def adapter_from_definition(
    settings: GatewaySettings,
    secrets: SecretManagerPort,
    manifest: ProviderManifest,
    definition: GatewayOnboardRequest,
) -> ProviderAdapterPort:
    """Build the RemoteGatewayAdapter for one registration definition.

    The route token resolves through the SecretManagerPort at the last
    moment (20 §5); the gateway shared secret stays the env-settings
    snapshot (G2 binding). Same derivation for route and hydration.
    """
    return build_gateway_adapter(
        settings,
        manifest=manifest,
        route_token_resolver=route_token_resolver_from_secret_manager(
            secrets,
            tenant_id=PLATFORM_TENANT_ID,
            route_token_ref=definition.route_token_ref,
        ),
        credential_mode=definition.credential_mode,
    )


class CatalogPersistence:
    """OnboardingPersistencePort over the Postgres catalogs (sync doorway).

    Same AsyncBridge posture as identity/durability: the pool lives on
    the bridge loop; every durable call crosses it. Failures re-raise
    verbatim (loud, never absorbed).
    """

    def __init__(self, bindings: DatabaseBindings, bridge: AsyncBridge) -> None:
        self._bindings = bindings
        self._bridge = bridge

    def persist_provider(self, provider: Provider) -> None:
        self._bridge.run(self._bindings.provider_catalog.upsert(provider))

    def persist_model(self, model: Model) -> None:
        self._bridge.run(self._bindings.model_catalog.upsert(model))

    def persist_binding(self, binding: ProviderModelBinding) -> None:
        self._bridge.run(self._bindings.binding_catalog.upsert(binding))


def build_onboarding_surface(
    *,
    providers: ProviderRegistry,
    models: ModelRegistry,
    bindings: BindingRegistry,
    adapters: MutableMapping[UUID, ProviderAdapterPort],
    credential_refs: MutableMapping[UUID, str],
    gateway_settings: GatewaySettings,
    secrets: SecretManagerPort,
    database: DatabaseBindings | None = None,
    bridge: AsyncBridge | None = None,
) -> ProviderOnboardingSurface:
    """Compose the onboarding surface over the SAME live instances.

    ``database``+``bridge`` present ⇒ full durability (catalog
    write-through + ADR-0011 registration row). Absent ⇒ in-memory
    onboarding only (honest dev posture — the report still says what
    happened; nothing survives restart).
    """
    persistence = (
        CatalogPersistence(database, bridge)
        if database is not None and bridge is not None
        else None
    )
    service = ProviderOnboardingService(
        providers=providers,
        models=models,
        bindings=bindings,
        adapters=adapters,
        credential_refs=credential_refs,
        persistence=persistence,
    )

    def _persist_registration(provider_id: UUID, definition: dict[str, object]) -> None:
        assert database is not None and bridge is not None  # guarded below
        bridge.run(database.gateway_registrations.upsert(provider_id, definition))

    return ProviderOnboardingSurface(
        onboarding=service,
        build_manifest=manifest_from_definition,
        build_adapter=lambda manifest, body: adapter_from_definition(
            gateway_settings, secrets, manifest, body
        ),
        persist_registration=(
            _persist_registration if persistence is not None else None
        ),
    )


def hydrate_gateway_providers(
    *,
    database: DatabaseBindings,
    bridge: AsyncBridge,
    providers: ProviderRegistry,
    models: ModelRegistry,
    bindings: BindingRegistry,
    adapters: MutableMapping[UUID, ProviderAdapterPort],
    credential_refs: MutableMapping[UUID, str],
    gateway_settings: GatewaySettings | None,
    secrets: SecretManagerPort | None,
) -> list[str]:
    """Replay durable onboarding rows into the LIVE registries at startup.

    For every ADR-0011 gateway registration row: re-derive the manifest,
    register the persisted provider entity with it, replay its models and
    bindings, and — when the gateway binding is configured — rebuild the
    adapter into the SAME maps the ExecutionService reads. Without
    gateway settings the DATA still hydrates (catalog visibility) but the
    provider stays honestly non-executable (AdapterNotBound at routing —
    a loud refusal, never a fake adapter). Returns hydrated provider keys.
    """
    registrations = bridge.run(database.gateway_registrations.load_all())
    if not registrations:
        return []

    provider_rows = {p.id: p for p in bridge.run(database.provider_catalog.load_all())}
    model_rows = {m.id: m for m in bridge.run(database.model_catalog.load_all())}
    binding_rows = bridge.run(database.binding_catalog.load_all())

    hydrated: list[str] = []
    for provider_id, raw_definition in registrations:
        provider = provider_rows.get(provider_id)
        if provider is None:
            # A registration without its provider row is catalog corruption —
            # loud, never skipped silently (FKs should make this impossible).
            msg = f"gateway registration without provider row: {provider_id}"
            raise RuntimeError(msg)
        definition = GatewayOnboardRequest.model_validate(raw_definition)
        manifest = manifest_from_definition(definition)
        providers.register(provider, manifest)
        for binding in binding_rows:
            if binding.provider_id != provider_id:
                continue
            model = model_rows.get(binding.model_id)
            if model is None:
                msg = f"binding without model row: {binding.model_id}"
                raise RuntimeError(msg)
            models.register(model)
            bindings.register(binding)
        if gateway_settings is not None and secrets is not None:
            adapters[provider.id] = adapter_from_definition(
                gateway_settings, secrets, manifest, definition
            )
            credential_refs[provider.id] = definition.credential_ref
        hydrated.append(provider.provider_key)
    return hydrated


__all__ = [
    "PLATFORM_TENANT_ID",
    "CatalogPersistence",
    "adapter_from_definition",
    "build_onboarding_surface",
    "hydrate_gateway_providers",
    "manifest_from_definition",
]
