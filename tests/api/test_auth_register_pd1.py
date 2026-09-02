"""P-D.1 — /v1/auth/register + /v1/auth/verify HTTP surface tests.

Operator authorization (verbatim): "نفّذ P-D خيار A1." — end-user UI needs
a self-serve account path; the PROVEN service-level register/verify_email
policies (41 §41, P-A.2 port parity) gain a thin HTTP surfacing, NO new
core code.

Honesty contracts asserted here (module = executable exit criteria):

- register 201 returns the PENDING user projection; the verification
  token NEVER appears in any HTTP body (it travels only through the
  composed EmailSenderPort — console in P-B runtime).
- duplicate email / empty fields collapse into ONE byte-identical 422
  (the route never re-differentiates what the service collapsed).
- invalid token / already-used token collapse into ONE byte-identical
  422 (no redemption oracle; unified VALIDATION_ERROR mapping).
- login before verification is the SAME constant 401 as every other
  login failure (anti-enumeration preserved end-to-end).
- rate limiting: a limited caller creates NO account and no email is
  sent (zero residue); disabled by default so pre-P-D compositions are
  byte-identical (P2).
- closed request shapes: extra fields are rejected (422).

Conventions: asyncio.run + httpx.ASGITransport (ADR-0001 note; no
pytest-asyncio for API tests).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api.auth import AuthSurface, create_auth_router
from core.identity.service import InMemoryIdentityService
from core.runtime.memory import InMemoryRateLimiter


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


# --- fixtures (mirrors tests/api/test_aa1_api_seams.py posture) --------------


class _Hasher:
    """Deterministic test hasher (NOT a security binding)."""

    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"h:{password}"


class _MailSink:
    """Captures verification tokens instead of sending email."""

    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}
        self.sent_count = 0

    def send_verification(self, email: str, token: str) -> None:
        self.tokens[email] = token
        self.sent_count += 1


EMAIL = "enduser@example.test"
PASSWORD = "correct-horse"


def make_app(
    *,
    rate_limits: InMemoryRateLimiter | None = None,
    register_rate_limit: int = 0,
) -> tuple[FastAPI, InMemoryIdentityService, _MailSink]:
    sink = _MailSink()
    identity = InMemoryIdentityService(hasher=_Hasher(), email_sender=sink, default_plan_id=uuid4())
    app = FastAPI()
    app.include_router(
        create_auth_router(
            AuthSurface(
                identity=identity,
                rate_limits=rate_limits,
                register_rate_limit=register_rate_limit,
            )
        )
    )
    return app, identity, sink


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# --- register -----------------------------------------------------------------


class TestRegister:
    def test_register_returns_pending_projection_without_token(self) -> None:
        """201 + pending status; the emailed token is NOT in the body."""
        app, _, sink = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                response = await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["email"] == EMAIL
            assert body["status"] == "pending"
            assert body["verification"] == "sent"
            UUID(body["user_id"])
            UUID(body["tenant_id"])
            # The token went ONLY through the email port.
            token = sink.tokens[EMAIL]
            assert token not in response.text

        run(scenario())

    def test_full_self_serve_flow_register_verify_login(self) -> None:
        """register → verify → login — the P-D.1 acceptance path."""
        app, _, sink = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                created = await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                assert created.status_code == 201
                verified = await c.post("/v1/auth/verify", json={"token": sink.tokens[EMAIL]})
                assert verified.status_code == 200, verified.text
                assert verified.json()["email_verified"] is True
                assert verified.json()["status"] == "active"
                login = await c.post(
                    "/v1/auth/login",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                assert login.status_code == 200, login.text
                assert isinstance(login.json()["token"], str)

        run(scenario())

    def test_rejection_causes_are_byte_identical(self) -> None:
        """Duplicate email and empty password: ONE constant 422 body."""
        app, _, _ = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                first = await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                assert first.status_code == 201
                duplicate = await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                empty = await c.post(
                    "/v1/auth/register",
                    json={"email": "x@example.test", "password": ""},
                )
            assert duplicate.status_code == 422
            assert empty.status_code == 422
            assert duplicate.json() == empty.json()
            assert duplicate.json()["error"]["message"] == "Registration rejected."

        run(scenario())

    def test_extra_fields_rejected(self) -> None:
        """Closed request shape (extra=forbid) — 422 on unknown keys."""
        app, _, _ = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                response = await c.post(
                    "/v1/auth/register",
                    json={
                        "email": EMAIL,
                        "password": PASSWORD,
                        "is_admin": True,
                    },
                )
            assert response.status_code == 422

        run(scenario())

    def test_login_before_verification_is_the_constant_401(self) -> None:
        """PENDING account login = the same anti-enumeration 401."""
        app, _, _ = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                pending = await c.post(
                    "/v1/auth/login",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                unknown = await c.post(
                    "/v1/auth/login",
                    json={"email": "ghost@example.test", "password": PASSWORD},
                )
            assert pending.status_code == 401
            assert unknown.status_code == 401
            assert pending.json() == unknown.json()

        run(scenario())


# --- verify --------------------------------------------------------------------


class TestVerify:
    def test_invalid_and_reused_tokens_are_byte_identical(self) -> None:
        """Garbage token and second redemption: ONE constant 422."""
        app, _, sink = make_app()

        async def scenario() -> None:
            async with _client(app) as c:
                await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                token = sink.tokens[EMAIL]
                first = await c.post("/v1/auth/verify", json={"token": token})
                assert first.status_code == 200
                reused = await c.post("/v1/auth/verify", json={"token": token})
                garbage = await c.post("/v1/auth/verify", json={"token": "not-a-token"})
            assert reused.status_code == 422
            assert garbage.status_code == 422
            assert reused.json() == garbage.json()
            assert reused.json()["error"]["message"] == "Verification failed."

        run(scenario())


# --- rate limiting ---------------------------------------------------------------


class TestRegisterRateLimit:
    def test_limited_caller_creates_no_account_and_sends_no_email(self) -> None:
        """429 beyond the limit; zero residue (no account, no email)."""
        app, identity, sink = make_app(rate_limits=InMemoryRateLimiter(), register_rate_limit=1)

        async def scenario() -> None:
            async with _client(app) as c:
                first = await c.post(
                    "/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD},
                )
                assert first.status_code == 201
                limited = await c.post(
                    "/v1/auth/register",
                    json={"email": "second@example.test", "password": PASSWORD},
                )
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "rate_limited"
            assert limited.json()["error"]["retryable"] is True
            # Zero residue: exactly ONE verification email ever left.
            assert sink.sent_count == 1
            assert "second@example.test" not in sink.tokens

        run(scenario())

    def test_limiting_disabled_by_default(self) -> None:
        """Default surface (limit=0): many registrations, none limited (P2)."""
        app, _, _ = make_app(rate_limits=InMemoryRateLimiter())

        async def scenario() -> None:
            async with _client(app) as c:
                for i in range(5):
                    response = await c.post(
                        "/v1/auth/register",
                        json={
                            "email": f"user{i}@example.test",
                            "password": PASSWORD,
                        },
                    )
                    assert response.status_code == 201

        run(scenario())


# --- surface shape ---------------------------------------------------------------


class TestSurfaceShape:
    def test_routes_present_in_openapi(self) -> None:
        app, _, _ = make_app()
        paths = app.openapi()["paths"]
        assert "post" in paths["/v1/auth/register"]
        assert "post" in paths["/v1/auth/verify"]
