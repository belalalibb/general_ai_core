"""Hermetic AssemblyAI provider tests — facade + Layer 1 with MockTransport only.

ZERO network. The upstream is an ``httpx.MockTransport`` installed through
the Layer-1 test seam; the "credential" is a test-only sentinel placed in
the environment variable NAME the provider documents.

Mock bodies MIRROR what was recorded live in §2
(evidence/r174/02_upstream_probe/p1..p4): success shape with
input/output_tokens, the 401 ``{error,status}`` body, and the 400
``{code,message,metadata.errors[]}`` unknown-model body.

Proves, per ONBOARDING.md: canonical success shape · category mapping ·
no-leak · DEFINITION <-> HANDLERS parity · schema policing (extras rejected
as bad_request) · zero retries (ours AND upstream's, via fallback_config).
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
from providers.assemblyai import _upstream
from providers.assemblyai._upstream import ASSEMBLYAI_API_KEY_ENV
from providers.assemblyai.adapter import HANDLERS, generate_text
from providers.assemblyai.definition import DEFINITION

# Test-only sentinels — never real credentials.
FAKE_KEY = "TEST_ONLY_fake_assemblyai_key_never_real_0000"
UPSTREAM_SECRET_MARKER = "upstream-internal-detail-NEVER-crosses"


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ASSEMBLYAI_API_KEY_ENV, FAKE_KEY)


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


def _context(payload: dict[str, Any] | None = None, model: str = "qwen3.5-4b-32k-fast") -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model=model,
        request_id="req_aai_1",
        tenant_id="ten_aai_1",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,  # platform mode: nothing crosses
        payload=payload
        if payload is not None
        else {"messages": [{"role": "user", "content": "hi"}]},
        timeout_ms=5_000,
    )


def _live_success(
    content: str = "OK",
    finish_reason: str = "stop",
    *,
    usage: dict[str, Any] | None = None,
) -> Any:
    """Mirror of §2 p1 (200) — AssemblyAI's own usage names + OpenAI duplicates."""

    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request": {"temperature": 0, "model": "qwen3.5-4b-32k-fast", "max_tokens": 8},
                "request_id": "62053f87-0000-0000-0000-000000000000",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish_reason,
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": usage
                if usage is not None
                else {
                    "input_tokens": 19,
                    "prompt_tokens": 19,
                    "output_tokens": 2,
                    "completion_tokens": 2,
                    "total_tokens": 21,
                },
                "http_status_code": 200,
                "response_time": 47775149,
                "llm_status_code": 200,
            },
        )

    return _responder


def _error_shape_a(status: int) -> Any:
    """Mirror of §2 p3 (401): ``{"error": <text>, "status": "error", "request_id"}``."""

    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": UPSTREAM_SECRET_MARKER, "status": "error", "request_id": "rid-a"},
        )

    return _responder


