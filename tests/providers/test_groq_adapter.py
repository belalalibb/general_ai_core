"""Groq real-provider contract tests (T-IMPL-036; 31 §19 steps 9-10, §20 Type A).

HERMETIC — every test runs against ``httpx.MockTransport``; the gates never
touch the network. Live verification against the real endpoint is a separate,
manual, env-gated step (tests/providers/test_groq_live.py) per 41 §49.

31 §20 Type A required tests, mapped:

- api key validation        -> TestCredentialValidation
- text generation contract  -> TestGenerateContract
- streaming if declared     -> NOT declared (manifest has no streaming note;
                               stream=False is pinned in the request body)
- rate limit error mapping  -> TestErrorNormalization (429 + retry-after)
- secret redaction          -> TestSecretContainment
- provider unavailable      -> TestErrorNormalization (network failure)

Plus 31 §19 step 10 security checks and the manifest posture tests
(disabled-until-verified, real-not-template markers).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest

from core.contracts.domain import CredentialStatus
from core.contracts.provider import (
    HealthScope,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderHealthState,
    ProviderOperation,
)
from providers.real.groq import MANIFEST, GroqAdapter
from providers.real.groq.adapter import GroqCredentialCheckInconclusive

API_KEY = "gsk_TEST_ONLY_fake_key_for_mock_transport"
CRED_REF = "credref_test_opaque_handle"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _resolver(ref: str) -> str:
    assert ref == CRED_REF, f"adapter asked for unexpected ref: {ref}"
    return API_KEY


class _Recorder:
    """Records every outgoing request so tests can inspect what crossed."""

    def __init__(self, responder: Any) -> None:
        self.requests: list[httpx.Request] = []
        self._responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _adapter(responder: Any, *, health_ref: str | None = CRED_REF) -> tuple[GroqAdapter, _Recorder]:
    recorder = _Recorder(responder)
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=_resolver,
        health_credential_ref=health_ref,
        transport=httpx.MockTransport(recorder),
    )
    return adapter, recorder


def _generate_request(**overrides: Any) -> ProviderGenerateRequest:
    base: dict[str, Any] = {
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "operation": ProviderOperation.GENERATE_TEXT,
        "provider_model_name": "allam-2-7b",
        "credential_ref": CRED_REF,
        "payload": {"ask": "hello"},
    }
    base.update(overrides)
    return ProviderGenerateRequest.model_validate(base)


def _ok_chat(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": "hi there"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            "model": "allam-2-7b",
        },
    )


# --- manifest posture (31 §19 step 13; 41 §49) -----------------------------------------


class TestManifestPosture:
    def test_manifest_is_real_not_template(self) -> None:
        assert MANIFEST.is_template is False
        assert MANIFEST.is_functional is True
        assert MANIFEST.real_provider_required is False
        assert MANIFEST.auth.types  # real providers declare auth (30 §7)

    def test_manifest_ships_disabled_until_verified(self) -> None:
        # 31 §19 step 13: keep provider disabled until tests pass; step 14:
        # enable via Admin/Config only after verification.
        assert MANIFEST.status == "disabled"

    def test_manifest_declares_generate_text_only(self) -> None:
        assert MANIFEST.operations == [ProviderOperation.GENERATE_TEXT]
        assert MANIFEST.capabilities.chat is True
        # undeclared capabilities stay False (deny-by-default, 30 §4.3)
        assert MANIFEST.capabilities.image_generation is False
        assert MANIFEST.capabilities.audio_input is False

    def test_no_secret_material_anywhere_in_the_package(self) -> None:
        # 20 §5: the provider package must carry no key-shaped strings.
        import providers.real.groq
        import providers.real.groq.adapter

        for module in (providers.real.groq, providers.real.groq.adapter):
            source = open(module.__file__).read()  # noqa: SIM115
            assert "gsk_" not in source, f"key-shaped string in {module.__name__}"


# --- credential validation (31 §20: api key validation) ---------------------------------


class TestCredentialValidation:
    def test_valid_key_reports_active(self) -> None:
        adapter, recorder = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        health = run(adapter.validate_credential(CRED_REF))
        assert health.status is CredentialStatus.ACTIVE
        assert health.credential_ref == CRED_REF
        # the call was authenticated with the resolved key
        assert recorder.requests[0].headers["authorization"] == f"Bearer {API_KEY}"

    def test_rejected_key_reports_invalid(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(401, json={"error": {}}))
        health = run(adapter.validate_credential(CRED_REF))
        assert health.status is CredentialStatus.INVALID

    def test_server_error_is_inconclusive_not_a_verdict(self) -> None:
        # A 500 says NOTHING about the credential — it must not be recorded
        # as invalid (which could disable a good credential) nor as active.
        adapter, _ = _adapter(lambda req: httpx.Response(500))
        with pytest.raises(GroqCredentialCheckInconclusive):
            run(adapter.validate_credential(CRED_REF))

    def test_network_failure_is_inconclusive(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        adapter, _ = _adapter(explode)
        with pytest.raises(GroqCredentialCheckInconclusive):
            run(adapter.validate_credential(CRED_REF))

    def test_credential_health_never_carries_the_key(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        health = run(adapter.validate_credential(CRED_REF))
        assert API_KEY not in health.model_dump_json()


# --- text generation contract (31 §20) ---------------------------------------------------


class TestGenerateContract:
    def test_successful_generation_normalized_shape(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        request = _generate_request()
        response = run(adapter.generate(request))
        assert response.succeeded is True
        assert response.request_id == request.request_id
        assert response.output["content"] == "hi there"
        assert response.output["finish_reason"] == "stop"
        assert response.usage == {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}
        assert response.error is None
        assert response.latency_ms is not None and response.latency_ms >= 0
        # request body shape: model + user message from ask, stream pinned off
        sent = json.loads(recorder.requests[0].content)
        assert sent["model"] == "allam-2-7b"
        assert sent["stream"] is False
        assert {"role": "user", "content": "hello"} in sent["messages"]
        # R165 (live): GENERATE_TEXT declares no function tools, and says so —
        # gpt-oss otherwise emits a native tool call when the PROMPT names
        # tools and Groq answers 400 tool_use_failed.
        assert sent["tool_choice"] == "none"
        assert "tools" not in sent
        assert "response_format" not in sent  # plain asks are unconstrained

    def test_response_schema_maps_to_json_schema_response_format(self) -> None:
        """R165 (live): the agent's proposal schema becomes constrained decoding."""
        adapter, recorder = _adapter(_ok_chat)
        schema = {"type": "object", "properties": {"action": {"type": "string"}}}
        run(
            adapter.generate(
                _generate_request(
                    payload={"ask": "go", "response_schema": {"name": "p", "schema": schema}}
                )
            )
        )
        sent = json.loads(recorder.requests[0].content)
        assert sent["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "p", "schema": schema},
        }

    def test_malformed_response_schema_is_ignored(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        run(adapter.generate(_generate_request(payload={"ask": "go", "response_schema": "x"})))
        assert "response_format" not in json.loads(recorder.requests[0].content)

    def test_role_and_context_and_previous_output_map_to_messages(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        request = _generate_request(
            payload={
                "ask": "continue",
                "role": {"id": "r1", "objective": "You are terse."},
                "context": {"blocks": [{"kind": "preference", "text": "metric units"}]},
                "previous_output": {"content": "step one done"},
            }
        )
        run(adapter.generate(request))
        sent = json.loads(recorder.requests[0].content)
        roles = [m["role"] for m in sent["messages"]]
        assert roles == ["system", "system", "assistant", "user"]
        assert sent["messages"][0]["content"] == "You are terse."
        assert "metric units" in sent["messages"][1]["content"]
        assert sent["messages"][2]["content"] == "step one done"
        assert sent["messages"][3]["content"] == "continue"

    def test_generation_params_are_whitelisted(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        request = _generate_request(
            payload={
                "ask": "hi",
                "generation": {
                    "temperature": 0.2,
                    "max_tokens": 50,
                    "tools": [{"evil": "injection"}],  # NOT whitelisted
                    "response_format": {"type": "json"},  # NOT whitelisted
                },
            }
        )
        run(adapter.generate(request))
        sent = json.loads(recorder.requests[0].content)
        assert sent["temperature"] == 0.2
        assert sent["max_tokens"] == 50
        assert "tools" not in sent
        assert "response_format" not in sent

    def test_undeclared_operation_is_rejected_normalized(self) -> None:
        # 30 §8.1: the adapter rejects what the manifest does not declare.
        adapter, recorder = _adapter(_ok_chat)
        request = _generate_request(operation=ProviderOperation.GENERATE_IMAGE)
        response = run(adapter.generate(request))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY
        assert recorder.requests == []  # rejected BEFORE any network call

    def test_malformed_provider_json_normalizes_never_raises(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(200, json={"unexpected": True}))
        response = run(adapter.generate(_generate_request()))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.NON_RETRYABLE_ERROR

    def test_timeout_override_reaches_the_transport(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        run(adapter.generate(_generate_request(timeout_ms=5000)))
        # httpx exposes the effective timeout on the request extensions
        timeout = recorder.requests[0].extensions.get("timeout", {})
        assert timeout.get("read") == 5.0


# --- error normalization (31 §20: rate limit mapping + provider unavailable) ------------


class TestErrorNormalization:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, ProviderErrorCategory.INVALID_CREDENTIAL),
            (403, ProviderErrorCategory.INVALID_CREDENTIAL),
            (404, ProviderErrorCategory.MODEL_UNAVAILABLE),
            (400, ProviderErrorCategory.BAD_REQUEST),
            (422, ProviderErrorCategory.BAD_REQUEST),
            (429, ProviderErrorCategory.RATE_LIMITED),
            (500, ProviderErrorCategory.RETRYABLE_SERVER_ERROR),
            (503, ProviderErrorCategory.RETRYABLE_SERVER_ERROR),
        ],
    )
    def test_http_status_maps_to_normalized_category(
        self, status: int, expected: ProviderErrorCategory
    ) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(status, json={"error": {}}))
        response = run(adapter.generate(_generate_request()))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is expected

    def test_rate_limit_carries_retry_after_ms(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                429, headers={"retry-after": "2"}, json={"error": {"code": "rate_limited"}}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.RATE_LIMITED
        assert response.error.retryable is True
        assert response.error.retry_after_ms == 2000

    def test_content_policy_400_maps_to_content_rejected(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400, json={"error": {"code": "content_filter", "message": "nope"}}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.CONTENT_REJECTED

    def test_tool_use_failed_without_tools_returns_the_generation_as_text(self) -> None:
        """R165 (live): gpt-oss answered a tool-DESCRIBING prompt with a native
        function call although no tools were declared; Groq 400s but hands
        back the model's text in ``failed_generation``. We asked for text —
        that IS the text. It flows back as content for the caller's own
        validator (the agent refuses it as an invalid proposal, P4)."""
        native = '{"name": "ws_list", "arguments": {"path": ""}}'
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400,
                json={
                    "error": {
                        "code": "tool_use_failed",
                        "type": "invalid_request_error",
                        "message": "Tool choice is none, but model called a tool",
                        "failed_generation": native,
                    }
                },
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.succeeded is True
        assert response.error is None
        assert response.output == {"content": native, "finish_reason": "tool_use_failed"}

    def test_tool_use_failed_without_generation_stays_an_error(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400, json={"error": {"code": "tool_use_failed", "message": "x"}}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.BAD_REQUEST
        assert response.error.provider_code == "tool_use_failed"

    def test_network_failure_maps_to_provider_unavailable(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        adapter, _ = _adapter(explode)
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.PROVIDER_UNAVAILABLE
        assert response.error.retryable is True

    def test_timeout_maps_to_timeout_retryable(self) -> None:
        def slow(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        adapter, _ = _adapter(slow)
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.TIMEOUT
        assert response.error.retryable is True

    def test_raw_provider_error_message_never_crosses(self) -> None:
        # 30 §14: the raw message may echo request content — only the short
        # machine code may cross as provider_code.
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400,
                json={
                    "error": {
                        "code": "invalid_request_error",
                        "message": "SECRET-ECHO: user asked about gsk_something",
                    }
                },
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        serialized = response.error.model_dump_json()
        assert "SECRET-ECHO" not in serialized
        assert response.error.provider_code == "invalid_request_error"


# --- secret containment (31 §19 step 10; 20 §5) ------------------------------------------


class TestSecretContainment:
    def test_key_never_appears_in_any_returned_object(self) -> None:
        adapter, _ = _adapter(_ok_chat)
        response = run(adapter.generate(_generate_request()))
        assert API_KEY not in response.model_dump_json()

    def test_key_never_appears_in_failure_objects(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            # exception text deliberately carries the URL + headers bait
            raise httpx.ConnectError(f"failed: {request.url}", request=request)

        adapter, _ = _adapter(explode)
        response = run(adapter.generate(_generate_request()))
        assert API_KEY not in response.model_dump_json()

    def test_key_used_only_in_authorization_header(self) -> None:
        adapter, recorder = _adapter(_ok_chat)
        run(adapter.generate(_generate_request()))
        sent = recorder.requests[0]
        assert sent.headers["authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in sent.content.decode()  # never in the body
        assert API_KEY not in str(sent.url)  # never in the URL

    def test_resolver_called_lazily_per_call_never_cached_in_manifest(self) -> None:
        # The manifest (a shareable, loggable declaration) must not carry
        # the key even after generate() ran.
        adapter, _ = _adapter(_ok_chat)
        run(adapter.generate(_generate_request()))
        assert API_KEY not in adapter.get_manifest().model_dump_json()


# --- health + discovery (31 §19 steps 6, 12) ---------------------------------------------


class TestHealthAndDiscovery:
    def test_healthy_when_models_endpoint_authenticates(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.HEALTHY
        assert health.provider_id == "groq"

    def test_no_health_credential_reports_unavailable_honestly(self) -> None:
        # Cannot-verify is NOT healthy (30 §11 honesty).
        adapter, _ = _adapter(_ok_chat, health_ref=None)
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.UNAVAILABLE
        assert health.detail is not None

    def test_rejected_health_credential_degrades_not_kills(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(401))
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.DEGRADED

    def test_unreachable_provider_is_unavailable(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        adapter, _ = _adapter(explode)
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.UNAVAILABLE

    def test_discovery_reports_provider_declared_models(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "allam-2-7b", "context_window": 4096},
                        {"id": "openai/gpt-oss-20b", "context_window": 131072},
                        {"not_an_id": True},  # malformed entry skipped, not fatal
                    ]
                },
            )
        )
        models = run(adapter.discover_models())
        names = [m.provider_model_name for m in models]
        assert names == ["allam-2-7b", "openai/gpt-oss-20b"]
        assert models[0].limits_metadata == {"context_window": 4096}

    def test_discovery_without_health_credential_is_empty_never_invented(self) -> None:
        # 41 §49: no invented model names — cannot authenticate => [].
        adapter, recorder = _adapter(_ok_chat, health_ref=None)
        assert run(adapter.discover_models()) == []
        assert recorder.requests == []  # no unauthenticated probing either
