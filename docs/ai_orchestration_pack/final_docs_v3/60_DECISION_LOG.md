# 60 — Decision Log
## Part A: Q&A Decision Log From Conversation (carried) + Part B: Migration Decision Records (appended)

```text
STATUS: AUTHORITATIVE (V3) — LIVE APPEND-ONLY LOG
AUTHORED_BY_TASK: T-DOC-012
SOURCE (V2, now SUPERSEDED):
- final_docs_v2/18_QA_DECISION_LOG.md (CARRY — Part A, verbatim)
AUTHORITY SWITCH: final_docs_v3/00_INDEX.md (MIGRATION STATUS table)
APPEND RULES:
- This log is append-only. Existing entries are never edited or deleted;
  a superseded decision gets a NEW entry that references the old one.
- Conflict resolutions made during documentation migration are appended
  in Part B (this task appends MR-001..MR-004).
- Per 41 §31: out-of-scope improvement ideas found during implementation
  are recorded here (this file replaced the superseded FUTURE_IMPROVEMENTS.md
  / ARCHITECTURE_GAPS.md ledger scheme, per D10/D11).
- Part A Ref lines are historical and name v2 documents; resolve them
  through the V2 → V3 reference map below.
```

Resume / Handoff:
Project execution state is controlled by docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md.
Do not infer project progress from this document.
Resume only from the authorized task recorded in the project state file.

### V2 → V3 Reference Map (for Part A Ref lines)

```text
v2 01_PRODUCT_REQUIREMENTS.md            → v3 01_PRODUCT_REQUIREMENTS.md
v2 02_FINAL_ARCHITECTURE_BASELINE.md     → v3 02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md
v2 03_DOMAIN_MODEL.md                    → v3 03_DOMAIN_MODEL.md
v2 04_API_CONTRACTS.md                   → v3 10_API_CONTRACTS.md
v2 05_PROVIDER_PLUGIN_SPEC.md            → v3 30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md
v2 06_MODEL_ROUTING_SPEC.md              → v3 11_MODEL_ROUTING_AND_MODEL_CONTROL.md
v2 07_EXECUTION_GRAPH_SPEC.md            → v3 12_EXECUTION_GRAPH_AND_AGENT_MODE.md
v2 08_MEMORY_CONTEXT_SPEC.md             → v3 13_MEMORY_AND_CONTEXT.md
v2 09_SKILL_TOOL_SPEC.md                 → v3 14_SKILLS_AND_TOOLS.md
v2 10_SECURITY_THREAT_MODEL.md           → v3 20_SECURITY_THREAT_MODEL.md
v2 11_ADMIN_CONTROL_PLANE_SPEC.md        → v3 21_ADMIN_CONTROL_PLANE.md
v2 12_EVALUATION_LEARNING_SPEC.md        → v3 22_EVALUATION_AND_LEARNING.md
v2 13_MASTER_ENGINEERING_PROTOCOL.md     → v3 40_ENGINEERING_PROTOCOL.md
v2 14_MASTER_IMPLEMENTATION_PLAN.md      → v3 41_IMPLEMENTATION_PLAN_AND_MVP.md
v2 15_MVP_ROADMAP.md                     → v3 41_IMPLEMENTATION_PLAN_AND_MVP.md
v2 17_RESUME_PROMPT.md                   → v3 52_RESUME_AND_PROGRESS_PROTOCOL.md (retired/absorbed)
v2 21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md → v3 12_EXECUTION_GRAPH_AND_AGENT_MODE.md
v2 23_AI_PROVIDERS_SCAFFOLDING_POLICY.md → v3 31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md
v2 25 (real provider onboarding)         → v3 31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md
```

---

# PART A — Q&A DECISION LOG FROM CONVERSATION (CARRIED FROM V2 18)

هذه الوثيقة تربط أسئلة المستخدم الأصلية بالقرارات النهائية والمكان الذي تظهر فيه في المواصفات.

---

## Q1. هل المشروع مجرد Ensemble AI؟

### Decision
لا. المشروع AI Orchestration Platform.

### Reason
لو كان مجرد Model Router سيصبح محدودًا. المطلوب منصة reusable لأي منتج خارجي.

### Ref
`01_PRODUCT_REQUIREMENTS.md`, `02_FINAL_ARCHITECTURE_BASELINE.md`

---

## Q2. هل النماذج هي العقل الرئيسي؟

### Decision
لا. العقل في Core Orchestration + Router + Execution + Evaluation.

### Ref
`02_FINAL_ARCHITECTURE_BASELINE.md`, `06_MODEL_ROUTING_SPEC.md`

---

## Q3. كيف نضيف Providers مختلفة؟

### Decision
كل Provider يكون module مستقل بmanifest وadapter وcontract tests.

