"""Composition-root wiring for production infrastructure bindings (Lane C).

This package is the ONLY place that reads deployment environment variables
and constructs real infrastructure clients (boto3/hvac) and remote-gateway
bindings (httpx, ADR-0008). Core never sees
any of this — it receives ports (import-linter contracts 10/11 confine the
clients to infrastructure/, and this package to apps/).

Posture (recorded at R09x, reaffirmed here): "not configured ⇒ binding
absent" — each ``*_from_env`` returns ``None`` when the deployment has not
provided the required variables, and the caller keeps the in-memory
implementation (the dev/test profile ADR-0006/0007 record). Nothing is
ever silently half-configured.
"""

from apps.composition.bridge import AsyncBridge, BridgeClosed
from apps.composition.database import (
    DatabaseBindings,
    DatabaseSettings,
    build_database_bindings,
    database_settings_from_env,
)
from apps.composition.durability import (
    DurableExecutionStore,
    build_durable_execution_store,
)
from apps.composition.gateway import (
    GatewaySettings,
    build_gateway_adapter,
    gateway_secret_resolver_from_secret_manager,
    gateway_settings_from_env,
    route_token_resolver_from_secret_manager,
)
from apps.composition.identity import (
    DurableIdentityService,
    build_durable_identity_service,
)
from apps.composition.secrets import (
    VaultSettings,
    build_secret_manager,
    vault_settings_from_env,
)
from apps.composition.sourcechange import (
    DurableProposalStore,
    DurableSnapshotStore,
    build_durable_sourcechange_stores,
)
from apps.composition.storage import (
    ObjectStorageSettings,
    build_object_storage,
    object_storage_settings_from_env,
)

__all__ = [
    "AsyncBridge",
    "BridgeClosed",
    "DatabaseBindings",
    "DatabaseSettings",
    "DurableExecutionStore",
    "DurableIdentityService",
    "DurableProposalStore",
    "DurableSnapshotStore",
    "build_durable_execution_store",
    "build_durable_identity_service",
    "build_durable_sourcechange_stores",
    "GatewaySettings",
    "ObjectStorageSettings",
    "VaultSettings",
    "build_database_bindings",
    "build_gateway_adapter",
    "build_object_storage",
    "build_secret_manager",
    "gateway_secret_resolver_from_secret_manager",
    "database_settings_from_env",
    "gateway_settings_from_env",
    "route_token_resolver_from_secret_manager",
    "object_storage_settings_from_env",
    "vault_settings_from_env",
]
