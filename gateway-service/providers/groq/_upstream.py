"""Layer 1 — Groq upstream client. Internal territory; nothing here crosses.

Real HTTP calls to Groq's OpenAI-compatible API
(``https://api.groq.com/openai/v1/chat/completions``) via httpx.

Credential resolution (platform mode): the API key comes from the gateway
process environment variable ``GW_GROQ_API_KEY`` — resolved lazily per call,
never cached in module state, never logged, never included in any reply
object beyond the outgoing Authorization header.

Hermeticity: the transport is injectable so tests drive every path with
``httpx.MockTransport`` and zero network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

#: Environment variable NAME holding the Groq API key (platform mode).
#: The NAME is public documentation; the VALUE must never be printed/logged.
GROQ_API_KEY_ENV = "GW_GROQ_API_KEY"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_CHAT_COMPLETIONS_PATH = "/chat/completions"

#: Test seam (Layer 1 freedom): when set, used as the httpx transport for
#: every call that does not pass an explicit ``transport``. Hermetic tests
#: install an ``httpx.MockTransport`` here; production leaves it None.
_default_transport: httpx.AsyncBaseTransport | None = None

_DEFAULT_MAX_COMPLETION_TOKENS = 1024


@dataclass(frozen=True)
class UpstreamReply:
    """Internal reply shape (Layer 1 freedom) — the facade translates it.

    Exactly one of these is true:
    - ``ok`` with ``text``/``finish_reason``/``usage`` populated;
    - ``fail_kind`` set (an internal short code the facade maps to a
      canonical category). ``http_status``/``error_code`` are safe
      diagnostics only — never raw upstream body text.
    """

    ok: bool
    text: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    fail_kind: str | None = None  # "no_key"|"timeout"|"network"|"http"
    http_status: int | None = None
    error_code: str | None = None
    retry_after_ms: int | None = None


def resolve_api_key() -> str | None:
    """Resolve the platform-mode key from the gateway's own environment."""

    value = os.environ.get(GROQ_API_KEY_ENV)
    return value if value else None


def _safe_error_code(response: httpx.Response) -> str | None:
    """Extract Groq's short error code if present; never raw message text."""

    try:
        parsed = response.json()
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) and code else None


def _retry_after_ms(response: httpx.Response) -> int | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    return max(0, int(seconds * 1000)) if seconds >= 0 else None


async def call_chat_completions(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_tokens: int | None,
    timeout_ms: int,
    base_url: str = GROQ_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpstreamReply:
    """One upstream call; ZERO retries (v1 billing integrity, ADR-0008)."""

    api_key = resolve_api_key()
    if api_key is None:
        return UpstreamReply(ok=False, fail_kind="no_key")

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": (
            max_tokens if isinstance(max_tokens, int) else _DEFAULT_MAX_COMPLETION_TOKENS
        ),
        "stream": False,
    }
    if temperature is not None:
        body["temperature"] = temperature

    timeout_seconds = timeout_ms / 1000.0
    effective_transport = transport if transport is not None else _default_transport
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            transport=effective_transport,
            timeout=timeout_seconds,
        ) as client:
            response = await client.post(
                _CHAT_COMPLETIONS_PATH,
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.TimeoutException:
        return UpstreamReply(ok=False, fail_kind="timeout")
    except httpx.HTTPError:
        return UpstreamReply(ok=False, fail_kind="network")

    if response.status_code != 200:
        return UpstreamReply(
            ok=False,
            fail_kind="http",
            http_status=response.status_code,
            error_code=_safe_error_code(response),
            retry_after_ms=_retry_after_ms(response),
        )
    return _parse_success(response)


def _parse_success(response: httpx.Response) -> UpstreamReply:
    """Defensive parse of a 200 body; malformed -> http fail with status 200."""

    malformed = UpstreamReply(
        ok=False, fail_kind="http", http_status=200, error_code="malformed_upstream_body"
    )
    try:
        parsed = response.json()
    except ValueError:
        return malformed
    if not isinstance(parsed, dict):
        return malformed
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return malformed
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        content = ""
    finish = choices[0].get("finish_reason")
    usage_raw = parsed.get("usage")
    usage: dict[str, int] = {}
    if isinstance(usage_raw, dict):
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage_raw.get(key)
            if isinstance(value, int) and value >= 0:
                usage[key] = value
    return UpstreamReply(
        ok=True,
        text=content,
        finish_reason=finish if isinstance(finish, str) else None,
        usage=usage,
    )
