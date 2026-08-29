"""Remote Gateway adapter contract tests (G2; ADR-0008 ACCEPTED 2026-08-29).

HERMETIC — every test runs against ``httpx.MockTransport``; the gates never
touch the network. No live gateway, no credentials, no external calls.

Coverage map (G2 authorization requirements):

- contract parity (mechanical)   -> TestContractParity (loads the G1
  ``gateway-service/gateway/contracts.py`` by file path, READ-ONLY, and
  proves the platform contracts and the adapter's mirrored constants agree)
- route-token handling           -> TestSecurityHeaders (header always,
  never URL path/query)
- auth + version headers         -> TestSecurityHeaders, TestAuthRetry
- self-healing rotation retry    -> TestAuthRetry (401 auth_expired =>
  re-read secret, retry exactly once; wrong secret => no retry)
- unsupported operation          -> TestUnsupportedOperations (undeclared
  + OPEN-2 excluded; both without any network call)
- all 12 error categories        -> TestAllTwelveCategories
- no-leak                        -> TestNoLeak (secret / route token /
  BYOK key / slug never in responses, error messages, or reprs)
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from core.contracts.provider import (
    HealthScope,
    ProviderCapabilities,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealthState,
    ProviderOperation,
)
from providers.real.gateway import (
    CREDENTIAL_MODE_PLATFORM,
    CREDENTIAL_MODE_USER_KEY,
    EXCLUDED_OPERATIONS_V1,
    GatewayCredentialCheckUnsupported,
    GatewaySecret,
    RemoteGatewayAdapter,
    build_gateway_manifest,
)
from providers.real.gateway.adapter import (
    HEADER_GATEWAY_SECRET,
    HEADER_GATEWAY_SECRET_VERSION,
    HEADER_ROUTE_TOKEN,
)

# Test-only sentinel values (never real credentials).
GATEWAY_SECRET = "gwsecret_TEST_ONLY_fake_value_for_mock_transport"
GATEWAY_SECRET_VERSION = 3
ROUTE_TOKEN = "routetok_TEST_ONLY_fake_opaque_token"
USER_KEY = "userkey_TEST_ONLY_fake_byok_value"
CRED_REF = "credref_test_opaque_handle"
INTERNAL_SLUG = "slug_TEST_ONLY_never_crosses"  # must never appear anywhere

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATEWAY_CONTRACTS_PATH = _REPO_ROOT / "gateway-service" / "gateway" / "contracts.py"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _load_gateway_contracts() -> Any:
    """Load the G1 wire-contract module by file path — READ-ONLY.

    No sys.path pollution, no gateway-service package import; the module
    has no gateway-internal imports (pydantic/stdlib only).
    """
    name = "g1_gateway_contracts_readonly"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, _GATEWAY_CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: the module uses `from __future__ import
    # annotations`, so pydantic resolves its forward references through
    # sys.modules[cls.__module__] at validation time.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Records every outgoing request so tests can inspect what crossed."""

    def __init__(self, responder: Any) -> None:
        self.requests: list[httpx.Request] = []
        self._responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _manifest() -> Any:
    return build_gateway_manifest(
        provider_key="remote-alpha",
        display_name="Remote Alpha",
        operations=[ProviderOperation.GENERATE_TEXT],
        capabilities=ProviderCapabilities(chat=True),
    )


def _adapter(
    handler: Any,
    *,
    credential_mode: str = CREDENTIAL_MODE_USER_KEY,
    secret_sequence: list[GatewaySecret] | None = None,
) -> tuple[RemoteGatewayAdapter, _Recorder, list[int]]:
    """Build an adapter over MockTransport; returns (adapter, recorder, resolve_log)."""
    recorder = _Recorder(handler)
    resolve_log: list[int] = []
    secrets = secret_sequence or [
        GatewaySecret(value=GATEWAY_SECRET, version=GATEWAY_SECRET_VERSION)
    ]

    def _secret_resolver() -> GatewaySecret:
        index = min(len(resolve_log), len(secrets) - 1)
        resolve_log.append(index)
        return secrets[index]

    adapter = RemoteGatewayAdapter(
        _manifest(),
        base_url="https://gateway.internal.test",
        gateway_secret_resolver=_secret_resolver,
        route_token_resolver=lambda: ROUTE_TOKEN,
        credential_mode=credential_mode,
        user_key_resolver=(
            (lambda ref: USER_KEY) if credential_mode == CREDENTIAL_MODE_USER_KEY else None
        ),
        transport=httpx.MockTransport(recorder),
    )
    return adapter, recorder, resolve_log


