"""Genspark LLM proxy real-provider contract tests (T-IMPL-037; 31 §19 steps 9-10).

HERMETIC — every test runs against ``httpx.MockTransport``; the gates never
touch the network. Live verification against the real endpoint is a separate,
env-gated step (tests/providers/test_genspark_llm_live.py) per 41 §49.

31 §20 Type A required tests, mapped:

- api key validation        -> TestCredentialValidation
- text generation contract  -> TestGenerateContract
- streaming if declared     -> NOT declared (stream=False pinned in body)
- rate limit error mapping  -> TestErrorNormalization (429 + retry-after)
- secret redaction          -> TestSecretContainment
- provider unavailable      -> TestErrorNormalization (network failure)

Plus provider-SPECIFIC shapes verified live 2026-08-28: the proxy's
``{"detail": str}`` error bodies, the 422 ``{"errors": [...]}`` validation
shape, and the HTTP-400 model-allowlist rejection that must map to
``model_unavailable`` (not bad_request) WITHOUT the raw detail crossing.
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
from providers.real.genspark_llm import MANIFEST, GensparkLLMAdapter
from providers.real.genspark_llm.adapter import GensparkLLMCredentialCheckInconclusive

API_KEY = "gsk-TEST_ONLY_fake_key_for_mock_transport"
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


def _adapter(
    responder: Any, *, health_ref: str | None = CRED_REF
) -> tuple[GensparkLLMAdapter, _Recorder]:
    recorder = _Recorder(responder)
    adapter = GensparkLLMAdapter(
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
        "provider_model_name": "gpt-5-nano",
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
            "model": "gpt-5-nano",
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

    def test_manifest_declares_exactly_text_and_embeddings(self) -> None:
        # T-IMPL-038 added create_embeddings (live-verified); the set stays
        # CLOSED — nothing else is declared (deny-by-default, 30 §4.3).
        assert MANIFEST.operations == [
            ProviderOperation.GENERATE_TEXT,
            ProviderOperation.CREATE_EMBEDDINGS,
        ]
        assert MANIFEST.capabilities.chat is True
        assert MANIFEST.capabilities.embeddings is True
        # undeclared capabilities stay False
        assert MANIFEST.capabilities.image_generation is False
        assert MANIFEST.capabilities.audio_input is False
        assert MANIFEST.capabilities.moderation is False

    def test_manifest_id_does_not_collide_with_groq(self) -> None:
        # No duplicate providers/contracts: distinct id from the reference.
        from providers.real.groq import MANIFEST as GROQ_MANIFEST

        assert MANIFEST.id != GROQ_MANIFEST.id

    def test_no_secret_material_anywhere_in_the_package(self) -> None:
        # 20 §5: the provider package must carry no key-shaped strings and
        # no environment reads.
        import providers.real.genspark_llm
        import providers.real.genspark_llm.adapter

        for module in (providers.real.genspark_llm, providers.real.genspark_llm.adapter):
            source = open(module.__file__).read()  # noqa: SIM115
            assert "gsk-" not in source, f"key-shaped string in {module.__name__}"
            assert "os.environ" not in source, f"env read in {module.__name__}"


# --- credential validation (31 §20: api key validation) ---------------------------------


class TestCredentialValidation:
    def test_valid_key_reports_active(self) -> None:
        adapter, recorder = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        health = run(adapter.validate_credential(CRED_REF))
        assert health.status is CredentialStatus.ACTIVE
        assert health.credential_ref == CRED_REF
        assert recorder.requests[0].headers["authorization"] == f"Bearer {API_KEY}"

    def test_rejected_key_reports_invalid(self) -> None:
        # Live-verified shape: 401 {"detail": "Invalid or expired token"}
        adapter, _ = _adapter(
            lambda req: httpx.Response(401, json={"detail": "Invalid or expired token"})
        )
        health = run(adapter.validate_credential(CRED_REF))
        assert health.status is CredentialStatus.INVALID

    def test_server_error_is_inconclusive_not_a_verdict(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(500))
        with pytest.raises(GensparkLLMCredentialCheckInconclusive):
            run(adapter.validate_credential(CRED_REF))

    def test_network_failure_is_inconclusive(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        adapter, _ = _adapter(explode)
        with pytest.raises(GensparkLLMCredentialCheckInconclusive):
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
        sent = json.loads(recorder.requests[0].content)
        assert sent["model"] == "gpt-5-nano"
        assert sent["stream"] is False
        assert {"role": "user", "content": "hello"} in sent["messages"]

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
        timeout = recorder.requests[0].extensions.get("timeout", {})
        assert timeout.get("read") == 5.0


# --- embeddings contract (T-IMPL-038; 30 §5 create_embeddings) ---------------------------


def _ok_embeddings(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},  # out of order on purpose
            ],
            "usage": {"prompt_tokens": 2, "total_tokens": 2},
            "model": "text-embedding-3-small",
        },
    )


def _embeddings_request(**overrides: Any) -> ProviderGenerateRequest:
    base: dict[str, Any] = {
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "operation": ProviderOperation.CREATE_EMBEDDINGS,
        "provider_model_name": "text-embedding-3-small",
        "credential_ref": CRED_REF,
        "payload": {"input": ["hello", "world"]},
    }
    base.update(overrides)
    return ProviderGenerateRequest.model_validate(base)


class TestEmbeddingsContract:
    def test_successful_embeddings_normalized_shape(self) -> None:
        adapter, recorder = _adapter(_ok_embeddings)
        request = _embeddings_request()
        response = run(adapter.generate(request))
        assert response.succeeded is True
        # provider order restored by index — never trusted blindly
        assert response.output["embeddings"] == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        assert response.output["dimensions"] == 3
        assert response.usage == {"prompt_tokens": 2, "total_tokens": 2}
        # routed to /embeddings with the right body; no chat fields leak in
        sent_request = recorder.requests[0]
        assert sent_request.url.path.endswith("/embeddings")
        sent = json.loads(sent_request.content)
        assert sent == {"model": "text-embedding-3-small", "input": ["hello", "world"]}

    def test_string_input_accepted(self) -> None:
        adapter, recorder = _adapter(_ok_embeddings)
        run(adapter.generate(_embeddings_request(payload={"input": "solo"})))
        sent = json.loads(recorder.requests[0].content)
        assert sent["input"] == "solo"

    @pytest.mark.parametrize(
        "bad_payload",
        [
            {},  # missing input
            {"input": ""},  # empty string
            {"input": []},  # empty list
            {"input": ["ok", ""]},  # empty item
            {"input": [1, 2]},  # non-strings
            {"input": {"nested": "object"}},  # wrong type
        ],
    )
    def test_invalid_input_rejected_before_any_network_call(
        self, bad_payload: dict[str, Any]
    ) -> None:
        adapter, recorder = _adapter(_ok_embeddings)
        response = run(adapter.generate(_embeddings_request(payload=bad_payload)))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.BAD_REQUEST
        assert response.error.provider_code == "missing_input"
        assert recorder.requests == []  # fail-before-spend: zero network

    def test_embedding_allowlist_400_maps_to_model_unavailable(self) -> None:
        # Live-verified shape: the embeddings allowlist error uses the same
        # "Model '...' is not allowed" detail (with "Allowed embedding
        # models:") — the SAME structural detector must catch it.
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400,
                json={
                    "detail": (
                        "Model 'zzz' is not allowed. Allowed embedding models: "
                        "text-embedding-3-large, text-embedding-3-small"
                    )
                },
            )
        )
        response = run(adapter.generate(_embeddings_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.MODEL_UNAVAILABLE
        assert "Allowed embedding" not in response.error.model_dump_json()

    def test_malformed_embeddings_response_normalizes_never_raises(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        response = run(adapter.generate(_embeddings_request()))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.NON_RETRYABLE_ERROR

    def test_empty_vector_in_response_normalizes(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(200, json={"data": [{"index": 0, "embedding": []}]})
        )
        response = run(adapter.generate(_embeddings_request()))
        assert response.succeeded is False
        assert response.error is not None

    def test_key_only_in_authorization_header_for_embeddings(self) -> None:
        adapter, recorder = _adapter(_ok_embeddings)
        run(adapter.generate(_embeddings_request()))
        sent = recorder.requests[0]
        assert sent.headers["authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in sent.content.decode()
        assert API_KEY not in str(sent.url)

    def test_generate_image_still_rejected_operations_stay_closed(self) -> None:
        # Adding create_embeddings must NOT loosen the closed-set rejection.
        adapter, recorder = _adapter(_ok_embeddings)
        response = run(
            adapter.generate(_embeddings_request(operation=ProviderOperation.GENERATE_IMAGE))
        )
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY
        assert recorder.requests == []


# --- error normalization (31 §20 + genspark-specific shapes) -----------------------------


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
        adapter, _ = _adapter(
            lambda req: httpx.Response(status, json={"detail": "some upstream text"})
        )
        response = run(adapter.generate(_generate_request()))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category is expected

    def test_model_allowlist_400_maps_to_model_unavailable(self) -> None:
        # Live-verified 2026-08-28: disallowed model => HTTP 400 (not 404)
        # with detail "Model '<name>' is not allowed. Allowed models: ...".
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400,
                json={
                    "detail": (
                        "Model 'not-a-real-model' is not allowed. "
                        "Allowed models: gpt-5, gpt-5.1, claude-sonnet-4-5"
                    )
                },
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.MODEL_UNAVAILABLE
        assert response.error.provider_code == "model_not_allowed"
        # the allowlist echo (raw detail) must NOT cross
        assert "Allowed models" not in response.error.model_dump_json()

    def test_validation_422_carries_machine_type_code_only(self) -> None:
        # Live-verified shape: {"status":-2,"message":...,"errors":[{"type":
        # "list_type","loc":[...],"msg":...,"input": <ECHOED USER INPUT>}]}
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                422,
                json={
                    "status": -2,
                    "message": "Request parameter validation failed",
                    "errors": [
                        {
                            "type": "list_type",
                            "loc": ["body", "messages"],
                            "msg": "Input should be a valid list",
                            "input": "SECRET-ECHO-of-user-content",
                        }
                    ],
                    "data": {},
                },
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.BAD_REQUEST
        assert response.error.provider_code == "validation_list_type"
        # echoed input must never cross the boundary
        assert "SECRET-ECHO" not in response.error.model_dump_json()

    def test_rate_limit_carries_retry_after_ms(self) -> None:
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                429, headers={"retry-after": "2"}, json={"detail": "rate limited"}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.category is ProviderErrorCategory.RATE_LIMITED
        assert response.error.retryable is True
        assert response.error.retry_after_ms == 2000

    def test_openai_style_error_code_still_extracted(self) -> None:
        # When the proxy relays an upstream OpenAI-style error envelope.
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400, json={"error": {"code": "invalid_request_error", "message": "raw"}}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        assert response.error.provider_code == "invalid_request_error"

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

    def test_raw_detail_text_never_crosses(self) -> None:
        # 30 §14: the proxy's detail string may echo request content.
        adapter, _ = _adapter(
            lambda req: httpx.Response(
                400, json={"detail": "SECRET-ECHO: user asked about gsk-something"}
            )
        )
        response = run(adapter.generate(_generate_request()))
        assert response.error is not None
        serialized = response.error.model_dump_json()
        assert "SECRET-ECHO" not in serialized
        assert response.error.provider_code == "http_400"  # no machine code in body


# --- secret containment (31 §19 step 10; 20 §5) ------------------------------------------


class TestSecretContainment:
    def test_key_never_appears_in_any_returned_object(self) -> None:
        adapter, _ = _adapter(_ok_chat)
        response = run(adapter.generate(_generate_request()))
        assert API_KEY not in response.model_dump_json()

    def test_key_never_appears_in_failure_objects(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
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
        adapter, _ = _adapter(_ok_chat)
        run(adapter.generate(_generate_request()))
        assert API_KEY not in adapter.get_manifest().model_dump_json()


# --- health + discovery (31 §19 steps 6, 12) ---------------------------------------------


class TestHealthAndDiscovery:
    def test_healthy_when_models_endpoint_authenticates(self) -> None:
        adapter, _ = _adapter(lambda req: httpx.Response(200, json={"data": []}))
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.HEALTHY
        assert health.provider_id == "genspark_llm"

    def test_no_health_credential_reports_unavailable_honestly(self) -> None:
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
                        {"id": "gpt-5-nano"},
                        {"id": "claude-sonnet-4-5"},
                        {"not_an_id": True},  # malformed entry skipped, not fatal
                    ]
                },
            )
        )
        models = run(adapter.discover_models())
        names = [m.provider_model_name for m in models]
        assert names == ["gpt-5-nano", "claude-sonnet-4-5"]

    def test_discovery_without_health_credential_is_empty_never_invented(self) -> None:
        # 41 §49: no invented model names — cannot authenticate => [].
        adapter, recorder = _adapter(_ok_chat, health_ref=None)
        assert run(adapter.discover_models()) == []
        assert recorder.requests == []  # no unauthenticated probing either
