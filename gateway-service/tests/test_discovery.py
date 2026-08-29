"""Discovery tests — /v1/describe, /v1/models, /v1/health projections."""

from __future__ import annotations

from tests.conftest import auth_headers, routed_headers


def test_describe_projection(client) -> None:
    response = client.get("/v1/describe", headers=routed_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Example Provider (mock)"
    assert body["credential_mode"] == "user_key"
    assert body["operations"] == ["generate_text"]
    assert body["models"] == [{"name": "example-mock-model", "context_window": 8192}]
    assert body["definition_version"] == "1.0.0"
    assert body["health_supported"] is False


def test_describe_requires_auth(client) -> None:
    response = client.get("/v1/describe", headers={"X-Route-Token": "anything"})
    assert response.status_code == 401


def test_describe_route_token_in_header_not_url(client) -> None:
    # OPEN-3: the token travels ONLY in X-Route-Token. A token in the query
    # string must NOT route (and without the header the lookup fails 404).
    response = client.get(
        "/v1/describe?route_token=rtk_unit_test_opaque_token_value",
        headers=auth_headers(),
    )
    assert response.status_code == 404


def test_models_subset(client) -> None:
    response = client.get("/v1/models", headers=routed_headers())
    assert response.status_code == 200
    assert response.json() == {
        "models": [{"name": "example-mock-model", "context_window": 8192}]
    }


def test_health_unknown_is_honest(client) -> None:
    response = client.get("/v1/health", headers=routed_headers())
    assert response.status_code == 200
    assert response.json() == {"status": "UNKNOWN", "checked_at": None}


def test_discovery_unknown_route_uniform_404(client) -> None:
    for path in ("/v1/describe", "/v1/models", "/v1/health"):
        headers = auth_headers()
        headers["X-Route-Token"] = "rtk_ghost"
        response = client.get(path, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "unknown route"
