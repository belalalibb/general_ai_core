# البرومبت الجاهز — الزّقه للـ agent المنفّذ

> يضيف "RemoteGatewayAdapter" واحد generic يوصّل المنصة بخدمة Flask Gateway
> خارجية، دون هدم أي شيء ودون تعديل core. نمط العمل الصارم للمشروع محفوظ.
> يعكس كل القرارات: route_token مبهم، Gateway مواد خام فقط، اكتشاف تلقائي عبر
> /describe، وسرّ الـ Gateway عبر Vault AppRole مع kill-switch بالإبطال.

```
OPERATOR AUTHORIZATION — NEW TASK CLUSTER (Remote Provider Gateway integration)

السياق: المنصة عند آخر checkpoint (تحقّق منه أولًا). هذه مهمة مشغّل جديدة
صريحة لإضافة مسار مزوّدين عبر Gateway خارجي — لا إعادة فتح لأي phase مغلقة،
ولا هدم لأي شيء قائم.

اتبع طقس التعافي أولًا: git status / rev-parse HEAD / diff --stat، اقرأ
PROJECT_EXECUTION_STATE.md، تحقّق من نظافة الشجرة، ثم ابدأ.

╔════════════════════════════════════════════════════════════════════════╗
║ PROTOCOL DISCIPLINE — اقرأها قبل أي سطر كود (الأعلى أولوية على الإطلاق) ║
╠════════════════════════════════════════════════════════════════════════╣
║ هذه المهمة ليست refactor؛ أنت تبني protocol بين مشروعين منفصلين. أي     ║
║ انحراف صغير في envelope أو identity أو provisioning يُحدث divergence     ║
║ لاحقًا يصعب إصلاحه. لذا:                                                 ║
║                                                                        ║
║ 1. Treat the uploaded 00_CONTRACT.md as the IMMUTABLE protocol source   ║
║    of truth. عامله كعقد ثابت لا يُعدَّل — نفّذ إليه، لا تُعدِّله.          ║
║                                                                        ║
║ 2. Do NOT "improve" or reinterpret the contract during implementation. ║
║    Any discovered conflict (تعارض/غموض/نقص/تناقض مع الـ core) MUST be   ║
║    reported and you STOP for operator decision — لا تحلّه من عندك،       ║
║    ولا تفترض النية، ولا تختر أحد التفسيرين بنفسك.                        ║
╚════════════════════════════════════════════════════════════════════════╝

GOLDEN CONSTRAINTS (غير قابلة للتفاوض):
- لا تعدّل core/ إطلاقًا. المنصة ترى ProviderAdapterPort فقط (invariant #1).
- لا تلمس providers/real/groq أو genspark — يبقيان يضربان مزوّديهما مباشرة.
- الـ Gateway "مواد خام فقط": لا يقرّر مزوّدًا، لا يتحقّق من صلاحية، لا يطبّق
  سياسة. كل قرار (أي مزوّد/نموذج، هل مسموح؟) يُتّخذ في المنصة قبل النداء
  (invariants #5 الراوتر يقرّر، #7 الـ Gateway ليس سلطة).
- المصدر لا يظهر في أي ريكويست: لا "provider":"slug" صريح في المظروف. المنصة
  ترسل route_token مبهمًا فقط؛ الـ Gateway وحده يفكّه داخليًا. هذا يمنع التجاوز
  (bypass) والإرسال المباشر دون تحقّق الأدمن.
- لا hard-code لأي endpoint مزوّد. تفاصيل المزوّد إمّا data (config) أو تعيش
  داخل الـ Gateway (30 §9: "the Core must not see these details").
- احترم الـ 15 invariant. خصوصًا #4 (platform creds != user creds)،
  #7 (LLM/UI ليس سلطة)، #8 (unknown ⇒ DENY)، 20 §5 (الأسرار مبهمة).
- أي تغيير معماري = ADR.

العقود المرجعية (مرفقة): 00_CONTRACT.md (Request/Response Envelope، route_token
كنقطة التوجيه المبهمة، وضعا credential: user_key/platform، الفئات الاثنتا عشرة،
GET /describe للاكتشاف التلقائي) + 01_SECRET_AND_KILLSWITCH.md (Vault AppRole،
rotation مقابل kill-switch بالإبطال، فحص النسخة). التزم بهما حرفيًا.

AUTHORIZED SCOPE:
1. ADR-00XX (PROPOSED — اعرضه لموافقتي، لا تعتمده): يوثّق "Remote Provider
   Gateway" كحدود ثقة جديدة: adapter generic + خدمة Flask خارجية "مواد خام".
   يوثّق صراحةً: (أ) route_token المبهم يمنع التجاوز؛ (ب) سرّ الـ Gateway عبر
   Vault AppRole (least-privilege، short-lived) مع التمييز: تغيير القيمة =
   rotation، وإبطال الهوية/الـ policy = kill-switch؛ (ج) SSRF عبر
   gateway_base_url ⇒ allowlist admin-only؛ (د) TLS إلزامي؛ (هـ) أين تُفكّ
   أسرار user_key؛ (و) **فصل هوية المزوّد عن التوجيه**: ProviderManifest.id =
   UUID مستقر (هوية domain) + name = display_name (الهوية المقروءة)، منفصلان
   تمامًا عن route_token (routing credential). الـ slug الحقيقي Gateway-internal
   فقط — المنصة لا تعرفه ولا يظهر في /describe. ممنوع اشتقاق الـ id من
   route_token (لا hash) — السبب: دورتا حياة مختلفتان، وrotation/revocation
   للـ token يجب ألّا يكسر الهوية ولا bindings/history؛ (ز) **provisioning
   للـ route_token out-of-band**: المنصة المُصدِر الوحيد (تولّده عشوائيًا
   تشفيريًا عند تفعيل الأدمن، تربطه بـ provider.id)، والـ Gateway مستهلك يستقبل
   الربط عبر قناة سرّية — لا HTTP endpoint عام للتسجيل. سجّل كل ذلك في الـ
   ADR/contract. اذكر البدائل والمخاطر. لا تثبّت اعتمادًا قبل موافقتي.

2. providers/real/gateway/ (جديد — لا يمسّ أي مزوّد قائم):
   - adapter.py: RemoteGatewayAdapter ينفّذ ProviderAdapterPort السبعة كاملةً:
       * get_manifest: يبني ProviderManifest من config الصفّ + (اختياريًا) من
         GET /describe (اكتشاف تلقائي: operations/capabilities/models معلَنة من
         الـ Gateway، لا مُخمَّنة — deny-by-default محفوظ).
       * generate: يبني Request Envelope (00_CONTRACT §2) حاملًا route_token
         (لا slug صريح)، ينادي المسار الثابت المطابق للـ operation
         (generate_text→POST /generate ...)، ويحوّل Response Envelope إلى
         ProviderGenerateResponse. undeclared operation ⇒ unsupported_capability
         محليًا قبل أي نداء (30 §8.1).
       * validate_credential / discover_models / health_check: عبر /describe،
         GET /models، GET /health؛ الفراغ/UNKNOWN يُنقل بصدق (لا فبركة).
       * normalize_error: يترجم error.category من المظروف إلى ProviderError
         (الفئات الاثنتا عشرة)؛ أي شكل غير معروف ⇒ non_retryable_error.
       * credential: user_key ⇒ secret_resolver يفكّ credential_ref ويضعه في
         envelope.credential.value في آخر لحظة؛ platform ⇒ value=null (المنصة
         لا ترسل سرًّا). لا تسجّل القيمة إطلاقًا (20 §5).
       * HTTP transport injectable (httpx) ⇒ اختبارات hermetic بـ MockTransport،
         بلا شبكة في الـ gates (نفس نمط groq).
       * يُرسل عبر TLS رأسي X-Gateway-Secret + X-Gateway-Secret-Version
         (يُحقنان من composition، مصدرهما SecretManagerPort/Vault).
   - __init__.py: بنّاء manifest من config/describe (بلا أسماء موديلات مخترعة — 41 §49).

3. apps/composition/ (إضافة seam فقط، لا تغيير سلوك قائم):
   - قارئ config لمزوّدي الـ Gateway: الحدّ الأدنى فقط (route_token،
     gateway_base_url، status) — القدرات وdisplay_name تأتي من /describe.
     المنصة لا تخزّن الـ slug إطلاقًا (Gateway-internal فقط).
   - هوية المزوّد: provider.id = UUID مستقر + name = display_name، منفصلان عن
     route_token. الربط (provider.id ↔ route_token) داخلي في المنصة.
   - provisioning: المنصة تولّد route_token عشوائيًا تشفيريًا عند تفعيل الأدمن،
     تربطه بـ provider.id، وتوفّره للـ Gateway عبر قناة out-of-band سرّية (لا
     endpoint عام). rotation = تحديث الربط فقط (id/name/bindings ثابتة).
   - gateway_base_url عبر ALLOWLIST (ضد SSRF) — رابط خارجها ⇒ ValueError واضح
     (لا سقوط صامت).
   - سرّ الـ Gateway + رقمه (gateway_secret / gateway_secret_version) يُقرآن من
     Vault عبر AppRole وقت التشغيل فقط، في الذاكرة، لا يُكتبان على disk ولا في
     أي log/commit. "not configured ⇒ لا مزوّد gateway" (نفس سياسة S3/Vault).

4. اختبارات hermetic (بلا شبكة):
   - port conformance للـ RemoteGatewayAdapter (السبعة).
   - envelope round-trip (success / unsupported / rate_limited) عبر MockTransport.
   - route_token: المظروف يحمل route_token ولا يحمل الـ slug الحقيقي إطلاقًا.
   - user_key: credential_ref يُفكّ في اللحظة الأخيرة ولا يظهر في أي log/عائد.
   - platform: لا سرّ يغادر المنصة (value=null).
   - allowlist: رابط خارج القائمة يُرفض بـ ValueError.
   - /describe: القدرات تُبنى من ردّ الـ Gateway (لا افتراض).
   - version header: يُرسَل ويطابق النسخة الحالية.
   - undeclared operation ⇒ unsupported_capability بلا نداء.
   - لا تسريب: safe_message فقط، لا داخليات، لا slug، لا secret.

5. وثيقة onboarding قصيرة تحت 31 (أو ملف مجاور): "كيف تضيف مزوّد Gateway"
   = انسخ قالب Flask provider + أضف route (المصدر) + المنصة تكتشف عبر /describe
   + فعّل عبر Admin بعد التحقق (تُولَّد route_token عندها). حدّث
   providers/_pending_real_providers.md بصدق (كم مزوّدًا يعمل فعليًا).

BOUNDARIES:
- لا تبني خدمة الـ Flask نفسها داخل هذا الريبو (مشروع المشغّل المنفصل)؛ ابنِ
  جانب المنصة فقط + العقود + الاختبارات + قالب/مثال Flask في docs إن لزم.
- لا async/streaming جديد (ADR منفصل مستقبلي).
- لا تفعيل تلقائي لأي مزوّد: يبقى status=disabled حتى تمرّ الاختبارات (31 §19)،
  ثم يُفعَّل عبر Admin (عندها يُولَّد route_token).
- حافظ على كل البوابات خضراء؛ local-only commits (لا push يدوي).

DONE = RemoteGatewayAdapter كامل (ProviderAdapterPort السبعة) + seam الـ config
مع allowlist + route_token + AppRole secret/version + ADR PROPOSED + اختبارات
hermetic خضراء + كل البوابات خضراء (pytest/mypy/ruff/import-linter/check_repo)
+ تحديث الحالة + commit موثّق + تقرير نهائي: ماذا أُضيف، ماذا لم يُلمس (إثبات
عدم الهدم)، والقرارات المطلوبة مني.
```
