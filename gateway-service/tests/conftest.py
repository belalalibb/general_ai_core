"""Hermetic test fixtures — NO network anywhere in this suite.

The _example provider (mock upstream, in-process) is registered here for
test purposes only; it is never registered in any live composition.
"""

from __future__ import annotations

import sys
from pathlib import Path

# gateway-service is a self-contained project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from gateway.config import GatewayConfig
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from providers._example.definition import DEFINITION as EXAMPLE_DEFINITION

SECRET_V7 = "unit-test-secret-version-seven"
SECRET_V6 = "unit-test-secret-version-six!"
ROUTE_TOKEN = "rtk_unit_test_opaque_token_value"
EXAMPLE_SLUG = "example_mock"  # gateway-private; must never cross the wire


@pytest.fixture()
def config() -> GatewayConfig:
    return GatewayConfig(
        secrets_by_version={7: SECRET_V7, 6: SECRET_V6},
        current_secret_version=7,
        route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        dual_accept_window_seconds=600,
    )


@pytest.fixture()
def providers() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        slug=EXAMPLE_SLUG,
        raw_definition=dict(EXAMPLE_DEFINITION),
        facade_module="providers._example.adapter",
    )
    return registry


@pytest.fixture()
def routes(config: GatewayConfig) -> RouteRegistry:
    return RouteRegistry(config.route_map)


@pytest.fixture()
def client(config: GatewayConfig, providers: ProviderRegistry, routes: RouteRegistry):
    from fastapi.testclient import TestClient

    from app import build_app

    with TestClient(build_app(config, providers, routes)) as test_client:
        yield test_client


def auth_headers(version: int = 7, secret: str = SECRET_V7) -> dict[str, str]:
    return {"X-Gateway-Secret": secret, "X-Gateway-Secret-Version": str(version)}


def routed_headers(token: str = ROUTE_TOKEN, **auth_kwargs: object) -> dict[str, str]:
    headers = auth_headers(**auth_kwargs)  # type: ignore[arg-type]
    headers["X-Route-Token"] = token
    return headers


def valid_envelope(**overrides: object) -> dict[str, object]:
    envelope: dict[str, object] = {
        "operation": "generate_text",
        "model": "example-mock-model",
        "request_id": "req_unit_0001",
        "tenant_id": "ten_unit_0001",
        "credential": {"mode": "user_key", "value": "mock-key-abc123"},
        "payload": {"messages": [{"role": "user", "content": "hello gateway"}]},
        "timeout_ms": 30000,
    }
    envelope.update(overrides)
    return envelope
