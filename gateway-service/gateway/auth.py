"""Gateway authentication — X-Gateway-Secret[+Version], dual-accept rotation.

ADR-0008 security model (staged: NOW = TLS + shared secret + private
network; G4 later = AppRole -> HMAC signing -> optional mTLS).

Semantics (fixed by the contract, report §9 H/I):
    wrong secret          -> 401 invalid_credential, retryable=false
    stale/unknown version -> 401 auth_expired,       retryable=true
      (self-healing rotation: the platform adapter re-reads Vault and
       retries once — dual-accept keeps rotation downtime at zero)

Constant-time compare for every secret comparison. Explicit validation,
never ``assert``.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import StrEnum

from gateway.config import GatewayConfig


class AuthOutcome(StrEnum):
    OK = "ok"
    WRONG_SECRET = "wrong_secret"  # -> 401 invalid_credential (example H)
    STALE_VERSION = "stale_version"  # -> 401 auth_expired, retryable (example I)
    MISSING = "missing"  # -> 401 invalid_credential


@dataclass(frozen=True)
class AuthResult:
    outcome: AuthOutcome
    current_version: int


def authenticate(
    config: GatewayConfig,
    secret_header: str | None,
    version_header: str | None,
) -> AuthResult:
    """Validate the gateway secret headers against the dual-accept map."""

    current = config.current_secret_version
    if not secret_header or not version_header:
        return AuthResult(outcome=AuthOutcome.MISSING, current_version=current)
    if not version_header.isdigit():
        return AuthResult(outcome=AuthOutcome.MISSING, current_version=current)

    version = int(version_header)
    expected = config.secrets_by_version.get(version)
    if expected is None:
        # Unknown version: rotation signal, not an attack signal.
        return AuthResult(outcome=AuthOutcome.STALE_VERSION, current_version=current)

    if hmac.compare_digest(secret_header.encode(), expected.encode()):
        return AuthResult(outcome=AuthOutcome.OK, current_version=current)
    return AuthResult(outcome=AuthOutcome.WRONG_SECRET, current_version=current)


def auth_error_body(result: AuthResult) -> dict[str, object]:
    """401 bodies per wire examples H and I. Never leaks secret material."""

    if result.outcome is AuthOutcome.STALE_VERSION:
        return {
            "error": {
                "category": "auth_expired",
                "retryable": True,
                "message": (
                    "secret version no longer accepted; "
                    f"current is {result.current_version}"
                ),
            }
        }
    return {
        "error": {
            "category": "invalid_credential",
            "retryable": False,
            "message": "gateway authentication failed",
        }
    }
