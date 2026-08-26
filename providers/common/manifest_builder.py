"""Shared builder for scaffold template manifests (31 §7, T-IMPL-020).

Every template manifest carries the exact 31 §7 marker set:

- ``status: template_disabled``
- ``is_template: true``
- ``is_functional: false``
- ``real_provider_required: true``
- ``auth: types: []`` (verbatim; the INTENDED real auth shape is recorded in
  ``notes`` per 31 §12 diversity, because templates hold no credentials)
- ``models: discovery: not_implemented``
- scaffold notes (31 §7 verbatim lines first)

31 §12: unsupported modules are marked *not implemented / not applicable* —
never as TODOs implying mandatory work. That is why ``rate_limits.strategy``
and ``errors.mapping`` say ``not_implemented`` here.
"""

from __future__ import annotations

from core.contracts.provider import (
    ManifestAccountPool,
    ManifestAgentModule,
    ManifestAuth,
    ManifestErrors,
    ManifestHealth,
    ManifestModels,
    ManifestRateLimits,
    ManifestSecurity,
    ProviderCapabilities,
    ProviderManifest,
    ProviderOperation,
)

#: 31 §7 verbatim scaffold notes — present on every template manifest.
TEMPLATE_NOTES: tuple[str, ...] = (
    "This is a scaffold template only.",
    "Do not activate without a real provider adapter and contract tests.",
)


def build_template_manifest(
    *,
    template_id: str,
    name: str,
    capabilities: ProviderCapabilities,
    operations: list[ProviderOperation],
    intended_auth_shape: str,
    extra_notes: tuple[str, ...] = (),
    account_pool_supported: bool = False,
    agent_module: ManifestAgentModule | None = None,
    security: ManifestSecurity | None = None,
) -> ProviderManifest:
    """Build one disabled template manifest with the 31 §7 marker set.

    ``intended_auth_shape`` documents the provider shape the template stands
    for (api_key / oauth / session_cookie / no-auth local, 31 §12) without
    declaring functional auth — templates declare ``types: []`` verbatim.
    """
    notes = (
        *TEMPLATE_NOTES,
        f"Intended real-provider auth shape: {intended_auth_shape} (31 §12).",
        *extra_notes,
    )
    return ProviderManifest(
        id=template_id,
        name=name,
        version="0.0.0-template",
        status="template_disabled",
        is_template=True,
        is_functional=False,
        real_provider_required=True,
        auth=ManifestAuth(types=[], supports_refresh=False),
        account_pool=ManifestAccountPool(supported=account_pool_supported),
        capabilities=capabilities,
        operations=operations,
        models=ManifestModels(discovery="not_implemented"),
        rate_limits=ManifestRateLimits(strategy="not_implemented"),
        health=ManifestHealth(checks=[]),
        errors=ManifestErrors(mapping="not_implemented"),
        notes=list(notes),
        agent_module=agent_module,
        security=security,
    )