def _error_shape_b(
    status: int, *, errors: list[str] | None = None, retry_after: str | None = None
) -> Any:
    """Mirror of §2 p4 (400): ``{"code", "message", "metadata": {"errors": [...]}}``."""

    def _responder(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = {
            "code": status,
            "message": UPSTREAM_SECRET_MARKER,
            "request_id": "rid-b",
        }
        if errors is not None:
            body["metadata"] = {"errors": errors}
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

    def test_declared_models_are_the_two_exercised_live(self) -> None:
        names = {m["name"] for m in DEFINITION["models"]}  # type: ignore[union-attr]
        assert names == {"qwen3.5-4b-32k-fast", "gemini-2.5-flash-lite"}

    def test_env_var_name_mirrors_groq_convention(self) -> None:
        assert ASSEMBLYAI_API_KEY_ENV == "GW_ASSEMBLYAI_API_KEY"


# ------------------------------------------------------------------------- #
# Canonical success                                                          #
# ------------------------------------------------------------------------- #


class TestSuccess:
    async def test_success_output_is_canonical_shape(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(_context())
        assert result.succeeded is True
        assert result.output is not None
        assert set(result.output) == {"text", "finish_reason"}
        assert result.output["text"] == "OK"
        assert result.output["finish_reason"] == "stop"
        assert result.usage is not None
        assert result.usage.input_tokens == 19
        assert result.usage.output_tokens == 2
        assert result.usage.units == 1

    async def test_key_travels_as_raw_authorization_header_only(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        await generate_text(_context())
        assert len(recorder) == 1  # ONE request, ZERO retries
        request = recorder[0]
        # Documented AssemblyAI form: RAW key, no "Bearer " prefix (§2 p1).
        assert request.headers["authorization"] == FAKE_KEY
        assert not request.headers["authorization"].startswith("Bearer")
        assert FAKE_KEY not in str(request.url)
        assert FAKE_KEY not in request.content.decode()

    async def test_params_forwarded_and_upstream_url_is_chat_completions(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
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
        assert body["max_tokens"] == 32  # AssemblyAI name (Groq: max_completion_tokens)
        assert body["model"] == "qwen3.5-4b-32k-fast"
        assert body["stream"] is False
        assert recorder[0].url.host == "llm-gateway.assemblyai.com"
        assert recorder[0].url.path == "/v1/chat/completions"

    async def test_upstream_retry_is_explicitly_disabled(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        """AssemblyAI defaults fallback_config.retry=true; CONTRACT v1 = zero retries."""
        _install(monkeypatch, _live_success(), recorder)
        await generate_text(_context())
        body = json.loads(recorder[0].content)
        assert body["fallback_config"] == {"retry": False}

    async def test_default_max_tokens_applied_when_absent(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        await generate_text(_context())
        body = json.loads(recorder[0].content)
        assert body["max_tokens"] == 1024
        assert "temperature" not in body

    async def test_only_canonical_payload_keys_reach_upstream(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        """No tools/response_format/transcript_id/fallbacks ever leave the facade."""
        _install(monkeypatch, _live_success(), recorder)
        await generate_text(_context())
        body = json.loads(recorder[0].content)
        assert set(body) == {"model", "messages", "max_tokens", "stream", "fallback_config"}

    async def test_usage_falls_back_to_openai_names(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(
            monkeypatch,
            _live_success(usage={"prompt_tokens": 5, "completion_tokens": 9}),
            recorder,
        )
        result = await generate_text(_context())
        assert result.usage is not None
        assert result.usage.input_tokens == 5
        assert result.usage.output_tokens == 9

    async def test_usage_absent_yields_none_tokens_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(usage={}), recorder)
        result = await generate_text(_context())
        assert result.succeeded is True
        assert result.usage is not None
        assert result.usage.input_tokens is None
        assert result.usage.output_tokens is None
        assert result.usage.units == 1

    @pytest.mark.parametrize(
        ("upstream", "canonical"),
        [
            ("stop", "stop"),
            ("length", "length"),
            ("content_filter", "filter"),
            ("weird_new_reason", "stop"),
        ],
    )
    async def test_finish_reason_mapping(
        self,
        monkeypatch: pytest.MonkeyPatch,
        recorder: list[httpx.Request],
        upstream: str,
        canonical: str,
    ) -> None:
        _install(monkeypatch, _live_success(finish_reason=upstream), recorder)
        result = await generate_text(_context())
        assert result.output is not None
        assert result.output["finish_reason"] == canonical

    async def test_model_passes_through_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        await generate_text(_context(model="gemini-2.5-flash-lite"))
        body = json.loads(recorder[0].content)
        assert body["model"] == "gemini-2.5-flash-lite"


# ------------------------------------------------------------------------- #
# Schema policing (canonical payload only; extras -> bad_request)            #
# ------------------------------------------------------------------------- #


class TestSchemaPolicing:
    async def test_missing_messages_is_bad_request_no_network(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(_context({}))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []  # rejected BEFORE any upstream call

    @pytest.mark.parametrize(
        "extra",
        ["ask", "tools", "response_format", "transcript_id", "fallbacks", "fallback_config"],
    )
    async def test_extra_payload_keys_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request], extra: str
    ) -> None:
        """AssemblyAI-specific extras are NOT smuggled through the canonical schema."""
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], extra: "sneaky"})
        )
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []

    async def test_malformed_message_item_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(_context({"messages": [{"role": "user"}]}))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []

    async def test_non_numeric_temperature_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], "temperature": "hot"})
        )
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert recorder == []

    async def test_non_integer_max_tokens_rejected(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], "max_tokens": "many"})
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
            (413, ErrorCategory.BAD_REQUEST),
            (422, ErrorCategory.BAD_REQUEST),
            (500, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (502, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (503, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (504, ErrorCategory.RETRYABLE_SERVER_ERROR),
            (418, ErrorCategory.NON_RETRYABLE_ERROR),  # unmapped -> honest bucket
        ],
    )
    async def test_http_status_categories_shape_b(
        self,
        monkeypatch: pytest.MonkeyPatch,
        recorder: list[httpx.Request],
        status: int,
        category: ErrorCategory,
    ) -> None:
        _install(monkeypatch, _error_shape_b(status), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is category
        assert result.error.provider_code == str(status)  # str(code), never text
        assert len(recorder) == 1  # ZERO retries in every failure path

    async def test_401_shape_a_is_invalid_credential(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        """The live 401 body (§2 p3) is NOT the OpenAPI ErrorResponse — must still map."""
        _install(monkeypatch, _error_shape_a(401), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.INVALID_CREDENTIAL
        assert result.error.provider_code == "http_401"  # no int code in shape A
        assert len(recorder) == 1

    async def test_unknown_model_400_is_model_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        """Mirror of §2 p4: upstream has no 404 for models; 400 + marker => model_unavailable."""
        _install(
            monkeypatch,
            _error_shape_b(400, errors=["model no-such-model-r174 is not supported"]),
            recorder,
        )
        result = await generate_text(_context(model="no-such-model-r174"))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.MODEL_UNAVAILABLE
        assert result.error.provider_code == "unsupported_model"
        assert len(recorder) == 1

    async def test_other_400_with_metadata_errors_stays_bad_request(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(
            monkeypatch,
            _error_shape_b(400, errors=["max_tokens must be >= 1"]),
            recorder,
        )
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert result.error.provider_code == "400"

    async def test_rate_limit_carries_retry_after_ms(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _error_shape_b(429, retry_after="2"), recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.RATE_LIMITED
        assert result.error.retryable is True
        assert result.error.retry_after_ms == 2000

    async def test_retry_after_not_attached_to_non_rate_limit(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _error_shape_b(503, retry_after="2"), recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.RETRYABLE_SERVER_ERROR
        assert result.error.retry_after_ms is None

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
        assert len(recorder) == 1

    async def test_network_error_maps_to_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        def _raise_network(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        _install(monkeypatch, _raise_network, recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.PROVIDER_UNAVAILABLE
        assert result.error.retryable is True

    async def test_missing_platform_key_is_invalid_credential_no_network(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        monkeypatch.delenv(ASSEMBLYAI_API_KEY_ENV, raising=False)
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.INVALID_CREDENTIAL
        assert result.error.provider_code == "platform_credential_missing"
        assert recorder == []

    async def test_empty_platform_key_treated_as_missing(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        monkeypatch.setenv(ASSEMBLYAI_API_KEY_ENV, "")
        _install(monkeypatch, _live_success(), recorder)
        result = await generate_text(_context())
        assert result.error is not None
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

    async def test_200_without_choices_is_malformed(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, lambda request: httpx.Response(200, json={"choices": []}), recorder)
        result = await generate_text(_context())
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.provider_code == "malformed_upstream_body"

    async def test_non_json_error_body_still_maps_by_status(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, lambda request: httpx.Response(502, text="<html>bad gateway</html>"), recorder)
        result = await generate_text(_context())
        assert result.error is not None
        assert result.error.category is ErrorCategory.RETRYABLE_SERVER_ERROR
        assert result.error.provider_code == "http_502"


# ------------------------------------------------------------------------- #
# No-leak                                                                     #
# ------------------------------------------------------------------------- #


class TestNoLeak:
    @pytest.mark.parametrize("responder", [_error_shape_a(401), _error_shape_b(500)])
    async def test_error_results_never_carry_key_or_upstream_body(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request], responder: Any
    ) -> None:
        _install(monkeypatch, responder, recorder)
        result = await generate_text(_context())
        dumped = result.model_dump_json()
        assert FAKE_KEY not in dumped
        assert UPSTREAM_SECRET_MARKER not in dumped  # raw body text never echoed (both shapes)
        assert "assemblyai.com" not in dumped
        assert "request_id" not in dumped  # upstream ids do not cross either

    async def test_unknown_model_error_never_echoes_metadata_text(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(
            monkeypatch,
            _error_shape_b(400, errors=[f"model {UPSTREAM_SECRET_MARKER} is not supported"]),
            recorder,
        )
        result = await generate_text(_context())
        dumped = result.model_dump_json()
        assert UPSTREAM_SECRET_MARKER not in dumped
        assert result.error is not None
        assert result.error.category is ErrorCategory.MODEL_UNAVAILABLE

    async def test_success_results_never_carry_key(
        self, monkeypatch: pytest.MonkeyPatch, recorder: list[httpx.Request]
    ) -> None:
        _install(monkeypatch, _live_success(), recorder)
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
    def test_register_live_providers_registers_both_slugs(self) -> None:
        from app import register_live_providers
        from gateway.provider_registry import ProviderRegistry

        registry = ProviderRegistry()
        register_live_providers(registry)
        registry.eager_verify_all()  # DEFINITION valid + HANDLERS parity
        assert registry.get("assemblyai") is not None
        assert registry.get("groq") is not None  # Groq untouched by R174
