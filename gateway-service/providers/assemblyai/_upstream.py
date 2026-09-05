"""Layer 1 — AssemblyAI LLM Gateway upstream client. Internal territory.

Real HTTP calls to ``https://llm-gateway.assemblyai.com/v1/chat/completions``
via httpx. Wire facts verified LIVE in §2 (evidence/r174/02_upstream_probe):

- Auth: the DOCUMENTED form is the RAW key in the ``Authorization`` header
  (no ``Bearer`` prefix). ``Bearer <key>`` is also accepted upstream; the
  documented form is used.
- Success body: OpenAI-like ``choices[0].message.content`` /
  ``finish_reason``; usage carries ``input_tokens``/``output_tokens`` (and
  duplicate ``prompt_tokens``/``completion_tokens``). Canonical names are
  read first, OpenAI names as fallback.
- Error body has TWO observed shapes, neither OpenAI's ``{error:{...}}``:
    401 -> ``{"error": "<text>", "status": "error", "request_id"}``
    400 -> ``{"code": 400, "message": "<text>", "metadata": {"errors": [..]}}``
  Only the HTTP status and a fixed short code ever leave this layer — never
  message text.
- An unknown model is a 400 whose ``metadata.errors[]`` contains
  ``"is not supported"`` (upstream has no 404 for models) -> ``fail_kind``
  ``"unsupported_model"`` so the facade can report ``model_unavailable``.
- ``fallback_config.retry`` defaults to TRUE upstream (auto-retry after
  500 ms). CONTRACT v1 = ZERO retries (billing integrity, ADR-0008), so this
  layer sends ``fallback_config: {"retry": false}`` explicitly: one canonical
  request => at most one billed upstream attempt.

Credential resolution (platform mode): the API key comes from the gateway
process environment variable ``GW_ASSEMBLYAI_API_KEY`` — resolved lazily per
call, never cached in module state, never logged, never included in any
reply object beyond the outgoing Authorization header.

Hermeticity: the transport is injectable so tests drive every path with
``httpx.MockTransport`` and zero network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

#: Environment variable NAME holding the AssemblyAI API key (platform mode).
#: The NAME is public documentation; the VALUE must never be printed/logged.
ASSEMBLYAI_API_KEY_ENV = "GW_ASSEMBLYAI_API_KEY"

ASSEMBLYAI_BASE_URL = "https://llm-gateway.assemblyai.com/v1"
_CHAT_COMPLETIONS_PATH = "/chat/completions"

#: Test seam (Layer 1 freedom): when set, used as the httpx transport for
#: every call that does not pass an explicit ``transport``. Hermetic tests
#: install an ``httpx.MockTransport`` here; production leaves it None.
_default_transport: httpx.AsyncBaseTransport | None = None

_DEFAULT_MAX_TOKENS = 1024

#: Substring AssemblyAI puts in ``metadata.errors[]`` for an unknown model
#: (observed live: "model no-such-model-r174 is not supported").
_UNSUPPORTED_MODEL_MARKER = "is not supported"


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
    fail_kind: str | None = None  # "no_key"|"timeout"|"network"|"http"|"unsupported_model"
    http_status: int | None = None
    error_code: str | None = None
    retry_after_ms: int | None = None


def resolve_api_key() -> str | None:
    """Resolve the platform-mode key from the gateway's own environment."""

    value = os.environ.get(ASSEMBLYAI_API_KEY_ENV)
    return value if value else None


def _parse_error_body(response: httpx.Response) -> tuple[str | None, list[str]]:
    """Return (safe_code, metadata_errors) from either observed error shape.

    ``safe_code`` is ``str(code)`` when the body carries an integer ``code``
    (shape B) or None otherwise — NEVER message text. ``metadata_errors`` is
    the list of strings under ``metadata.errors`` (shape B) or empty. These
    strings are inspected for a fixed marker only and never forwarded.
    """

    try:
        parsed = response.json()
    except ValueError:
        return None, []
    if not isinstance(parsed, dict):
        return None, []
    code = parsed.get("code")
    safe_code = str(code) if isinstance(code, int) else None
    metadata = parsed.get("metadata")
    errors_raw = metadata.get("errors") if isinstance(metadata, dict) else None
    errors = [item for item in errors_raw if isinstance(item, str)] if isinstance(errors_raw, list) else []
    return safe_code, errors


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
    base_url: str = ASSEMBLYAI_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpstreamReply:
    """One upstream call; ZERO retries — ours AND AssemblyAI's (ADR-0008)."""

    api_key = resolve_api_key()
    if api_key is None:
        return UpstreamReply(ok=False, fail_kind="no_key")

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens if isinstance(max_tokens, int) else _DEFAULT_MAX_TOKENS,
        "stream": False,
        # Upstream default is retry=true; the contract forbids hidden retries.
        "fallback_config": {"retry": False},
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
                # Documented form: raw key, no "Bearer" prefix (verified §2 p1).
                headers={"Authorization": api_key},
            )
    except httpx.TimeoutException:
        return UpstreamReply(ok=False, fail_kind="timeout")
    except httpx.HTTPError:
        return UpstreamReply(ok=False, fail_kind="network")

    if response.status_code != 200:
        safe_code, metadata_errors = _parse_error_body(response)
        fail_kind = "http"
        if response.status_code == 400 and any(
            _UNSUPPORTED_MODEL_MARKER in item for item in metadata_errors
        ):
            fail_kind = "unsupported_model"
        return UpstreamReply(
            ok=False,
            fail_kind=fail_kind,
            http_status=response.status_code,
            error_code=safe_code,
            retry_after_ms=_retry_after_ms(response),
        )
    return _parse_success(response)


def _read_usage(usage_raw: object) -> dict[str, int]:
    """AssemblyAI names first (input/output_tokens); OpenAI names as fallback."""

    usage: dict[str, int] = {}
    if not isinstance(usage_raw, dict):
        return usage
    for canonical, candidates in (
        ("input_tokens", ("input_tokens", "prompt_tokens")),
        ("output_tokens", ("output_tokens", "completion_tokens")),
    ):
        for key in candidates:
            value = usage_raw.get(key)
            if isinstance(value, int) and value >= 0:
                usage[canonical] = value
                break
    return usage


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
    return UpstreamReply(
        ok=True,
        text=content,
        finish_reason=finish if isinstance(finish, str) else None,
        usage=_read_usage(parsed.get("usage")),
    )
