"""
Provider Gateway — خدمة Flask موحّدة (النسخة الموحّدة NEW design).

مبادئ ثابتة (لا تعارض):
- المصدر لا يظهر في أي request: كل النقاط تستخدم route_token فقط، لا provider slug.
- route_token يُفكّ داخليًا عبر Route Registry إلى provider identity (slug داخلي)،
  ثم إلى handler + credential — الـ handler لا يرى route_token ولا slug (internal context).
- الـ Gateway مواد خام فقط: لا سياسات، لا authorization — كلها في المنصة.
- الأهلية (eligibility) مصدرها إعلان DEFINITION في ملف المزوّد، لا وجود الدوال.
- الأمان: X-Gateway-Secret + X-Gateway-Secret-Version (النسخة القديمة تُرفض).
- safe_message لا يكشف slug/route/داخليات إطلاقًا.

التشغيل:
    export GATEWAY_SHARED_SECRET=<سر-من-Vault>
    export GATEWAY_SECRET_VERSION=3
    export GATEWAY_ROUTES_JSON='{"<route_token>":"<internal_slug>"}'
    python app.py            # dev
    # للإنتاج: gunicorn -w 4 -b 0.0.0.0:9000 app:app  (خلف TLS)
"""
from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from flask import Flask, jsonify, request

app = Flask(__name__)

# --- الأمان: السرّ + رقم النسخة (يُقرآن من Vault في المنصة؛ هنا من env للـ kit) ---
SHARED_SECRET = os.environ.get("GATEWAY_SHARED_SECRET", "")
SECRET_VERSION = os.environ.get("GATEWAY_SECRET_VERSION", "")

# --- Route Registry: route_token -> internal slug (خريطة سرّية، لا تغادر الـ Gateway) ---
# تُحمّل من مصدر آمن خارج الشيفرة؛ لا hard-code. الشكل: {"<route_token>":"<slug>"}
_ROUTES: dict[str, str] = json.loads(os.environ.get("GATEWAY_ROUTES_JSON", "{}"))

# خريطة operation -> اسم دالة الـ handler المتوقّعة في ملف المزوّد.
OPERATION_FUNCS = {
    "generate_text": "generate_text",
    "create_embeddings": "create_embeddings",
    "transcribe_audio": "transcribe_audio",
    "synthesize_speech": "synthesize_speech",
    "generate_image": "generate_image",
    "analyze_vision": "analyze_vision",
    "rerank_documents": "rerank_documents",
    "moderate_content": "moderate_content",
}

# الفئات المقفولة الاثنتا عشرة (يجب أن تطابق المنصة حرفيًا — 30 §14).
ERROR_CATEGORIES = {
    "auth_expired", "invalid_credential", "rate_limited", "quota_exceeded",
    "model_unavailable", "provider_unavailable", "unsupported_capability",
    "bad_request", "content_rejected", "timeout", "retryable_server_error",
    "non_retryable_error",
}


# ---------------------------------------------------------------------------
# السياق الداخلي المُمرَّر للـ handler — لا يحتوي slug ولا route_token.
# الـ handler ينفّذ فقط؛ لا يعرف هويته الخارجية ولا مصدره في الـ request.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderContext:
    operation: str
    model: str
    payload: dict
    credential: str | None      # مفكوك مسبقًا بواسطة الـ Gateway (user_key أو platform)
    timeout_ms: int


# ---------------------------------------------------------------------------
# مساعدات المظروف الموحّد (Response Envelope) — لا تكشف داخليات.
# ---------------------------------------------------------------------------
def ok(output: dict, usage: dict | None = None, latency_ms: int | None = None):
    return jsonify({
        "ok": True, "output": output, "usage": usage or {}, "latency_ms": latency_ms,
    })


def err(category: str, safe_message: str, *, retryable: bool = False,
        retry_after_ms: int | None = None, provider_code: str | None = None):
    assert category in ERROR_CATEGORIES, f"فئة خطأ غير معروفة: {category}"
    return jsonify({
        "ok": False,
        "error": {
            "category": category, "retryable": retryable,
            "retry_after_ms": retry_after_ms, "provider_code": provider_code,
            "safe_message": safe_message,
        },
    })


