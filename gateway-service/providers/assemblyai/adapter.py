"""Layer 2 — the AssemblyAI FACADE. The only layer the gateway sees.

ProviderContext in, FacadeResult out — success matches the canonical
``generate_text`` output schema (``{"text", "finish_reason"}``) or the
error maps to one of the 12 categories. No third shape.

Credential mode is ``platform``: the key is resolved inside Layer 1
(environment variable name documented in ``_upstream.ASSEMBLYAI_API_KEY_ENV``);
``context.credential_value`` is always None here and is never consulted.

ONE REQUEST -> ONE CANONICAL RESPONSE. ZERO retries (v1, ADR-0008) — Layer 1
also disables AssemblyAI's own default retry.
Imports: gateway.contracts / gateway.errors + own Layer-1 modules only.
"""

from __future__ import annotations

from typing import Any

from gateway.contracts import (
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers.assemblyai._upstream import UpstreamReply, call_chat_completions

#: The ONLY payload keys the canonical generate_text schema admits (CONTRACT §1).
_ALLOWED_PAYLOAD_KEYS = frozenset({"messages", "temperature", "max_tokens"})

#: Canonical finish reasons (CONTRACT §1). AssemblyAI documents finish_reason
#: as a free string; values outside this set (or absent) map to "stop".
_FINISH_REASON_MAP = {
    "stop": "stop",
    "length": "length",
    "content_filter": "filter",
}

#: Upstream HTTP status -> canonical category. AssemblyAI has no 404 for an
#: unknown model (it is a 400 — handled by Layer 1's ``unsupported_model``
#: fail_kind); 404 stays mapped for route-level not-found parity with Groq.
_HTTP_STATUS_MAP: dict[int, ErrorCategory] = {
    401: ErrorCategory.INVALID_CREDENTIAL,
    403: ErrorCategory.INVALID_CREDENTIAL,
    404: ErrorCategory.MODEL_UNAVAILABLE,
    429: ErrorCategory.RATE_LIMITED,
    400: ErrorCategory.BAD_REQUEST,
    413: ErrorCategory.BAD_REQUEST,
    422: ErrorCategory.BAD_REQUEST,
    500: ErrorCategory.RETRYABLE_SERVER_ERROR,
    502: ErrorCategory.RETRYABLE_SERVER_ERROR,
    503: ErrorCategory.RETRYABLE_SERVER_ERROR,
    504: ErrorCategory.RETRYABLE_SERVER_ERROR,
}


def _validate_payload(payload: dict[str, Any]) -> FacadeResult | None:
    """Canonical schema policing; returns a bad_request FacadeResult or None."""

    extras = set(payload) - _ALLOWED_PAYLOAD_KEYS
    if extras:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "payload carries keys outside the generate_text schema",
            ),
        )
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.messages is required"),
        )
    for item in messages:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("role"), str)
            or not isinstance(item.get("content"), str)
        ):
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    "payload.messages items must be {role: str, content: str}",
                ),
            )
    temperature = payload.get("temperature")
    if temperature is not None and not isinstance(temperature, int | float):
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.temperature must be a number"),
        )
    max_tokens = payload.get("max_tokens")
    if max_tokens is not None and not isinstance(max_tokens, int):
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.max_tokens must be an integer"),
        )
    return None


def _translate_failure(reply: UpstreamReply) -> FacadeResult:
    """Layer-1 failure shape -> canonical error. Fixed safe messages only."""

    if reply.fail_kind == "no_key":
        # Platform-mode key missing at the GATEWAY — a gateway deployment
        # fault, not a caller fault; invalid_credential is the honest bucket.
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "provider credential is not configured at the gateway",
                provider_code="platform_credential_missing",
            ),
        )
    if reply.fail_kind == "timeout":
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.TIMEOUT, "upstream call timed out"),
        )
    if reply.fail_kind == "network":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "upstream is unreachable",
                retryable=True,
            ),
        )
    if reply.fail_kind == "unsupported_model":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.MODEL_UNAVAILABLE,
                "model is not supported by the provider",
                provider_code="unsupported_model",
            ),
        )
    # fail_kind == "http"
    status = reply.http_status or 0
    category = _HTTP_STATUS_MAP.get(status, ErrorCategory.NON_RETRYABLE_ERROR)
    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            "upstream call failed",
            provider_code=reply.error_code or f"http_{status}",
            retry_after_ms=(
                reply.retry_after_ms if category is ErrorCategory.RATE_LIMITED else None
            ),
        ),
    )


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade — canonical payload in, canonical result out."""

    invalid = _validate_payload(context.payload)
    if invalid is not None:
        return invalid

    reply = await call_chat_completions(
        model=context.model,
        messages=context.payload["messages"],
        temperature=context.payload.get("temperature"),
        max_tokens=context.payload.get("max_tokens"),
        timeout_ms=context.timeout_ms,
    )
    if not reply.ok:
        return _translate_failure(reply)

    finish = _FINISH_REASON_MAP.get(reply.finish_reason or "", "stop")
    return FacadeResult(
        succeeded=True,
        output={"text": reply.text, "finish_reason": finish},
        usage=Usage(
            input_tokens=reply.usage.get("input_tokens"),
            output_tokens=reply.usage.get("output_tokens"),
            units=1,
        ),
    )


# The registry's parity check verifies: HANDLERS keys == DEFINITION operations.
HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
}
