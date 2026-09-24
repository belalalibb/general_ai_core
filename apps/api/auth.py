"""Auth HTTP surface — /v1/auth/* (Phase AA-1, seam IDN-1).

Binds the PROVEN ``InMemoryIdentityService`` sessions (core/identity/
service.py, 41 §41) to the API as per-request identity. NO new core code —
this module is a thin surfacing, exactly the doc B §5 IDN-1 minimal
addition.

Recorded decisions (AA-1):

- LOGIN (POST /v1/auth/login): every failure path — unknown email, wrong
  password, unverified account, disabled account/tenant — returns ONE
  byte-identical ``unauthenticated`` 401 with a constant message. The
  identity service already collapses these into ``AuthenticationFailed``
  (anti-enumeration, 20 §6); the route preserves that collapse and never
  re-differentiates. Success returns the opaque session token; a LOGIN
  audit event (20 §9 must-audit) is appended when an audit port is bound.
- LOGOUT (POST /v1/auth/logout): ALWAYS 204, idempotent — the response
  must not become a token-validity oracle (a 401-on-unknown-token logout
  would let an attacker probe token liveness). A LOGOUT audit event is
  appended ONLY when a live session was actually revoked (honesty: no
  audit records for no-ops, 41 §49).
- SESSION (GET /v1/auth/session): the caller's OWN identity + the
  ``is_admin`` projection. Tokenless/invalid ⇒ the same constant 401.
- ``is_admin`` comes from a composition-data email allowlist
  (``AuthSurface.admin_emails``) — NOT a rebuilt RBAC system, just the
  single seam a real 20 §3 role binding will later populate (the same
  posture as Principal.is_admin, T-IMPL-032 / R049 boundary (e)).
- Bearer scheme only: a missing header, a non-Bearer scheme, and a
  garbage token are all the SAME constant-message 401 (no scheme oracle).

Recorded decisions (P-D.1 — operator-authorized end-user surface):

- REGISTER (POST /v1/auth/register): thin surfacing of the PROVEN
  ``IdentityServicePort.register`` policy (41 §41) — NO new core code.
  Duplicate-email feedback is inherently observable at this endpoint
  (core/identity/errors.py records this); the DOCUMENTED mitigation is
  rate limiting, bound here through the EXISTING ``RateLimitPort`` seam
  (same posture as the /v1/execute limit, T-IMPL-070): a limited caller
  creates NO account and leaves no state. The limit scope is GLOBAL
  ("auth:register") — per-IP scoping requires trusting proxy headers,
  an infrastructure concern recorded, not silently invented. Disabled
  by default (``register_rate_limit=0``) so every existing composition
  is byte-identical (P2).
- VERIFY (POST /v1/auth/verify): redeems the single-use emailed token
  (``verify_email``). Invalid and already-used tokens collapse into ONE
  constant 422 (unified VALIDATION_ERROR mapping) — the response never
  separates the two (no redemption
  oracle). Tokens are opaque high-entropy values; brute-force pressure
  is absorbed by the same optional register-scope limiter posture.
- NO audit events for register/verify: ``AuditEventType`` (20 §9) is a
  CLOSED set carried verbatim and contains no registration value —
  inventing one would widen a frozen contract (41 §49: never fake a
  record type the spec does not name).

Recorded decisions (completion program v2, operator rulings D-1 = b and D-2):

- DEV ONBOARDING (C-02, D-1 = b): on the IN-MEMORY profile ONLY, the
  composition may hand the router a ``dev_verification_tokens`` capture
  (the SAME token the ConsoleEmailSender prints). The register response
  then carries ``verification: "dev_token"`` plus
  ``dev_verification_token`` and an explicit ``dev_note`` naming this as
  development / in-memory behaviour. The durable profile never binds the
  capture, so its response is byte-identical (``verification: "sent"``).
  This is NOT email verification and is labelled so in the body.
- COOKIE SESSION (C-05, D-2): the SAME opaque session token the identity
  service issues is ALSO set as an ``HttpOnly; SameSite=Strict; Path=/``
  cookie (``qevion_session``) on login and cleared on logout. Resolution
  order is Bearer FIRST, cookie second (``session_token``): API clients
  are unchanged; browsers no longer hold the token in script-reachable
  storage. CSRF posture: state-changing requests carrying ONLY the cookie
  must also present ``X-Requested-With: QEVION`` (a custom header a
  cross-site form cannot set; SameSite=Strict is the second layer) —
  enforced in the app admission middleware, never here. Expiry is the
  identity service's (revocation on logout; no separate cookie lifetime
  is invented — the cookie is a session cookie).
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from apps.api.errors import error_response
from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.errors import ErrorCode
from core.identity.errors import (
    AuthenticationFailed,
    RegistrationError,
    SessionInvalid,
    VerificationFailed,
)
from core.identity.ports import IdentityServicePort
from core.runtime.ports import RateLimitPort

if TYPE_CHECKING:  # annotation only — apps.api.app imports this module (no cycle)
    from apps.api.app import Principal

#: One constant client-facing message for EVERY auth failure (20 §6).
_AUTH_FAILED_MESSAGE = "Authentication failed."

#: C-05 (D-2): the HttpOnly session cookie name and the CSRF header a
#: cookie-only state-changing request must carry (browser same-origin fact).
SESSION_COOKIE = "qevion_session"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "QEVION"


@dataclass(frozen=True)
class AuthSurface:
    """Everything the /v1/auth/* router composes over — injected, existing.

    ``admin_emails`` is composition DATA (the allowlist the deployment
    grants admin to); ``audit`` is optional — absent means login/logout
    events are not recorded, never faked (41 §49).
    """

    identity: IdentityServicePort
    admin_emails: frozenset[str] = frozenset()
    audit: AuditLogPort | None = None
    #: P-D.1 — optional registration admission control (the documented
    #: RegistrationError mitigation). ``None``/``0`` ⇒ no limiting; every
    #: pre-P-D composition is byte-identical (P2).
    rate_limits: RateLimitPort | None = None
    register_rate_limit: int = 0
    register_rate_window_seconds: float = 3600.0
    #: C-02 (D-1 = b): IN-MEMORY profile only — the composition's capture of
    #: issued verification tokens (email -> token). ``None`` (durable) ⇒ the
    #: register response is byte-identical to the pre-C-02 shape.
    dev_verification_tokens: MutableMapping[str, str] | None = None
    #: C-05 (D-2): set ``Secure`` on the session cookie (composition data;
    #: the local HTTP dev profile leaves it False or the browser drops it).
    cookie_secure: bool = False


class LoginRequest(BaseModel):
    """POST /v1/auth/login body — closed shape (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class RegisterRequest(BaseModel):
    """POST /v1/auth/register body — closed shape (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    preferred_language: str = "en"


class VerifyRequest(BaseModel):
    """POST /v1/auth/verify body — closed shape (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    token: str


def bearer_token(request: Request) -> str | None:
    """Extract the Bearer token or None (missing/malformed/other scheme)."""
    header = request.headers.get("Authorization")
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def cookie_token(request: Request) -> str | None:
    """C-05: the HttpOnly session cookie value or None."""
    value = request.cookies.get(SESSION_COOKIE)
    return value if value else None


def session_token(request: Request) -> str | None:
    """The ONE session-token resolution: Bearer first, HttpOnly cookie second.

    A present-but-malformed Authorization header still yields None (the
    Bearer rule is unchanged); the cookie is consulted only when no Bearer
    token was presented, so API clients see byte-identical behaviour.
    """
    token = bearer_token(request)
    if token is not None:
        return token
    return cookie_token(request)


def csrf_ok(request: Request) -> bool:
    """C-05 CSRF rule for COOKIE-ONLY state-changing requests.

    Safe methods and Bearer-carrying requests are always fine; a request
    authenticated ONLY by the cookie must carry the custom header.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    if bearer_token(request) is not None or cookie_token(request) is None:
        return True
    return request.headers.get(CSRF_HEADER) == CSRF_HEADER_VALUE


def csrf_rejected() -> JSONResponse:
    """The ONE refusal for a cookie-only state change without the CSRF header."""
    return error_response(
        ErrorCode.UNAUTHORIZED,
        f"Cookie-authenticated state changes require the {CSRF_HEADER} header.",
        details={"header": CSRF_HEADER},
    )


def set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    """Bind the session token as an HttpOnly, SameSite=Strict session cookie."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def unauthenticated() -> JSONResponse:
    """The ONE 401 every auth failure returns (constant message, 20 §6)."""
    return error_response(ErrorCode.UNAUTHENTICATED, _AUTH_FAILED_MESSAGE)


def create_auth_router(surface: AuthSurface, *, fallback: Principal | None = None) -> APIRouter:
    """Build the /v1/auth/* router over the injected identity service.

    ``fallback`` (R160 hybrid mode) is the principal an UNAUTHENTICATED
    caller is resolved to by the app; when set, ``GET /session`` without a
    token describes it honestly (``mode: "demo"``, ``is_admin: false``)
    instead of answering 401 — the UI probes this, it never assumes.
    """
    router = APIRouter(prefix="/v1/auth")

    @router.post("/register", status_code=201)
    async def register(body: RegisterRequest) -> Response:
        # Rate limit FIRST (module docstring: the documented duplicate-
        # feedback mitigation) — a limited caller creates NO account.
        if surface.rate_limits is not None and surface.register_rate_limit > 0:
            within = await surface.rate_limits.hit(
                "auth:register",
                surface.register_rate_limit,
                surface.register_rate_window_seconds,
            )
            if not within:
                return error_response(
                    ErrorCode.RATE_LIMITED,
                    "Rate limit exceeded for registration.",
                    retryable=True,
                    details={"scope": "auth:register"},
                )
        try:
            user = surface.identity.register(body.email, body.password, body.preferred_language)
        except RegistrationError:
            # ONE constant message for every rejection cause (empty
            # fields, duplicate email) — the service already collapses
            # them; the route never re-differentiates.
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Registration rejected.",
                details={"field": "email"},
            )
        # 201: the account is PENDING until the verification token is
        # redeemed (deny-by-default, 41 §41). Durable profile: the token
        # NEVER appears here — it travels only through the composed
        # EmailSenderPort. In-memory profile (C-02, D-1 = b): the SAME
        # token the console sender printed is returned, explicitly labelled
        # as development behaviour — never implied to be email delivery.
        content: dict[str, object] = {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "email": user.email,
            "status": user.status.value,
            "verification": "sent",
        }
        if surface.dev_verification_tokens is not None:
            dev_token = surface.dev_verification_tokens.pop(user.email, None)
            if dev_token is not None:
                content["verification"] = "dev_token"
                content["dev_verification_token"] = dev_token
                content["dev_note"] = (
                    "development / in-memory profile only: no email was sent; "
                    "this token is returned so the local onboarding journey can "
                    "complete. The durable profile never returns it."
                )
        return JSONResponse(status_code=201, content=content)

    @router.post("/verify")
    async def verify(body: VerifyRequest) -> Response:
        try:
            user = surface.identity.verify_email(body.token)
        except VerificationFailed:
            # Invalid and already-used tokens are the SAME constant 422
            # (no redemption oracle — module docstring).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Verification failed.",
                details={"field": "token"},
            )
        return JSONResponse(
            status_code=200,
            content={
                "user_id": str(user.id),
                "email": user.email,
                "email_verified": user.email_verified,
                "status": user.status.value,
            },
        )

    @router.post("/login")
    async def login(body: LoginRequest) -> Response:
        try:
            session = surface.identity.login(body.email, body.password)
        except AuthenticationFailed:
            # One constant-message 401 for ALL causes (module docstring).
            return unauthenticated()
        if surface.audit is not None:
            surface.audit.append(
                AuditEvent(
                    tenant_id=session.tenant_id,
                    event_type=AuditEventType.LOGIN,
                    actor_id=session.user_id,
                )
            )
        response = JSONResponse(
            status_code=200,
            content={"token": session.token},
        )
        # C-05 (D-2): the SAME token, also as the HttpOnly session cookie.
        set_session_cookie(response, session.token, secure=surface.cookie_secure)
        return response

    @router.post("/logout", status_code=204)
    async def logout(request: Request) -> Response:
        # ALWAYS 204 (idempotent; no token-validity oracle). Audit only
        # a real revocation — never a no-op (recorded decision).
        # C-05: the cookie is cleared on every logout (idempotent too).
        token = session_token(request)
        if token is not None:
            try:
                session = surface.identity.resolve_session(token)
            except SessionInvalid:
                session = None
            if session is not None:
                surface.identity.logout(token)
                if surface.audit is not None:
                    surface.audit.append(
                        AuditEvent(
                            tenant_id=session.tenant_id,
                            event_type=AuditEventType.LOGOUT,
                            actor_id=session.user_id,
                        )
                    )
        response = Response(status_code=204)
        clear_session_cookie(response)
        return response

    @router.get("/session")
    async def session_info(request: Request) -> Response:
        token = session_token(request)
        if token is None:
            if fallback is not None:
                return JSONResponse(
                    status_code=200,
                    content={
                        "user_id": str(fallback.user_id),
                        "tenant_id": str(fallback.tenant_id),
                        "email": None,
                        "is_admin": False,
                        "mode": "demo",
                    },
                )
            return unauthenticated()
        try:
            user = surface.identity.get_user_for_session(token)
        except SessionInvalid:
            return unauthenticated()
        return JSONResponse(
            status_code=200,
            content={
                "user_id": str(user.id),
                "tenant_id": str(user.tenant_id),
                "email": user.email,
                "is_admin": user.email in surface.admin_emails,
            },
        )

    return router
