# OPERATOR AUTHORIZATION — PROVIDER GATEWAY ARCHITECTURE REVIEW & PROPOSAL

## PURPOSE

أريد منك مراجعة المعمارية الحالية للمشروع فعليًا من الـrepository، ثم إعداد
**تصميم مقترح شامل** لطبقة Provider Gateway الخارجية التي ناقشناها.

هذه الجلسة **Planning / Architecture Review فقط**.

**ممنوع تنفيذ أي كود أو تعديل أي ملف أو اعتماد أي ADR.**

الهدف هو أن تعرض لي **اقتراحك الهندسي في كل جزء** بناءً على الواقع الحالي
للمشروع، ثم أتخذ أنا القرارات النهائية قبل أي implementation.

---

# 0. EVIDENCE DISCIPLINE — شرط ثقة غير قابل للتفاوض

سبق أن استلمتُ تقريرًا وصف ملفات وكوميتات واختبارات وأرقامًا **غير موجودة في
الشجرة**. لن يتكرر ذلك. لذلك:

```text
- كل ادّعاء عن واقع الـrepo يجب أن يُرفَق بـ:
    الأمر المُنفَّذ + مخرجاته الفعلية + commit SHA + tree SHA (عند اللزوم)
    + عدد اختبارات أستطيع إعادة تشغيله بنفسي.
- أي ملف/كوميت/اختبار/رقم بوابة تذكره ولا يوجد فعليًا في الشجرة = خرق مباشر
  لمبدأ never-fake (41 §49) ويُبطل التقرير.
- لا تصف سلوكًا "متوقّعًا" كأنه "متحقَّق". ميّز بوضوح: [متحقَّق بدليل] مقابل
  [مقترح/فرضية].
```

**Repository reality = source of truth. Evidence = source of trust.**

---

# 1. RECOVERY / REALITY FIRST

قبل أي تحليل:

```text
git status
git rev-parse HEAD
git diff --stat
git log --oneline -10
git remote -v
```

ثم اقرأ:

```text
engineering/PROJECT_EXECUTION_STATE.md
```

وأي وثائق/ADRs/Contracts ذات صلة بالـproviders والـrouting والـcredentials
والـusage والـdeployment.

لا تفترض أن رقم checkpoint الموجود في أي prompt هو الأحدث.

**Repository reality = source of truth for current implementation state.**

---

# 1.b PRIOR ART — الـkit الذي بنيناه (قيّمه، لا تعتمده)

يوجد kit تصميمي سابق أنجزناه (خارج الـrepo، في `provider_gateway_kit/`):
`00_CONTRACT.md` · `01_SECRET_AND_KILLSWITCH.md` · `app.py` (نموذج Flask) ·
`providers/` · `platform_manifest_template.md` · `AGENT_PROMPT.md` · `README.md`.

عامله كـ **prior art / مرشّح تصميم — وليس قرارًا نهائيًا**:
- أين يتفق اقتراحك معه ولماذا؟
- أين تراه ناقصًا أو خاطئًا أو over-engineered ولماذا؟
- لا ترضخ له لمجرد وجوده، ولا تتجاهله فتعيد اختراع ما حُسم. **قيّمه نقديًا.**

---

# 2. GOLDEN RULE

هذه ليست جلسة تنفيذ.

لا تقم بأي من التالي:

* لا تعدّل `core/`
* لا تعدّل providers القائمة
* لا تنشئ `RemoteGatewayAdapter`
* لا تنشئ Flask Gateway
* لا تغيّر contracts الحالية
* لا تضف dependencies
* لا تنشئ ADR جديدًا كـACCEPTED
* لا تعمل migration
* لا تعمل refactor لمجرد التحسين

إذا وجدت تعارضًا بين الفكرة المقترحة وبين المعمارية الحالية:

**لا تحل التعارض بنفسك.**

سجّل:

```text
Conflict
Current reality
Why it matters
Possible options
Your recommendation
Operator decision required
```