def _generate_request(
    operation: ProviderOperation = ProviderOperation.GENERATE_TEXT,
) -> ProviderGenerateRequest:
    return ProviderGenerateRequest(
        request_id=uuid4(),
        tenant_id=uuid4(),
        operation=operation,
        provider_model_name="alpha-model-1",
        credential_ref=CRED_REF,
        payload={"ask": "hello"},
        timeout_ms=5_000,
    )


def _success_body(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "succeeded": True,
            "output": {"content": "hi", "finish_reason": "stop"},
            "usage": {"input_tokens": 3, "output_tokens": 5, "units": 1},
            "latency_ms": 12,
            "error": None,
        },
    )


def _wire_failure(
    category: str,
    *,
    retryable: bool,
    retry_after_ms: int | None = None,
    provider_code: str | None = None,
) -> Any:
    def _responder(request: httpx.Request) -> httpx.Response:
        error: dict[str, Any] = {
            "category": category,
            "retryable": retryable,
            "message": f"normalized {category} from facade",
        }
        if retry_after_ms is not None:
            error["retry_after_ms"] = retry_after_ms
        if provider_code is not None:
            error["provider_code"] = provider_code
        return httpx.Response(
            200,
            json={
                "succeeded": False,
                "output": None,
                "usage": None,
                "latency_ms": 7,
                "error": error,
            },
        )

    return _responder


# --------------------------------------------------------------------------- #
# Contract parity — mechanical, against the ACTUAL G1 module (read-only)      #
# --------------------------------------------------------------------------- #


class TestContractParity:
    def test_g1_contracts_file_exists(self) -> None:
        assert _GATEWAY_CONTRACTS_PATH.is_file()

    def test_error_categories_identical_and_ordered(self) -> None:
        gw = _load_gateway_contracts()
        core_values = [m.value for m in ProviderErrorCategory]
        gateway_values = [m.value for m in gw.ErrorCategory]
        assert gateway_values == core_values  # 12 values, verbatim, same order

    def test_gateway_operations_are_exact_core_subset(self) -> None:
        gw = _load_gateway_contracts()
        core_ops = {m.value for m in ProviderOperation}
        gateway_ops = {m.value for m in gw.GatewayOperation}
        assert gateway_ops <= core_ops
        assert core_ops - gateway_ops == set(gw.EXCLUDED_OPERATIONS)

    def test_excluded_operations_mirror_matches_g1(self) -> None:
        gw = _load_gateway_contracts()
        assert EXCLUDED_OPERATIONS_V1 == frozenset(gw.EXCLUDED_OPERATIONS)

    def test_capability_keys_match_core_capabilities(self) -> None:
        gw = _load_gateway_contracts()
        core_keys = set(ProviderCapabilities.model_fields.keys())
        assert set(gw.CAPABILITY_KEYS) == core_keys

    def test_header_names_mirror_matches_g1(self) -> None:
        gw = _load_gateway_contracts()
        assert HEADER_GATEWAY_SECRET == gw.HEADER_GATEWAY_SECRET
        assert HEADER_GATEWAY_SECRET_VERSION == gw.HEADER_GATEWAY_SECRET_VERSION
        assert HEADER_ROUTE_TOKEN == gw.HEADER_ROUTE_TOKEN

    def test_credential_modes_mirror_matches_g1(self) -> None:
        gw = _load_gateway_contracts()
        assert {CREDENTIAL_MODE_USER_KEY, CREDENTIAL_MODE_PLATFORM} == {
            m.value for m in gw.CredentialMode
        }

    def test_adapter_envelope_is_valid_g1_request_envelope(self) -> None:
        """The adapter's serialized envelope parses under the ACTUAL G1 model."""
        gw = _load_gateway_contracts()
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        (request,) = recorder.requests
        envelope = json.loads(request.content)
        parsed = gw.RequestEnvelope.model_validate(envelope)  # extra=forbid
        assert parsed.operation.value == "generate_text"
        assert parsed.credential.mode.value == CREDENTIAL_MODE_USER_KEY

    def test_g1_success_envelope_parses_into_core_response(self) -> None:
        """A G1-valid ResponseEnvelope round-trips into the core response."""
        gw = _load_gateway_contracts()
        body = _success_body(None).json()
        gw.ResponseEnvelope.model_validate(body)  # valid on the wire side
        adapter, _, _ = _adapter(_success_body)
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True
        assert result.output == {"content": "hi", "finish_reason": "stop"}
        assert result.usage == {"input_tokens": 3, "output_tokens": 5, "units": 1}


