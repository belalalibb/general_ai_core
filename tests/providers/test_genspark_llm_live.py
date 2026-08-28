"""Genspark LLM proxy LIVE verification (T-IMPL-037; 41 §49 real-provider proof).

NOT part of the hermetic gates: every test here is SKIPPED unless
``GSK_API_KEY`` is present in the environment. The key is read from env
ONLY inside this module, stored into an InMemorySecretManager, and used
through the same opaque-credential_ref path production uses (20 §5) —
it is never printed, asserted-on, or embedded in any artifact.

Run manually:  GSK_API_KEY=... python3 -m pytest tests/providers/test_genspark_llm_live.py -v
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
from providers.real.genspark_llm import MANIFEST, GensparkLLMAdapter

requires_live_key = pytest.mark.skipif(
    not os.environ.get("GSK_API_KEY"),
    reason="GSK_API_KEY not set — live verification runs manually only (41 §49)",
)

#: Cheapest verified text model for the live smoke.
LIVE_MODEL = "gpt-5-nano"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _live_adapter() -> tuple[GensparkLLMAdapter, str]:
    """Build the adapter exactly the way the composition root would."""
    tenant_id = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant_id, os.environ["GSK_API_KEY"])
    adapter = GensparkLLMAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant_id, r),
        health_credential_ref=ref,
    )
    return adapter, ref


@requires_live_key
class TestGensparkLLMLive:
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
        names = [m.provider_model_name for m in models]
        assert LIVE_MODEL in names
        assert len(names) >= 10  # 52 at onboarding; assert a safe floor only

    def test_generation_succeeds_with_real_tokens(self) -> None:
        adapter, ref = _live_adapter()
        request = ProviderGenerateRequest.model_validate(
            {
                "request_id": uuid4(),
                "tenant_id": uuid4(),
                "operation": ProviderOperation.GENERATE_TEXT,
                "provider_model_name": LIVE_MODEL,
                "credential_ref": ref,
                "payload": {"ask": "Reply with exactly the word: OK"},
            }
        )
        response = run(adapter.generate(request))
        assert response.succeeded is True, f"live generate failed: {response.error}"
        assert isinstance(response.output["content"], str)
        assert response.output["content"].strip() != ""
        assert response.usage.get("total_tokens", 0) > 0

    def test_disallowed_model_maps_to_model_unavailable_live(self) -> None:
        # Live confirmation of the structural allowlist mapping.
        adapter, ref = _live_adapter()
        request = ProviderGenerateRequest.model_validate(
            {
                "request_id": uuid4(),
                "tenant_id": uuid4(),
                "operation": ProviderOperation.GENERATE_TEXT,
                "provider_model_name": "definitely-not-a-real-model",
                "credential_ref": ref,
                "payload": {"ask": "x"},
            }
        )
        response = run(adapter.generate(request))
        assert response.succeeded is False
        assert response.error is not None
        assert response.error.category.value == "model_unavailable"
        # the allowlist echo never crosses
        assert "Allowed models" not in response.error.model_dump_json()

    def test_key_absent_from_all_artifacts(self) -> None:
        adapter, ref = _live_adapter()
        key = os.environ["GSK_API_KEY"]
        health = run(adapter.validate_credential(ref))
        assert key not in health.model_dump_json()
        assert key not in adapter.get_manifest().model_dump_json()
