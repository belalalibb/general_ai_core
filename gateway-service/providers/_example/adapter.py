"""Layer 2 — the FACADE. The only layer the gateway sees.

THREE-LAYER MODEL, applied:
    BELOW this layer (Layer 1: _engine.py, _wire.py) — implement anything,
      any structure. The mock upstream's shapes are deliberately alien.
    ABOVE this layer (Layer 3: gateway.contracts) — fixed, never changes.
    THIS layer — the mandatory translator: ProviderContext in,
      FacadeResult out. Success matches the canonical output schema, or the
      error maps to one of the 12 categories. No third shape.

ONE REQUEST -> ONE CANONICAL RESPONSE: whatever happens internally (here:
an auth step + one mock call; in a real provider possibly N upstream calls
+ internal fallback), exactly one canonical FacadeResult comes out.

Imports: gateway.contracts ONLY from the gateway side — never `app`,
never gateway core modules.

example — not a live provider (mock upstream, never registered live).
"""

from __future__ import annotations

from gateway.contracts import (
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers._example._engine import call_mock_upstream
from providers._example._wire import MockUpstreamRequest

# Upstream-native code -> canonical category (the facade's translation table).
_FAIL_CODE_MAP: dict[str, ErrorCategory] = {
    "401": ErrorCategory.INVALID_CREDENTIAL,
    "429": ErrorCategory.RATE_LIMITED,
    "500": ErrorCategory.RETRYABLE_SERVER_ERROR,
}


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade — translates canonical <-> mock-internal.

    Input payload fields: messages: list[{role, content}] (required).
    Canonical success output: {"text": str, "finish_reason": str}.
    """

    messages = context.payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.messages is required"),
        )
    last = messages[-1]
    content = last.get("content") if isinstance(last, dict) else None
    if not isinstance(content, str) or not content:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST, "payload.messages[-1].content must be a string"
            ),
        )

    # ---- Layer 1 begins: internal shapes, internal workflow ----
    reply = call_mock_upstream(
        MockUpstreamRequest(
            api_key=context.credential_value or "",
            model_id=context.model,
            prompt_blob=content,
            max_units=1,
        )
    )
    # ---- Layer 1 ends: translate back to the canonical contract ----

    if not reply.ok:
        category = _FAIL_CODE_MAP.get(reply.fail_code or "", ErrorCategory.NON_RETRYABLE_ERROR)
        return FacadeResult(
            succeeded=False,
            error=make_error(
                category,
                "upstream call failed",
                provider_code=reply.fail_code,
                retry_after_ms=2000 if category is ErrorCategory.RATE_LIMITED else None,
            ),
        )

    return FacadeResult(
        succeeded=True,
        output={"text": reply.body_text, "finish_reason": "stop"},
        usage=Usage(input_tokens=reply.tokens_in, output_tokens=reply.tokens_out, units=1),
    )


# The registry's parity check verifies: HANDLERS keys == DEFINITION operations.
HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
}
