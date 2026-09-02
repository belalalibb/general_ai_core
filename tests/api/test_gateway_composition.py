"""Composition-root wiring tests for the ADR-0008 gateway binding (G2).

Hermetic: ``environ`` is injected as a plain dict — no real environment
variables are read; the built adapter runs against ``httpx.MockTransport``.
Verified WIRING policy (same posture as test_composition_bindings_t075):

- "not configured ⇒ binding absent": no GATEWAY_BASE_URL returns None.
- half-configuration is an ERROR, never a silent guess (20 §5).
- OPEN-4: https is REQUIRED; plaintext only for explicit loopback dev.
- settings reprs never leak the gateway secret (20 §5 — reprs get logged).
- the builder produces a working RemoteGatewayAdapter bound to the
  configured gateway with the configured secret/version headers.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.composition import (
    GatewaySettings,
    build_gateway_adapter,
    gateway_settings_from_env,
)
from core.contracts.provider import (
    ProviderCapabilities,
    ProviderGenerateRequest,
    ProviderOperation,
)
from providers.real.gateway import (
    CREDENTIAL_MODE_PLATFORM,
    RemoteGatewayAdapter,
    build_gateway_manifest,
)

SECRET = "gwsecret_TEST_ONLY_composition_value"
ROUTE_TOKEN = "routetok_TEST_ONLY_composition_token"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class TestGatewaySettings:
    def test_not_configured_returns_none(self) -> None:
        assert gateway_settings_from_env({}) is None

    def test_blank_base_url_is_not_configured(self) -> None:
        assert gateway_settings_from_env({"GATEWAY_BASE_URL": "   "}) is None

    def test_full_configuration_parsed(self) -> None:
        settings = gateway_settings_from_env(
            {
                "GATEWAY_BASE_URL": "https://gateway.internal.example/",
                "GATEWAY_SECRET": SECRET,
                "GATEWAY_SECRET_VERSION": "7",
            }
        )
        assert settings == GatewaySettings(
            base_url="https://gateway.internal.example",  # trailing slash stripped
            secret=SECRET,
            secret_version=7,
        )

    @pytest.mark.parametrize(
        "partial",
        [
            {},
            {"GATEWAY_SECRET": SECRET},
            {"GATEWAY_SECRET_VERSION": "1"},
        ],
    )
    def test_half_configuration_is_error(self, partial: dict[str, str]) -> None:
        env = {"GATEWAY_BASE_URL": "https://gw.example", **partial}
        with pytest.raises(ValueError, match="half-configured"):
            gateway_settings_from_env(env)

    @pytest.mark.parametrize("bad_version", ["0", "-1", "two", "1.5", ""])
    def test_bad_version_is_error(self, bad_version: str) -> None:
        env = {
            "GATEWAY_BASE_URL": "https://gw.example",
            "GATEWAY_SECRET": SECRET,
            "GATEWAY_SECRET_VERSION": bad_version,
        }
        with pytest.raises(ValueError):
            gateway_settings_from_env(env)

    def test_plaintext_non_loopback_rejected(self) -> None:
        """OPEN-4: TLS to the gateway — http:// to a real host is an error."""
        env = {
            "GATEWAY_BASE_URL": "http://gateway.internal.example",
            "GATEWAY_SECRET": SECRET,
            "GATEWAY_SECRET_VERSION": "1",
        }
        with pytest.raises(ValueError, match="https"):
            gateway_settings_from_env(env)

    @pytest.mark.parametrize(
        "loopback",
        ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost/x"],
    )
    def test_loopback_plaintext_allowed_for_dev(self, loopback: str) -> None:
        env = {
            "GATEWAY_BASE_URL": loopback,
            "GATEWAY_SECRET": SECRET,
            "GATEWAY_SECRET_VERSION": "1",
        }
        settings = gateway_settings_from_env(env)
        assert settings is not None

    def test_loopback_lookalike_host_rejected(self) -> None:
        """localhost.evil.example must not pass the loopback exception."""
        env = {
            "GATEWAY_BASE_URL": "http://localhost.evil.example",
            "GATEWAY_SECRET": SECRET,
            "GATEWAY_SECRET_VERSION": "1",
        }
        with pytest.raises(ValueError, match="https"):
            gateway_settings_from_env(env)

    def test_repr_scrubs_secret(self) -> None:
        settings = GatewaySettings(base_url="https://gw.example", secret=SECRET, secret_version=2)
        text = repr(settings)
        assert SECRET not in text
        assert "[SCRUBBED]" in text


class TestBuildGatewayAdapter:
    def test_builder_produces_bound_working_adapter(self) -> None:
        settings = GatewaySettings(base_url="https://gw.example", secret=SECRET, secret_version=5)
        seen: list[httpx.Request] = []

        def _responder(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                json={
                    "succeeded": True,
                    "output": {"content": "ok"},
                    "usage": {"units": 1},
                    "latency_ms": 3,
                    "error": None,
                },
            )

        manifest = build_gateway_manifest(
            provider_key="remote-alpha",
            display_name="Remote Alpha",
            operations=[ProviderOperation.GENERATE_TEXT],
            capabilities=ProviderCapabilities(chat=True),
        )
        adapter = build_gateway_adapter(
            settings,
            manifest=manifest,
            route_token_resolver=lambda: ROUTE_TOKEN,
            credential_mode=CREDENTIAL_MODE_PLATFORM,
            transport=httpx.MockTransport(_responder),
        )
        assert isinstance(adapter, RemoteGatewayAdapter)
        result = run(
            adapter.generate(
                ProviderGenerateRequest(
                    request_id=uuid4(),
                    tenant_id=uuid4(),
                    operation=ProviderOperation.GENERATE_TEXT,
                    provider_model_name="alpha-model-1",
                    credential_ref="credref_unused_in_platform_mode",
                    payload={"ask": "hello"},
                    timeout_ms=2_000,
                )
            )
        )
        assert result.succeeded is True
        (request,) = seen
        assert request.url.host == "gw.example"
        assert request.headers["X-Gateway-Secret"] == SECRET
        assert request.headers["X-Gateway-Secret-Version"] == "5"
        assert request.headers["X-Route-Token"] == ROUTE_TOKEN
        assert json.loads(request.content)["credential"] == {"mode": "platform"}
