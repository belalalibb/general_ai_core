"""R168 D-02 — Groq normaliser: ``detail``-only 400 "model not allowed" is a MODEL problem.

Defect (ledger D-02, S2): the OpenAI-compatible proxy fronting Groq answers a
disallowed model with HTTP 400 ``{"detail": "Model '<x>' is not allowed. See GET
/v1/models…"}`` — FastAPI's ``detail`` shape, no ``error.code``. The shipped
normaliser only read ``error.code``/``error.param`` and booked ``bad_request``
(request-indicting ⇒ no retry, no failover), so a route that merely lacked the
model was never shopped to a provider that has it.

Contract now (mirrors the genspark_llm adapter's structural detection):

- 400 + ``detail`` starting "Model " and containing "is not allowed" ⇒
  ``model_unavailable``, ``retryable=False``, ``provider_code="model_not_allowed"``
  — a candidate-indicting category the execution walk fails over from;
- the detail text (echoes the requested model name and the allowlist) never
  reaches ``safe_message`` / ``provider_code``;
- any OTHER ``detail``-only 400 keeps ``bad_request`` — nothing in the captured
  evidence says an unknown FastAPI detail is non-indicting (INV-4: decided, not
  guessed; the genspark_llm adapter holds the same line).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx

from core.contracts.provider import (
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderOperation,
)
from providers.real.groq import MANIFEST, GroqAdapter

CRED_REF = "credref_d02_placeholder"
MODEL_DETAIL = (
    "Model 'no-such-model-qevion' is not allowed. See GET /v1/models for the available models."
)


def _replay(status: int, body: Any) -> ProviderGenerateResponse:
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda ref: "not-a-real-key",
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(lambda _req: httpx.Response(status, json=body)),
    )
    request = ProviderGenerateRequest.model_validate(
        {
            "request_id": uuid4(),
            "tenant_id": uuid4(),
            "operation": ProviderOperation.GENERATE_TEXT,
            "provider_model_name": "no-such-model-qevion",
            "credential_ref": CRED_REF,
            "payload": {"ask": "hello"},
        }
    )
    return asyncio.run(adapter.generate(request))


def test_detail_only_400_model_not_allowed_is_model_unavailable() -> None:
    r = _replay(400, {"detail": MODEL_DETAIL})
    assert r.succeeded is False and r.error is not None
    assert r.error.category is ProviderErrorCategory.MODEL_UNAVAILABLE
    assert r.error.retryable is False
    assert r.error.provider_code == "model_not_allowed"


def test_detail_text_never_crosses_the_boundary() -> None:
    r = _replay(400, {"detail": MODEL_DETAIL})
    assert r.error is not None
    dumped = r.error.model_dump_json()
    assert "no-such-model-qevion" not in dumped
    assert "/v1/models" not in dumped


def test_other_detail_only_400_stays_bad_request() -> None:
    # Recorded decision: an unknown FastAPI ``detail`` is still request-indicting.
    r = _replay(400, {"detail": "Invalid request payload."})
    assert r.error is not None
    assert r.error.category is ProviderErrorCategory.BAD_REQUEST
    assert r.error.retryable is False


def test_error_code_shapes_unchanged() -> None:
    # INV-1: the existing ``error.code`` path is untouched by the new branch.
    r = _replay(400, {"error": {"code": "invalid_request_error", "message": "x"}})
    assert r.error is not None
    assert r.error.category is ProviderErrorCategory.BAD_REQUEST
    assert r.error.provider_code == "invalid_request_error"
