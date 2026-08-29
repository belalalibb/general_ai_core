"""Error normalization helpers + provider_code sanitizer.

Fixes prior-art weakness #8: exception class names NEVER cross the wire.
``provider_code`` is sanitized to short alphanumeric/dash/underscore/dot
tokens (HTTP codes, upstream short codes) — anything else is dropped.
"""

from __future__ import annotations

import re

from gateway.contracts import ErrorCategory, GatewayError

_PROVIDER_CODE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Retryability defaults per category (facades may override retryable
# explicitly; these are the canonical defaults used by helpers).
RETRYABLE_DEFAULTS: dict[ErrorCategory, bool] = {
    ErrorCategory.AUTH_EXPIRED: True,
    ErrorCategory.INVALID_CREDENTIAL: False,
    ErrorCategory.RATE_LIMITED: True,
    ErrorCategory.QUOTA_EXCEEDED: False,
    ErrorCategory.MODEL_UNAVAILABLE: False,
    ErrorCategory.PROVIDER_UNAVAILABLE: False,
    ErrorCategory.UNSUPPORTED_CAPABILITY: False,
    ErrorCategory.BAD_REQUEST: False,
    ErrorCategory.CONTENT_REJECTED: False,
    ErrorCategory.TIMEOUT: True,
    ErrorCategory.RETRYABLE_SERVER_ERROR: True,
    ErrorCategory.NON_RETRYABLE_ERROR: False,
}


def sanitize_provider_code(raw: str | None) -> str | None:
    """Keep short safe diagnostic codes; drop anything resembling internals."""

    if raw is None:
        return None
    candidate = raw.strip()
    if _PROVIDER_CODE_RE.fullmatch(candidate):
        return candidate
    return None


def make_error(
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool | None = None,
    retry_after_ms: int | None = None,
    provider_code: str | None = None,
) -> GatewayError:
    """Build a canonical GatewayError with sanitized diagnostics."""

    return GatewayError(
        category=category,
        retryable=RETRYABLE_DEFAULTS[category] if retryable is None else retryable,
        message=message,
        retry_after_ms=retry_after_ms,
        provider_code=sanitize_provider_code(provider_code),
    )


def internal_fault() -> GatewayError:
    """500-path error — deliberately generic; never carries exception names."""

    return make_error(
        ErrorCategory.RETRYABLE_SERVER_ERROR,
        "gateway internal fault",
        provider_code=None,
    )
