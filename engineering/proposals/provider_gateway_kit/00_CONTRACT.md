# عقد بوابة المزوّدين (Provider Gateway Contract) — نقطة التعريف الواحدة الثابتة

> هذا هو "العقد الموحّد" بين المنصة (FastAPI الحالية) وبين خدمة الـ Gateway
> الخارجية (Flask `app.py`). طالما الطرفان يحترمان هذا العقد، يمكن إضافة أي
> مزوّد جديد **ببيانات فقط** (اسم + رابط) دون تعديل core المنصة ودون هدم أي شيء.
>
> القاعدة الذهبية: المنصة لا ترى endpoints أي مزوّد أبداً. هي ترى الـ Gateway
> فقط عبر adapter واحد generic. تفاصيل كل مزوّد تعيش داخل الـ Gateway (30 §9).

---

## 1. نقطة التعريف الواحدة الثابتة (Single Fixed Definition Point)

مفتاحان يجب أن يتطابقا حرفياً بين الطرفين:

```text
provider_slug   ← معرّف نصّي فريد للمزوّد (مثال: "openai", "anthropic", "my_gpt")
                  = ProviderManifest.id في المنصة
                  = الاسم الذي يوجّه به الـ Gateway الطلب لملف المزوّد المناسب
```

كل operation له مسار ثابت في الـ Gateway (لا يتغيّر مهما زاد عدد المزوّدين):

| operation (منصة) | مسار Gateway الثابت | القدرة (capability) |
|---|---|---|
| `generate_text`     | `POST /generate`    | chat / text |
| `create_embeddings` | `POST /embeddings`  | embeddings |
| `transcribe_audio`  | `POST /transcribe`  | audio_input |
| `synthesize_speech` | `POST /speech`      | audio_output |
| `generate_image`    | `POST /image`       | image_generation |
| `analyze_vision`    | `POST /vision`      | vision_input |
| `rerank_documents`  | `POST /rerank`      | rerank |
| `moderate_content`  | `POST /moderate`    | moderation |
| (اكتشاف القدرات)    | `GET  /describe?route_token=...` | مصدر الأهلية |
| (اكتشاف الموديلات)  | `GET  /models?route_token=...`   | اختياري |
| (فحص الصحة)         | `GET  /health?route_token=...`   | اختياري |

> كل النقاط — POST و GET — تستخدم route_token فقط. لا يظهر الـ slug/المصدر
> في أي request إطلاقًا. إضافة operation جديدة = مسار ثابت جديد هنا.

---

## 1.b الاكتشاف عبر الإعلان (DEFINITION) — لا عبر وجود الدوال

`GET /describe?route_token=<token>` يعيد **إعلان DEFINITION** الموجود في ملف
المزوّد (operations/capabilities/models/credential_mode) — الـ Gateway **لا
يستنتج** القدرات من وجود دوال. الإعلان هو مصدر الأهلية الوحيد (يوافق نموذج
manifest/registry في المنصة: القدرات declarations، والدوال مجرد implementation).

```json
{
  "operations": ["generate_text"],
  "capabilities": { "chat": true },
  "models": ["my-llm-default", "my-llm-pro"],
  "credential_mode": "platform",
  "display_name": "My LLM"
}
```

> `/describe` **لا يعيد slug** إطلاقًا: الـ slug الحقيقي (اسم ملف المزوّد داخل
> الـ Gateway) يبقى Gateway-internal فقط — إعادته تسرّب المصدر. المنصة تعرض
> `display_name` كهوية مقروءة، لا الـ slug.

المنصة (بعد التفعيل عبر Admin) تنادي /describe وتبني ProviderManifest منه —
فلا تُدخِل capabilities/operations يدويًا. يبقى في config الحدّ الأدنى فقط:
route_token (مبهم) + gateway_base_url (allowlist) + status.

---

## 2. مظروف الطلب (Request Envelope) — المنصة ← الـ Gateway

شكل ثابت واحد لكل العمليات. المنصة تبنيه، الـ Gateway يقرأه:

