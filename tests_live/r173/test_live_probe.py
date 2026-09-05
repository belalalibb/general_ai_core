"""R173 §1.2b/§1.3 — LIVE Groq probe THROUGH THE PLATFORM'S OWN EXECUTE PATH.

Differences from ``tests_live/r172`` (recorded as R173 findings):

* R172 called ``GroqAdapter.generate`` directly with a model name that is NOT in
  the shipped manifest (``llama-3.1-8b-instant``). R173 composes the platform with
  ``build_runtime_profile(environ={GROQ_API_KEY: <key_n>, DEV_DEMO_PRINCIPAL: "1"})``
  and posts ``/v1/execute`` — router, ExecutionService, adapter, error envelope,
  the whole path a real caller uses. Model selection is the router's.
* R172's recorder asserted against a hard-coded 4-tuple of key names and was blind
  to any other secret. R173's recorder asserts against EVERY environment value
  whose NAME looks secret-shaped (``KEY|TOKEN|SECRET|PASSWORD``, len >= 12) plus
  the ``gsk_``/``ghp_``/``gsk-`` prefixes, before any line is written.
* Attempts per key are bounded to 2 total (``PROVIDER_MAX_RETRIES=0`` in the
  injected environ => 1 attempt per candidate; ``allow_fallback=False`` => 1
  candidate). A second HTTP call is made only for a ``timeout`` category.

Secrets are read from ``os.environ`` ONLY; nothing here prints, asserts on, or
persists a secret value. Evidence lines carry NAME / len / first-four / HTTP /
category / code / latency only.

Run (keys exported in-shell, never persisted)::

    python -m pytest tests_live/r173 -q -p no:cacheprovider -o addopts="" -rs

``tests_live/`` sits OUTSIDE ``pyproject.toml::testpaths`` and outside every
``green_manifest.json`` slice.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from apps.composition.runtime import (
    DEV_DEMO_PRINCIPAL_ENV,
    ENV_PROVIDER_RETRIES,
    RuntimeProfile,
    build_runtime_profile,
)

EVIDENCE = Path(os.environ.get("R173_LIVE_EVIDENCE", "evidence/r173/live_transport.txt"))
FORBIDDEN_REPO_MARKER = "general_ai_core"
_SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)
_SECRET_PREFIX_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|gsk-[A-Za-z0-9._-]{20,}")

# Every key name of the form GROQ_API_KEY_<n> present in the shell — discovered,
# never enumerated, so a 7th key cannot be silently ignored.
present_groq_keys: list[str] = sorted(
    name for name in os.environ if re.fullmatch(r"GROQ_API_KEY_\d+", name) and os.environ[name]
)
_selected = os.environ.get("R173_PROBE_KEYS", "")
if _selected:
    wanted = {s.strip() for s in _selected.split(",") if s.strip()}
    present_groq_keys = [k for k in present_groq_keys if k in wanted]

requires_groq = pytest.mark.skipif(
    not present_groq_keys, reason="no GROQ_API_KEY_n in environment — live run only"
)


def present_secret_values() -> dict[str, str]:
    """NAME -> value for every secret-shaped env var (len >= 12). Values never leave RAM."""
    return {
        name: value
        for name, value in os.environ.items()
        if _SECRET_NAME_RE.search(name) and len(value) >= 12
    }


def assert_no_secret(text: str) -> None:
    for name, value in present_secret_values().items():
        assert value not in text, f"refusing: text contains the value of ${name}"
    assert not _SECRET_PREFIX_RE.search(text), "refusing: text contains a secret-shaped token"


def record(section: str, **fields: object) -> None:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "section": section,
    }
    payload.update(fields)
    line = json.dumps(payload, sort_keys=True)
    assert_no_secret(line)
    with EVIDENCE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _compose(var: str) -> RuntimeProfile:
    """One composition per key: the platform's own custody (InMemorySecretManager
    -> opaque ref -> adapter resolver). The key never touches this module's state."""
    environ = {
        "GROQ_API_KEY": os.environ[var],
        DEV_DEMO_PRINCIPAL_ENV: "1",
        ENV_PROVIDER_RETRIES: "0",  # one attempt per candidate
    }
    return build_runtime_profile(environ=environ)


