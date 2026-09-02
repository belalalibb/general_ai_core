"""S2 — pooled httpx client for the DIRECT real adapters (groq, genspark_llm)
and the runtime-profile shutdown release.

Before this pin only the gateway adapter pooled; groq/genspark built a fresh
client per call. Pins: same client instance across calls; ``aclose`` releases
idempotently; a closed pool is transparently rebuilt; per-request timeout
still rides the request; ``RuntimeProfile.release_adapters`` closes every
adapter exposing ``aclose`` and tolerates adapters that do not. Hermetic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx

from providers.real.genspark_llm import MANIFEST as GS_MANIFEST
from providers.real.genspark_llm import GensparkLLMAdapter
from providers.real.groq import MANIFEST as GROQ_MANIFEST
from providers.real.groq import GroqAdapter
from tests.providers.test_groq_adapter import CRED_REF, _generate_request, _ok_chat, _resolver


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _groq() -> GroqAdapter:
    return GroqAdapter(
        GROQ_MANIFEST,
        secret_resolver=_resolver,
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(_ok_chat),
    )


def _genspark() -> GensparkLLMAdapter:
    return GensparkLLMAdapter(
        GS_MANIFEST,
        secret_resolver=_resolver,
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(_ok_chat),
    )


class TestDirectAdaptersPool:
    def test_groq_reuses_one_client_and_releases(self) -> None:
        adapter = _groq()
        assert adapter._pooled_client is None

        async def flow() -> None:
            await adapter.generate(_generate_request())
            first = adapter._pooled_client
            assert first is not None and not first.is_closed
            await adapter.health_check(_scope())
            await adapter.discover_models()
            assert adapter._pooled_client is first
            await adapter.aclose()
            assert adapter._pooled_client is None and first.is_closed
            await adapter.aclose()  # idempotent
            # rebuilt transparently after release
            await adapter.generate(_generate_request())
            assert adapter._pooled_client is not None and adapter._pooled_client is not first
            await adapter.aclose()

        run(flow())

    def test_genspark_reuses_one_client_and_releases(self) -> None:
        adapter = _genspark()

        async def flow() -> None:
            await adapter.generate(_generate_request(provider_model_name="gpt-4o-mini"))
            first = adapter._pooled_client
            assert first is not None
            await adapter.discover_models()
            assert adapter._pooled_client is first
            await adapter.aclose()
            assert first.is_closed
            await adapter.aclose()

        run(flow())

    def test_per_request_timeout_rides_the_request(self) -> None:
        seen: list[float | None] = []

        def responder(request: httpx.Request) -> httpx.Response:
            timeout = request.extensions.get("timeout", {})
            seen.append(timeout.get("read"))
            return _ok_chat(request)

        adapter = GroqAdapter(
            GROQ_MANIFEST, secret_resolver=_resolver, transport=httpx.MockTransport(responder)
        )
        run(adapter.generate(_generate_request(timeout_ms=1500)))
        run(adapter.generate(_generate_request()))
        run(adapter.aclose())
        assert seen[0] == 1.5 and seen[1] == 30.0


class _NoCloseAdapter:
    """An adapter with no long-lived resources — nothing to release."""


class TestRuntimeProfileRelease:
    def test_release_adapters_closes_only_those_that_expose_aclose(self) -> None:
        from apps.composition.runtime import RuntimeProfile

        groq = _groq()
        run(groq.generate(_generate_request()))
        assert groq._pooled_client is not None
        profile = RuntimeProfile.__new__(RuntimeProfile)
        profile.adapters = {uuid4(): groq, uuid4(): _NoCloseAdapter()}  # type: ignore[assignment]
        released = run(profile.release_adapters())
        assert released == 1
        assert groq._pooled_client is None

    def test_local_profile_release_is_safe(self) -> None:
        from apps.composition.runtime import build_runtime_profile

        profile = build_runtime_profile(environ={})
        assert profile.provider_keys == ("local_echo",)
        assert len(profile.adapters) == 1
        assert run(profile.release_adapters()) == 0  # echo adapter owns nothing


def _scope() -> Any:
    from core.contracts.provider import HealthScope

    return HealthScope.PROVIDER
