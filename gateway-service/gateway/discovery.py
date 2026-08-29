"""Discovery projections — /v1/describe, /v1/models, /v1/health.

The projection NEVER contains the slug or any upstream identity: only the
DEFINITION's own declared fields cross (display_name is the single name
allowed across the boundary — 5-layer identity model, ADR-0008).
"""

from __future__ import annotations

from gateway.contracts import (
    DescribeResponse,
    HealthResponse,
    ModelsResponse,
    ProviderDefinition,
)


def project_describe(definition: ProviderDefinition) -> DescribeResponse:
    return DescribeResponse(
        display_name=definition.display_name,
        credential_mode=definition.credential_mode,
        capabilities=definition.capabilities,
        operations=definition.operations,
        models=definition.models,
        definition_version=definition.definition_version,
        health_supported=definition.health_supported,
    )


def project_models(definition: ProviderDefinition) -> ModelsResponse:
    return ModelsResponse(models=definition.models)


def project_health(definition: ProviderDefinition) -> HealthResponse:
    """G1: health checks are not implemented; UNKNOWN is the honest answer.

    ``health_supported: false`` => UNKNOWN by contract; true providers will
    get real checks in a later authorized phase.
    """

    return HealthResponse(status="UNKNOWN", checked_at=None)
