# AI Orchestration Platform — Final Engineering Specification Pack V2

**Status:** Rebuilt / Stronger Version  
**Purpose:** تحويل كامل قرارات المحادثة إلى حزمة مواصفات تنفيذية قابلة للبناء، المراجعة، الاستئناف، والتسليم لأي AI Agent أو مهندس.

---

---

## V2 Baseline / V3 Target Notice

```text
PACK STATUS: ARCHIVED_BASELINE — NOT AUTHORITATIVE (T-DOC-013)
Current Baseline: V3 (../final_docs_v3/ — all 20 documents COMPLETE_AUTHORITATIVE)
Authority index: ../final_docs_v3/00_INDEX.md (single authority switch)
Every V2 document (01–25) carries a SUPERSEDED banner pointing to its V3
successor. This pack is read-only historical source material, kept for
traceability audits only. Never cite a V2 document as authority.
```

This index describes the current V2 documentation pack.
It is not a mandatory final file structure for V3.

During V3 re-architecture, an Agent may merge, split, rename, reorder, move, create, or remove documents when this improves execution value.
Accepted product decisions, requirements, contracts, architecture invariants, security constraints, and critical decisions must remain preserved and traceable.

---

## لماذا V2؟

النسخة السابقة كانت قوية كـ Architecture + Engineering Governance، لكنها ناقصة في مواصفات التنفيذ المباشر مثل:

- API contracts.
- Domain model.
- Provider plugin spec.
- Routing decision spec.
- Execution graph schema.
- Memory retrieval rules.
- Security threat model.
- Admin control matrix.
- MVP roadmap.
- Q&A decision traceability.

هذه النسخة تضيف تلك الطبقات بدون تغيير الهدف المعماري.

---

## الوثائق

| # | File | Purpose |
|---|---|---|
| 01 | `01_PRODUCT_REQUIREMENTS.md` | متطلبات المنتج، المستخدمين، القدرات، والحدود |
| 02 | `02_FINAL_ARCHITECTURE_BASELINE.md` | المعمارية النهائية المعتمدة |
| 03 | `03_DOMAIN_MODEL.md` | الكيانات الأساسية والعلاقات بينها |
| 04 | `04_API_CONTRACTS.md` | عقود API وRequest/Response/Error schemas |
| 05 | `05_PROVIDER_PLUGIN_SPEC.md` | مواصفة إضافة Providers وحساباتهم وقدراتهم |
| 06 | `06_MODEL_ROUTING_SPEC.md` | مواصفة Router، التصنيف، scoring، fallback |
| 07 | `07_EXECUTION_GRAPH_SPEC.md` | مواصفة Execution Graph وAgent workflows |
| 08 | `08_MEMORY_CONTEXT_SPEC.md` | مواصفة الذاكرة والسياق والتفضيلات |
| 09 | `09_SKILL_TOOL_SPEC.md` | مواصفة Skills وTools وClient Runtime |
| 10 | `10_SECURITY_THREAT_MODEL.md` | Threat model وحماية AI/Tools/Tenants/Secrets |
| 11 | `11_ADMIN_CONTROL_PLANE_SPEC.md` | ما يتحكم فيه الأدمن وما لا يجوز تعطيله |
| 12 | `12_EVALUATION_LEARNING_SPEC.md` | Evaluation, Verification, Learning lifecycle |
| 13 | `13_MASTER_ENGINEERING_PROTOCOL.md` | البروتوكول الهندسي الأعلى |
| 14 | `14_MASTER_IMPLEMENTATION_PLAN.md` | خطة التنفيذ المرحلية |
| 15 | `15_MVP_ROADMAP.md` | Roadmap تنفيذية من MVP إلى Production |
| 16 | `16_MASTER_BUILD_PROMPT.md` | Prompt البناء الرئيسي للـAgent |
| 17 | `17_RESUME_PROMPT.md` | Prompt الاستئناف الثابت |
| 18 | `18_QA_DECISION_LOG.md` | ربط أسئلة المستخدم بالقرارات النهائية |
| 19 | `19_AGENT_COGNITIVE_OPERATING_PROTOCOL.md` | بروتوكول إجبار الـAgent على التفكير العميق، المقارنة، red-team، والدليل |
| 20 | `20_ULTRA_EXECUTION_PROMPT.md` | برومبت تنفيذ فائق الجودة لاستخراج أقصى قوة تفكير وتنفيذ من الـAgent |
| 21 | `21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md` | مواصفة استخدام أكثر من Agent من المزودين كـsub-agents داخل Agent المنتج الأساسي |
| 22 | `22_LIGHTWEIGHT_RESUME_AND_PROGRESS_STATE_PROTOCOL.md` | بروتوكول استئناف خفيف قليل التوكن مع قواعد صارمة لحفظ حالة التقدم والتعافي من الانقطاع |
| 23 | `23_AI_PROVIDERS_SCAFFOLDING_POLICY.md` | سياسة إنشاء بنية Providers متنوعة وآمنة عند عدم وجود مزودين حقيقيين بعد |
| 24 | `24_FINAL_PROVIDER_ARCHITECTURE_SPEC.md` | المواصفة النهائية المركزة لجزء الـProviders بعد الفهم الجديد: capability-driven وبدون فرض lifecycle واحد |
| 25 | `25_REAL_PROVIDER_ONBOARDING_GUIDE.md` | دليل واضح لحالة عدم وجود مزودين حقيقيين حاليًا وكيفية إضافة مزود حقيقي حسب كل نوع |

---

## طريقة الاستخدام

1. اقرأ `01_PRODUCT_REQUIREMENTS.md` لفهم المنتج.
2. اقرأ `02_FINAL_ARCHITECTURE_BASELINE.md` لفهم النظام.
3. استخدم `03` إلى `12` كمواصفات تنفيذ تفصيلية.
4. استخدم `13` و`14` كقواعد تنفيذ وإدارة.
5. استخدم `15` لتحديد نطاق MVP.
6. استخدم `16` مع أي Agent يبدأ التنفيذ.
7. استخدم `17` في بداية كل جلسة جديدة.
8. استخدم `18` لفهم لماذا اتخذت القرارات.
9. استخدم `19` كقواعد تشغيل معرفية للـAgent أثناء القرارات الصعبة.
10. استخدم `20` بدل `16` عندما تريد أقصى جودة تفكير وتنفيذ من الـAgent.
11. استخدم `21` لفهم وتنفيذ Orchestration لأكثر من Provider-native Agent داخل Agent Mode.
12. استخدم `22` كبرومبت وبروتوكول الاستئناف الخفيف لكل جلسة تنفيذ أو إعادة كتابة وثائق.
13. استخدم `23` عند عدم وجود `ai_providers` أو مزودين حقيقيين لإنشاء scaffold فقط بدون ادعاء وظائف مزيفة.
14. استخدم `24` كمرجع نهائي مركز عند تنفيذ أو مراجعة جزء الـProviders فقط.
15. استخدم `25` كدليل عملي لإضافة مزود حقيقي لاحقًا، مع أمثلة لكل نوع Provider.

---

## قاعدة الحقيقة

```text
Git committed state + passing verification = trusted progress
```

المحادثة، الملفات، والخطط تساعد في الملاحة، لكنها ليست إثبات إنجاز.

---

## النتيجة

هذه الحزمة لا تكتفي بوصف المعمارية؛ بل تحدد كيف تُبنى، كيف تُختبر، كيف تُؤمّن، كيف تُستأنف، وكيف تتطور بدون كسر الـCore.