async def _execute(profile: RuntimeProfile, *, timeout_s: float) -> tuple[int, dict[str, Any], int]:
    body = {
        "ask": "Reply with exactly the word: OK",
        "model_policy": {"type": "auto", "allow_fallback": False},
    }
    transport = httpx.ASGITransport(app=profile.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://probe", timeout=timeout_s
    ) as client:
        started = time.perf_counter()
        response = await client.post("/v1/execute", json=body)
        latency_ms = int((time.perf_counter() - started) * 1000)
    return response.status_code, response.json(), latency_ms


def _summarize(status: int, payload: dict[str, Any]) -> dict[str, object]:
    if "error" in payload:
        err = payload["error"]
        details = err.get("details") or {}
        return {
            "http": status,
            "succeeded": False,
            "code": err.get("code"),
            "retryable": err.get("retryable"),
            "category": details.get("provider_error_category"),
            "execution_id": details.get("execution_id"),
        }
    return {
        "http": status,
        "succeeded": True,
        "status": payload.get("status"),
        "content_len": len((payload.get("result") or {}).get("content", "")),
        "execution_id": payload.get("execution_id"),
    }


class _Observer:
    """Wraps the composition's OWN adapter instance so the normalized error the
    ExecutionService sees (category + provider_code) is captured in-process. The HTTP
    envelope deliberately exposes only the category. No key is touched: requests
    carry the composition's opaque credential_ref, and resolution stays inside the
    wrapped adapter."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.attempts: list[dict[str, object]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def generate(self, request: Any) -> Any:
        response = await self._inner.generate(request)
        err = response.error
        self.attempts.append(
            {
                "model": request.provider_model_name,
                "succeeded": response.succeeded,
                "latency_ms": response.latency_ms,
                "category": err.category.value if err else None,
                "provider_code": err.provider_code if err else None,
                "retryable": err.retryable if err else None,
                "retry_after_ms": err.retry_after_ms if err else None,
            }
        )
        return response


def _observe(profile: RuntimeProfile) -> _Observer:
    (provider_id,) = list(profile.adapters.keys())
    observer = _Observer(profile.adapters[provider_id])
    profile.adapters[provider_id] = observer  # same dict ExecutionService holds
    return observer


@requires_groq
class TestGroqExecutePath:
    @pytest.mark.parametrize("var", present_groq_keys or ["GROQ_API_KEY_0"])
    def test_key_through_v1_execute(self, var: str) -> None:
        value = os.environ[var]
        meta = {"key": var, "len": len(value), "first4": value[:4]}

        async def _run() -> None:
            profile = _compose(var)
            try:
                assert profile.provider_keys == ("groq",), profile.provider_keys
                observer = _observe(profile)
                attempts = 0
                status, payload, latency = await _execute(profile, timeout_s=45.0)
                attempts += 1
                summary = _summarize(status, payload)
                summary["latency_ms"] = latency
                if summary.get("category") == "timeout":
                    status, payload, latency = await _execute(profile, timeout_s=45.0)
                    attempts += 1
                    summary = _summarize(status, payload)
                    summary["latency_ms"] = latency
                summary["attempts"] = attempts
                summary["provider_attempts"] = observer.attempts
                assert_no_secret(json.dumps(payload))
                record("groq.execute", **meta, **summary)
                # Either a real completion or a typed refusal — never an internal error.
                assert status in {200, 400, 401, 402, 403, 429, 502, 503, 504}, status
                if status != 200:
                    assert payload["error"]["code"] != "internal_error"
            finally:
                await profile.release_adapters()

        asyncio.run(_run())

    def test_recorder_refuses_every_present_secret(self) -> None:
        """The recorder is blind to nothing: every present secret-shaped value is refused."""
        names = sorted(present_secret_values())
        assert names, "no secret-shaped env values present — recorder cannot be exercised"
        for name in names:
            with pytest.raises(AssertionError):
                assert_no_secret(f"leak={os.environ[name]}")
        record("recorder.coverage", secret_names_checked=names, count=len(names))

    def test_refuses_general_ai_core_repo(self) -> None:
        repo = os.environ.get("R173_LIVE_GITHUB_REPO", "")
        assert FORBIDDEN_REPO_MARKER not in repo