### Ref
`05_PROVIDER_PLUGIN_SPEC.md`

---

## Q4. ماذا لو نفس النموذج موجود عند أكثر من Provider؟

### Decision
نفصل Model عن Provider عن Account. Explicit model يحاول provider bindings المتاحة لنفس model أولًا.

### Ref
`03_DOMAIN_MODEL.md`, `06_MODEL_ROUTING_SPEC.md`

---

## Q5. هل Router يحتاج Model؟

### Decision
قد يستخدم model في task analysis، لكن Router Engine ليس model. يستخدم Bootstrap Routing Policy لاختيار router model.

### Ref
`06_MODEL_ROUTING_SPEC.md`

---

## Q6. كيف يعمل Agent Mode؟

### Decision
Agent Mode هو Execution Graph/Workflow، وليس boolean.

### Ref
`07_EXECUTION_GRAPH_SPEC.md`

---

## Q7. كيف تكون الذاكرة؟

### Decision
تقسيم الذاكرة إلى conversation, episodic, semantic/user, project, working context، مع evidence/confidence/scope.

### Ref
`08_MEMORY_CONTEXT_SPEC.md`

---

## Q8. كيف يتعلم النظام مع الوقت؟

### Decision
التعلم يتم فقط من verified eligible data عبر pipeline: sanitize → evaluate → verify → dataset → train → shadow → canary → promote.

### Ref
`12_EVALUATION_LEARNING_SPEC.md`

---

## Q9. هل User Feedback يدخل التعلم مباشرة؟

### Decision
لا. Feedback signal فقط، وليس حقيقة. الظهور للمستخدم يتحكم فيه الأدمن.

### Ref
`12_EVALUATION_LEARNING_SPEC.md`, `11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q10. كيف تعمل Skills؟

### Decision
Skill هي versioned/importable/composable instruction/workflow/tool-enabled module، وليست tool فقط.

### Ref
`09_SKILL_TOOL_SPEC.md`

---

## Q11. هل نستورد Skills من GitHub؟

### Decision
نعم كمصادر reference/import، لكن تصبح local version بعد scan/validate/review/approve.

### Ref
`09_SKILL_TOOL_SPEC.md`

---

## Q12. كيف نربط GitHub؟

### Decision
GitHub Tool Provider بصلاحيات granular: read, branch, commit, PR, merge. الكتابة تحتاج approval.

### Ref
`09_SKILL_TOOL_SPEC.md`, `10_SECURITY_THREAT_MODEL.md`

---

## Q13. هل المستخدم يضيف API keys الخاصة به؟

### Decision
نعم. User-owned credentials منفصلة عن platform credentials داخل Secret Manager، مع سياسات platform_only/user_only/prefer_user/auto.

### Ref
`03_DOMAIN_MODEL.md`, `05_PROVIDER_PLUGIN_SPEC.md`

---

## Q14. كيف تكون الصلاحيات والباقات؟

### Decision
RBAC + entitlements + policy engine + capability firewall. الباقات تعتمد على task units.

### Ref
`01_PRODUCT_REQUIREMENTS.md`, `11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q15. هل الأدمن يتحكم في كل شيء؟

### Decision
الأدمن يتحكم في السياسات والكتالوجات والباقات، لكنه لا يستطيع تعطيل security invariants.

