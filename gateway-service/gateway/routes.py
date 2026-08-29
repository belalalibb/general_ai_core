"""HTTP surface — thin: validate -> dispatch -> respond. No business logic.

API surface (Deliverable C / OPEN-1):
    POST /v1/execute   auth   execute any declared operation (envelope
                              carries `operation` — single source of truth)
    GET  /v1/describe  auth   manifest projection (per X-Route-Token)
    GET  /v1/models    auth   declared model list
    GET  /v1/health    auth   provider health (UNKNOWN is legal)
    GET  /healthz      none   process liveness only (no provider info)

X-Route-Token is a HEADER on ALL surfaces including GETs (OPEN-3) — the
token never appears in a URL. Route addressing exists ONLY via that header.

Status discipline (contracts.HTTP_STATUS_MAP): 200 carries both success and
execution failures; 400 malformed envelope; 401 auth; 404 uniform unknown
route (anti-enumeration); 500 sanitized internal fault.

Gateway-level retries: ZERO in v1 (billing integrity, ADR-0008).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from gateway import API_VERSION
from gateway.auth import AuthOutcome, auth_error_body, authenticate
from gateway.config import GatewayConfig
from gateway.context import build_context
from gateway.contracts import (
    HEADER_GATEWAY_SECRET,
    HEADER_GATEWAY_SECRET_VERSION,
    HEADER_ROUTE_TOKEN,
    UNKNOWN_ROUTE_BODY,
    ErrorCategory,
    RequestEnvelope,
    ResponseEnvelope,
)
from gateway.credentials import check_credential_mode
from gateway.discovery import project_describe, project_health, project_models
from gateway.errors import internal_fault, make_error
from gateway.provider_registry import ProviderRegistry, RegisteredProvider
from gateway.route_registry import RouteRegistry


def _auth_or_response(config: GatewayConfig, request: Request) -> JSONResponse | None:
    result = authenticate(
        config,
        request.headers.get(HEADER_GATEWAY_SECRET),
        request.headers.get(HEADER_GATEWAY_SECRET_VERSION),
    )
    if result.outcome is AuthOutcome.OK:
        return None
    return JSONResponse(status_code=401, content=auth_error_body(result))


def _resolve_provider_or_response(
    routes: RouteRegistry,
    providers: ProviderRegistry,
    request: Request,
) -> RegisteredProvider | JSONResponse:
    """Uniform 404 for unknown/revoked/disabled — anti-enumeration."""

    lookup = routes.lookup(request.headers.get(HEADER_ROUTE_TOKEN))
    if not lookup.routable:
        return JSONResponse(status_code=404, content=UNKNOWN_ROUTE_BODY)
    provider = providers.get(lookup.slug or "")
    if provider is None:
        # Route map points at a slug that is not registered — identical 404.
        return JSONResponse(status_code=404, content=UNKNOWN_ROUTE_BODY)
    return provider


def _failure(error_kwargs: dict[str, Any], latency_ms: int) -> ResponseEnvelope:
    return ResponseEnvelope(
        succeeded=False,
        output=None,
        usage=None,
        latency_ms=latency_ms,
        error=make_error(**error_kwargs),
    )


def build_router(
    config: GatewayConfig,
    routes: RouteRegistry,
    providers: ProviderRegistry,
) -> APIRouter:
    router = APIRouter()
    prefix = f"/{API_VERSION}"

    @router.get("/healthz")
    async def healthz() -> dict[str, str]:
        # Liveness ONLY: no provider info, no secrets, no versions.
        return {"status": "ok"}

    @router.post(f"{prefix}/execute")
    async def execute(request: Request) -> JSONResponse:
        started = time.monotonic()

        denied = _auth_or_response(config, request)
        if denied is not None:
            return denied

        resolved = _resolve_provider_or_response(routes, providers, request)
        if isinstance(resolved, JSONResponse):
            return resolved
        provider = resolved

        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "category": ErrorCategory.BAD_REQUEST.value,
                        "retryable": False,
                        "message": "request body is not valid JSON",
                    }
                },
            )
        try:
            envelope = RequestEnvelope.model_validate(body)
        except ValidationError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "category": ErrorCategory.BAD_REQUEST.value,
                        "retryable": False,
                        "message": "malformed request envelope",
                    }
                },
            )

        def latency() -> int:
            return int((time.monotonic() - started) * 1000)

        # Undeclared operation -> 200 execution failure (example C).
        if envelope.operation not in provider.definition.operations:
            failure = _failure(
                {
                    "category": ErrorCategory.UNSUPPORTED_CAPABILITY,
                    "message": "operation not declared by this provider",
                },
                latency(),
            )
            return JSONResponse(status_code=200, content=failure.model_dump())

        # Credential mode must match the DEFINITION (200 execution failure).
        mode_error = check_credential_mode(provider.definition, envelope.credential)
        if mode_error is not None:
            failure = ResponseEnvelope(
                succeeded=False,
                output=None,
                usage=None,
                latency_ms=latency(),
                error=mode_error,
            )
            return JSONResponse(status_code=200, content=failure.model_dump())

        try:
            handlers = provider.handlers()  # lazy import + parity check
            handler = handlers[envelope.operation]
            result = await handler(build_context(envelope))
            response = ResponseEnvelope(
                succeeded=result.succeeded,
                output=result.output,
                usage=result.usage,
                latency_ms=latency(),
                error=result.error,
            )
            return JSONResponse(status_code=200, content=response.model_dump())
        except Exception:  # noqa: BLE001 — boundary catch-all, sanitized on purpose
            # 500: sanitized fault; exception class names never cross the wire.
            failure = ResponseEnvelope(
                succeeded=False,
                output=None,
                usage=None,
                latency_ms=latency(),
                error=internal_fault(),
            )
            return JSONResponse(status_code=500, content=failure.model_dump())

    @router.get(f"{prefix}/describe")
    async def describe(request: Request) -> JSONResponse:
        denied = _auth_or_response(config, request)
        if denied is not None:
            return denied
        resolved = _resolve_provider_or_response(routes, providers, request)
        if isinstance(resolved, JSONResponse):
            return resolved
        return JSONResponse(
            status_code=200,
            content=project_describe(resolved.definition).model_dump(),
        )

    @router.get(f"{prefix}/models")
    async def models(request: Request) -> JSONResponse:
        denied = _auth_or_response(config, request)
        if denied is not None:
            return denied
        resolved = _resolve_provider_or_response(routes, providers, request)
        if isinstance(resolved, JSONResponse):
            return resolved
        return JSONResponse(
            status_code=200,
            content=project_models(resolved.definition).model_dump(),
        )

    @router.get(f"{prefix}/health")
    async def health(request: Request) -> JSONResponse:
        denied = _auth_or_response(config, request)
        if denied is not None:
            return denied
        resolved = _resolve_provider_or_response(routes, providers, request)
        if isinstance(resolved, JSONResponse):
            return resolved
        return JSONResponse(
            status_code=200,
            content=project_health(resolved.definition).model_dump(),
        )

    return router
