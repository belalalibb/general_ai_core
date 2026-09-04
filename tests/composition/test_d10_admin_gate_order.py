"""R168 D-10 — admin admission precedes body validation on EVERY /v1/admin/* route.

Fail-first evidence (defect ledger D-10): a NON-ADMIN session posting ``{}``
to typed admin routes received 422 with field-level schema hints, because
FastAPI validated the body before ``_admit(request)`` ran. Route enumeration
over the served OpenAPI: every ``/v1/admin/*`` operation must now answer 403
``unauthorized`` to a non-admin session and 401 ``unauthenticated`` to an
anonymous caller — regardless of body — while an ADMIN session still reaches
validation (the 422 with hints is an admin-only observation).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re

import httpx

from apps.composition.runtime import RuntimeProfile, build_runtime_profile

ADMIN_EMAIL = "gate-admin@example.test"
USER_EMAIL = "gate-user@example.test"
PASSWORD = "correct horse battery staple"
_UUID = "00000000-0000-4000-8000-000000000000"
_BODY = {"post": {}, "put": {}, "patch": {}}


def _session(profile: RuntimeProfile, email: str) -> str:
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(email, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(email, PASSWORD).token


def _admin_ops(profile: RuntimeProfile) -> list[tuple[str, str]]:
    paths = profile.app.openapi()["paths"]
    ops = [
        (method.upper(), re.sub(r"\{[^}]+\}", _UUID, path))
        for path, methods in sorted(paths.items())
        if path.startswith("/v1/admin/")
        for method in methods
    ]
    assert len(ops) >= 55, "enumeration must cover the whole admin surface (59 at R168)"
    return ops


async def _sweep(
    profile: RuntimeProfile, headers: dict[str, str]
) -> list[tuple[str, str, int, str]]:
    out: list[tuple[str, str, int, str]] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
    ) as client:
        for method, path in _admin_ops(profile):
            response = await client.request(
                method, path, json=_BODY.get(method.lower()), headers=headers
            )
            body = response.json()
            code = body["error"]["code"] if isinstance(body, dict) and "error" in body else ""
            out.append((method, path, response.status_code, code))
    return out


def test_non_admin_session_is_403_on_every_admin_operation_before_validation() -> None:
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    token = _session(profile, USER_EMAIL)
    rows = asyncio.run(_sweep(profile, {"Authorization": f"Bearer {token}"}))
    leaks = [r for r in rows if (r[2], r[3]) != (403, "unauthorized")]
    assert leaks == [], f"non-admin saw something other than the constant 403: {leaks}"


def test_anonymous_is_401_on_every_admin_operation_before_validation() -> None:
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    rows = asyncio.run(_sweep(profile, {}))
    leaks = [r for r in rows if (r[2], r[3]) != (401, "unauthenticated")]
    assert leaks == [], f"anonymous saw something other than the constant 401: {leaks}"


def test_admin_session_still_reaches_validation() -> None:
    # The gate reorders, it does not swallow: an ADMIN posting {} to a
    # typed route gets the honest 422 — schema hints are admin-only.
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    token = _session(profile, ADMIN_EMAIL)

    async def probe() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
        ) as client:
            return await client.post(
                "/v1/admin/scenarios", json={}, headers={"Authorization": f"Bearer {token}"}
            )

    response = asyncio.run(probe())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
