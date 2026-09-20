"""R194-A — security response headers + admin-gated OpenAPI documents (CS1 I-1 / I-2).

RED-first for `apps/api/app.py`: every response carries the hardening headers
(nosniff, frame DENY, referrer policy, CSP) while HSTS is opt-in
(`create_app(hsts=True)`); `create_app(openapi_public=False)` puts
`/openapi.json` and `/redoc` behind the SAME admin posture as `/v1/admin/*`
(401 tokenless, 403 non-admin, 200 admin) without touching the in-process
`app.openapi()` used by the freeze derivation. The composition root computes
`openapi_public` as `OPENAPI_PUBLIC` env if set, else `not durable`.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.composition.runtime import (
    OPENAPI_PUBLIC_ENV,
    RuntimeProfile,
    build_runtime_profile,
    openapi_public_from_env,
)
from core.execution.service import ExecutionService
from core.routing.router import SimpleScoringRouter
from tests.api.test_execute_api import World

ADMIN_EMAIL = "r194-admin@example.test"
USER_EMAIL = "r194-user@example.test"
PASSWORD = "correct horse battery staple"

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(_seconds: float) -> None:
    return None


def _app(world: World, **kwargs: Any) -> FastAPI:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        healthz=True,
        sse=True,
        **kwargs,
    )


async def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers or {})


def _session(profile: RuntimeProfile, email: str) -> str:
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(email, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(email, PASSWORD).token


def _assert_hardening_headers(response: httpx.Response) -> None:
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == EXPECTED_CSP


class TestHeadersOnEveryResponse:
    def test_healthz_json_and_error_responses_carry_headers(self) -> None:
        app = _app(World())
        for path, status in (
            ("/healthz", 200),
            ("/v1/executions", 200),
            ("/v1/executions/00000000-0000-4000-8000-000000000000", 404),
            ("/does-not-exist", 404),
        ):
            response = run(_get(app, path))
            assert response.status_code == status, (path, response.text)
            _assert_hardening_headers(response)
            assert "strict-transport-security" not in response.headers

    def test_sse_stream_response_carries_headers(self) -> None:
        app = _app(World())
        response = run(_get(app, "/v1/executions/00000000-0000-4000-8000-000000000000/events"))
        # Unknown execution: the route answers with its recorded envelope —
        # whatever the status, the headers must be present.
        _assert_hardening_headers(response)

    def test_static_ui_mount_carries_headers(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        response = run(_get(profile.app, "/admin/"))
        assert response.status_code == 200
        assert "<script src=" in response.text
        _assert_hardening_headers(response)

    def test_hsts_is_opt_in(self) -> None:
        app = _app(World(), hsts=True)
        response = run(_get(app, "/healthz"))
        assert response.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )
        _assert_hardening_headers(response)


class TestOpenApiDocuments:
    def test_default_is_public(self) -> None:
        app = _app(World())
        assert run(_get(app, "/openapi.json")).status_code == 200
        assert run(_get(app, "/redoc")).status_code == 200

    def test_gated_documents_follow_the_admin_posture(self) -> None:
        profile = build_runtime_profile(
            environ={"ADMIN_EMAILS": ADMIN_EMAIL, OPENAPI_PUBLIC_ENV: "0"}
        )
        app = profile.app
        for path in ("/openapi.json", "/redoc"):
            anonymous = run(_get(app, path))
            assert anonymous.status_code == 401
            assert anonymous.json()["error"]["code"] == "unauthenticated"
            _assert_hardening_headers(anonymous)

        user = _session(profile, USER_EMAIL)
        admin = _session(profile, ADMIN_EMAIL)
        for path in ("/openapi.json", "/redoc"):
            denied = run(_get(app, path, {"Authorization": f"Bearer {user}"}))
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "unauthorized"
            allowed = run(_get(app, path, {"Authorization": f"Bearer {admin}"}))
            assert allowed.status_code == 200
        assert (
            "/v1/execute"
            in run(_get(app, "/openapi.json", {"Authorization": f"Bearer {admin}"})).json()["paths"]
        )
        # In-process derivation (freeze guard, apps.cli check) is unaffected.
        assert "/v1/execute" in app.openapi()["paths"]

    def test_gate_without_auth_seam_is_a_composition_error(self) -> None:
        # A fixed principal has no admin identity to admit — gating would be
        # unreachable; refuse loudly instead of composing a locked door.
        with pytest.raises(ValueError, match="openapi_public"):
            _app(World(), openapi_public=False)

    def test_in_memory_profile_stays_public_by_default(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        assert run(_get(profile.app, "/openapi.json")).status_code == 200

    def test_env_resolution_rule(self) -> None:
        assert openapi_public_from_env({}, durable=False) is True
        assert openapi_public_from_env({}, durable=True) is False
        assert openapi_public_from_env({OPENAPI_PUBLIC_ENV: "1"}, durable=True) is True
        assert openapi_public_from_env({OPENAPI_PUBLIC_ENV: "0"}, durable=False) is False
        with pytest.raises(ValueError, match=OPENAPI_PUBLIC_ENV):
            openapi_public_from_env({OPENAPI_PUBLIC_ENV: "maybe"}, durable=False)
