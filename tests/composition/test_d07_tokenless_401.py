"""R168 D-07 — a missing bearer is 401 on every protected route (default profile).

Route enumeration over the served OpenAPI of the zero-config profile: every
path that is not in the composition's declared PUBLIC_PATHS must answer 401
``unauthenticated`` to a token-less request, before any body validation
(so no 422, no 403, no 404 leaks route existence to an anonymous caller).
The demo principal is an EXPLICIT dev opt-in (``DEV_DEMO_PRINCIPAL=1``),
closed by default.
"""

from __future__ import annotations

import asyncio
import re

import httpx

from apps.composition.runtime import DEV_DEMO_PRINCIPAL_ENV, PUBLIC_PATHS, build_runtime_profile

_METHOD_BODY = {"post": {}, "put": {}, "patch": {}}
_UUID = "00000000-0000-4000-8000-000000000000"


def _template(path: str) -> str:
    # Fill path params with a well-formed UUID so 401 is not confused with 422.
    return re.sub(r"\{[^}]+\}", _UUID, path)


async def _sweep(app: object, paths: dict[str, dict[str, object]]) -> list[tuple[str, str, int]]:
    leaks: list[tuple[str, str, int]] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        for path, ops in sorted(paths.items()):
            if path in PUBLIC_PATHS:
                continue
            for method in ops:
                body = _METHOD_BODY.get(method)
                response = await client.request(method.upper(), _template(path), json=body)
                if response.status_code != 401:
                    leaks.append((method.upper(), path, response.status_code))
                else:
                    assert response.json()["error"]["code"] == "unauthenticated"
    return leaks


def test_default_profile_has_no_demo_principal() -> None:
    profile = build_runtime_profile(environ={})
    assert profile.demo_principal is None


def test_every_protected_route_is_401_without_token_by_default() -> None:
    profile = build_runtime_profile(environ={})
    paths = profile.app.openapi()["paths"]
    assert len(paths) > 70, "route enumeration must cover the whole served app"
    leaks = asyncio.run(_sweep(profile.app, paths))
    assert leaks == [], f"token-less requests admitted or leaked route state: {leaks}"


def test_public_paths_are_exactly_the_declared_ones() -> None:
    profile = build_runtime_profile(environ={})
    served = set(profile.app.openapi()["paths"])
    assert set(PUBLIC_PATHS) <= served | {"/openapi.json", "/docs", "/redoc"}
    assert "/healthz" in PUBLIC_PATHS
    assert "/v1/auth/login" in PUBLIC_PATHS
    assert "/v1/execute" not in PUBLIC_PATHS
    assert not any(p.startswith("/v1/admin") for p in PUBLIC_PATHS)


def test_dev_opt_in_restores_demo_principal_explicitly() -> None:
    profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})
    assert profile.demo_principal is not None
    assert profile.demo_principal.is_admin is False

    async def probe() -> int:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
        ) as client:
            return (await client.get("/v1/usage")).status_code

    assert asyncio.run(probe()) == 200


def test_only_the_literal_one_opens_the_dev_profile() -> None:
    for raw in ("", "0", "false", "yes", "true"):
        profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: raw})
        assert profile.demo_principal is None, raw
