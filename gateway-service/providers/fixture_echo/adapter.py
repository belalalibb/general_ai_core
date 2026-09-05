"""Layer 2 — the fixture_echo FACADE. No Layer 1 exists; nothing is called.

ProviderContext in, FacadeResult out — success matches the canonical
``generate_text`` output schema (``{"text", "finish_reason"}``). The text
is a fixed MARKER plus an echo of the last user message, so any consumer
can tell, without ambiguity, that THIS slug answered and not a live one.

Schema policing mirrors the live facades (extras → bad_request) so the
fixture never appears more permissive than the providers it stands beside.
``context.credential_value`` is never consulted (platform mode, no key).
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

#: Appears verbatim at the start of every successful answer.
FIXTURE_ECHO_MARKER = "[FIXTURE_ECHO r174 — not a live model]"

#: The ONLY payload keys the canonical generate_text schema admits (CONTRACT §1).
_ALLOWED_PAYLOAD_KEYS = frozenset({"messages", "temperature", "max_tokens"})


def _validate_payload(payload: dict[str, Any]) -> FacadeResult | None:
    extras = set(payload) - _ALLOWED_PAYLOAD_KEYS
    if extras:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "payload contains keys outside the canonical generate_text schema",
                provider_code="schema_extra_keys",
            ),
        )
    messages = payload.get("messages")
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
    return None


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade — marker + echo, no upstream, no credential."""

    invalid = _validate_payload(context.payload)
    if invalid is not None:
        return invalid

    last_content: str = context.payload["messages"][-1]["content"]
    text = f"{FIXTURE_ECHO_MARKER} model={context.model} echo={last_content}"
    return FacadeResult(
        succeeded=True,
        output={"text": text, "finish_reason": "stop"},
        usage=Usage(
            input_tokens=len(last_content.split()),
            output_tokens=len(text.split()),
            units=1,
        ),
    )


# The registry's parity check verifies: HANDLERS keys == DEFINITION operations.
HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
}
