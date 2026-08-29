"""Observability contract — CLOSED allowed-field set (ADR-0008 / report §21).

Allowed fields (anything else = rejection, enforced by a hermetic test):
    request_id, execution_id, operation, model, latency_ms, error_category,
    retryable, input_tokens, output_tokens, units, api_version,
    definition_version

Forbidden ALWAYS (never loggable): secrets, credential.value,
credential_ref, route_token, slug, upstream URL/host, upstream account
identity, raw payload (by default), exception class names.
"""

from __future__ import annotations

import json
import sys
from typing import Any

ALLOWED_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "request_id",
        "execution_id",
        "operation",
        "model",
        "latency_ms",
        "error_category",
        "retryable",
        "input_tokens",
        "output_tokens",
        "units",
        "api_version",
        "definition_version",
    }
)


class ForbiddenLogFieldError(ValueError):
    """Raised when an event carries a key outside the closed allowed set."""


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Reject any event carrying a key outside the closed set."""

    unknown = set(event) - ALLOWED_LOG_FIELDS
    if unknown:
        msg = f"forbidden log fields (closed observability contract): {sorted(unknown)}"
        raise ForbiddenLogFieldError(msg)
    return event


def emit(event: dict[str, Any]) -> None:
    """Validate then emit one structured event line to stdout."""

    sys.stdout.write(json.dumps(validate_event(event), sort_keys=True) + "\n")
    sys.stdout.flush()