---

# 3. CONTEXT — THE DESIGN WE ARE EXPLORING

الفكرة العامة التي أريد منك تقييمها:

```text
                 MAIN PLATFORM
                       │
                 Provider boundary
                       │
             Generic Remote Adapter
                       │
               Unified Gateway API
                       │
                PRIVATE GATEWAY
                       │
                Provider Registry
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Provider A Provider B Provider C
```

الـGateway الخارجي يكون:

**raw execution/data plane فقط**

ولا يكون:

* authorization authority
* entitlement authority
* billing authority
* routing authority
* admin authority
* policy authority

الـPlatform الرئيسية تظل صاحبة كل هذه القرارات.

---

# 4. REQUIREMENT A — PROVIDER ISOLATION

حلّل واقترح أفضل طريقة بحيث:

* كل Provider يعيش في مشروع/مساحة Gateway مستقلة.
* يمكن أن يكون للـProvider عدة ملفات/handlers/capabilities.
* المنصة لا تحتاج تعديل كود لكل Provider جديد.
* إضافة Provider جديد يجب أن تكون معزولة في Gateway قدر الإمكان.
* الـCore الحالي لا يعرف provider-specific HTTP/SDK details.
* providers القائمة مثل Groq/Genspark لا يتم كسرها أو إعادة بنائها بلا سبب.

أعرض:

```text
Recommended structure
Alternative structure(s)
Trade-offs
Migration impact
```

---

# 5. REQUIREMENT B — UNIFIED GATEWAY API

أريد اقتراحك للـAPI الموحدة بين Platform وGateway.

قيّم العمليات الحالية مثل:

```text
generate_text
create_embeddings
transcribe_audio
synthesize_speech
generate_image
analyze_vision
rerank_documents
moderate_content
```

واقترح:

* ما الذي يجب أن يبقى ثابتًا؟
* ما الذي يجب أن يكون extensible؟
* هل نستخدم routes ثابتة؟
* هل نحتاج operation registry؟
* كيف نضيف operation مستقبلية بدون كسر الـCore؟
* هل `/describe` مناسب؟
* ما هي أفضل صيغة للـRequest Envelope؟
* ما هي أفضل صيغة للـResponse Envelope؟

**لا تثبّت أي اختيار. اعرض البدائل ثم توصيتك.**

---

# 6. REQUIREMENT C — PROVIDER DISCOVERY

أريد منك تقييم آلية:

```text
GET /describe
```

بحيث الـGateway يعلن:

```text
operations
capabilities
models
credential_mode
display_name
```

حلّل:

* هل discovery من DEFINITION هو الأفضل؟
* هل يجب أن تكون DEFINITION إلزامية؟
* هل الـGateway يستنتج capabilities من handlers أم لا؟
* كيف نحافظ على deny-by-default؟
* ماذا تفعل المنصة لو `/describe` غير متاح؟
* كيف نمنع Gateway من أن يصبح authority؟

اعرض تصميمك الموصى به.

---

# 7. REQUIREMENT D — PROVIDER IDENTITY VS ROUTING

هذه نقطة شديدة الأهمية.

نريد فصل:

```text
ProviderManifest.id
logical/provider identity
route_token
```

بحيث:

* identity مستقرة
* route_token قابل للrotation/revocation
* تغيير route_token لا يكسر bindings/history
* لا يتم اشتقاق الـidentity من route_token
* provider slug الحقيقي يظل Gateway-internal

اقترح أفضل model لهذه العلاقة.

وضح:

```text
Platform data
Gateway data
Mapping
Lifecycle
Rotation behavior
Revocation behavior
```

---

# 8. REQUIREMENT E — ROUTE TOKEN / BYPASS PREVENTION

نريد أن لا يظهر المصدر الحقيقي في أي request:

مرفوض:

```json
{
  "provider": "openai"
}
```

ونبحث عن design يعتمد على:

```text
opaque route_token
```

قيّم:

* توليد token
* تخزينه
* rotation
* revocation
* out-of-band provisioning
* anti-enumeration
* هل يجب أن يظهر token في query/header/body؟
* كيف تمنع استخدام Gateway مباشرة لتجاوز Platform authorization؟
* هل Gateway URL نفسه يجب أن يكون private/internal؟

اقترح **أبسط تصميم آمن**.

---

# 9. REQUIREMENT F — CREDENTIALS / BYOK

لدينا نوعان:

### USER KEY

```text
user
→ platform
→ SecretManager/Vault
→ credential_ref
→ runtime resolution
→ Gateway
```

### PLATFORM

```text
platform
→ credential.mode = platform
→ value = null
→ Gateway يستخدم credentials/accounts الخاصة به
```

أريد تقييمك:

* هل الفصل ده صحيح؟
* أين يجب فك user secret؟
* هل raw credential يجب أن يدخل Gateway؟
* كيف نمنع logging/leakage؟
* ما مسؤولية Gateway؟
* ما مسؤولية Platform؟
* هل يحتاج Gateway credential provider abstraction؟
* كيف ندعم token/account/OAuth/session في platform mode بدون تغيير Platform؟

---

# 10. REQUIREMENT G — GATEWAY SHARED AUTH

نريد حماية الاتصال بين Platform وGateway.

التصميم المقترح حاليًا:

```text
Managed Vault
    ↓
AppRole
    ↓
Least privilege
    ↓
Gateway credential
    ↓
TLS
    ↓
Private Gateway
```

ولدينا:

```text
X-Gateway-Secret
X-Gateway-Secret-Version
```

وكذلك الفرق:

```text
Rotation ≠ Kill-Switch
```

قيّم:

* هل shared secret كافٍ؟
* هل version header له قيمة حقيقية؟
* هل AppRole مناسب؟
* ما البدائل؟
* هل mTLS أفضل؟
* هل workload identity أفضل؟
* ما الأسهل الآن؟
* ما الأنسب Cloud لاحقًا؟

أعطني:

```text
Recommended now
Recommended later
Why
Migration path
```

---

# 11. REQUIREMENT H — KILL-SWITCH

نريد ability لإيقاف platform access إلى Gateway مركزيًا.

ناقش بوضوح:

```text
Rotation
vs
Revocation
vs
Policy disable
```

حدد:

* ما الذي يوقف الوصول فعليًا؟
* ما الذي لا يوقفه؟
* ماذا يحدث لو المنصة compromised؟
* ماذا يحدث لو Gateway compromised؟
* ما هو blast radius؟

لا تستخدم "path secrecy" كضمان أمني.

---

# 12. REQUIREMENT I — USAGE / BILLING

أريد الحفاظ على النظام الحالي.

القاعدة:

```text
Gateway
→ provider/raw usage evidence

Platform
→ Estimate
→ Reserve
→ Execute
→ Settle / Refund / Fail
→ usage_ledger
→ Plan / Entitlement / Quota
```

قيّم:

* ما الذي يجب أن يرجعه Gateway؟
* هل provider usage يعتبر billing truth؟
* كيف نتعامل مع providers مختلفة في usage units؟
* كيف تمنع duplicate accounting؟
* كيف تتعامل مع retries؟
* هل Gateway يمكنه حساب provider cost؟
* أين تعيش platform pricing policies؟

**يجب ألا يتحول Gateway إلى Billing Engine.**

---

# 13. REQUIREMENT J — ROUTING / PROVIDER SELECTION

حلّل مسؤولية كل طرف:

```text
Platform:
"Which provider/model should run?"

Gateway:
"How do I execute the selected provider request?"
```

وضح:

* AUTO
* TIER
* EXPLICIT
* fallback
* model eligibility
* account selection
* provider outage
* unsupported capability

يجب أن يكون Gateway غير قادر على تجاوز قرار Platform.

---

