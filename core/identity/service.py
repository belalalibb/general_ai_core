"""In-memory identity service skeleton (MVP Phase 2, 41 §41).

Delivers: user registration (creating a personal tenant), email
verification, login/session issuance — against in-memory state, behind
ports for password hashing and email delivery.

Spec anchors:

- 41 §41: "user registration / email verification / login/session /
  personal tenant"; exit = auth tests + tenant isolation tests pass.
- 41 Phase 2 security list: deny-by-default, anti-enumeration,
  Argon2id (production binding deferred — see ports.PasswordHasherPort).
- 20 §5 secrets rules: no plaintext passwords stored or logged; the service
  keeps only the opaque hash from the hasher port. Session tokens are
  opaque random strings; verification tokens leave only via the email port.
- 20 §6 tenant isolation: every user is bound to exactly one tenant at
  registration; sessions resolve to (user_id, tenant_id) and can never
  cross tenants.
- 03 §2: User starts ``pending`` / ``email_verified=False``; registration
  creates a ``personal`` tenant (41 §41), which starts ``active``.

Deny-by-default decisions (explicit):

- login is refused unless the user is ``active`` AND ``email_verified``.
- verification tokens are single-use.
- unknown/revoked session tokens raise ``SessionInvalid``.

This is a skeleton: persistence (PostgreSQL), rate limiting, secure-cookie
transport, TLS, re-authentication and device identity are later-phase
bindings and intentionally absent here.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from core.contracts.base import utc_now
from core.contracts.identity import (
    Tenant,
    TenantStatus,
    TenantType,
    User,
    UserStatus,
)
from core.identity.errors import (
    AuthenticationFailed,
    RegistrationError,
    SessionInvalid,
    VerificationFailed,
)
from core.identity.ports import EmailVerificationPort, PasswordHasherPort


@dataclass(frozen=True)
class Session:
    """An issued session: opaque token bound to (user_id, tenant_id)."""

    token: str
    user_id: UUID
    tenant_id: UUID
    created_at: datetime


@dataclass
class _Account:
    """Internal mutable account record (not a contract object)."""

    user: User
    password_hash: str


def _new_opaque_token() -> str:
    """Opaque, unguessable token (session / verification)."""
    return secrets.token_urlsafe(32)


@dataclass
class InMemoryIdentityService:
    """Identity service skeleton with in-memory state.

    ``default_plan_id`` is the plan assigned to personal tenants created at
    registration (plan catalogs are a later-phase concern; the Tenant
    contract requires ``plan_id``).
    """

    hasher: PasswordHasherPort
    email_sender: EmailVerificationPort
    default_plan_id: UUID
    clock: Callable[[], datetime] = utc_now

    _accounts_by_email: dict[str, _Account] = field(default_factory=dict)
    _tenants: dict[UUID, Tenant] = field(default_factory=dict)
    _verification_tokens: dict[str, str] = field(default_factory=dict)
    _sessions: dict[str, Session] = field(default_factory=dict)

    # --- registration (41 §41: registration + personal tenant) ------------

    def register(self, email: str, password: str, preferred_language: str) -> User:
        """Register a user; create their personal tenant; send verification.

        The returned User is ``pending`` and unverified until the emailed
        token is redeemed (deny-by-default).
        """
        normalized = _normalize_email(email)
        if not normalized or not password:
            raise RegistrationError("email and password are required")
        if normalized in self._accounts_by_email:
            raise RegistrationError("registration rejected")

        now = self.clock()
        tenant = Tenant(
            id=uuid4(),
            name=normalized,
            type=TenantType.PERSONAL,
            status=TenantStatus.ACTIVE,
            plan_id=self.default_plan_id,
        )
        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=normalized,
            email_verified=False,
            preferred_language=preferred_language,
            status=UserStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._tenants[tenant.id] = tenant
        self._accounts_by_email[normalized] = _Account(
            user=user, password_hash=self.hasher.hash(password)
        )

        token = _new_opaque_token()
        self._verification_tokens[token] = normalized
        self.email_sender.send_verification(normalized, token)
        return user

    # --- email verification (41 §41) ---------------------------------------

    def verify_email(self, token: str) -> User:
        """Redeem a single-use verification token; activate the user."""
        email = self._verification_tokens.pop(token, None)
        if email is None:
            raise VerificationFailed("invalid or already-used token")
        account = self._accounts_by_email[email]
        account.user = account.user.model_copy(
            update={
                "email_verified": True,
                "status": UserStatus.ACTIVE,
                "updated_at": self.clock(),
            }
        )
        return account.user

    # --- login / session (41 §41) -------------------------------------------

    def login(self, email: str, password: str) -> Session:
        """Authenticate and issue an opaque session token.

        Anti-enumeration: every failure path raises the same
        ``AuthenticationFailed`` (constant message). A dummy hash check runs
        for unknown emails so the timing profile does not separate
        "unknown email" from "wrong password".
        """
        normalized = _normalize_email(email)
        account = self._accounts_by_email.get(normalized)
        if account is None:
            # Equalize work factor; result intentionally discarded.
            self.hasher.hash(password)
            raise AuthenticationFailed()
        if not self.hasher.verify(password, account.password_hash):
            raise AuthenticationFailed()
        user = account.user
        if not user.email_verified or user.status is not UserStatus.ACTIVE:
            raise AuthenticationFailed()
        tenant = self._tenants[user.tenant_id]
        if tenant.status is not TenantStatus.ACTIVE:
            raise AuthenticationFailed()

        session = Session(
            token=_new_opaque_token(),
            user_id=user.id,
            tenant_id=user.tenant_id,
            created_at=self.clock(),
        )
        self._sessions[session.token] = session
        return session

    def resolve_session(self, token: str) -> Session:
        """Return the session for ``token`` or raise (deny-by-default).

        Constant-time token comparison via dict lookup + hmac.compare_digest
        on the stored token to avoid trivial timing oracles.
        """
        session = self._sessions.get(token)
        if session is None or not hmac.compare_digest(session.token, token):
            raise SessionInvalid("invalid session")
        return session

    def logout(self, token: str) -> None:
        """Revoke a session token (idempotent)."""
        self._sessions.pop(token, None)

    # --- tenant-scoped reads (20 §6 isolation surface) ----------------------

    def get_user_for_session(self, token: str) -> User:
        """Resolve the session's user; the session's tenant_id must match."""
        session = self.resolve_session(token)
        account = self._account_by_user_id(session.user_id)
        if account.user.tenant_id != session.tenant_id:
            raise SessionInvalid("tenant mismatch")  # pragma: no cover - invariant
        return account.user

    def get_tenant(self, tenant_id: UUID, *, session_token: str) -> Tenant:
        """Return a tenant only if the session belongs to it (20 §6)."""
        session = self.resolve_session(session_token)
        if session.tenant_id != tenant_id:
            raise SessionInvalid("cross-tenant access denied")
        return self._tenants[tenant_id]

    # --- internals -----------------------------------------------------------

    def _account_by_user_id(self, user_id: UUID) -> _Account:
        for account in self._accounts_by_email.values():
            if account.user.id == user_id:
                return account
        raise SessionInvalid("invalid session")  # pragma: no cover - invariant


def _normalize_email(email: str) -> str:
    return email.strip().lower()
