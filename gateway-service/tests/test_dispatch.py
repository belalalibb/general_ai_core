"""Dispatch tests — POST /v1/execute end to end, hermetic (mock upstream)."""

from __future__ import annotations

from tests.conftest import ROUTE_TOKEN, auth_headers, routed_headers, valid_envelope


def test_execute_success_wire_shape(client) -> None:
    response = client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())
    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["output"]["finish_reason"] == "stop"
    assert "hello gateway" in body["output"]["text"]
    assert body["usage"]["units"] == 1
    assert body["error"] is None
    assert body["latency_ms"] >= 0


def test_execute_missing_auth_401(client) -> None:
    response = client.post(
        "/v1/execute", headers={"X-Route-Token": ROUTE_TOKEN}, json=valid_envelope()
    )
    assert response.status_code == 401
    assert response.json()["error"]["category"] == "invalid_credential"


def test_execute_stale_secret_version_401_retryable(client) -> None:
    headers = routed_headers()
    headers["X-Gateway-Secret-Version"] = "5"
    response = client.post("/v1/execute", headers=headers, json=valid_envelope())
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["category"] == "auth_expired"
    assert body["error"]["retryable"] is True


def test_execute_previous_secret_version_accepted(client) -> None:
    # OPEN-7 dual-accept: version 6 works during the rotation window.
    from tests.conftest import SECRET_V6

    headers = routed_headers(version=6, secret=SECRET_V6)
    response = client.post("/v1/execute", headers=headers, json=valid_envelope())
    assert response.status_code == 200


def test_execute_unknown_route_uniform_404(client) -> None:
    headers = auth_headers()
    headers["X-Route-Token"] = "rtk_totally_unknown"
    response = client.post("/v1/execute", headers=headers, json=valid_envelope())
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "category": "provider_unavailable",
            "retryable": False,
            "message": "unknown route",
        }
    }


def test_execute_missing_route_token_uniform_404(client) -> None:
    response = client.post("/v1/execute", headers=auth_headers(), json=valid_envelope())
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "unknown route"


def test_execute_malformed_envelope_400(client) -> None:
    response = client.post(
        "/v1/execute", headers=routed_headers(), json={"not": "an envelope"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["category"] == "bad_request"


def test_execute_undeclared_operation_200_unsupported(client) -> None:
    envelope = valid_envelope(operation="create_embeddings", payload={"inputs": ["x"]})
    response = client.post("/v1/execute", headers=routed_headers(), json=envelope)
    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert body["error"]["category"] == "unsupported_capability"


def test_execute_credential_mode_mismatch_200_bad_request(client) -> None:
    envelope = valid_envelope(credential={"mode": "platform"})
    response = client.post("/v1/execute", headers=routed_headers(), json=envelope)
    assert response.status_code == 200
    assert response.json()["error"]["category"] == "bad_request"


def test_execute_upstream_rate_limit_maps_to_rate_limited(client) -> None:
    envelope = valid_envelope(
        payload={"messages": [{"role": "user", "content": "TRIGGER_RATE_LIMIT"}]}
    )
    response = client.post("/v1/execute", headers=routed_headers(), json=envelope)
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["category"] == "rate_limited"
    assert body["error"]["retryable"] is True
    assert body["error"]["retry_after_ms"] == 2000
    assert body["error"]["provider_code"] == "429"


def test_execute_bad_user_key_maps_to_invalid_credential(client) -> None:
    envelope = valid_envelope(credential={"mode": "user_key", "value": "wrong-key"})
    response = client.post("/v1/execute", headers=routed_headers(), json=envelope)
    assert response.status_code == 200
    assert response.json()["error"]["category"] == "invalid_credential"


def test_execute_upstream_5xx_maps_to_retryable_server_error(client) -> None:
    envelope = valid_envelope(
        payload={"messages": [{"role": "user", "content": "TRIGGER_SERVER_ERROR"}]}
    )
    response = client.post("/v1/execute", headers=routed_headers(), json=envelope)
    assert response.status_code == 200
    assert response.json()["error"]["category"] == "retryable_server_error"


def test_healthz_no_auth_no_info(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
