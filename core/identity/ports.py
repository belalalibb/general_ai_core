"""Identity service ports (dependency-inversion boundaries).

Authority: 41_IMPLEMENTATION_PLAN_AND_MVP.md §41 (MVP Phase 2 deliverables)
and 20_SECURITY_THREAT_MODEL.md §5 (secrets rules).

MVP Phase 2 delivers the identity *skeleton*: real infrastructure bindings
(Argon2id hashing per 41 Phase 2 security list, real email delivery) are
deferred to the infrastructure phase. The service depends only on these
ports; tests supply in-memory fakes.

Security posture:

- Password material crosses only the ``PasswordHasherPort`` boundary; the
  service stores the returned opaque hash, never the plaintext (20 §5).
- Email verification tokens are delivered only through
  ``EmailVerificationPort``; the service never logs or returns them from
  authentication APIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # service/contract types for the port surface only
    from uuid import UUID

    from core.contracts.identity import Tenant, User
    from core.identity.service import Session


class PasswordHasherPort(Protocol):
    """Hashes and verifies passwords.

    Production binding must be Argon2id (41 Phase 2 security list); that
    binding lives in ``infrastructure/`` in a later phase. Contracts and the
    core service never see plaintext beyond this boundary.
    """

    def hash(self, password: str) -> str:
        """Return an opaque hash for ``password``."""
        ...

    def verify(self, password: str, hashed: str) -> bool:
        """Return True iff ``password`` matches ``hashed``."""
        ...


class EmailVerificationPort(Protocol):
    """Delivers an email-verification token to an address.

    MVP Phase 2 forbids real delivery; tests use a recording fake.
    """

    def send_verification(self, email: str, token: str) -> None:
        """Deliver ``token`` to ``email`` out-of-band."""
        ...


class IdentityServicePort(Protocol):
    """The full identity service surface (P-A.2 durability seam).

    Exactly the shape ``InMemoryIdentityService`` has always exposed —
    extracted as a Protocol so the composition root can swap in a
    durable binding WITHOUT touching the auth router or resolvers
    (the "persistence (PostgreSQL) is a later-phase binding" this
    package's docstrings promised).  Structural typing: BOTH the
    in-memory service and the durable service satisfy this as-is.
    """

    def register(
        self, email: str, password: str, preferred_language: str
    ) -> User: ...

    def verify_email(self, token: str) -> User: ...

    def login(self, email: str, password: str) -> Session: ...

    def resolve_session(self, token: str) -> Session: ...

    def logout(self, token: str) -> None: ...

    def get_user_for_session(self, token: str) -> User: ...

    def get_tenant(self, tenant_id: UUID, *, session_token: str) -> Tenant: ...
