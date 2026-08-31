"""Identity service skeleton (MVP Phase 2, 41 §41).

Public surface: ports, errors, and the in-memory service. Real
infrastructure bindings (Argon2id, email delivery, persistence) arrive in
later phases behind the same ports.
"""

from core.identity.errors import (
    AuthenticationFailed,
    IdentityError,
    RegistrationError,
    SessionInvalid,
    VerificationFailed,
)
from core.identity.ports import (
    EmailVerificationPort,
    IdentityServicePort,
    PasswordHasherPort,
)
from core.identity.service import InMemoryIdentityService, Session

__all__ = [
    "AuthenticationFailed",
    "EmailVerificationPort",
    "IdentityError",
    "IdentityServicePort",
    "InMemoryIdentityService",
    "PasswordHasherPort",
    "RegistrationError",
    "Session",
    "SessionInvalid",
    "VerificationFailed",
]
