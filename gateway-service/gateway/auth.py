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
import time
from collections.abc import Callable
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


def _window_expired(config: GatewayConfig, now: float) -> bool:
    """True iff rotation tracking is configured AND the window has elapsed.

    G4 hardening: the dual-accept window (OPEN-7) is now ENFORCED, not just
    configured. ``rotation_started_at`` unset keeps the pre-G4 behavior
    (previous version accepted while configured) — honest, no fake expiry.
    The window duration stays OPERATIONAL configuration.
    """

    if config.rotation_started_at is None:
        return False
    return now >= config.rotation_started_at + config.dual_accept_window_seconds


def authenticate(
    config: GatewayConfig,
    secret_header: str | None,
    version_header: str | None,
    *,
    clock: Callable[[], float] = time.time,
) -> AuthResult:
    """Validate the gateway secret headers against the dual-accept map.

    ``clock`` is injectable so the rotation drill is DETERMINISTIC in tests;
    production callers pass nothing and get wall time.
    """

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

    if version != current and _window_expired(config, clock()):
        # Previous version outlived the dual-accept window: expired.
        # Same wire semantics as unknown version (auth_expired, retryable
        # — the adapter self-heals by re-reading the CURRENT secret).
        # Deliberately signaled BEFORE the value compare: an expired
        # version is expired regardless of what value rides with it.
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
