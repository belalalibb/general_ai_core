"""S2 — one long-lived pooled httpx client per RemoteGatewayAdapter.

Pins: the same client instance serves successive calls (no per-attempt
client construction), per-request timeouts still ride each request,
``aclose`` releases idempotently, a closed pool is transparently rebuilt,
and the auth-expired self-healing retry is unchanged over the pool.
Hermetic — httpx.MockTransport only.
"""

from __future__ import annotations

import httpx

from providers.real.gateway.adapter import GatewaySecret
from tests.providers.test_gateway_adapter import (
    GATEWAY_SECRET,
    _adapter,
    _generate_request,
    _success_body,
    run,
)


class TestPooledClient:
    def test_same_client_reused_across_calls(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        assert adapter._pooled_client is None  # lazy: nothing until first use
        run(adapter.generate(_generate_request()))
        first = adapter._pooled_client
        assert first is not None and not first.is_closed
        run(adapter.generate(_generate_request()))
        run(adapter.discover_models())
        assert adapter._pooled_client is first  # ONE client, three exchanges
        assert len(recorder.requests) == 3

    def test_per_request_timeout_rides_each_request(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))  # timeout_ms=5_000
        timeout = recorder.requests[0].extensions["timeout"]
        assert timeout["read"] == 5.0

    def test_aclose_releases_and_is_idempotent(self) -> None:
        adapter, _, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        client = adapter._pooled_client
        assert client is not None

        async def _close_twice() -> None:
            await adapter.aclose()
            await adapter.aclose()

        run(_close_twice())
        assert client.is_closed
        assert adapter._pooled_client is None

    def test_closed_pool_is_rebuilt_on_next_call(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        first = adapter._pooled_client
        run(adapter.aclose())
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True
        assert adapter._pooled_client is not first
        assert len(recorder.requests) == 2

    def test_auth_expired_retry_unchanged_over_pool(self) -> None:
        calls = {"n": 0}

        def _responder(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(401, json={"error": {"category": "auth_expired"}})
            return _success_body(request)

        adapter, recorder, resolve_log = _adapter(
            _responder,
            secret_sequence=[
                GatewaySecret(value=GATEWAY_SECRET, version=3),
                GatewaySecret(value=GATEWAY_SECRET, version=4),
            ],
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True
        assert len(recorder.requests) == 2  # exactly one retry
        assert len(resolve_log) == 2  # secret re-read per attempt
        client = adapter._pooled_client
        assert client is not None and not client.is_closed
