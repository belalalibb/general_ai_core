"""Hermetic Groq provider tests — facade + Layer 1 with MockTransport only.

ZERO network. The upstream is an ``httpx.MockTransport`` installed through
the Layer-1 test seam; the "credential" is a test-only sentinel placed in
the environment variable NAME the provider documents.

Proves, per ONBOARDING.md: canonical success shape · category mapping ·
no-leak · DEFINITION <-> HANDLERS parity · schema policing (extras rejected
as bad_request).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.groq import _upstream
from providers.groq._upstream import GROQ_API_KEY_ENV
from providers.groq.adapter import HANDLERS, generate_text
from providers.groq.definition import DEFINITION

# Test-only sentinels — never real credentials.
FAKE_KEY = "gsk_TEST_ONLY_fake_groq_key_never_real"
UPSTREAM_SECRET_MARKER = "upstream-internal-detail-NEVER-crosses"


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GROQ_API_KEY_ENV, FAKE_KEY)


@pytest.fixture
def recorder() -> list[httpx.Request]:
    """The request log; the transport is installed per-test via _install."""
    return []


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responder: Any,
    log: list[httpx.Request],
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        return responder(request)

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))


def _context(payload: dict[str, Any] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="allam-2-7b",
        request_id="req_groq_1",
        tenant_id="ten_groq_1",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,  # platform mode: nothing crosses
        payload=payload
        if payload is not None
        else {"messages": [{"role": "user", "content": "hi"}]},
        timeout_ms=5_000,
    )


def _openai_success(
    content: str = "Hello!",
    finish_reason: str = "stop",
) -> Any:
    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": content},
                     "finish_reason": finish_reason}
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 7},
            },
        )

    return _responder


def _http_error(status: int, *, code: str | None = None, retry_after: str | None = None) -> Any:
    def _responder(request: httpx.Request) -> httpx.Response:
        body = {"error": {"message": UPSTREAM_SECRET_MARKER, "code": code or f"code_{status}"}}
        headers = {"retry-after": retry_after} if retry_after else {}
        return httpx.Response(status, json=body, headers=headers)

    return _responder


# ------------------------------------------------------------------------- #
# Parity + declaration honesty                                               #
# ------------------------------------------------------------------------- #


class TestDefinitionParity:
    def test_handlers_match_definition_operations(self) -> None:
        declared = {GatewayOperation(op) for op in DEFINITION["operations"]}  # type: ignore[union-attr]
        assert set(HANDLERS) == declared

    def test_definition_declares_platform_mode_and_generate_text_only(self) -> None:
        assert DEFINITION["credential_mode"] == "platform"
        assert DEFINITION["operations"] == ["generate_text"]
        assert DEFINITION["health_supported"] is False  # honest: no probe built


# ------------------------------------------------------------------------- #
# Canonical success                                                          #
# ------------------------------------------------------------------------- #


class TestSuccess:
    async def test_success_output_is_canonical_shape(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(_context())
        assert result.succeeded is True
        assert result.output is not None
        assert set(result.output) == {"text", "finish_reason"}
        assert result.output["text"] == "Hello!"
        assert result.output["finish_reason"] == "stop"
        assert result.usage is not None
        assert result.usage.input_tokens == 4
        assert result.usage.output_tokens == 7
        assert result.usage.units == 1

    async def test_key_travels_as_bearer_header_only(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        await generate_text(_context())
        assert len(recorder) == 1  # ONE request, ZERO retries
        request = recorder[0]
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        assert FAKE_KEY not in str(request.url)
        assert FAKE_KEY not in request.content.decode()

    async def test_params_forwarded_and_upstream_url_is_chat_completions(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        await generate_text(
            _context(
                {
                    "messages": [{"role": "user", "content": "hi"}],
                    "temperature": 0.1,
                    "max_tokens": 32,
                }
            )
        )
        body = json.loads(recorder[0].content)
        assert body["temperature"] == 0.1
        assert body["max_completion_tokens"] == 32
        assert body["model"] == "allam-2-7b"
        assert body["stream"] is False
        assert recorder[0].url.path.endswith("/chat/completions")

    @pytest.mark.parametrize(
        ("upstream", "canonical"),
        [("stop", "stop"), ("length", "length"), ("content_filter", "filter"),
         ("weird_new_reason", "stop")],
    )
    async def test_finish_reason_mapping(
        self,
        monkeypatch: pytest.MonkeyPatch,
        recorder: list[httpx.Request],
        upstream: str,
        canonical: str,
    ) -> None:
        _install(monkeypatch, _openai_success(finish_reason=upstream), recorder)
        result = await generate_text(_context())
        assert result.output is not None
        assert result.output["finish_reason"] == canonical


# ------------------------------------------------------------------------- #
# Schema policing (canonical payload only; extras -> bad_request)            #
# ------------------------------------------------------------------------- #


class TestSchemaPolicing:
    async def test_missing_messages_is_bad_request_no_network(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(_context({}))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []  # rejected BEFORE any upstream call

    async def test_extra_payload_keys_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], "ask": "sneaky"})
        )
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []

    async def test_malformed_message_item_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(_context({"messages": [{"role": "user"}]}))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []

    async def test_non_numeric_temperature_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], "temperature": "hot"})
        )
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []


# ------------------------------------------------------------------------- #
# Category mapping                                                           #
# ------------------------------------------------------------------------- #


class TestCategoryMapping:
    @pytest.mark.parametrize(
        ("status", "category"),
        [
            (401, ErrorCategory.INVALID_CREDENTIAL),
            (403, ErrorCategory.INVALID_CREDENTIAL),
            (404, ErrorCategory.MODEL_UNAVAILABLE),
            (429, ErrorCategory.RATE_LIMITED),
            (400, ErrorCategory.BAD_REQUEST),
            (422, ErrorCategory.BAD_REQUEST),
            (500, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (503, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (418, ErrorCategory.NON_RETRYABLE_ERROR),  # unmapped -> honest bucket
        ],
    )
    async def test_http_status_categories(
        self,
        monkeypatch: pytest.MonkeyPatch,
        recorder: list[httpx.Request],
        status: int,
        category: ErrorCategory,
    ) -> None:
        _install(monkeypatch, _http_error(status), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is category
        assert len(recorder) == 1  # ZERO retries in every failure path

    async def test_rate_limit_carries_retry_after_ms(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _http_error(429, retry_after="2"), recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.RATE_LIMITED
        assert result.error.retryable is True
        assert result.error.retry_after_ms == 2000

    async def test_content_policy_400_maps_to_content_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _http_error(400, code="content_policy_violation"), recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.CONTENT_REJECTED

    async def test_timeout_maps_to_timeout(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        def _raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("boom")

        _install(monkeypatch, _raise_timeout, recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.TIMEOUT
        assert result.error.retryable is True

    async def test_network_error_maps_to_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        def _raise_network(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        _install(monkeypatch, _raise_network, recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.PROVIDER_UNAVAILABLE

    async def test_missing_platform_key_is_invalid_credential_no_network(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        monkeypatch.delenv(GROQ_API_KEY_ENV, raising=False)
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.INVALID_CREDENTIAL
        assert result.error.provider_code == "platform_credential_missing"
        assert recorder == []

    async def test_malformed_200_body_never_crashes(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, lambda request: httpx.Response(200, text="not json"), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.provider_code == "malformed_upstream_body"


# ------------------------------------------------------------------------- #
# No-leak                                                                     #
# ------------------------------------------------------------------------- #


class TestNoLeak:
    async def test_error_results_never_carry_key_or_upstream_body(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _http_error(500), recorder)
        result = await generate_text(_context())
        dumped = result.model_dump_json()
        assert FAKE_KEY not in dumped
        assert UPSTREAM_SECRET_MARKER not in dumped  # raw body text never echoed
        assert "https://api.groq.com" not in dumped

    async def test_success_results_never_carry_key(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _openai_success(), recorder)
        result = await generate_text(_context())
        assert FAKE_KEY not in result.model_dump_json()

    async def test_exception_class_names_never_cross(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        def _raise_network(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("internal detail")

        _install(monkeypatch, _raise_network, recorder)
        result = await generate_text(_context())
        dumped = result.model_dump_json()
        assert "ConnectError" not in dumped
        assert "internal detail" not in dumped


# ------------------------------------------------------------------------- #
# Live registration wiring (app.py main() path, verified hermetically)       #
# ------------------------------------------------------------------------- #


class TestLiveRegistration:
    def test_register_live_providers_passes_eager_verification(self) -> None:
        from app import register_live_providers
        from gateway.provider_registry import ProviderRegistry

        registry = ProviderRegistry()
        register_live_providers(registry)
        registry.eager_verify_all()  # DEFINITION valid + HANDLERS parity
        assert registry.get("groq") is not None
