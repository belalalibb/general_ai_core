"""Credential-mode enforcement (ADR-0008 credential/BYOK model).

user_key: resolved PLATFORM-side, crosses TLS inside the envelope,
          memory-only here — never persisted, never logged.
platform: resolved INTERNALLY by the facade, keyed by slug — never from
          the request; the platform never learns the credential kind.

This module only ENFORCES that the envelope's mode matches the provider
DEFINITION (mismatch = bad_request). It never stores anything.
"""

from __future__ import annotations

from gateway.contracts import (
    EnvelopeCredential,
    ErrorCategory,
    GatewayError,
    ProviderDefinition,
)
from gateway.errors import make_error


def check_credential_mode(
    definition: ProviderDefinition,
    credential: EnvelopeCredential,
) -> GatewayError | None:
    """Return a bad_request error on mode mismatch, else None."""

    if credential.mode is not definition.credential_mode:
        return make_error(
            ErrorCategory.BAD_REQUEST,
            "credential mode does not match provider declaration",
        )
    return None
