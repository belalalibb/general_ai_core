"""Development-agent HTTP read surface (R169 A6).

One endpoint, modelled on ``GET /v1/models``: enumerate the publish modes a
UI dropdown may bind to for a repository binding — never hard-coded on the
client.

    GET /v1/dev/bindings/{binding_id}/publish-modes

* bearer/principal resolution is injected (same ``resolve`` seam the admin
  router uses); the route never reads a client-supplied tenant id;
* tenant-scoped through ``RepoBindingRegistry.get`` — an unknown id and a
  foreign-tenant id answer the SAME 404 (anti-enumeration, 20 §6);
* the body is the typed ``PublishModesResponse`` from ``core.contracts`` —
  ``direct_push`` is listed but ``selectable=false`` with the machine-readable
  ``reason`` unless the binding explicitly allows it (INV-2, INV-5).

This module is a mountable router only. Composing it into the API app is an
operator decision (see ``docs/r169/R169_CLOSURE_REPORT.md``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from apps.api.errors import error_response
from core.contracts.errors import ErrorCode
from core.contracts.publish_mode import PublishModesResponse, publish_mode_options

from .git_tools import BindingLookupRefused, RepoBindingRegistry

DEV_ROUTER_PREFIX = "/v1/dev"


class TenantPrincipal(Protocol):
    """The only identity fact this surface needs: the caller's tenant."""

    @property
    def tenant_id(self) -> UUID: ...


PrincipalResolver = Callable[[Request], TenantPrincipal | JSONResponse]


def _binding_not_found(binding_id: str) -> JSONResponse:
    # Closed 10 §9 set has no not_found — validation_error body, HTTP 404
    # (same recorded mapping as the admin router).
    return error_response(
        ErrorCode.VALIDATION_ERROR,
        "Unknown repository binding id.",
        details={"binding_id": binding_id},
        http_status=404,
    )


def create_dev_router(
    bindings: RepoBindingRegistry,
    *,
    resolve: PrincipalResolver,
) -> APIRouter:
    """Build the ``/v1/dev/*`` read router over a per-request principal resolver."""
    router = APIRouter(prefix=DEV_ROUTER_PREFIX)

    @router.get("/bindings/{binding_id}/publish-modes")
    async def list_publish_modes(request: Request, binding_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(binding_id)
        except ValueError:
            return _binding_not_found(binding_id)
        try:
            binding = bindings.get(parsed, tenant_id=caller.tenant_id)
        except BindingLookupRefused:
            # BINDING_UNKNOWN and BINDING_TENANT_MISMATCH collapse to one 404.
            return _binding_not_found(binding_id)
        body = PublishModesResponse(
            binding_id=str(binding.id),
            modes=publish_mode_options(binding.allowed_modes),
        )
        return JSONResponse(
            status_code=200,
            content=body.model_dump(mode="json"),
        )

    return router


__all__ = [
    "DEV_ROUTER_PREFIX",
    "PrincipalResolver",
    "TenantPrincipal",
    "create_dev_router",
]
