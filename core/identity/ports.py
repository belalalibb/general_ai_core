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

from typing import Protocol


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