# 14. REQUIREMENT K — PROVIDER REGISTRY

اقترح كيف يبني Gateway registry داخلي بدون coupling سيئ مثل:

```text
provider_slug == filename
```

نريد:

```text
logical provider identity
        ↓
registry
        ↓
provider implementation
```

اشرح:

* registry structure
* registration
* discovery
* lifecycle
* duplicate prevention
* capability declaration
* loading strategy

---

# 15. REQUIREMENT L — ADDING A NEW PROVIDER

أريد منك كتابة workflow عملي من الصفر:

```text
Engineer receives new provider
        ↓
Creates provider implementation
        ↓
Declares capabilities
        ↓
Registers provider
        ↓
Tests
        ↓
Gateway exposes it
        ↓
Platform discovers it
        ↓
Admin approves
        ↓
Provider becomes eligible
```

أريدك تقترح:

**ما أقل عدد خطوات ممكنة بدون التضحية بالأمان؟**

---

# 16. REQUIREMENT M — PLATFORM CONFIGURATION

نريد أقل configuration ممكنة في Platform.

قيّم هل يكفي:

```text
provider.id
display_name
gateway_base_url
route_token
status
```

أم تقترح شكلًا آخر.

ممنوع أن تحتاج Platform إلى:

```text
provider-specific endpoint
provider-specific auth method
provider-specific request schema
provider-specific SDK
```

إلا لو عندك سبب معماري قوي جدًا.

---

# 17. REQUIREMENT N — SECURITY THREATS

أعمل Threat Review حقيقي للتصميم المقترح على الأقل ضد:

```text
SSRF
Provider enumeration
Gateway direct access
route-token guessing
credential leakage
log leakage
replay
stale token
stale secret version
compromised Gateway
compromised Platform
malicious provider response
capability spoofing
billing manipulation
tenant isolation bypass
```

لكل threat أعطني:

```text
Risk
Attack path
Mitigation
Residual risk
```

---

# 18. REQUIREMENT O — EXISTING ARCHITECTURE IMPACT

من الـrepository الفعلي، اعمل impact map:

```text
core/
providers/
apps/composition/
routing/
execution/
usage/
identity/
security/
admin/
tests/
```

لكل منطقة:

```text
Do we touch it?
Why?
How much?
Can we avoid touching it?
```

الهدف:

**minimal change surface**

---

# 19. REQUIREMENT P — TEST STRATEGY

صمّم test strategy للـGateway integration:

### Contract

* request envelope
* response envelope
* error mapping
* describe

### Security

* route token
* secret
* version
* leakage
* anti-enumeration

### Compatibility

* existing providers unchanged
* existing ProviderAdapterPort unchanged

### E2E

```text
Platform
→ Adapter
→ Gateway
→ Real Provider
→ Platform
```

### Failure

```text
timeout
429
invalid credential
unsupported capability
gateway unavailable
stale token
stale secret version
```

اعرض اختبارات:

```text
Hermetic
Integration
Live
```

وحدد ما يجب أن يكون mandatory وما يمكن أن يكون optional.

---

# 20. REQUIREMENT Q — OBSERVABILITY

اقترح ما الذي يسمح للـPlatform بتسجيله بدون تسريب:

مسموح مثل:

```text
request_id
execution_id
latency
operation
normalized error category
usage metadata
```

ممنوع:

```text
secret
raw user key
provider internal URL
route_token
internal provider slug
```

حدد أيضًا كيف نتعامل مع tracing بحيث لا تتسرب الأسرار أو المصدر الداخلي.

---

# 21. REQUIREMENT R — FAILURE / RECOVERY SEMANTICS

حلّل ماذا يحدث في الحالات:

```text
Gateway unavailable
Provider unavailable
Gateway timeout
Provider timeout
Gateway returns malformed envelope
Gateway returns unknown error
Provider capability disappears
Provider model disappears
credential expires
route token rotates
secret rotates
Vault unavailable
```

