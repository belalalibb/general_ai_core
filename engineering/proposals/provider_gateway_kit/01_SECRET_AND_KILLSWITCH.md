# أمان الـ Gateway: الهوية، التدوير، والـ Kill-Switch (التصميم المصحّح)

> تصحيح جوهري: "تغيير قيمة الـ shared secret" ليس kill-switch إن كان الطرفان
> يقرآن القيمة الجديدة تلقائيًا — عندها كلاهما يأخذ الجديدة ويكمل. هذا **rotation**
> فقط. الـ kill-switch الحقيقي = **إبطال الهوية/الصلاحية** (revoke identity / disable policy).
> الوصول في Vault مرتبط بالهوية والسياسة، لا بمعرفة قيمة سرّ.

---

## 1. القرار المعتمد (النموذج النهائي)

```text
Managed Vault (HCP Vault Dedicated)
        ↓
AppRole  (machine/application authentication)
        ↓
Least-privilege policy  (سياسة ضيّقة لكل هوية)
        ↓
Gateway credential  (secret مستقل: platform/gateway-auth)
        ↓
TLS
        ↓
Private Gateway  (شبكة خاصة/allowlist)
```

مبدأ حاكم: **لا نعتمد على غموض المسار (path obscurity) كحماية**. الحماية الحقيقية
طبقات: TLS + مصادقة الـ Gateway + Vault policy + auth قصيرة العمر + لا سرّ في
logs/files.

---

## 2. مرحلتان (سهولة الآن + انتقال سلس للـ cloud)

القرار المعتمد: **AppRole من البداية** (لا هجرة لاحقة — نفس الهوية تنتقل من
local إلى cloud بتعديل الـ policy فقط).

### الآن (Local / RDP)
```text
AppRole
- role_id  : ثابت، غير سرّي (معرّف الهوية)
- secret_id: سرّي، بـ TTL قصير + عدد استخدامات محدود (يُجدَّد)
- token الناتج بـ TTL قصير
- least-privilege policy: قراءة platform/gateway-auth فقط، لا شيء غيره
```

### وقت الـ Cloud
```text
نفس AppRole
+ short-lived Vault token
+ least-privilege policy (تُضيَّق أكثر حسب البيئة)
+ (اختياريًا لاحقًا) response-wrapping لتسليم الـ secret_id بأمان
```

> تجنّبنا Kubernetes auth عمدًا: لسنا على k8s بعد. AppRole هو المناسب لمصادقة
> التطبيقات مع ضبط TTL للـ SecretID والـ token.

### تدفّق AppRole عمليًا (ما يحدث وقت التشغيل)
```text
1. المنصة تملك role_id (env، غير سرّي) + secret_id (من مصدر آمن، TTL قصير).
2. POST auth/approle/login {role_id, secret_id} ⇒ Vault يعيد token قصير العمر.
3. المنصة تستخدم الـ token لقراءة platform/gateway-auth (السرّ + رقم النسخة).
4. السرّ يبقى في الذاكرة فقط، يُحقن كـ X-Gateway-Secret عبر TLS، لا يُكتب على disk.
5. عند انتهاء الـ token/الـ secret_id ⇒ إعادة login (خطوة 2) ما دامت الهوية صالحة.
```

### أين يعيش الـ secret_id في المرحلة الحالية؟
```text
- ليس في الريبو، ليس في أي commit، ليس في أي log (يطابق 20 §5 القائم).
- محليًا/RDP: متغيّر بيئة يُحقن وقت التشغيل (VAULT_APPROLE_SECRET_ID) بـ TTL قصير.
- cloud لاحقًا: response-wrapping أو حقن من منصّة الأسرار السحابية — بلا كتابة على disk.
```

---

## 3. الـ Gateway Secret نفسه

```text
Vault
└── platform/gateway-auth
       ├── gateway_secret          ← السرّ المشترك (X-Gateway-Secret)
       └── gateway_secret_version  ← رقم النسخة الحالية (لضبط الصلاحية)
```

- المنصة تحصل عليه **وقت التشغيل فقط**، في الذاكرة، **لا يُكتب على disk**.
- لا يظهر في أي log/عائد (20 §5).

---

## 4. تمييز حاسم: Rotation مقابل Kill-Switch

| العملية | التعريف | التأثير | كيف تُنفَّذ |
|---|---|---|---|
| **Rotation** | تغيير قيمة السرّ | لا توقف (الطرفان يزامنان الجديد) | تحديث `gateway_secret` + رفع `gateway_secret_version` |
| **Kill-Switch** | إبطال الوصول | توقف فوري وكامل | **revoke هوية المنصة (AppRole)** أو **disable الـ policy** |

### الـ Kill-Switch الحقيقي (عند compromise للمنصة)
```text
1. Vault: revoke SecretID/token الخاص بهوية المنصة  (أو disable الـ policy)
2. المنصة تفقد القدرة على قراءة أي سرّ من Vault فورًا
3. لا تستطيع تجديد credential الـ Gateway ⇒ تتوقف عن نداء المزوّدين
4. السرّ نفسه لم يكن مكتوبًا على السيرفر المخترَق أصلًا
```

### التحكّم بالنسخة (طبقة إضافية على جانب الـ Gateway)
```text
- الـ Gateway يقبل فقط credential المطابق لـ gateway_secret_version الحالية.
- المنصة لا تحصل على نسخة جديدة صالحة إلا بعد إعادة authentication ناجحة
  (أي: هويتها ما زالت صالحة في Vault).
- عند revoke/rotate: تُسحب هوية المنصة أو تنتهي صلاحيتها — لا نعتمد على
  تغيير قيمة السرّ وحده.
```

---

## 5. النموذج المبسّط للبداية (نفس المبدأ، أقل تعقيد)

```text
Vault
   ↓ (AppRole أو token مؤقت)
Platform authenticates
   ↓ (يقرأ platform/gateway-auth وقت التشغيل)
Gateway credential  →  يُرسَل عبر TLS كـ X-Gateway-Secret
   ↓
Gateway validates credential (النسخة الحالية فقط)
```

kill-switch في هذه البداية = **إيقاف صلاحية هوية المنصة في Vault**، لا تغيير
قيمة السرّ.

---

## 6. ما الذي نضيفه لعقد الـ Gateway نتيجة هذا؟

- الـ Gateway يتحقّق من `X-Gateway-Secret` **ومن رقم النسخة** (يرفض النسخ القديمة).
- المنصة تقرأ الـ credential من `SecretManagerPort` (Vault) وقت التشغيل فقط.
- لا credential ولا token يُكتب في الريبو/الـ logs/الـ commits (يطابق 20 §5 القائم).
- التوثيق الصريح: revocation = kill-switch ؛ تغيير القيمة = rotation.

---

## مراجع HashiCorp (للتثبيت في الـ ADR)

- AppRole للمصادقة الآلية وتضييق الـ policy وتقليل عمر الـ credentials.
- HCP Vault Dedicated يدعم AppRole رسميًا.
- المصادقة في Vault مرتبطة بالهوية والسياسة، لا بمعرفة قيمة السرّ.
- أفضل ممارسات AppRole (short-lived SecretID، least-privilege).
