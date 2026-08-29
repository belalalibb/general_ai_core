"""Per-provider hermetic tests — the _example facade in isolation.

Demonstrates the promised property: a provider package is testable against
gateway.contracts ALONE (no app, no HTTP, no gateway core).
"""

from __future__ import annotations

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers._example.adapter import HANDLERS, generate_text


def _context(content: str, key: str = "mock-key-abc123") -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="example-mock-model",
        request_id="req_x",
        tenant_id="ten_x",
        credential_mode=CredentialMode.USER_KEY,
        credential_value=key,
        payload={"messages": [{"role": "user", "content": content}]},
        timeout_ms=1000,
    )


async def test_facade_success_is_canonical() -> None:
    result = await generate_text(_context("hi"))
    assert result.succeeded
    assert result.output is not None
    assert set(result.output) == {"text", "finish_reason"}
    assert result.usage is not None and result.usage.units == 1


async def test_facade_maps_upstream_codes_to_categories() -> None:
    rate = await generate_text(_context("TRIGGER_RATE_LIMIT"))
    assert rate.error is not None and rate.error.category is ErrorCategory.RATE_LIMITED
    server = await generate_text(_context("TRIGGER_SERVER_ERROR"))
    assert (
        server.error is not None
        and server.error.category is ErrorCategory.RETRYABLE_SERVER_ERROR
    )
    bad_key = await generate_text(_context("hi", key="bad"))
    assert (
        bad_key.error is not None
        and bad_key.error.category is ErrorCategory.INVALID_CREDENTIAL
    )


async def test_facade_bad_payload_is_bad_request() -> None:
    context = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="m",
        request_id="r",
        tenant_id="t",
        credential_mode=CredentialMode.USER_KEY,
        credential_value="mock-key-x",
        payload={},
        timeout_ms=1000,
    )
    result = await generate_text(context)
    assert result.error is not None and result.error.category is ErrorCategory.BAD_REQUEST


def test_handlers_parity_with_definition() -> None:
    from providers._example.definition import DEFINITION

    assert {op.value for op in HANDLERS} == set(DEFINITION["operations"])  # type: ignore[arg-type]