### Ref
`11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q16. كيف نضمن الأمان ضد prompt injection والأدوات؟

### Decision
LLM ليس security authority. كل action يمر عبر Capability Firewall، مع sandbox/approval/audit.

### Ref
`10_SECURITY_THREAT_MODEL.md`

---

## Q17. كيف نتعامل مع requests كثيرة وبيانات ضخمة؟

### Decision
PostgreSQL durable state + Outbox + Redis Streams + Workers + backpressure + DLQ + idempotency.

### Ref
`02_FINAL_ARCHITECTURE_BASELINE.md`, `14_MASTER_IMPLEMENTATION_PLAN.md`

---

## Q18. هل نبدأ Microservices؟

### Decision
لا. نبدأ Modular Monolith + Workers + Workflow Runtime. Microservices لاحقًا عند الحاجة.

### Ref
`02_FINAL_ARCHITECTURE_BASELINE.md`, `15_MVP_ROADMAP.md`

---

## Q19. كيف نستأنف المشروع بعد انقطاع؟

### Decision
Git committed state هو مصدر الحقيقة. Uncommitted work recovery candidate فقط. لا DONE بدون tests + commit.

### Ref
`13_MASTER_ENGINEERING_PROTOCOL.md`, `17_RESUME_PROMPT.md`

---

## Q20. ماذا لو ظهرت فكرة تطوير أثناء التنفيذ؟

### Decision
تسجل في FUTURE_IMPROVEMENTS.md ولا تنفذ إلا لو blocker. أي تغيير معماري يحتاج ADR.

### Note (appended by T-DOC-012, see MR-003)
The recording target FUTURE_IMPROVEMENTS.md was superseded by D10/D11:
record such ideas in this file (60_DECISION_LOG.md). The rule itself
(record, do not implement unless blocker; ADR for architecture change)
is unchanged.

### Ref
`13_MASTER_ENGINEERING_PROTOCOL.md`, `14_MASTER_IMPLEMENTATION_PLAN.md`

---

## Q21. هل المستخدم يستطيع تحديد النماذج التي يرسل لها النظام؟

### Decision
نعم. يجب دعم تحكم كامل في اختيار النماذج، وليس Auto فقط.

### Accepted Modes

```text
AUTO
TIER
EXPLICIT_MODEL
EXPLICIT_MODELS
AGENT_NODE_MAPPING
```

### Agent Mode Decision
في Agent Mode، يمكن تحديد نموذج مختلف لكل Node أو Role مثل:

```text
planner
coder
reviewer
security_reviewer
judge
finalizer
```

### Constraints
اختيار المستخدم له أولوية على تفضيل Router، لكنه لا يتجاوز:

```text
security
entitlements
model availability
provider/account health
credential boundaries
admin policy
usage/cost limits
```

### Ref
`04_API_CONTRACTS.md`, `06_MODEL_ROUTING_SPEC.md`, `07_EXECUTION_GRAPH_SPEC.md`, `11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q22. هل ممكن النموذج نفسه يكون Agent داخل مزود معين؟

### Decision
نعم. بعض المزودين قد يوفرون نموذجًا أو endpoint يعمل كـAgent أو Assistant أو Code Agent أو Tool-Using Model.

### Architecture Rule
هذا يُمثل كـ:

```text
Provider Agent Capability
أو
Agent-Capable Model
```

وليس بديلًا عن Agent Runtime الأساسي للمنصة.

### Important Distinction

```text
Provider Agent Capability ≠ Platform Agent Runtime
```

المنصة قد تستخدم Provider Agent كـNode داخل Execution Graph أو كخيار Routing، لكنها تظل مسؤولة عن:

```text
authorization
capability firewall
tool approval
tenant isolation
usage accounting
evaluation
audit
final response policy
```

### Ref
`03_DOMAIN_MODEL.md`, `05_PROVIDER_PLUGIN_SPEC.md`, `06_MODEL_ROUTING_SPEC.md`, `07_EXECUTION_GRAPH_SPEC.md`, `09_SKILL_TOOL_SPEC.md`, `10_SECURITY_THREAT_MODEL.md`, `11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q23. هل يمكن إضافة أكثر من Agent من المزودين داخل Agent المنتج نفسه؟

### Decision
نعم. Agent المنتج الأساسي يمكنه orchestration لأكثر من provider-native agent كـsub-agents أو specialist nodes داخل Execution Graph واحد.

### Example

```text
Platform Agent
  ├── Provider A Research Agent
  ├── Provider B Code Agent
  ├── Provider C Review Agent
  └── Platform Judge / Finalizer
