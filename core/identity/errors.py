"""Identity service errors.

Anti-enumeration rule (41 Phase 2 security list): authentication failures
must not reveal whether the email exists, whether the password was wrong, or
whether the account is unverified/disabled. All of those collapse into the
single :class:`AuthenticationFailed` with one constant message.
"""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for identity service errors."""


class RegistrationError(IdentityError):
    """Registration was rejected (e.g. email already registered).

    NOTE: registration duplicate feedback is inherently observable at the
    registration endpoint; rate limiting (an infrastructure-phase concern)
    is the documented mitigation. The login path stays non-enumerating.
    """


class AuthenticationFailed(IdentityError):
    """Login failed — constant message, no cause disclosed (anti-enumeration)."""

    MESSAGE = "authentication failed"

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


class VerificationFailed(IdentityError):
    """Email verification failed — invalid or already-used token."""


class SessionInvalid(IdentityError):
    """Session token unknown, expired, or revoked (deny-by-default)."""
