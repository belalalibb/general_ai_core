# 18 — Q&A Decision Log From Conversation

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
