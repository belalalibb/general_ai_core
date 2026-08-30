"""HTTP surface for the Admin Agent — /v1/agent/* (AA-2).

Mounted by ``apps/composition/admin_console.py`` (apps/api is NOT touched
this phase — allowed-files constraint). Session resolution rebuilds the
AA-1 posture: Bearer token → identity session → Principal, ``is_admin``
from the composition-data email allowlist. Every route: anonymous ⇒ the
ONE constant 401; non-admin ⇒ 403. Unknown execution ids ⇒ uniform 404
(validation_error body — the recorded unknown-resource mapping).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from apps.admin_agent.dispatcher import ToolRegistry
from apps.admin_agent.service import AdminAgentService
from apps.api.app import Principal
from apps.api.auth import AuthSurface, bearer_token, unauthenticated
from apps.api.errors import error_response
from core.contracts.errors import ErrorCode
from core.identity.errors import SessionInvalid

Resolver = Callable[[Request], Principal | JSONResponse]


def session_resolver(auth: AuthSurface) -> Resolver:
    """Per-request Principal resolution over the injected AuthSurface."""

    def resolve(request: Request) -> Principal | JSONResponse:
        token = bearer_token(request)
        if token is None:
            return unauthenticated()
        try:
            user = auth.identity.get_user_for_session(token)
        except SessionInvalid:
            return unauthenticated()
        return Principal(
            tenant_id=user.tenant_id,
            user_id=user.id,
            is_admin=user.email in auth.admin_emails,
        )

    return resolve


class ConverseRequest(BaseModel):
    """POST /v1/agent/converse body — closed shape."""

    model_config = ConfigDict(extra="forbid")

    message: str


def create_agent_router(
    service: AdminAgentService,
    registry: ToolRegistry,
    *,
    resolve: Resolver,
) -> APIRouter:
    router = APIRouter(prefix="/v1/agent")

    def _admit(request: Request) -> Principal | JSONResponse:
        resolved = resolve(request)
        if isinstance(resolved, JSONResponse):
            return resolved
        if not resolved.is_admin:
            return error_response(ErrorCode.UNAUTHORIZED, "Admin access required.")
        return resolved

    def _unknown_execution() -> JSONResponse:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Unknown execution id.",
            http_status=404,
        )

    @router.get("/tools")
    async def tools(request: Request) -> JSONResponse:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return JSONResponse(status_code=200, content={"tools": registry.describe()})

    @router.post("/converse")
    async def converse(request: Request, body: ConverseRequest) -> JSONResponse:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        if not body.message or len(body.message) > 100_000:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "message must be 1..100000 characters",
                details={"field": "message"},
            )
        answer = await service.converse(admitted, body.message)
        return JSONResponse(
            status_code=200,
            content=answer.model_dump(mode="json", exclude_none=True),
        )

    @router.get("/executions/{execution_id}/trace")
    async def trace(request: Request, execution_id: str) -> JSONResponse:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        try:
            parsed = UUID(execution_id)
        except ValueError:
            return _unknown_execution()
        result = service.trace(admitted, parsed)
        if result is None:
            return _unknown_execution()
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json", exclude_none=True)
        )

    @router.get("/executions/{execution_id}/diagnosis")
    async def diagnosis(request: Request, execution_id: str) -> JSONResponse:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        try:
            parsed = UUID(execution_id)
        except ValueError:
            return _unknown_execution()
        result = service.diagnose(admitted, parsed)
        if result is None:
            return _unknown_execution()
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json", exclude_none=True)
        )

    return router
