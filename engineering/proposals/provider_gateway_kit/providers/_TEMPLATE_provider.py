"""
قالب مزوّد واحد (النسخة الموحّدة NEW design) — انسخه إلى providers/<slug>.py.

اسم الملف (slug) = internal slug في Route Registry (app.py). لا يظهر في أي request.

مبدآن جديدان:
1. الإعلان (DEFINITION) هو مصدر الأهلية — لا وجود الدوال. القدرات/العمليات/
   الموديلات تُعلَن صراحةً هنا، والـ Gateway يقرؤها في /describe.
2. الـ handler يستقبل ProviderContext داخليًا (operation/model/payload/credential/
   timeout) — لا يرى slug ولا route_token ولا حقل provider. المصدر مخفي تمامًا.

القاعدة:
- أعلن في DEFINITION فقط ما ينفّذه هذا المزوّد فعلًا.
- كل handler يُرجع ok(...) أو err(<category>, ...) — لا None، لا استثناء خام.
- لا تطبع ctx.credential في أي log.
"""
from __future__ import annotations

import time
from typing import Any

from app import ProviderContext, ok, err


# ---------------------------------------------------------------------------
# DEFINITION — الإعلان الرسمي (مصدر الأهلية؛ يقرؤه الـ Gateway في /describe).
# ---------------------------------------------------------------------------
DEFINITION: dict[str, Any] = {
    "display_name": "Template Provider",
    "credential_mode": "platform",          # "platform" | "user_key"
    "capabilities": {"chat": True},          # deny-by-default: أعلن ما تدعمه فقط
    "operations": ["generate_text"],         # يجب أن يطابق ما تنفّذه الـ handlers
    "models": [],                            # أسماء موديلات حقيقية أو [] بصدق
}


# ---------------------------------------------------------------------------
# generate_text — handler يستقبل ProviderContext داخليًا (لا مصدر مكشوف).
# ---------------------------------------------------------------------------
def generate_text(ctx: ProviderContext) -> Any:
    if not ctx.credential:
        return err("invalid_credential", "no usable credential")

    ask = ctx.payload.get("ask", "")
    if not ask:
        return err("bad_request", "empty ask")
    gen = ctx.payload.get("generation", {})
    timeout_s = ctx.timeout_ms / 1000.0

    started = time.monotonic()
    # >>> نداؤك الحقيقي للمزوّد (requests/httpx/SDK) — استخدم ctx.credential <<<
    #   ثم طبّع أخطاءه إلى الفئات الاثنتي عشرة (429→rate_limited، 401→invalid_credential..).
    content = f"[example only] {ctx.model}: {ask[:60]}"   # ← استبدله بالرد الحقيقي
    latency_ms = int((time.monotonic() - started) * 1000)

    return ok(
        output={"content": content, "finish_reason": "stop"},
        usage={"input_tokens": 0, "output_tokens": 0, "units": 1},
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# قدرات أخرى: أضِف handler لها وأعلنها في DEFINITION، أو احذفها تمامًا.
# (لا تعلن operation بلا handler، ولا تكتب handler بلا إعلان.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# اختياري: الصحة (الفراغ/UNKNOWN صادق ومقبول). الموديلات تُعلَن في DEFINITION.
# ---------------------------------------------------------------------------
def health() -> str:
    return "UNKNOWN"    # HEALTHY / DEGRADED / UNAVAILABLE / UNKNOWN — لا تُفبرِك.
