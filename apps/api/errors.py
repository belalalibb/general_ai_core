"""Unified error responses for the API surface (10 §9).

Every non-success response body is the unified ``{"error": {...}}`` envelope
(core/contracts/errors.py — closed 11-code set, carried verbatim). This
module owns the ONLY mapping from internal failure shapes to that envelope,
so route handlers never hand-build error JSON.

Mapping decisions (recorded once, applied uniformly):

- Request validation failures (Pydantic/FastAPI) -> ``validation_error`` 422.
- Router selection failures -> ``model_unavailable`` 503 with the router's
  explainable message in ``details`` (11 §14 "fail clearly"); unsupported
  policy types -> ``validation_error`` 422 (the request asked for a policy
  outside the deployed surface).
- Unknown execution id -> HTTP 404. The closed 10 §9 set has no
  ``not_found`` code; the closest honest category is ``validation_error``
  (the request references a nonexistent resource) — recorded as a mapping
  decision, not a contract change.
- Failed executions -> the last normalized ProviderError category picks the
  closest unified code (rate_limited/model_unavailable/provider_unavailable),
  else ``execution_failed``; HTTP status follows the code.
- Anything unexpected -> ``internal_error`` 500 with a generic message
  (20 §4: internals never leak to clients).
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from core.contracts.base import JsonObject
from core.contracts.errors import ErrorCode, ErrorDetail, ErrorEnvelope
from core.contracts.provider import ProviderError, ProviderErrorCategory

#: HTTP status per unified error code (10 §9 codes; conventional REST mapping).
HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.UNAUTHORIZED: 403,
    ErrorCode.ENTITLEMENT_EXCEEDED: 403,
    ErrorCode.CAPABILITY_DENIED: 403,
    ErrorCode.PROVIDER_UNAVAILABLE: 503,
    ErrorCode.MODEL_UNAVAILABLE: 503,
    ErrorCode.TOOL_APPROVAL_REQUIRED: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.EXECUTION_FAILED: 502,
    ErrorCode.INTERNAL_ERROR: 500,
}

#: Provider error categories that map onto a MORE SPECIFIC unified code than
#: the generic ``execution_failed`` (explainability without leaking internals).
_CODE_BY_PROVIDER_CATEGORY: dict[ProviderErrorCategory, ErrorCode] = {
    ProviderErrorCategory.RATE_LIMITED: ErrorCode.RATE_LIMITED,
    ProviderErrorCategory.QUOTA_EXCEEDED: ErrorCode.ENTITLEMENT_EXCEEDED,
    ProviderErrorCategory.MODEL_UNAVAILABLE: ErrorCode.MODEL_UNAVAILABLE,
    ProviderErrorCategory.PROVIDER_UNAVAILABLE: ErrorCode.PROVIDER_UNAVAILABLE,
}


def error_response(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool = False,
    details: JsonObject | None = None,
    http_status: int | None = None,
) -> JSONResponse:
    """Build a unified-error JSONResponse (the only error body shape)."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            details=details if details is not None else {},
        )
    )
    status = http_status if http_status is not None else HTTP_STATUS_BY_CODE[code]
    return JSONResponse(
        status_code=status,
        content=envelope.model_dump(mode="json"),
    )


def execution_failure_detail(
    execution_id: str,
    provider_error: ProviderError | None,
    *,
    agent_failure: JsonObject | None = None,
) -> ErrorDetail:
    """Map a failed execution's last normalized error to the unified shape.

    Only the adapter-normalized ``safe_message`` and category cross this
    boundary (30 §14) — raw provider internals never reach clients.

    ``agent_failure`` (R165) is a ``strategy=agent`` run's recorded cause —
    ``{"stop_reason": ..., "node": ..., "error": {...}}``, already scrubbed by
    the caller — so a client sees WHY the bounded loop stopped (invalid
    proposal detail, refused capability, deadline) instead of an opaque
    "Execution failed.". Absent ⇒ the historical shape, unchanged.
    """
    if provider_error is None:
        details: JsonObject = {"execution_id": execution_id}
        message = "Execution failed."
        if agent_failure:
            details["agent"] = dict(agent_failure)
            stop_reason = agent_failure.get("stop_reason")
            if isinstance(stop_reason, str):
                message = f"Execution failed: agent stopped ({stop_reason})."
        return ErrorDetail(
            code=ErrorCode.EXECUTION_FAILED,
            message=message,
            retryable=False,
            details=details,
        )
    code = _CODE_BY_PROVIDER_CATEGORY.get(provider_error.category, ErrorCode.EXECUTION_FAILED)
    return ErrorDetail(
        code=code,
        message=provider_error.safe_message,
        retryable=provider_error.retryable,
        details={
            "execution_id": execution_id,
            "provider_error_category": provider_error.category.value,
        },
    )
