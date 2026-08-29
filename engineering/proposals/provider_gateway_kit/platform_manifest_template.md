# قالب تسجيل مزوّد Gateway داخل المنصة (النسخة الموحّدة NEW design)

> الحد الأدنى فقط في config. القدرات/العمليات/الموديلات **تأتي من GET /describe**،
> لا تُكتب يدويًا (لمنع مسارين متعارضين). المصدر الحقيقي (slug) لا يظهر في أي
> request — المنصة تتعامل بـ route_token مبهم.

## 1. صفّ الـ config لكل مزوّد (الحد الأدنى — قابل للإضافة من الـ UI مستقبلاً)

```yaml
- route_token: "a9f3e1c7-...-opaque"   # مبهم؛ المنصة تولّده عند تفعيل الأدمن
  display_name: "OpenAI"               # للعرض فقط
  gateway_base_url: "https://gateway.internal:9000"   # admin-only + allowlist (ضد SSRF)
  status: disabled                     # disabled حتى تمرّ اختبارات العقد (31 §19)
```

> ملاحظة: لا `capabilities` ولا `operations` ولا `models` هنا — كلها من /describe.
> الـ slug الداخلي للمزوّد يعيش في Route Registry داخل الـ Gateway فقط، ومربوط
> بالـ route_token؛ المنصة لا تخزّن الـ slug في مسار الطلب.

## 2. كيف يُبنى ProviderManifest (تلقائيًا داخل المنصة)

بعد تفعيل الأدمن، الـ RemoteGatewayAdapter ينادي `GET /describe?route_token=...`
ويبني manifest حقيقيًا:

```text
ProviderManifest(
    id            = هوية domain مستقرة (UUID) — مستقلة تمامًا عن route_token
    name          = display_name (من /describe) — الهوية المقروءة في UI/Admin
    status        = "disabled"          # حتى التحقق، ثم يُفعَّل عبر Admin
    is_template   = False
    is_functional = True
    auth          = من credential_mode في /describe (user_key ⇒ API_KEY)
    capabilities  = من /describe (deny-by-default)
    operations    = من /describe
    models        = من /describe
    errors.mapping= "providers/real/gateway/adapter.py:_normalize"
    notes         = ["Remote Gateway provider; endpoints live in the gateway (30 §9)"]
)
```

### فصل الهوية عن التوجيه — قرار مثبّت (لا coupling، ولا تسريب slug)

```text
داخل المنصة                          داخل الـ Gateway (سرّي)
────────────                        ──────────────────────
Provider.id   = UUID مستقر          slug = "my_llm"  ← Gateway-internal فقط
Provider.name = display_name        route_token → slug (Route Registry)
route_token   = opaque handle

- المنصة لا تعرف الـ slug الحقيقي إطلاقًا: هويتها id (UUID) + name (display_name).
- /describe لا يعيد slug (يسرّب المصدر). الـ slug يبقى داخل الـ Gateway وحده.
- ProviderManifest.id لا يُشتقّ من route_token (مرفوض: hash) — دورتا حياة مختلفتان.
- rotation/revocation للـ route_token = تحديث الربط الداخلي فقط؛
  id/name/bindings/history ثابتة.
- الـ UI يعرض name/status/capabilities؛ لا يعرف route_token ولا slug.
```

### provisioning للـ route_token (out-of-band — لا HTTP عام)

```text
Admin activation → المنصة تولّد route_token عشوائيًا تشفيريًا وتربطه بـ provider.id
   → توفير آمن للـ Gateway (config محمي/Vault) يُدخِل {route_token → slug}
   → الـ Gateway يخزّن الربط ويبدأ قبول الطلبات.
المنصة = المُصدِر الوحيد؛ الـ Gateway = مستهلك. لا endpoint عام للتسجيل.
```

## 3. سلوك الـ credential حسب النوعين

```text
credential_mode = user_key (من /describe):
    المستخدم أضاف مفتاحه ⇒ يُخزَّن عبر SecretManagerPort ⇒ credential_ref مبهم.
    المنصة تفكّه في آخر لحظة وتضعه في envelope.credential.value.

credential_mode = platform (من /describe):
    envelope.credential = {"mode":"platform","value":null}
    المنصة لا ترسل أي سرّ؛ الـ Gateway يفكّ مفتاحه داخليًا بالـ slug (لا من الطلب).
```

## 4. الأمان الإلزامي

```text
- الإضافة/التعديل admin-only (خلف is_admin gate الموجود).
- gateway_base_url عبر allowlist (نطاقات مسموحة) ⇒ يمنع SSRF.
- القناة: TLS + X-Gateway-Secret + X-Gateway-Secret-Version (من Vault/AppRole).
- route_token يُولَّد ويُخزَّن عند التفعيل فقط؛ لا مزوّد يعمل بلا token صادر عن الأدمن.
- المزوّد يبقى status=disabled حتى تمرّ اختبارات العقد، ثم يُفعَّل عبر Admin/Config.
```
