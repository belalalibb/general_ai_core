"""
EXAMPLE ONLY — لا يُدرَج في أي live registry ولا يُدَّعى أنه functional.

مثال مزوّد user_key/BYOK (النسخة الموحّدة NEW design). slug داخلي = "openai".
يدعم النص + embeddings (مُعلَن في DEFINITION). في user_key، المفتاح جاء من
المنصة داخل المظروف وفكّه الـ Gateway إلى ctx.credential — الـ handler لا يرى
مصدره ولا هويته الخارجية.
"""
from __future__ import annotations

import time
from typing import Any

from app import ProviderContext, err, ok

DEFINITION: dict[str, Any] = {
    "display_name": "OpenAI (example)",
    "credential_mode": "user_key",       # BYOK: مفتاح المستخدم يأتي من المنصة
    "capabilities": {"chat": True, "embeddings": True},
    "operations": ["generate_text", "create_embeddings"],
    "models": ["gpt-4o", "gpt-4o-mini", "text-embedding-3-small"],
}


def generate_text(ctx: ProviderContext) -> Any:
    if not ctx.credential:
        return err("invalid_credential", "no usable credential")
    ask = ctx.payload.get("ask", "")
    started = time.monotonic()
    # --- نداء حقيقي لـ /v1/chat/completions باستخدام ctx.credential ---
    #   ثم طبّع 429→rate_limited، 401/403→invalid_credential، 5xx→retryable_server_error.
    content = f"[example only] {ctx.model}: {ask[:60]}"      # ← استبدله
    usage = {"input_tokens": 0, "output_tokens": 0, "units": 1}
    return ok(output={"content": content, "finish_reason": "stop"},
              usage=usage, latency_ms=int((time.monotonic() - started) * 1000))


def create_embeddings(ctx: ProviderContext) -> Any:
    if not ctx.credential:
        return err("invalid_credential", "no usable credential")
    inputs = ctx.payload.get("input", [])
    # --- نداء حقيقي لـ /v1/embeddings باستخدام ctx.credential ---
    vectors = [[0.0] * 8 for _ in inputs]                     # ← استبدله بالمتجهات الحقيقية
    return ok(output={"embeddings": vectors, "dimensions": 8},
              usage={"input_tokens": 0, "units": len(inputs)})


def health() -> str:
    return "UNKNOWN"     # example: لا تُفبرِك HEALTHY.

# ملاحظة: transcribe/speech/image/vision/rerank/moderate غير مُعلَنة في DEFINITION
# وغير مُنفَّذة ⇒ الـ Gateway يرفضها بـ unsupported_capability ⇒ المنصة تتخطّاها.
