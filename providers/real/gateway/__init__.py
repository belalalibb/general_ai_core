"""Remote Provider Gateway adapter package (G2; ADR-0008 ACCEPTED 2026-08-29).

Platform-side (control-plane) adapter for providers that execute on the
Remote Provider Gateway data plane (``gateway-service/``, G1 baseline).
Unlike ``providers/real/groq`` this package ships NO fixed manifest:
gateway-backed providers are registered from platform configuration
(one manifest per registered remote provider — ``provider_key``,
``display_name``, declared operations/capabilities/models), built by the
composition seam ``apps/composition/gateway.py``. See
:func:`build_gateway_manifest` for the manifest construction rules.

Credential posture (20 §5): this package contains NO secret material and
no environment reads. The gateway shared secret, the per-provider route
token and any BYOK user keys enter only through injected resolvers bound
by the composition root; all are used at the last moment, header/envelope
only, and never logged or echoed.
"""

from __future__ import annotations

from core.contracts.domain import AuthType
from core.contracts.provider import (
    ManifestAccountPool,
    ManifestAuth,
    ManifestErrors,
    ManifestHealth,
    ManifestModels,
    ManifestRateLimits,
    ProviderCapabilities,
    ProviderManifest,
    ProviderOperation,
)
from providers.real.gateway.adapter import (
    CREDENTIAL_MODE_PLATFORM,
    CREDENTIAL_MODE_USER_KEY,
    EXCLUDED_OPERATIONS_V1,
    GatewayCredentialCheckUnsupported,
    GatewaySecret,
    RemoteGatewayAdapter,
)

__all__ = [
    "CREDENTIAL_MODE_PLATFORM",
    "CREDENTIAL_MODE_USER_KEY",
    "EXCLUDED_OPERATIONS_V1",
    "GatewayCredentialCheckUnsupported",
    "GatewaySecret",
    "RemoteGatewayAdapter",
    "build_gateway_manifest",
]


def build_gateway_manifest(
    *,
    provider_key: str,
    display_name: str,
    operations: list[ProviderOperation],
    capabilities: ProviderCapabilities,
    static_models: list[str] | None = None,
    definition_version: str = "1.0.0",
) -> ProviderManifest:
    """Build the platform manifest for ONE gateway-backed remote provider.

    Configuration-driven (no fixed manifest constant): the platform admin
    registers remote providers with their declared surface; the gateway's
    ``/v1/describe`` is the upstream source of these declarations, but the
    PLATFORM decision of what to register stays a control-plane act —
    nothing is auto-imported (30 §4.2: the registry trusts declarations,
    and this function is where the operator's declaration is shaped).

    Rules enforced:

    - OPEN-2: the v1-excluded operations cannot be declared — honest
      load-time refusal, mirroring the gateway's own registry rule.
    - ``status="disabled"`` always (31 §19 step 13): a remote provider
      stays disabled until its contract verification passes and an admin
      enables it — same posture as every real provider.
    - Identity: ``id=provider_key`` (platform-chosen), ``name=display_name``
      (the ONLY name that crosses the boundary). No slug appears anywhere.
    """
    declared_excluded = sorted({op.value for op in operations} & EXCLUDED_OPERATIONS_V1)
    if declared_excluded:
        msg = (
            f"operations {declared_excluded} are excluded from gateway v1 "
            "(ADR-0008 OPEN-2) and cannot be declared for a gateway-backed provider"
        )
        raise ValueError(msg)
    return ProviderManifest(
        id=provider_key,
        name=display_name,
        version=definition_version,
        status="disabled",  # 31 §19 step 13: disabled until verified + admin-enabled
        is_template=False,
        is_functional=True,
        real_provider_required=False,
        # AuthType.CUSTOM: the platform authenticates to the GATEWAY
        # (shared secret + route token); the upstream auth kind is a
        # gateway-internal fact the platform never learns (ADR-0008).
        auth=ManifestAuth(types=[AuthType.CUSTOM], supports_refresh=False),
        account_pool=ManifestAccountPool(supported=False),
        capabilities=capabilities,
        operations=list(operations),
        models=ManifestModels(
            discovery="dynamic",  # GET /v1/models projection
            static_models=list(static_models or []),
        ),
        rate_limits=ManifestRateLimits(strategy="provider_defined"),
        health=ManifestHealth(checks=["gateway_v1_health_endpoint"]),
        errors=ManifestErrors(mapping="providers/real/gateway/adapter.py:_normalize_http_response"),
        notes=[
            "Remote gateway-backed provider (ADR-0008 data plane; G2 adapter).",
            "Gateway secret / route token / BYOK keys enter via injected "
            "resolvers only; headers and envelope only; never logged.",
            "Usage figures are raw gateway evidence; the platform ledger "
            "remains the sole billing authority (zero gateway retries in v1).",
        ],
    )
