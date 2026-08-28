"""Groq LIVE verification (T-IMPL-036; 41 §49 real-provider proof).

NOT part of the hermetic gates: every test here is SKIPPED unless
``GROQ_API_KEY`` is present in the environment. The key is read from env
ONLY inside this module, stored into an InMemorySecretManager, and used
through the same opaque-credential_ref path production uses (20 §5) —
it is never printed, asserted-on, or embedded in any artifact.

Run manually:  GROQ_API_KEY=... python3 -m pytest tests/providers/test_groq_live.py -v
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import pytest

from core.contracts.domain import CredentialStatus
from core.contracts.provider import (
    HealthScope,
    ProviderGenerateRequest,
    ProviderHealthState,
    ProviderOperation,
)
from core.secrets.memory import InMemorySecretManager
from providers.real.groq import MANIFEST, GroqAdapter

requires_live_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — live verification runs manually only (41 §49)",
)

#: Cheapest verified text model for the live smoke.
LIVE_MODEL = "allam-2-7b"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _live_adapter() -> tuple[GroqAdapter, str]:
    """Build the adapter exactly the way the composition root would."""
    tenant_id = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant_id, os.environ["GROQ_API_KEY"])
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant_id, r),
        health_credential_ref=ref,
    )
    return adapter, ref


@requires_live_key
class TestGroqLive:
    def test_credential_validates_active(self) -> None:
        adapter, ref = _live_adapter()
        health = run(adapter.validate_credential(ref))
        assert health.status is CredentialStatus.ACTIVE

    def test_provider_health_is_healthy(self) -> None:
        adapter, _ = _live_adapter()
        health = run(adapter.health_check(HealthScope.PROVIDER))
        assert health.state is ProviderHealthState.HEALTHY

    def test_discovery_returns_real_models(self) -> None:
        adapter, _ = _live_adapter()
        models = run(adapter.discover_models())
        names = {m.provider_model_name for m in models}
        assert LIVE_MODEL in names  # the verified model list stays honest

    def test_end_to_end_generation(self) -> None:
        adapter, ref = _live_adapter()
        request = ProviderGenerateRequest(
            request_id=uuid4(),
            tenant_id=uuid4(),
            operation=ProviderOperation.GENERATE_TEXT,
            provider_model_name=LIVE_MODEL,
            credential_ref=ref,
            payload={
                "ask": "Reply with exactly the word: OK",
                "generation": {"max_tokens": 10, "temperature": 0},
            },
            timeout_ms=30_000,
        )
        response = run(adapter.generate(request))
        assert response.succeeded is True, response.error
        content = response.output["content"]
        assert isinstance(content, str) and content.strip()
        assert response.usage.get("total_tokens", 0) > 0

    def test_live_key_never_in_response_artifacts(self) -> None:
        adapter, ref = _live_adapter()
        request = ProviderGenerateRequest(
            request_id=uuid4(),
            tenant_id=uuid4(),
            operation=ProviderOperation.GENERATE_TEXT,
            provider_model_name=LIVE_MODEL,
            credential_ref=ref,
            payload={"ask": "Say hi", "generation": {"max_tokens": 5}},
            timeout_ms=30_000,
        )
        response = run(adapter.generate(request))
        assert os.environ["GROQ_API_KEY"] not in response.model_dump_json()