```

### Rule
الـProvider Agents تنفذ أعمالًا مفوضة فقط. Agent المنتج يظل هو المتحكم في:

```text
routing
permissions
tool approval
audit
evaluation
usage
fallback
final response
```

### Ref
`21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md`, `07_EXECUTION_GRAPH_SPEC.md`, `06_MODEL_ROUTING_SPEC.md`, `05_PROVIDER_PLUGIN_SPEC.md`, `11_ADMIN_CONTROL_PLANE_SPEC.md`

---

## Q24. ماذا يحدث لو لا يوجد `ai_providers` أو مزودين حقيقيين بعد؟

### Decision
لا يتم تعطيل المشروع ولا يتم اختراع مزودين وهميين. يتم إنشاء بنية Providers فقط مع Templates متنوعة ومعطلة، والمزودين الحقيقيين يضافون لاحقًا.

### Rules

```text
Create scaffold only.
Represent diversity.
Keep templates disabled.
Do not claim execution works.
Do not contaminate Core with provider-specific shortcuts.
```

### Required Diversity

```text
chat/text
reasoning
coding
vision
image generation
audio STT
audio TTS
embeddings
rerank
moderation/safety
multimodal
provider-native agent
```

### Ref
`23_AI_PROVIDERS_SCAFFOLDING_POLICY.md`, `05_PROVIDER_PLUGIN_SPEC.md`, `15_MVP_ROADMAP.md`, `14_MASTER_IMPLEMENTATION_PLAN.md`

---

## Q25. هل كل مزود لازم يكون عنده تسجيل حساب وتحديث جلسة وحسابات وgenerate؟

### Decision
لا. تصميم المزودين يجب أن يكون capability-driven، وليس قالبًا واحدًا مفروضًا على كل المزودين.

### Rule
كل مزود يجب أن يعلن فقط ما يدعمه فعليًا:

```text
auth type
capabilities
modalities
operations
health behavior
error mapping
account/session needs if any
```

### Examples

```text
API-key text provider لا يحتاج تسجيل حساب أو session refresh.
Embeddings-only provider لا يحتاج text generation.
Image-only provider لا يحتاج chat.
Session-based website provider قد يحتاج account/session/cooldown.
Provider-native agent يحتاج provider_agent capability وليس generate عادي فقط.
```

### Ref
`05_PROVIDER_PLUGIN_SPEC.md`, `23_AI_PROVIDERS_SCAFFOLDING_POLICY.md`

---

# PART B — MIGRATION DECISION RECORDS (V2 → V3, appended by T-DOC-012)

These records document the conflict resolutions applied during the V2 → V3
documentation migration (T-DOC-002 … T-DOC-012). They resolve conflicts
between v2 documents and the governance decisions D10/D11
(CURRENT_SESSION_DECISIONS.md). No product/architecture decision was changed.

---

## MR-001. Single mutable state file supersedes legacy multi-file state scheme

### Conflict
v2 13 (§39/§40/§41/§50), v2 14 (§32/§33/§35/§37/§39/§42), v2 15 (state-file
wording), v2 16/20 ("state/handoff files"), and v2 17 (STATE.md / PROGRESS.md /
HANDOFF.md / NEXT_PLAN.md / engineering/state/*) described a multi-file mutable
state scheme.

### Resolution
Per D10/D11: the only mutable project state file is
`docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md`. All legacy
state-file references were explicitly superseded in the v3 successors
(40, 41, 50, 52) and recorded in each successor's traceability ledger and
each v2 banner. The underlying trust rule (state alone is never proof;
Git + filesystem verify facts) is unchanged.

### Applied by
T-DOC-010 (40), T-DOC-011 (41), T-DOC-012 (50/52).

---

## MR-002. v2 17 retired; v2 22 carried as the single resume authority

### Conflict
v2 17 referenced dead `final_docs/` paths and the forbidden legacy state
scheme, while duplicating rules already present in v2 22 and README.

### Resolution
v2 17 RETIRED as a document. Its still-valid, non-duplicated session-discipline
rules were absorbed verbatim into v3 52 §17; everything else was already the
weaker duplicate of v2 22 content. Full absorption accounting is in the v3 52
traceability ledger.

### Applied by
T-DOC-012.

---

## MR-003. Scope-control recording target: FUTURE_IMPROVEMENTS.md → 60_DECISION_LOG.md

### Conflict
v2 13/14/16/20 (and Q20 above) directed out-of-scope improvement ideas to
FUTURE_IMPROVEMENTS.md / ARCHITECTURE_GAPS.md ledger files, which conflict
with the single-state decision D10/D11.

### Resolution
Record such items in this file (60_DECISION_LOG.md); until this file existed,
the state file SESSION NOTES was the interim target (decided in T-DOC-011,
recorded in 41 §31). The rule itself — record, never implement unless
blocking, ADR for architecture change — is unchanged. A note was appended
to Q20 above; the historical Q20 text remains untouched otherwise.

### Applied by
T-DOC-011 (41 §31), T-DOC-012 (this file exists; target now live).

---

## MR-004. Dual build-prompt authority removed

### Conflict
v2 16 (Master Build Prompt) and v2 20 (Ultra Execution Prompt) were two
parallel build prompts with overlapping but non-identical rules — an
authority ambiguity.

### Resolution
v3 50 is the single build-prompt authority: v2 20 is the base (Part I,
Ultra Profile); v2 16 survives as the explicitly subordinate Part II
(Standard Profile). READ FIRST lists repointed to v3 successors. No
invariant, checklist, output format, or stop condition dropped or weakened.

### Applied by
T-DOC-012.

---

## Traceability (V2 → V3) Ledger

```text
v2 18 (all 25 Q&A entries) → Part A CARRIED VERBATIM (Arabic decision text
        untouched), except one clearly-marked appended Note under Q20
        (MR-003 cross-reference; original text preserved).
v2 18 Ref lines            → kept as historical v2 names; resolvable via the
        V2 → V3 Reference Map at the top (no Ref rewritten in place).

Additions (recorded, not silent):
- Authority/status banner + append-only rules.
- Static Resume/Handoff pointer per D10/D11.
- V2 → V3 Reference Map.
- Part B migration decision records MR-001..MR-004.

No Q&A decision was dropped, reworded, or changed.
```