```json
{
  "route_token": "a9f3e1c7-...-opaque",
  "operation": "generate_text",
  "model": "gpt-4o",
  "request_id": "0f2c...-uuid",
  "tenant_id": "aa11...-uuid",
  "credential": {
    "mode": "user_key",
    "value": "sk-..."
  },
  "payload": {
    "ask": "اكتب لي ملخصًا...",
    "generation": { "temperature": 0.2, "max_tokens": 512 }
  },
  "timeout_ms": 30000
}
```

### مبدأ أمني حاكم: المصدر لا يظهر في الريكويست (منع التجاوز)

```text
- لا يوجد "provider": "my_llm" صريح في المظروف. بدله "route_token" مبهم.
- الـ Gateway وحده يفكّ route_token داخليًا إلى ملف المزوّد الحقيقي عبر
  خريطة سرّية (routing table) لا تغادر الـ Gateway أبدًا.
- من لا يملك خريطة الفكّ لا يستطيع اختيار مزوّد ⇒ لا يمكن لأحد أن يبعث
  للـ Gateway ويحدّد المزوّد بنفسه متجاوزًا تحقّق الأدمن في المنصة.
- المنصة تولّد/تخزّن route_token لكل مزوّد مُفعَّل (بعد موافقة الأدمن) وتربطه
  بالـ provider_slug داخليًا. لا شيء في مسار الطلب يكشف المزوّد الحقيقي.
```

### الـ Gateway "مواد خام فقط" (لا يدير أي عملية)

```text
- الـ Gateway لا يوجّه بناءً على منطق، لا يختار مزوّدًا، لا يطبّق سياسة.
- كل ما يفعله: يفكّ route_token → ينفّذ الدالة → يرجّع مواد خام موحّدة.
- كل قرار (أي مزوّد، أي نموذج، هل مسموح؟) اتُّخذ في المنصة قبل هذا النداء.
```

### حقل `credential` — قلب قراري بشأن المفاتيح (نوعان)

```text
mode = "user_key"  ← BYOK: المستخدم أضاف مفتاحه الخاص (OpenAI/Anthropic/..).
                     المنصة فكّته من Vault في آخر لحظة ووضعت المادة في "value".
                     الـ Gateway يستخدم "value" كما هو ولا يخزّنه.

mode = "platform"  ← مفتاح/حساب المنصة: "value" يكون null.
                     الـ Gateway يستخدم مفاتيحه/حساباته الخاصة (نظامك الخارجي).
                     المنصة لا تعرف نوعه (مفتاح أم حساب) — لا يهمّها.
```

> أمان (20 §5): المفتاح لا يُسجَّل ولا يُطبع في أي log على أي طرف. القناة بين
> المنصة والـ Gateway **TLS إلزامي** + رأسان: `X-Gateway-Secret` و
> `X-Gateway-Secret-Version`. الـ Gateway يرفض أي طلب لا يحمل السرّ الصحيح
> **والنسخة الحالية** (النسخ القديمة مرفوضة). السرّ والنسخة يُقرآن من Vault عبر
> AppRole وقت التشغيل (تفاصيل: 01_SECRET_AND_KILLSWITCH.md). التفرقة: تغيير
> القيمة = rotation؛ الـ kill-switch الحقيقي = إبطال هوية المنصة (AppRole) أو
> الـ policy.

---

## 3. مظروف الرد (Response Envelope) — الـ Gateway ← المنصة

**شكل واحد ثابت دائماً** (نجاح أو فشل). هذا يحلّ نقطة "يرجّع none ويكمل":

### 3.1 نجاح

```json
{
  "ok": true,
  "output": { "content": "النص الناتج...", "finish_reason": "stop" },
  "usage": { "input_tokens": 42, "output_tokens": 128, "units": 1 },
  "latency_ms": 812
}
```

### 3.2 قدرة غير متاحة عند هذا المزوّد (الحالة التي تقصدها بـ "none")

اكتب الدالة في الـ Flask، ودعها ترجّع هذا **بدلاً من none صامتة** —
المنصة تفهمها وتكمل بأمان دون تلويث المحاسبة:

```json
{
  "ok": false,
  "error": {
    "category": "unsupported_capability",
    "retryable": false,
    "safe_message": "operation not offered by this route"
  }
}
```

