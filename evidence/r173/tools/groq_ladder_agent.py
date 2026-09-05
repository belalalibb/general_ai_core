#!/usr/bin/env python3
"""R173 §1.6 — Groq key ladder THROUGH THE AGENT PATH, in order, stop at first 200.

For each key NAME in ``R173_LADDER_KEYS`` (comma list, in order) the platform is
composed in-process with ``build_runtime_profile(environ={GROQ_API_KEY: <value>,
DEV_DEMO_PRINCIPAL: "1", PROVIDER_MAX_RETRIES: "0"})`` and ONE agent turn
(``execution_policy.strategy=agent``, no tools) is posted to ``/v1/execute`` over
ASGI. The first key whose turn returns HTTP 200 wins; its NAME (never value) is
written to ``R173_WINNER_FILE`` for the caller to compose a server with.

Evidence lines carry: key NAME, len, first-four, HTTP, error code/category, the
adapter-level attempts (model, category, provider_code, latency), latency. Every
line is scanned against every secret-shaped env value + prefixes before write.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, os.getcwd())
from apps.composition.runtime import (  # noqa: E402
    DEV_DEMO_PRINCIPAL_ENV,
    ENV_PROVIDER_RETRIES,
    RuntimeProfile,
    build_runtime_profile,
)

OUT = Path(os.environ["R173_LADDER_OUT"])
OUT.parent.mkdir(parents=True, exist_ok=True)
WINNER_FILE = Path(os.environ["R173_WINNER_FILE"])
KEYS = [k.strip() for k in os.environ["R173_LADDER_KEYS"].split(",") if k.strip()]

_SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)
_SECRET_PREFIX_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|gsk-[A-Za-z0-9._-]{20,}")
_SECRETS = [v for k, v in os.environ.items() if _SECRET_NAME_RE.search(k) and len(v) >= 12]


def record(section: str, **facts: Any) -> None:
    line = json.dumps(
        {"section": section, "utc": datetime.now(UTC).isoformat(timespec="seconds"), **facts},
        sort_keys=True,
    )
    for s in _SECRETS:
        assert s not in line, f"secret value would leak into evidence ({section})"
    assert not _SECRET_PREFIX_RE.search(line), f"secret-shaped literal in evidence ({section})"
    with OUT.open("a") as fh:
        fh.write(line + "\n")
    print(line)


class _Observer:
    """Wraps the composition's own adapter to capture the normalized error the
    ExecutionService sees (category + provider_code). No key is touched."""

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


def _compose(name: str) -> RuntimeProfile:
    return build_runtime_profile(
        environ={
            "GROQ_API_KEY": os.environ[name],
            DEV_DEMO_PRINCIPAL_ENV: "1",
            ENV_PROVIDER_RETRIES: "0",
        }
    )


async def _agent_turn(profile: RuntimeProfile) -> tuple[int, dict[str, Any], int]:
    body = {
        "ask": "Reply with the single word PONG.",
        "execution_policy": {"strategy": "agent", "max_steps": 2},
    }
    transport = httpx.ASGITransport(app=profile.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ladder", timeout=120) as c:
        t0 = time.perf_counter()
        r = await c.post("/v1/execute", json=body)
        ms = int((time.perf_counter() - t0) * 1000)
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        j = {}
    return r.status_code, j, ms


async def _run() -> str | None:
    for name in KEYS:
        value = os.environ.get(name, "")
        if not value:
            record("ladder.skip", key=name, reason="not present in environment")
            continue
        profile = _compose(name)
        try:
            assert profile.provider_keys == ("groq",), profile.provider_keys
            (pid,) = list(profile.adapters.keys())
            obs = _Observer(profile.adapters[pid])
            profile.adapters[pid] = obs
            status, payload, ms = await _agent_turn(profile)
            err = payload.get("error") or {}
            details = err.get("details") or {}
            facts: dict[str, Any] = {
                "key": name,
                "len": len(value),
                "first4": value[:4],
                "http": status,
                "latency_ms": ms,
                "status": payload.get("status"),
                "stop_reason": payload.get("stop_reason"),
                "content_len": len((payload.get("result") or {}).get("content") or ""),
                "error_code": err.get("code") or None,
                "error_message": (err.get("message") or None),
                "category": details.get("provider_error_category"),
                "execution_id": payload.get("execution_id") or details.get("execution_id"),
                "provider_attempts": obs.attempts,
            }
            record("ladder.agent_turn", **facts)
            if status == 200:
                WINNER_FILE.write_text(name + "\n")
                record("ladder.winner", key=name, latency_ms=ms)
                return name
        finally:
            await profile.release_adapters()
    record("ladder.exhausted", keys=KEYS)
    return None


if __name__ == "__main__":
    winner = asyncio.run(_run())
    sys.exit(0 if winner else 3)