# ---------------------------------------------------------------------------
# الحرّاس: السرّ + النسخة، وفكّ الـ route داخليًا.
# ---------------------------------------------------------------------------
def require_secret(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        secret_ok = bool(SHARED_SECRET) and \
            request.headers.get("X-Gateway-Secret") == SHARED_SECRET
        # النسخة القديمة تُرفض: يجب أن تطابق النسخة الحالية بالضبط.
        version_ok = bool(SECRET_VERSION) and \
            request.headers.get("X-Gateway-Secret-Version") == SECRET_VERSION
        if not (secret_ok and version_ok):
            return err("invalid_credential", "gateway authentication failed"), 401
        return fn(*args, **kwargs)
    return wrapper


def resolve_route(route_token: str) -> str | None:
    """يفكّ route_token المبهم إلى internal slug (داخليًا فقط)."""
    return _ROUTES.get(route_token)


def load_provider(slug: str):
    """حمّل providers/<slug>.py — عزل: كل مزوّد ملف مستقل."""
    try:
        return importlib.import_module(f"providers.{slug}")
    except ModuleNotFoundError:
        return None


def _resolve_from_request() -> tuple[Any, str] | tuple[None, str]:
    """يفكّ route_token من الـ request إلى (module, slug) داخليًا.

    يعيد (None, "") إذا فشل الفكّ — المتصل يرجّع خطأ عامًّا لا يكشف السبب
    (anti-enumeration): لا فرق ظاهر بين token خاطئ ومزوّد غير موجود.
    """
    body = request.get_json(silent=True) or {}
    slug = resolve_route(body.get("route_token", ""))
    if slug is None:
        return None, ""
    module = load_provider(slug)
    if module is None:
        return None, ""
    return module, slug


def _resolve_credential(module: Any, slug: str, body: dict) -> str | None:
    """يفكّ الـ credential داخليًا قبل تمريره للـ handler.

    - user_key : المفتاح جاء من المنصة داخل المظروف (credential.value).
    - platform : يُستعلَم من credential profile داخلي مفتاحه slug الداخلي
      (ليس من الـ request) — عبر providers._credentials.
    """
    from providers._credentials import resolve_platform_credential
    cred = body.get("credential") or {}
    mode = getattr(module, "DEFINITION", {}).get("credential_mode", cred.get("mode"))
    if mode == "user_key":
        return cred.get("value")
    return resolve_platform_credential(slug)   # platform: مفتاح الـ Gateway الداخلي


def dispatch(operation: str):
    """المنطق المشترك: فكّ route داخليًا، تحقّق الإعلان، مرّر internal context للـ handler."""
    module, slug = _resolve_from_request()
    if module is None:
        return err("provider_unavailable", "unknown route"), 404

    definition = getattr(module, "DEFINITION", {})
    declared_ops = set(definition.get("operations", []))

    # الأهلية مصدرها الإعلان (DEFINITION)، لا وجود الدالة.
    if operation not in declared_ops:
        return err("unsupported_capability", "operation not offered by this route")

    func = getattr(module, OPERATION_FUNCS[operation], None)
    if func is None:
        # مُعلَن لكن غير مُنفَّذ = خطأ تهيئة (لا يكشف slug).
        return err("non_retryable_error", "route misconfigured")

    body = request.get_json(silent=True) or {}
    ctx = ProviderContext(
        operation=operation,
        model=body.get("model", ""),
        payload=body.get("payload", {}),
        credential=_resolve_credential(module, slug, body),
        timeout_ms=int(body.get("timeout_ms", 30000)),
    )
    try:
        return func(ctx)     # الـ handler يستقبل internal context فقط
    except Exception as exc:  # noqa: BLE001 — كل فشل يُطبّع، لا يُرفع خام
        return err("retryable_server_error", "provider gateway internal error",
                   retryable=True, provider_code=type(exc).__name__)


# ---------------------------------------------------------------------------
# النقاط الثابتة (كلها route_token — لا slug في أي request).
# ---------------------------------------------------------------------------
@app.post("/generate")
@require_secret
def generate():
    return dispatch("generate_text")


@app.post("/embeddings")
@require_secret
def embeddings():
    return dispatch("create_embeddings")


@app.post("/transcribe")
@require_secret
def transcribe():
    return dispatch("transcribe_audio")


@app.post("/speech")
@require_secret
def speech():
    return dispatch("synthesize_speech")


@app.post("/image")
@require_secret
def image():
    return dispatch("generate_image")


@app.post("/vision")
@require_secret
def vision():
    return dispatch("analyze_vision")


@app.post("/rerank")
@require_secret
def rerank():
    return dispatch("rerank_documents")


@app.post("/moderate")
@require_secret
def moderate():
    return dispatch("moderate_content")


@app.get("/describe")
@require_secret
def describe():
    """اكتشاف: يعيد إعلان DEFINITION للمزوّد (لا يستنتج من وجود الدوال).

    route_token في query. لا يكشف الـ slug الداخلي في الرد.
    """
    token = request.args.get("route_token", "")
    slug = resolve_route(token)
    module = load_provider(slug) if slug else None
    if module is None:
        return err("provider_unavailable", "unknown route"), 404
    d = getattr(module, "DEFINITION", {})
    return jsonify({
        "operations": d.get("operations", []),
        "capabilities": d.get("capabilities", {}),
        "models": d.get("models", []),
        "credential_mode": d.get("credential_mode", "platform"),
        "display_name": d.get("display_name", ""),
    })


@app.get("/models")
@require_secret
def models():
    token = request.args.get("route_token", "")
    slug = resolve_route(token)
    module = load_provider(slug) if slug else None
    if module is None:
        return jsonify({"models": []})
    d = getattr(module, "DEFINITION", {})
    return jsonify({"models": d.get("models", [])})


@app.get("/health")
@require_secret
def health():
    token = request.args.get("route_token", "")
    slug = resolve_route(token)
    module = load_provider(slug) if slug else None
    if module is None:
        return jsonify({"state": "UNAVAILABLE"})
    func = getattr(module, "health", None)
    return jsonify({"state": func() if func else "UNKNOWN"})


@app.get("/healthz")
def healthz():
    """liveness للـ Gateway نفسها (بدون سرّ)."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "9000")))
