"""No-leak tests — route_token, secrets, slug NEVER appear in any trace.

Same discipline as the platform's tests/providers/test_groq_live.py:108
pattern: feed sensitive values through every surface and assert they are
absent from every response body. Plus the closed observability contract.
"""

from __future__ import annotations

import pytest

from gateway.observability import ForbiddenLogFieldError, validate_event
from tests.conftest import (
    EXAMPLE_SLUG,
    ROUTE_TOKEN,
    SECRET_V6,
    SECRET_V7,
    auth_headers,
    routed_headers,
    valid_envelope,
)

SENSITIVE = (ROUTE_TOKEN, SECRET_V7, SECRET_V6, EXAMPLE_SLUG, "mock-key-abc123")


def _assert_clean(text: str) -> None:
    for value in SENSITIVE:
        assert value not in text, f"sensitive value leaked: {value[:8]}..."


def test_no_leak_success_path(client) -> None:
    response = client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())
    assert response.status_code == 200
    _assert_clean(response.text)


def test_no_leak_all_error_paths(client) -> None:
    # 401 wrong secret
    headers = routed_headers()
    headers["X-Gateway-Secret"] = "wrong-secret-value"
    _assert_clean(client.post("/v1/execute", headers=headers, json=valid_envelope()).text)
    # 401 stale version
    headers = routed_headers()
    headers["X-Gateway-Secret-Version"] = "5"
    _assert_clean(client.post("/v1/execute", headers=headers, json=valid_envelope()).text)
    # 404 unknown route
    h404 = auth_headers()
    h404["X-Route-Token"] = "rtk_ghost"
    _assert_clean(client.post("/v1/execute", headers=h404, json=valid_envelope()).text)
    # 400 malformed
    _assert_clean(client.post("/v1/execute", headers=routed_headers(), json={}).text)
    # 200 execution failures (bad key / rate limit / server error)
    for envelope in (
        valid_envelope(credential={"mode": "user_key", "value": "wrong-key"}),
        valid_envelope(payload={"messages": [{"role": "user", "content": "TRIGGER_RATE_LIMIT"}]}),
        valid_envelope(
            payload={"messages": [{"role": "user", "content": "TRIGGER_SERVER_ERROR"}]}
        ),
    ):
        _assert_clean(client.post("/v1/execute", headers=routed_headers(), json=envelope).text)


def test_no_leak_discovery_surfaces(client) -> None:
    for path in ("/v1/describe", "/v1/models", "/v1/health"):
        response = client.get(path, headers=routed_headers())
        assert response.status_code == 200
        _assert_clean(response.text)  # includes: slug never crosses


def test_slug_never_in_describe(client) -> None:
    body = client.get("/v1/describe", headers=routed_headers()).text
    assert EXAMPLE_SLUG not in body


def test_observability_closed_field_set_rejects_unknown_keys() -> None:
    validate_event({"request_id": "r", "operation": "generate_text", "latency_ms": 5})
    with pytest.raises(ForbiddenLogFieldError):
        validate_event({"request_id": "r", "route_token": "rtk_x"})
    with pytest.raises(ForbiddenLogFieldError):
        validate_event({"slug": EXAMPLE_SLUG})
    with pytest.raises(ForbiddenLogFieldError):
        validate_event({"credential_value": "secret"})
    with pytest.raises(ForbiddenLogFieldError):
        validate_event({"exception_class": "ValueError"})


def test_exception_names_never_cross_the_wire(client, providers) -> None:
    """Force an internal crash; the 500 body must be sanitized."""

    from gateway.contracts import GatewayOperation

    provider = providers.get(EXAMPLE_SLUG)
    assert provider is not None

    async def exploding_handler(_context):  # noqa: ANN001
        raise RuntimeError("SECRET_INTERNAL_DETAIL_XYZ")

    handlers = provider.handlers()
    original = handlers[GatewayOperation.GENERATE_TEXT]
    handlers[GatewayOperation.GENERATE_TEXT] = exploding_handler
    try:
        response = client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())
        assert response.status_code == 500
        body = response.json()
        assert body["error"]["category"] == "retryable_server_error"
        assert "RuntimeError" not in response.text
        assert "SECRET_INTERNAL_DETAIL_XYZ" not in response.text
        _assert_clean(response.text)
    finally:
        handlers[GatewayOperation.GENERATE_TEXT] = original
