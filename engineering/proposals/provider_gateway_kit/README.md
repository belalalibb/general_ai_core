# عدّة بوابة المزوّدين (Provider Gateway Kit)

هذه العدّة تحوّل فكرتك إلى تصميم آمن لا يهدم المعمارية الحالية:

> خدمة Flask واحدة (`app.py`) بنقاط نهاية ثابتة (`/generate`, `/embeddings`, ...)
> تخدم كل المزوّدين. المنصة تكلّمها عبر **adapter واحد generic**، فتضيف أي مزوّد
> جديد مستقبلًا بـ **اسم + رابط** فقط — بدون كود منصة، بدون hard-code، بدون هدم.

## الملفات

| الملف | ماذا يفعل | أين يعيش |
|---|---|---|
| `00_CONTRACT.md` | **العقد الموحّد** (route_token, envelopes, /describe) — اقرأه أولًا | مرجع للطرفين |
| `01_SECRET_AND_KILLSWITCH.md` | Vault AppRole + rotation مقابل kill-switch بالإبطال | مرجع أمني |
| `app.py` | قالب خدمة الـ Flask (route_token + النسخة + internal context) | مشروعك المنفصل |
| `providers/_TEMPLATE_provider.py` | **قالب مزوّد** (DEFINITION + handlers) — انسخه | داخل الـ Flask |
| `providers/_credentials.py` | إدارة مفاتيح platform بالـ slug الداخلي | داخل الـ Flask |
| `providers/my_llm.py` · `openai.py` | **أمثلة فقط (example only)** — لا تُدرَج كـ live | داخل الـ Flask |
| `platform_manifest_template.md` | صفّ config الحد الأدنى (route_token + url + status) | جانب FastAPI |
| `AGENT_PROMPT.md` | **البرومبت النهائي** لتنفيذ جانب المنصة | للـ agent |

> كل ملفات الـ kit موحّدة على تصميم واحد (NEW): route_token مبهم، Gateway مواد
> خام، اكتشاف عبر DEFINITION/describe، Vault AppRole. لا بقايا للتصميم القديم
> (provider في الطلب / مفتاح env لكل slug من الطلب / config يدوي للقدرات).

## كيف يحقّق كل ما طلبته

- **"كل حاجة زي ما هي بدون هدم"** ⇒ لا تعديل على core/ ولا groq/genspark. إضافة
  مجلد `providers/real/gateway/` فقط + seam config.
- **"نقاط نهاية ثابتة (generate/ask/...)"** ⇒ جدول العمليات الثابت في `00_CONTRACT.md §1`.
- **"نقطة تعريف واحدة ثابتة بين الاتنين"** ⇒ `provider_slug` (= اسم ملف الـ Flask
  = `ProviderManifest.id` في المنصة).
- **"نوعا المفاتيح"** ⇒ `credential.mode`: `user_key` (BYOK، يُفكّ من Vault في آخر
  لحظة) و `platform` (الـ Gateway يملك مفاتيحه/حساباته، المنصة لا تعرفها).
- **"ميزة غير متاحة ترجّع none ويكمل"** ⇒ بدل none الصامتة (التي تكسر المحاسبة)،
  الدالة ترجّع مظروف `unsupported_capability` ⇒ المنصة تتخطّاها بصدق وبدون أي أثر.
- **"أضيف الرابط من الـ UI مستقبلًا"** ⇒ صفّ config (slug + gateway_base_url) عبر
  Admin، خلف allowlist (ضد SSRF).

## خطوات البدء

1. راجع `00_CONTRACT.md` (العقد) و`AGENT_PROMPT.md` (البرومبت).
2. اعطِ البرومبت للـ agent لبناء **جانب المنصة** (RemoteGatewayAdapter + seam + tests).
3. وافق على الـ ADR عندما يعرضه PROPOSED.
4. ابنِ خدمة الـ Flask من `app.py` + `providers/_TEMPLATE_provider.py` في مشروعك.
5. سجّل أول مزوّد (`disabled`)، شغّل اختبارات العقد، ثم فعّله عبر Admin.

## القرارات المتبقية لك (أمنية)

- سرّ مشترك قوي للـ Gateway (`GATEWAY_SHARED_SECRET`) في SecretManager.
- allowlist لنطاقات `gateway_base_url`.
- TLS إلزامي على الـ Gateway قبل أي مفتاح `user_key` حقيقي.