أريد semantic واضحة:

```text
retry?
fallback?
fail?
mark unavailable?
```

---

# 22. REQUIREMENT S — VERSIONING

اقترح كيف يكون:

```text
Gateway Contract version
Provider definition version
route-token version
secret version
```

من غير أن نربط الأشياء ببعض بطريقة تكسر backward compatibility.

---

# 23. REQUIREMENT T — DEPLOYMENT / NETWORKING

لا تنفذ deployment.

لكن اقترح أفضل shape:

```text
Platform
   ↓
Private Gateway
```

وقارن:

```text
same host
private network
VPN
internal load balancer
public HTTPS
mTLS
```

مع التركيز على:

```text
easiest now
safest now
easiest cloud migration
```

---

# 24. REQUIREMENT U — FINAL RECOMMENDATION

في نهاية التقرير أريد منك أن تقدم:

## Recommended Architecture
رسم معماري واحد واضح.

## Recommended Contracts
قائمة مختصرة بالعقود التي يجب أن تثبت.

## Recommended Data Model
ما الذي تخزنه Platform وما الذي يخزنه Gateway.

## Recommended Security Model
كيف تتم authentication / authorization / secret handling.

## Recommended Provider Onboarding
أقل خطوات لإضافة Provider.

## Recommended Migration Strategy
كيف نضيف هذا فوق الموجود بدون هدم.

## Open Decisions
قائمة بكل قرار يحتاج موافقة Operator.

لا تعتمد أي قرار.

---

# 25. HARD CONSTRAINTS FOR YOUR RECOMMENDATION

اقتراحك يجب أن يحترم:

```text
1. Existing Core architecture is valuable and must not be unnecessarily changed.
2. Existing Groq/Genspark providers remain functional.
3. Platform remains the only authority for:
   authorization
   routing
   entitlement
   billing
   usage settlement
   provider activation
4. Gateway remains raw execution/data plane.
5. Unknown capability => DENY.
6. Secrets are opaque and never logged.
7. Provider-specific details stay outside Core.
8. Adding a provider should require minimal or ideally zero Platform code changes.
9. route_token is not provider identity.
10. Gateway must not expose enough information to bypass Platform controls.
11. No hard-coded provider implementation in Platform.
12. No fake provider functionality.
```

---

# 26. OUTPUT FORMAT

لا أريد كود.

أريد تقريرًا منظمًا بهذا الترتيب:

```text
1. Current Repository Reality
2. Existing Provider Architecture
3. Proposed Gateway Architecture
4. Option A
5. Option B
6. Option C
7. Recommendation
8. Detailed Component Responsibilities
9. Contract Proposal
10. Security Model
11. Credential Model
12. Routing Model
13. Usage/Billing Model
14. Provider Onboarding Model
15. Registry Model
16. Discovery Model
17. Failure Model
18. Versioning Model
19. Deployment Model
20. Test Strategy
21. Migration Impact
22. Risks
23. Open Decisions
24. Recommended Implementation Phases
```

لكل قرار مهم اعرض:

```text
Problem
Options
Trade-offs
Recommendation
Why
Operator decision required?
```

> ملاحظة عن العمق: لو بند يستحق تعمّقًا أكبر من غيره، صرّح بذلك وركّز المجهود
> على القرارات ذات الأثر الأعلى — لا تملأ بنودًا بكلام عام لمجرد التغطية.

---

# FINAL RULE

**Do not implement.**

**Do not modify files.**

**Do not create or accept an ADR.**

**Do not assume my preferred design is automatically correct.**

أنا أريد منك أن تتعامل مع المتطلبات أعلاه كـrequirements، ثم تستخدم **الـrepository الفعلي** لتقديم أفضل تصميم هندسي ممكن، وتوضح لي أين تتفق مع التصميم الحالي وأين تقترح تغييره ولماذا.

في النهاية توقّف وانتظر قرار الـOperator قبل أي implementation.
