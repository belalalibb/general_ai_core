"""R172 §0 — a deliberately failing Groq call never surfaces the API key.

HERMETIC: the "key" is a synthetic ``gsk_``-shaped string that never touches a
real provider; the transport is ``httpx.MockTransport``. Three surfaces are
checked: the typed ``ProviderError`` payload, captured log records, and a
formatted traceback when the failure is allowed to escape.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from uuid import uuid4

import httpx
import pytest

from core.contracts.provider import ProviderGenerateRequest, ProviderOperation
from core.secrets.errors import SecretNotFound
from core.secrets.memory import InMemorySecretManager
from providers.real.groq import MANIFEST, GroqAdapter

FAKE_KEY = "gsk_" + "A" * 52  # synthetic, matches the R172 scan regex on purpose


def _request(ref: str) -> ProviderGenerateRequest:
    return ProviderGenerateRequest(
        request_id=uuid4(),
        tenant_id=uuid4(),
        operation=ProviderOperation.GENERATE_TEXT,
        provider_model_name="allam-2-7b",
        credential_ref=ref,
        payload={"ask": "hi", "generation": {"max_tokens": 1}},
        timeout_ms=1_000,
    )


def _leaky_transport() -> httpx.MockTransport:
    """A transport that misbehaves by echoing the auth header into the error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {request.headers.get('authorization')}", request=request)

    return httpx.MockTransport(handler)


def test_failing_call_error_and_logs_contain_no_key(caplog: pytest.LogCaptureFixture) -> None:
    tenant = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant, FAKE_KEY)
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant, r),
        transport=_leaky_transport(),
    )
    with caplog.at_level(logging.DEBUG):
        response = asyncio.run(adapter.generate(_request(ref)))
    assert response.succeeded is False
    dumped = response.model_dump_json()
    assert "gsk_" not in dumped and FAKE_KEY not in dumped
    assert response.error is not None and response.error.provider_code == "ConnectError"
    assert "gsk_" not in caplog.text


def test_escaping_failure_traceback_contains_no_key() -> None:
    """If the resolver itself raises, the traceback names the ref, never a value."""
    tenant = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant, FAKE_KEY)
    secrets.revoke(tenant, ref)
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant, r),
        transport=_leaky_transport(),
    )
    with pytest.raises(SecretNotFound):
        try:
            asyncio.run(adapter.generate(_request(ref)))
        except SecretNotFound:
            tb = traceback.format_exc()
            assert "gsk_" not in tb
            raise


def test_adapter_repr_contains_no_key() -> None:
    tenant = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant, FAKE_KEY)
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant, r),
        health_credential_ref=ref,
        transport=_leaky_transport(),
    )
    assert "gsk_" not in repr(adapter) and "gsk_" not in repr(secrets)