> لماذا ليست none؟ لأن `generate` إذا رجع فراغاً صامتاً يكسر المحاسبة
> (حجز بلا تسوية) وقاعدة "لا تزييف". المظروف أعلاه = طريقة نظيفة تقول
> "غير مدعوم" فتتخطّاها المنصة بصدق. النتيجة نفس ما تريد: بدون أي تأثير جانبي.

### 3.3 فشل حقيقي (خطأ مزوّد) — فئة من 12 فئة مقفولة

```json
{
  "ok": false,
  "error": {
    "category": "rate_limited",
    "retryable": true,
    "retry_after_ms": 2000,
    "provider_code": "429",
    "safe_message": "provider rate limit reached"
  }
}
```

الفئات الاثنتا عشرة المسموح بها (verbatim من 30 §14):

```text
auth_expired · invalid_credential · rate_limited · quota_exceeded
model_unavailable · provider_unavailable · unsupported_capability
bad_request · content_rejected · timeout · retryable_server_error
non_retryable_error
```

### 3.4 السطوح الاختيارية (`/models`, `/health`) — هنا "الفراغ" مقبول فعلاً

- `/models` لمزوّد لا يدعم الاكتشاف ⇒ `{"models": []}` (فراغ صادق، مقبول).
- `/health` غير محسوم ⇒ `{"state": "UNKNOWN"}` (لا تُفبرِك HEALTHY).

---

## 3.b توفير route_token (Provisioning) — قناة out-of-band، لا HTTP عام

الأمان كله قائم على route_token، لذا آليّة توفيره **محدّدة صراحةً، لا ضمنية**.

```text
1. Admin activation (في المنصة)
        ↓
2. المنصة تولّد route_token عشوائيًا تشفيريًا (secrets.token_urlsafe / UUIDv4)
   وتربطه داخليًا بـ provider.id (هوية domain مستقرة).
        ↓
3. Provisioning آمن للـ Gateway (out-of-band): إدخال الزوج
   {route_token → internal slug} في Route Registry الخاص بالـ Gateway عبر
   قناة سرّية (نفس مصدر أسرار الـ Gateway: Vault/AppRole أو حقن config محمي).
        ↓
4. الـ Gateway يخزّن الربط داخليًا؛ من تلك اللحظة يقبل الطلبات الحاملة للـ token.
```

قواعد ملزِمة:

```text
- لا يوجد HTTP endpoint عام لتسجيل route_token في الـ Gateway (سطح هجوم مرفوض).
- المنصة هي المُصدِر الوحيد (single issuer)؛ الـ Gateway مستهلك فقط.
- route_token عشوائي تشفيريًا (لا مشتقّ من id/slug/secret).
- deactivation/rotation: المنصة تُبطِل الربط وتوفّر token جديدًا بنفس القناة؛
  الهوية (id/slug/bindings/history) تبقى ثابتة (فصل الهوية عن التوجيه).
- حتى يتزامن الطرفان على الربط، الـ Gateway يرفض الطلب بـ provider_unavailable
  عام (لا يكشف السبب).
```

المرحلة الحالية (Local/RDP): الربط يُوفَّر عبر config محمي يقرؤه الطرفان من
نفس مصدر الأسرار (Vault). المرحلة السحابية: نفس القناة، مضيَّقة بالـ policy.

---

## 4. لماذا لا يهدم هذا شيئاً؟

```text
core/                    ← لا يتغيّر إطلاقاً (يرى ProviderAdapterPort فقط)
providers/real/groq/     ← يبقى كما هو (يضرب api.groq.com مباشرة)
providers/real/genspark/ ← يبقى كما هو
providers/real/gateway/  ← جديد: adapter واحد generic يكلّم الـ Gateway بهذا العقد
apps/composition/        ← يسجّل مزوّدي الـ Gateway من config (رابط + slug)
app.py (Flask, خارجي)    ← مشروعك المنفصل، ينفّذ هذا العقد
```

إضافة مزوّد جديد مستقبلاً من الـ UI = صفّ config جديد (slug + gateway_base_url +
capabilities) ⇒ لا كود منصة، لا hard-code. (SSRF: الروابط admin-only + allowlist.)