# --------------------------------------------------------------------------- #
# Security headers: secret+version on every call; route token HEADER only     #
# --------------------------------------------------------------------------- #


class TestSecurityHeaders:
    def test_execute_carries_all_three_headers(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        (request,) = recorder.requests
        assert request.headers[HEADER_GATEWAY_SECRET] == GATEWAY_SECRET
        assert request.headers[HEADER_GATEWAY_SECRET_VERSION] == str(
            GATEWAY_SECRET_VERSION
        )
        assert request.headers[HEADER_ROUTE_TOKEN] == ROUTE_TOKEN

    def test_discovery_and_health_carry_headers_too(self) -> None:
        def _responder(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"models": []})
            return httpx.Response(200, json={"status": "OK", "checked_at": None})

        adapter, recorder, _ = _adapter(_responder)
        run(adapter.discover_models())
        run(adapter.health_check(HealthScope.PROVIDER))
        assert len(recorder.requests) == 2
        for request in recorder.requests:
            assert request.headers[HEADER_ROUTE_TOKEN] == ROUTE_TOKEN
            assert request.headers[HEADER_GATEWAY_SECRET] == GATEWAY_SECRET

    def test_route_token_never_in_url(self) -> None:
        """OPEN-3: the token appears in the header and NOWHERE in the URL."""
        def _responder(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"models": []})
            if request.url.path == "/v1/health":
                return httpx.Response(200, json={"status": "OK", "checked_at": None})
            return _success_body(request)

        adapter, recorder, _ = _adapter(_responder)
        run(adapter.generate(_generate_request()))
        run(adapter.discover_models())
        run(adapter.health_check(HealthScope.PROVIDER))
        for request in recorder.requests:
            url = str(request.url)
            assert ROUTE_TOKEN not in url
            assert GATEWAY_SECRET not in url
            assert request.url.query == b""

    def test_operation_rides_envelope_not_url(self) -> None:
        """OPEN-1: unified /v1/execute — no per-operation routes."""
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        (request,) = recorder.requests
        assert request.url.path == "/v1/execute"
        assert json.loads(request.content)["operation"] == "generate_text"


# --------------------------------------------------------------------------- #
# Self-healing rotation: 401 auth_expired => re-read secret, retry ONCE       #
# --------------------------------------------------------------------------- #

_STALE_401 = {
    "error": {
        "category": "auth_expired",
        "retryable": True,
        "message": "secret version no longer accepted; current is 4",
    }
}
_WRONG_401 = {
    "error": {
        "category": "invalid_credential",
        "retryable": False,
        "message": "gateway authentication failed",
    }
}


