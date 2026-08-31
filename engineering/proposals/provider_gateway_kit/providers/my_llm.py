"""
EXAMPLE ONLY — لا يُدرَج في أي live registry ولا يُدَّعى أنه functional.

مثال مزوّد platform (النسخة الموحّدة NEW design). slug داخلي = "my_llm".
يدعم النص فقط (مُعلَن في DEFINITION). المفتاح يُفكّ داخليًا بالـ slug عبر
providers._credentials — لا يأتي من الـ request. الـ handler لا يرى مصدره.
"""
from __future__ import annotations

import time
from typing import Any

from app import ProviderContext, err, ok

DEFINITION: dict[str, Any] = {
    "display_name": "My LLM (example)",
    "credential_mode": "platform",
    "capabilities": {"chat": True},
    "operations": ["generate_text"],
    "models": ["my-llm-default", "my-llm-pro"],
}


def generate_text(ctx: ProviderContext) -> Any:
    # platform mode: الـ Gateway فكّ المفتاح بالـ slug الداخلي ووضعه في ctx.credential.
    if not ctx.credential:
        return err("invalid_credential", "platform key not configured")

    ask = ctx.payload.get("ask", "")
    if not ask:
        return err("bad_request", "empty ask")
    gen = ctx.payload.get("generation", {})  # noqa: F841 — blueprint placeholder for the real call
    timeout_s = ctx.timeout_ms / 1000.0  # noqa: F841 — blueprint placeholder for the real call

    started = time.monotonic()
    # --- نداؤك الحقيقي (مثال؛ استبدل الـ stub) ---
    #   import requests
    #   try:
    #       r = requests.post("https://my-llm.internal/v1/complete",
    #           headers={"Authorization": f"Bearer {ctx.credential}"},
    #           json={"model": ctx.model, "prompt": ask,
    #                 "temperature": gen.get("temperature", 0.7),
    #                 "max_tokens": gen.get("max_tokens", 512)},
    #           timeout=timeout_s)
    #   except requests.Timeout:
    #       return err("timeout", "provider timed out", retryable=True)
    #   except requests.RequestException:
    #       return err("provider_unavailable", "provider unreachable", retryable=True)
    #   if r.status_code == 429:
    #       return err("rate_limited", "rate limit", retryable=True,
    #                  retry_after_ms=2000, provider_code="429")
    #   if r.status_code in (401, 403):
    #       return err("invalid_credential", "provider rejected the key")
    #   if r.status_code >= 500:
    #       return err("retryable_server_error", "server error",
    #                  retryable=True, provider_code=str(r.status_code))
    #   if r.status_code != 200:
    #       return err("non_retryable_error", "error", provider_code=str(r.status_code))
    #   data = r.json(); content = data["text"]
    content = f"[example only] {ctx.model}: {ask[:60]}"      # ← استبدله
    usage = {"input_tokens": 0, "output_tokens": 0, "units": 1}

    return ok(output={"content": content, "finish_reason": "stop"},
              usage=usage, latency_ms=int((time.monotonic() - started) * 1000))


def health() -> str:
    return "UNKNOWN"     # example: لا تُفبرِك HEALTHY حتى تربط نداءً حقيقيًا.
