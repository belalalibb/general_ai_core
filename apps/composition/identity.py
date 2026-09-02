"""P-A.2 — durable identity service over PostgresIdentityRepository.

``DurableIdentityService`` exposes the EXACT sync surface of the proven
``InMemoryIdentityService`` (register / verify_email / login /
resolve_session / logout / get_user_for_session / get_tenant) so
``AuthSurface`` and ``session_resolver`` accept it unchanged (P2 — the
composition root swaps the binding; route code stays byte-identical).

Policy is REUSED, not re-derived (P1):

- anti-enumeration login: same constant AuthenticationFailed on every
  failure path, same dummy-hash timing equalization for unknown emails;
- deny-by-default: login requires active+verified user AND active
  tenant; unknown/revoked sessions raise SessionInvalid;
- single-use verification tokens (durable DELETE-on-redeem, one tx);
- 20 §5: plaintext passwords never stored; session/verification tokens
  cross to the database ONLY as SHA-256 digests — the durable rows hold
  no replayable secret.  The digest also gives constant-time lookup
  semantics (an attacker-supplied token is hashed, then looked up —
  no timing oracle over token bytes).

Sync/async: all repository calls cross the shared AsyncBridge (the ONE
primitive from P-A.1) — same recorded tradeoff.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
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
from core.identity.service import Session, _new_opaque_token, _normalize_email
from infrastructure.db.repositories.identity import (
    PostgresIdentityRepository,
    SessionRecord,
)


def _digest(token: str) -> str:
    """SHA-256 hex digest — the ONLY form a token takes at rest (20 §5)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class DurableIdentityService:
    """Identity service with PostgreSQL-durable state (P-A.2).

    Same construction shape as ``InMemoryIdentityService`` plus the
    repository + bridge — tests and composition build it the same way.
    """

    hasher: PasswordHasherPort
    email_sender: EmailVerificationPort
    default_plan_id: UUID
    repository: PostgresIdentityRepository
    bridge: AsyncBridge
    clock: Callable[[], datetime] = field(default=utc_now)

    # --- registration (41 §41) ------------------------------------------------

    def register(self, email: str, password: str, preferred_language: str) -> User:
        normalized = _normalize_email(email)
        if not normalized or not password:
            raise RegistrationError("email and password are required")
        if self.bridge.run(self.repository.get_account_by_email(normalized)):
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
        token = _new_opaque_token()
        self.bridge.run(
            self.repository.create_account(
                tenant=tenant,
                user=user,
                password_hash=self.hasher.hash(password),
                verification_token_sha256=_digest(token),
            )
        )
        # Email leaves ONLY via the port, AFTER the durable truth exists
        # (P6 — never notify about state the database does not have).
        self.email_sender.send_verification(normalized, token)
        return user

    # --- email verification -----------------------------------------------------

    def verify_email(self, token: str) -> User:
        user = self.bridge.run(
            self.repository.redeem_verification_token(_digest(token), now=self.clock())
        )
        if user is None:
            raise VerificationFailed("invalid or already-used token")
        return user

    # --- login / session ----------------------------------------------------------

    def login(self, email: str, password: str) -> Session:
        normalized = _normalize_email(email)
        account = self.bridge.run(self.repository.get_account_by_email(normalized))
        if account is None:
            self.hasher.hash(password)  # equalize work factor (recorded)
            raise AuthenticationFailed()
        if not self.hasher.verify(password, account.password_hash):
            raise AuthenticationFailed()
        user = account.user
        if not user.email_verified or user.status is not UserStatus.ACTIVE:
            raise AuthenticationFailed()
        tenant = self.bridge.run(self.repository.get_tenant(user.tenant_id))
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise AuthenticationFailed()

        session = Session(
            token=_new_opaque_token(),
            user_id=user.id,
            tenant_id=user.tenant_id,
            created_at=self.clock(),
        )
        self.bridge.run(
            self.repository.save_session(
                SessionRecord(
                    token_sha256=_digest(session.token),
                    user_id=session.user_id,
                    tenant_id=session.tenant_id,
                    created_at=session.created_at,
                )
            )
        )
        return session

    def resolve_session(self, token: str) -> Session:
        record = self.bridge.run(self.repository.get_session(_digest(token)))
        if record is None:
            raise SessionInvalid("invalid session")
        # The RAW token is returned to the caller's Session shape — it
        # came from the caller; the store never held it (20 §5).
        return Session(
            token=token,
            user_id=record.user_id,
            tenant_id=record.tenant_id,
            created_at=record.created_at,
        )

    def logout(self, token: str) -> None:
        self.bridge.run(self.repository.delete_session(_digest(token)))

    # --- tenant-scoped reads (20 §6) ------------------------------------------------

    def get_user_for_session(self, token: str) -> User:
        session = self.resolve_session(token)
        user = self.bridge.run(self.repository.get_user_by_id(session.user_id))
        if user is None or user.tenant_id != session.tenant_id:
            raise SessionInvalid("invalid session")
        return user

    def get_tenant(self, tenant_id: UUID, *, session_token: str) -> Tenant:
        session = self.resolve_session(session_token)
        if session.tenant_id != tenant_id:
            raise SessionInvalid("cross-tenant access denied")
        tenant = self.bridge.run(self.repository.get_tenant(tenant_id))
        if tenant is None:  # pragma: no cover - FK invariant
            raise SessionInvalid("invalid session")
        return tenant


def build_durable_identity_service(
    bindings: DatabaseBindings,
    bridge: AsyncBridge,
    *,
    hasher: PasswordHasherPort,
    email_sender: EmailVerificationPort,
    default_plan_id: UUID,
    clock: Callable[[], datetime] = utc_now,
) -> DurableIdentityService:
    """Compose the durable identity service from the EXISTING bindings.

    Same posture as the execution store: callers reach here only via the
    ``database_settings_from_env`` branch — no DATABASE_URL, no durable
    identity (keep ``InMemoryIdentityService``, byte-identical to today).
    """
    return DurableIdentityService(
        hasher=hasher,
        email_sender=email_sender,
        default_plan_id=default_plan_id,
        repository=PostgresIdentityRepository(bindings.session_factory),
        bridge=bridge,
        clock=clock,
    )