class TestAuthRetry:
    def test_auth_expired_rereads_secret_and_retries_once(self) -> None:
        rotated = GatewaySecret(value="gwsecret_TEST_ONLY_rotated", version=4)

        def _responder(request: httpx.Request) -> httpx.Response:
            if request.headers[HEADER_GATEWAY_SECRET_VERSION] == str(rotated.version):
                return _success_body(request)
            return httpx.Response(401, json=_STALE_401)

        adapter, recorder, resolve_log = _adapter(
            _responder,
            secret_sequence=[
                GatewaySecret(value=GATEWAY_SECRET, version=GATEWAY_SECRET_VERSION),
                rotated,
            ],
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True  # healed transparently
        assert len(recorder.requests) == 2  # exactly one retry
        assert len(resolve_log) == 2  # secret re-read per attempt
        assert recorder.requests[1].headers[HEADER_GATEWAY_SECRET] == rotated.value

    def test_auth_expired_retries_exactly_once_then_reports(self) -> None:
        adapter, recorder, _ = _adapter(
            lambda request: httpx.Response(401, json=_STALE_401)
        )
        result = run(adapter.generate(_generate_request()))
        assert len(recorder.requests) == 2  # never a third attempt
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.AUTH_EXPIRED
        assert result.error.retryable is True

    def test_wrong_secret_is_terminal_no_retry(self) -> None:
        adapter, recorder, _ = _adapter(
            lambda request: httpx.Response(401, json=_WRONG_401)
        )
        result = run(adapter.generate(_generate_request()))
        assert len(recorder.requests) == 1  # invalid_credential: no retry
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.INVALID_CREDENTIAL
        assert result.error.retryable is False


# --------------------------------------------------------------------------- #
# Unsupported operations: undeclared + OPEN-2 excluded — zero network         #
# --------------------------------------------------------------------------- #


class TestUnsupportedOperations:
    def test_undeclared_operation_rejected_without_network(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        result = run(
            adapter.generate(_generate_request(ProviderOperation.GENERATE_IMAGE))
        )
        assert recorder.requests == []  # no call crossed
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY

    @pytest.mark.parametrize(
        "operation",
        [
            ProviderOperation.RUN_PROVIDER_AGENT,
            ProviderOperation.UPLOAD_ASSET,
            ProviderOperation.DOWNLOAD_ASSET,
        ],
    )
    def test_open2_excluded_operations_rejected(
        self, operation: ProviderOperation
    ) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        result = run(adapter.generate(_generate_request(operation)))
        assert recorder.requests == []
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY
        assert result.error.provider_code == "excluded_operation_v1"

    def test_manifest_builder_refuses_excluded_operations(self) -> None:
        with pytest.raises(ValueError, match="OPEN-2"):
            build_gateway_manifest(
                provider_key="remote-bad",
                display_name="Remote Bad",
                operations=[ProviderOperation.RUN_PROVIDER_AGENT],
                capabilities=ProviderCapabilities(agent_module=True),
            )


# --------------------------------------------------------------------------- #
# All 12 error categories cross the boundary intact                           #
# --------------------------------------------------------------------------- #


class TestAllTwelveCategories:
    @pytest.mark.parametrize("category", list(ProviderErrorCategory))
    def test_wire_execution_failure_maps_one_to_one(
        self, category: ProviderErrorCategory
    ) -> None:
        """HTTP 200 + succeeded=false envelope: every category passes verbatim."""
        adapter, _, _ = _adapter(
            _wire_failure(
                category.value,
                retryable=category
                in (
                    ProviderErrorCategory.AUTH_EXPIRED,
                    ProviderErrorCategory.RATE_LIMITED,
                    ProviderErrorCategory.TIMEOUT,
                    ProviderErrorCategory.RETRYABLE_SERVER_ERROR,
                ),
                retry_after_ms=(
                    1500 if category is ProviderErrorCategory.RATE_LIMITED else None
                ),
                provider_code="upstream_evidence",
            )
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is category
        assert result.error.provider_code == "upstream_evidence"
        if category is ProviderErrorCategory.RATE_LIMITED:
            assert result.error.retry_after_ms == 1500

    def test_transport_timeout_maps_to_timeout(self) -> None:
        def _raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("boom", request=request)

        adapter, _, _ = _adapter(_raise_timeout)
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.TIMEOUT
        assert result.error.retryable is True

    def test_transport_failure_maps_to_provider_unavailable(self) -> None:
        def _raise_connect(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        adapter, _, _ = _adapter(_raise_connect)
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.PROVIDER_UNAVAILABLE
        assert result.error.retryable is True

    def test_http_400_maps_to_bad_request(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(
                400,
                json={
                    "error": {
                        "category": "bad_request",
                        "retryable": False,
                        "message": "malformed envelope",
                    }
                },
            )
        )
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.BAD_REQUEST

    def test_http_404_uniform_route_body_maps_to_provider_unavailable(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(
                404,
                json={
                    "error": {
                        "category": "provider_unavailable",
                        "retryable": False,
                        "message": "unknown route",
                    }
                },
            )
        )
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.PROVIDER_UNAVAILABLE
        assert result.error.retryable is False

    def test_http_500_maps_to_retryable_server_error(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(
                500,
                json={
                    "error": {
                        "category": "retryable_server_error",
                        "retryable": True,
                        "message": "gateway internal error",
                        "provider_code": "gw_fault",
                    }
                },
            )
        )
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.RETRYABLE_SERVER_ERROR
        assert result.error.retryable is True
        assert result.error.provider_code == "gw_fault"

    def test_malformed_200_body_is_non_retryable_never_a_crash(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(200, content=b"not json at all")
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.NON_RETRYABLE_ERROR
        assert result.error.provider_code == "malformed_gateway_response"

    def test_unknown_wire_category_treated_as_malformed(self) -> None:
        adapter, _, _ = _adapter(
            _wire_failure("totally_new_category", retryable=False)
        )
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.NON_RETRYABLE_ERROR
        assert result.error.provider_code == "malformed_gateway_response"


# --------------------------------------------------------------------------- #
# Port surface + remaining operations                                          #
# --------------------------------------------------------------------------- #


class TestPortSurface:
    def test_manifest_and_capabilities(self) -> None:
        adapter, _, _ = _adapter(_success_body)
        manifest = adapter.get_manifest()
        assert manifest.id == "remote-alpha"
        assert manifest.name == "Remote Alpha"
        assert manifest.status == "disabled"  # disabled until verified + enabled
        capabilities = run(adapter.get_capabilities())
        assert capabilities.chat is True

    def test_validate_credential_is_honest_refusal(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        with pytest.raises(GatewayCredentialCheckUnsupported):
            run(adapter.validate_credential(CRED_REF))
        assert recorder.requests == []  # no call, no fake answer
        normalized = adapter.normalize_error(
            GatewayCredentialCheckUnsupported("gateway v1 has no such surface")
        )
        assert normalized.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY

    def test_discover_models_projects_declared_models(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "alpha-model-1", "context_window": 8192},
                        {"name": "alpha-model-2", "context_window": None},
                    ]
                },
            )
        )
        models = run(adapter.discover_models())
        assert [m.provider_model_name for m in models] == [
            "alpha-model-1",
            "alpha-model-2",
        ]
        assert models[0].limits_metadata == {"context_window": 8192}

    def test_discover_models_honest_empty_on_failure(self) -> None:
        adapter, _, _ = _adapter(lambda request: httpx.Response(500, json={}))
        assert run(adapter.discover_models()) == []

    @pytest.mark.parametrize(
        ("wire_status", "expected"),
        [
            ("OK", ProviderHealthState.HEALTHY),
            ("DEGRADED", ProviderHealthState.DEGRADED),
            ("DOWN", ProviderHealthState.UNAVAILABLE),
            ("UNKNOWN", ProviderHealthState.UNAVAILABLE),  # unknown never healthy
        ],
    )
    def test_health_status_mapping(
        self, wire_status: str, expected: ProviderHealthState
    ) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(
                200, json={"status": wire_status, "checked_at": None}
            )
        )
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is expected
        assert health.provider_id == "remote-alpha"

    def test_health_unreachable_is_unavailable(self) -> None:
        def _raise(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        adapter, _, _ = _adapter(_raise)
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.UNAVAILABLE

    def test_platform_credential_mode_sends_no_value(self) -> None:
        adapter, recorder, _ = _adapter(
            _success_body, credential_mode=CREDENTIAL_MODE_PLATFORM
        )
        run(adapter.generate(_generate_request()))
        (request,) = recorder.requests
        credential = json.loads(request.content)["credential"]
        assert credential == {"mode": "platform"}  # no value key at all

    def test_user_key_mode_sends_resolved_key_in_envelope(self) -> None:
        adapter, recorder, _ = _adapter(_success_body)
        run(adapter.generate(_generate_request()))
        (request,) = recorder.requests
        credential = json.loads(request.content)["credential"]
        assert credential == {"mode": "user_key", "value": USER_KEY}

    def test_constructor_rejects_bad_wiring(self) -> None:
        with pytest.raises(ValueError, match="credential_mode"):
            RemoteGatewayAdapter(
                _manifest(),
                base_url="https://gateway.internal.test",
                gateway_secret_resolver=lambda: GatewaySecret(value="x", version=1),
                route_token_resolver=lambda: ROUTE_TOKEN,
                credential_mode="something_else",
            )
        with pytest.raises(ValueError, match="user_key_resolver"):
            RemoteGatewayAdapter(
                _manifest(),
                base_url="https://gateway.internal.test",
                gateway_secret_resolver=lambda: GatewaySecret(value="x", version=1),
                route_token_resolver=lambda: ROUTE_TOKEN,
                credential_mode=CREDENTIAL_MODE_USER_KEY,
                user_key_resolver=None,
            )


# --------------------------------------------------------------------------- #
# No-leak: secrets / tokens / BYOK keys / slug never escape                    #
# --------------------------------------------------------------------------- #


def _all_text_of(response: ProviderGenerateResponse) -> str:
    return response.model_dump_json()


class TestNoLeak:
    _SENTINELS = (GATEWAY_SECRET, ROUTE_TOKEN, USER_KEY, INTERNAL_SLUG)

    def test_success_response_carries_no_secret_material(self) -> None:
        adapter, _, _ = _adapter(_success_body)
        result = run(adapter.generate(_generate_request()))
        text = _all_text_of(result)
        for sentinel in self._SENTINELS:
            assert sentinel not in text

    def test_failure_responses_carry_no_secret_material(self) -> None:
        responders = [
            lambda request: httpx.Response(401, json=_WRONG_401),
            lambda request: httpx.Response(401, json=_STALE_401),
            lambda request: httpx.Response(404, json={"error": {
                "category": "provider_unavailable", "retryable": False,
                "message": "unknown route"}}),
            lambda request: httpx.Response(200, content=b"garbage"),
            _wire_failure("rate_limited", retryable=True, retry_after_ms=100),
        ]
        for responder in responders:
            adapter, _, _ = _adapter(responder)
            result = run(adapter.generate(_generate_request()))
            text = _all_text_of(result)
            for sentinel in self._SENTINELS:
                assert sentinel not in text

    def test_transport_exception_result_carries_no_secret_material(self) -> None:
        def _raise(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        adapter, _, _ = _adapter(_raise)
        result = run(adapter.generate(_generate_request()))
        text = _all_text_of(result)
        for sentinel in self._SENTINELS:
            assert sentinel not in text

    def test_gateway_secret_repr_is_scrubbed(self) -> None:
        secret = GatewaySecret(value=GATEWAY_SECRET, version=GATEWAY_SECRET_VERSION)
        assert GATEWAY_SECRET not in repr(secret)
        assert "[SCRUBBED]" in repr(secret)

    def test_health_and_discovery_never_leak(self) -> None:
        adapter, _, _ = _adapter(
            lambda request: httpx.Response(200, json={"status": "OK"})
        )
        health = run(adapter.health_check(HealthScope.PROVIDER))
        text = health.model_dump_json()
        for sentinel in self._SENTINELS:
            assert sentinel not in text

    def test_error_messages_never_echo_raw_bodies(self) -> None:
        """A hostile 500 body with sentinel-like content is never echoed."""
        hostile = {"error": {"category": "retryable_server_error",
                             "retryable": True,
                             "message": "leak " + INTERNAL_SLUG}}

        adapter, _, _ = _adapter(lambda request: httpx.Response(500, json=hostile))
        result = run(adapter.generate(_generate_request()))
        assert result.error is not None
        # 500 path uses the FIXED safe message; hostile body text is dropped.
        assert result.error.safe_message == "gateway internal error"
        assert INTERNAL_SLUG not in _all_text_of(result)
