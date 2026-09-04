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

---

## Part C — Implementation-Phase Decisions (Phase 2, append-only)

## IMPL-001. Implementation stack: Python / FastAPI / Pydantic (ADR-0001 ACCEPTED)

### Question
Which implementation language/stack does the platform use? (Blocked MVP
Phase 1 — Contracts; required an ADR + explicit user approval.)

### Decision (explicit user decision, 2026-08-25)
Python 3.12+ / FastAPI / Pydantic v2. The user selected Alternative B over
the proposed TypeScript/Node stack; ADR-0001 Decision/Reason were rewritten
accordingly and the ADR flipped to ACCEPTED at T-IMPL-003.

Stack summary: Pydantic v2 contracts (runtime validation + JSON Schema
export), FastAPI (`POST /v1/execute`), PostgreSQL via SQLAlchemy 2.x async +
Alembic (+ pgvector), Redis Streams (redis-py), outbox-first workflows
(Temporal Python later via its own ADR), OpenTelemetry + structlog, pytest,
mypy --strict on core/, ruff, import-linter boundary tests.

### Consequences recorded
Admin UI / client-runtime stack deferred to a future ADR (they consume the
language-neutral JSON-Schema contract exports).

### Ref
engineering/adr/ADR-0001-implementation-stack.md (ACCEPTED, append-only from
this point). Applied by T-IMPL-003.

---

## IMPL-002. Persistence toolchain: SQLAlchemy 2.x async + asyncpg + Alembic + pgvector (ADR-0002 ACCEPTED)

### Question
Which persistence toolchain binds core contracts to PostgreSQL (40 §5.1)?
Blocked MVP Phase 3 — PostgreSQL migrations; required an ADR + explicit
operator approval before any DB dependency landed.

### Decision (explicit operator decision, 2026-08-25)
"ADR-0002 = ACCEPTED" — Alternative A as proposed: SQLAlchemy 2.x async +
asyncpg + Alembic + pgvector, ALL confined to infrastructure/; a dedicated
import-linter contract (core must not import sqlalchemy/alembic/asyncpg/
pgvector) landed in the SAME commit as the dependency pins; downgrade paths
mandatory per 40 §8.2; autogenerate output treated as reviewed draft only.

### Consequences recorded
infrastructure/db/ owns alembic env + tables + migrations; first migration
0001_identity_tenancy (hand-written, reversible). Hermetic gates prove
contract/schema parity and offline PostgreSQL DDL compile — no live DB in CI.

### Ref
engineering/adr/ADR-0002-persistence-toolchain.md (ACCEPTED, append-only from
this point). Applied by T-IMPL-015 (implementation part).

---

## IMPL-003. Redis binding: redis-py asyncio under core runtime ports (ADR-0003 ACCEPTED)

### Question
How does the platform bind Redis for queue/lease/cache/rate-limit roles
(40 §5.1, §4) without letting a task framework impose competing semantics?

### Decision (explicit operator decision, 2026-08-25)
"ADR-0003 = ACCEPTED" — Alternative A as proposed: redis-py (>=5) asyncio
client under core-owned ports (Queue via Streams consumer groups, Lease via
SET NX PX + fencing token + Lua compare-and-delete release, Cache
tenant-scoped, RateLimiter fixed-window). DLQ terminal record belongs to
PostgreSQL — Redis is never the source of truth. Import-linter contract
(core must not import redis) landed with the dependency. Task frameworks
(arq/taskiq/celery) rejected: they impose competing job/retry semantics vs
40 §4's outbox/retry-taxonomy/DLQ/leases-with-fencing design.

### Consequences recorded
core/runtime/ defines ports + in-memory fakes (hermetic gates use fakes
only); infrastructure/redis/binding.py is the sole Redis touchpoint.

### Ref
engineering/adr/ADR-0003-redis-binding.md (ACCEPTED, append-only from this
point). Applied by T-IMPL-016 (implementation part).

---

## IMPL-004. Observability: OpenTelemetry API/SDK + structlog, composition-root only (ADR-0004 ACCEPTED)

### Question
How is tracing/logging wired (40 §5.3) without polluting core purity and
without binding to a vendor or to a collector that does not exist yet?

### Decision (explicit operator decision, 2026-08-25)
"ADR-0004 = ACCEPTED" — Alternative A as proposed: opentelemetry-python
API/SDK split + structlog. SDK wiring ONLY at the apps/ composition root;
dev/test default to console/no-op exporters (gates stay hermetic); custom
AdaptiveSampler per 40 §5.3 (normal traffic reduced-rate; error/slow/
high-value/debug-flag full-rate; ParentBased root composition); structlog
JSON pipeline with trace-id correlation and a secret-scrubbing processor at
the pipeline head (20 §5). The OTLP exporter dependency is DEFERRED until a
collector exists. Audit port (T-IMPL-014) untouched — telemetry references
audit ids only. Import-linter contract (core must not import
opentelemetry/structlog) lands with the dependency.

### Consequences recorded
Vendor lock-in avoided (OTel standard per 40 §5.3); tracing of execution and
provider spans is retrofit-free from day one.

### Ref
engineering/adr/ADR-0004-observability-setup.md (ACCEPTED, append-only from
this point). Applied by T-IMPL-017 (implementation part).

---

## IMPL-005. Single verifier reads a green manifest: pytest slices with counters and a floor gate, widened secret scan with bounded per-line exceptions, NOT EVALUATED lines, change-budget guard (R168 §6)

### Question
How does `engineering/verification/check_repo.sh` stay the single verifier
(INV-3) while distinguishing failed from skipped, scanning production code for
secrets, surfacing what was not evaluated, and enforcing the R168 production
change budget — without `|| true`, raised ceilings, or a second script?

### Decision (R168, 2026-09-04)
(a) `engineering/verification/green_manifest.json` is the only authority the
script reads; every other consumer reads and never writes. (b) pytest runs per
declared slice with `-o addopts="" -q` (conflict ledger C-02), each slice under
its own time ceiling; the gate is failed == 0, errors == 0, skipped <= 64,
passed >= 2706 (floor = baseline; ceilings never rise). (c) The secret scan is
widened to `*.py *.js *.html *.css *.env*`; hits are allowed only by declared
`file:line` exceptions (ceiling 5, reasons must not self-match); a tracked
`.env` is FAIL. (d) NOT EVALUATED items print one line each with a reason from
the closed set {missing dependency, credential unavailable, environment
unavailable}; any other reason or count over ceiling is FAIL; the count is a
SUMMARY line, never green. (e) `change_budget.changes_used` must equal the log
length and stay <= 5 per round; log files must live under core/ apps/
infrastructure/.

### Guard
`tests/verification/test_green_manifest_guards.py` executes the real shell
sections in a temporary git skeleton: planted secret → FAIL, tracked `.env` →
FAIL, exception list over ceiling → FAIL, reason outside closed set → FAIL,
budget over ceiling → FAIL, clean tree → PASS; plus the AH partition guard that
every `tests/<pkg>` belongs to exactly one slice.

### Ref
`engineering/verification/green_manifest.md` (human view),
`evidence/r168_conflict_ledger.md` (C-01, C-02, C-03).

---

## IMPL-006. mypy gate scope widened to `core`, `apps.api`, `apps.composition` (R168 §6.7)

### Question
The strict-mypy gate covered only `core`. Should `apps/` enter the gate, and how?

### Decision (R168, 2026-09-04)
Measure first, then widen only to zero-error scopes: `mypy --strict -p apps.api`
(22 files) and `-p apps.composition` (15 files) both measured 0 errors, so
`pyproject.toml [tool.mypy].packages` is now `["core", "apps.api", "apps.composition"]`.
`check_repo.sh` is unchanged — it already calls `python3 -m mypy` and reads the
scope from pyproject. `apps.admin_agent` also measured 0 errors but stays out of
the gate until R169 (mandate §6.7); it is listed in `green_manifest.json
deferred_out_of_gate`. Stub naming corrected in OPERATIONS §10: the dev extra is
`boto3-stubs[s3]` (installs `mypy_boto3_s3`) plus `types-hvac`; `types-boto3` is
a different package and must not be added.

### Guard
`tests/verification/test_green_manifest_guards.py::test_mypy_gate_scope_never_shrinks`
— pyproject scope must be a superset of `green_manifest.json mypy.gate_scope_packages`
and `strict = true` must stay.

### Ref
`evidence/r168/V-02/{fail_first,after_fix,gate_before_after}.txt`, `notes.md`.

---

## IMPL-007. Identity before schema: one admission middleware, one public-path list (R168 D-07/D-10)

### Question
A token-less caller was silently mapped to a composition-owned demo principal
(D-07), and FastAPI validated typed bodies before `_admit` so non-admins saw
schema hints (D-10). Fix both without a route-signature refactor and within
the R168 budget.

### Decision (R168, 2026-09-04)
1. The demo principal is an EXPLICIT dev opt-in: `DEV_DEMO_PRINCIPAL=1`
   (literal "1", in-memory profile only). Default = auth only in BOTH
   profiles; `GET /v1/admin/system` reports `identity_mode`.
2. `apps.composition.runtime.PUBLIC_PATHS` is the ONE list of token-less
   paths (`/healthz`, `/v1/auth/{register,verify,login,logout}`), passed to
   `create_app(public_paths=…)`. `apps/api/app.py` keeps `_AUTH_ENTRY_PATHS`
   public by construction — a composition may add, never remove.
3. One `@app.middleware("http")` (registered only when `auth` is composed)
   runs BEFORE body validation on every `/v1/` path: anonymous ⇒ the constant
   401; `/v1/admin/*` non-admin ⇒ 403; then the route's own `_principal` /
   `_admit` still runs (defence in depth, zero signature changes).
4. `/v1/auth/logout` is public because its frozen contract is "always 204,
   never a token-validity oracle"; `/v1/auth/session` is identity-bearing.

### Guards
`tests/composition/test_d07_tokenless_401.py` (route enumeration: every
served non-public path ⇒ 401), `tests/composition/test_d10_admin_gate_order.py`
(all admin operations: 403 non-admin, 401 anonymous, admin reaches 422),
`test_cli_entrypoint` (describe reports `demo_principal` false by default).

### Ref
`evidence/r168/D-07/`, `evidence/r168/D-10/`; budget round A 2/5.

---

## IMPL-008. A body reference is admitted like a path reference (R168 D-08)

### Question
`POST /v1/execute` accepted any `project_id` and ignored it — a foreign
tenant's project, an unknown UUID or `not-a-uuid` all ran (silent acceptance
of a foreign reference).

### Decision (R168, 2026-09-04)
1. `project_id` is resolved in the CALLER's tenant before replay, persistence
   or composition; a reference that does not resolve leaves zero state.
2. Foreign, unknown and malformed references all receive the ONE 404 body the
   projects surface gives for an unknown id (`unknown_project`, now exported
   from `apps/api/workspaces.py`) — byte-identical, no oracle between the
   three (20 §6). Malformed is UNKNOWN, not a 422 field error.
3. The store is ONE object (`project_store`) shared by `/v1/projects` and
   `/v1/execute`; the field stays in `ExecuteRequest`; no attachment
   semantics are introduced (nothing downstream consumes the reference).

### Guards
`tests/api/test_d08_execute_project_reference.py` (foreign / unknown /
malformed ⇒ byte-identical 404; owned passes and equals the no-field path).

### Ref
`evidence/r168/D-08/`; budget round A 4/5.

## IMPL-009. An in-band HTTP-200 refusal is a FAILED provider call (R168 D-01)

### Question
`genspark_llm` returns HTTP 200 with the gateway's plan-refusal sentence as the
assistant message and `usage = {0,0,0}`. The adapter booked it as a completion:
run SUCCEEDED, 1.0 unit settled, refusal text served as the answer, no
provider error recorded, no failover.

### Decision (R168, 2026-09-04)
1. Detection lives in the ADAPTER (`providers/real/genspark_llm/adapter.py`),
   the only layer that knows this gateway's wording. Core stays provider-agnostic.
2. A 200 is a refusal iff BOTH signals hold: reported usage present with
   `total_tokens == 0 and completion_tokens == 0` (no inference) AND the content
   carries a plan-refusal marker. One signal alone is never a refusal (a real
   completion quoting the wording consumed tokens; zero-usage plain text is not
   a refusal).
3. Classification: `quota_exceeded`, `retryable=False`,
   `provider_code="plan_refusal_200"`, generic `safe_message`; output/usage
   empty — the refusal text never crosses the boundary. `content_rejected` was
   rejected because it is request-indicting and forbids failover in the frozen
   core (conflict ledger C-05).
4. Downstream is unchanged and already correct: route-indicting ⇒ failover to
   the next candidate, else node FAILED; usage `fail` ⇒ 0 units; evaluation
   `JudgeFailure` ⇒ unverified; API `403 entitlement_exceeded`.

### Guards
`tests/providers/test_d01_refusal_contract.py` (6: failed call, no leak, quoted
wording stays success, zero usage alone stays success, run FAILED + 0 units,
failover to next provider); `tests/certification/test_r167a_routing_matrix.py::
test_shape_200_plan_refusal_is_quota_exceeded_r168` (replaces the R167-A row that
asserted the defect).

### Ref
`evidence/r168/D-01/`; budget round A unchanged 4/5 (providers/ only).

## IMPL-010. Account-complete routes and per-account credentials (R168 D-03/D-04)

### Question
`RoutingDecision` named a provider+model but never an account; `credential_refs`
is `Mapping[provider_id, str]`, so a second credential for the same provider
overwrote the first and no failover between accounts of ONE provider existed
(D-03). No emitter named the account a call used (D-04). 30 §10 defines
`CredentialPolicy` and `AccountPool`; 11 §2 defines Provider/Account Selection —
both had zero call sites.

### Decision (R168, 2026-09-04)
1. `RoutingRequest.credential_policy: CredentialPolicy | None` — the 30 §10
   policy travels WITH the request; `None` means the caller expressed no
   preference and the selector applies AUTO. Additive (INV-2).
2. `ResourceSelector.complete(decision, *, policy, rate_limits, bindings)` turns
   a model-level decision into an account-complete one: every pooled candidate
   becomes one candidate per eligible account (LRU order, all seven
   `eligible_accounts` filters), pool-less candidates pass through unchanged,
   candidates with no eligible account become `ExclusionRecord`s, and an empty
   route raises `NoEligibleAccount`. `select()` is unchanged.
3. `ExecutionService(account_credentials=..., audit=...)` — two optional seams.
   The account's credential_ref wins over the provider-level ref; the
   `_validate_route` precheck accepts either. Existing composition passes
   neither and behaves exactly as before.
4. `PROVIDER_ACCOUNT_USED` is emitted once per ATTEMPT for pooled candidates
   only, with `account_id, provider_id, model_id, node_key, attempt, succeeded,
   error_category`; never a secret, never a credential_ref value. It is not an
   admin change, so it carries no `admin_change`.
5. Wiring `complete()`/the two seams into `apps/composition/runtime.py` is
   deferred: OUT OF SCOPE (R168): budget — scheduled for R169. Until then the
   HTTP surface is unchanged and D-03/D-04 are closed at the contract level.

### Guards
`tests/routing/test_d03_d04_two_account_failover.py` (7 tests: two accounts of
ONE provider, first INVALID_CREDENTIAL → second succeeds; policy filter;
audit rows; pool-less pass-through; NoEligibleAccount; no secret in audit).

### Ref
`evidence/r168/D-03-04/`; `evidence/credential_binding_boundary.md` (R168
re-evaluation); budget round B 3/5.

## IMPL-011. Denials are audited in the actor's tenant (R168 D-11)

### Question
`PERMISSION_DENIED` and `CROSS_TENANT_ACCESS_DENIED` are must-audit events
(20 §9) with zero emitters: after 30+ denials the admin audit read showed only
`login`. Which denials, written where, readable by whom — without turning the
audit row into an enumeration oracle (20 §6)?

### Decision (R168, 2026-09-04)
1. ONE emitter in `apps/api/app.py` (`_audit_denied`) over the SAME
   `admin.audit` log the admin surface reads. Absent admin seam ⇒ no-op
   (nothing to write into; no new seam invented).
2. `PERMISSION_DENIED` is written when the admission middleware refuses a
   NON-ADMIN session on `/v1/admin/*` (details: `method`, `path`,
   `reason=admin_required`). Anonymous 401s are NOT audited: there is no
   principal, hence no tenant to attribute to (recorded; R169 may add a
   system-tenant sink).
3. `CROSS_TENANT_ACCESS_DENIED` is written when `project_id` on
   `/v1/execute` does not resolve in the caller's tenant. Foreign, unknown and
   malformed references are recorded IDENTICALLY (`resource=project`,
   `reference` as given) because the gate cannot tell them apart by design
   (absent == foreign, D-08) — the row must not know more than the response.
4. Rows are written in the ACTOR's tenant with `actor_id`; nothing is written
   in any other tenant (the target is unknowable; an owner-side row would be
   an oracle). The tenant's admin reads them on `GET /v1/admin/audit`.
5. HTTP bodies are byte-identical to pre-fix (asserted). Details never carry a
   request body, a credential, or a target-tenant fact.
6. A PLATFORM-wide read across tenants is NOT added: `AuditLogPort` forbids
   cross-tenant reads by design (20 §6) and the codebase has no platform-admin
   identity distinct from `is_admin`. OUT OF SCOPE (R168): design —
   scheduled for R169 (needs a contract decision, not a patch).

### Guards
`tests/composition/test_d11_denials_are_audited.py` (4 tests over the
composed runtime: 403 + row; foreign 404 + row, owner tenant empty;
unknown/malformed recorded; admin reads over HTTP).

### Ref
`evidence/r168/D-11/`; budget round B 4/5 (`apps/api/app.py` +37/−0).

## IMPL-012. Groq normaliser: `detail`-only 400 "model not allowed" (R168 D-02)

### Question
The OpenAI-compatible proxy fronting Groq rejects a disallowed model with HTTP
400 `{"detail": "Model '<x>' is not allowed…"}` (FastAPI shape, no
`error.code`). The Groq normaliser read only `error.code`/`error.param` and
booked `bad_request` — request-indicting, so the execution walk never failed
over to a provider that has the model (ledger D-02, S2).

### Decision (R168, 2026-09-04)
1. Structural detection `_is_model_not_allowed(response)` in
   `providers/real/groq/adapter.py` (same predicate the genspark_llm adapter
   already uses): 400 + `detail` str starting "Model " and containing "is not
   allowed" ⇒ `model_unavailable`, `retryable=False`,
   `provider_code="model_not_allowed"`, fixed safe message. Candidate-indicting
   (30 §14): the walk fails over; the request is not indicted.
2. The detail text (echoes the requested model name and the allowlist) never
   crosses the boundary — only the boolean verdict does.
3. Any OTHER `detail`-only 400 stays `bad_request`. No captured evidence says an
   unknown FastAPI detail is non-indicting; widening would be a guess (INV-4).
   Revisit only with a captured shape.
4. The branch sits BEFORE the generic 400/413/422 branch and AFTER the
   `error.code`-driven ones; every existing `error.code` mapping is unchanged
   (guarded).
5. Budget: `providers/` is outside the counted set ⇒ round B stays 4/5.

### Guards
`tests/providers/test_d02_groq_detail_only_400.py` (4);
`tests/certification/test_r167a_routing_matrix.py::test_shape_unknown_model_400_detail_only_is_model_unavailable`
(MAP row `…|model_unavailable|retryable=False|D-02 FIXED R168`).

### Ref
`evidence/r168/D-02/`; `evidence/error_classification_map.md` row updated.

## IMPL-013 — R169 §3 per-round change-budget roots (verifier extension, additive)

### Decision
`green_manifest.json` gains `change_budget.round_r169` (ceiling 6, roots
`core/ apps/ ui/`, items A2/A3/A5/A6). `check_repo.sh` §6 iterates
`("round_a","round_b","round_r169")`, skips absent rounds, and reads each
round's own `counts_production_code_under` (falling back to the global roots).

### Why
1. R169 mandate counts `ui/` and NOT `infrastructure/`; rounds A/B counted
   `infrastructure/` and not `ui/`. Rewriting the existing rounds' roots would
   change how their logged entries are judged (INV-6). A separate block keeps
   both truths verifiable.
2. Existing round_a/round_b evaluation is byte-identical: their blocks carry no
   `counts_production_code_under`, so the fallback equals the previous roots.
3. `if r not in cb: continue` makes the loop forward-compatible for future
   rounds without another verifier edit.

### Guards
`tests/verification/test_green_manifest_guards.py::test_change_budget_round_r169_consistent`
(ceiling, roots, used == len(log), item set, every logged file exists under its
roots). Existing `test_change_budget_consistent` unchanged.

### Ref
`evidence/r169_conflict_ledger.md` C-01; `evidence/r169_state_ledger.md`.

## IMPL-014 — R169 A2: write capability as a separate primitive, refusals as data

### Decision
Introduce `core/tools/source_writer.py::SourceWriter` as a new primitive that is
NOT registered anywhere by the core package. The admin agent keeps exactly its
R0/R1/R2 registry; the writer will only be composed into the separate
development-agent root (A3).

### Why
1. INV-7: widening the admin registry would change an audited permission class;
   a new primitive held by a new composition root does not.
2. INV-2: `overwrite`/`delete` refuse without a matching `expected_sha256`; every
   refusal is a typed `SourceWriteRefusal` (12 codes) returned as tool data, so
   the ToolExecutor still emits exactly one `TOOL_CALL` audit event and the
   gate/firewall path is untouched.
3. Symmetry: the jail (`_admit`) and denylist are the reader's, so the set of
   unwritable paths is a superset of the unreadable ones.

### Guards
`tests/tools/test_source_writer.py` (42): jail escapes (abs, `..`, symlink
file/dir), denylist, byte/op caps, preconditions, executor audit for admitted /
handler-refused / invalid / gate-refused calls.

### Ref
`docs/r169/CAPABILITY_MAP.md`; `evidence/r169/A2/`; budget `round_r169` 1/6.

## IMPL-015 — R169 A3/A4: a separate development-agent composition root

### Decision
Compose the development agent in a NEW root, `apps/agent_dev/surface.py`
(`build_dev_surface`), that reuses the core tool fabric (`ToolRegistry`,
`ToolCallGate`, `ToolExecutor`) and the R169 source engines. The admin agent
(`apps/admin_agent`) is not imported by it and not modified.

### Why
1. INV-7: the admin registry and its R0/R1/R2 classes are audited surfaces; new
   write power is composed separately instead of widening them.
2. INV-2: every refusal on the dev path is data — gate refusals as
   `ToolCallRecord(status="refused", gate_decision.reason=...)`, engine refusals
   as `ok=False` payloads with a machine-readable `code`.
3. INV-5: `source.write` carries `ApprovalRequirement.BEFORE_ACTION`; without an
   approved request the gate refuses before the handler runs.

### Guards
`tests/agent_dev/test_dev_surface.py` (28) and
`tests/agent_dev/test_admin_boundary.py` (9): admin name/class snapshots,
disjointness of dev/admin names, closed admin registry, unchanged
`AgentToolSurface` fields.

### Ref
`docs/r169/CAPABILITY_MAP.md`; `evidence/r169/A3/`; budget `round_r169` 2/6.

## IMPL-016 — R169 A5: GitHub connectivity as typed tool calls behind a RepoBinding

### Decision
Model repository access as a typed `RepoBinding` (`core/contracts/repo_binding.py`:
tenant, https remote, branch, local root, `allowed_modes`, opaque `credential_ref`)
and expose `git.fetch/status/commit/publish` only as tools on the dev surface
(`apps/agent_dev/git_tools.py::GitToolset`) executed through the existing
`ToolExecutor`. The network side is a `GitTransportPort` protocol; no live
implementation is shipped in R169.

### Why
1. INV-3: the binding never carries a token. `SecretManagerPort.resolve` is called
   inside the handler at the last moment; the token reaches only the transport and
   is asserted absent from `ToolCallRecord`, audit and trace.
2. Per-binding jail: `jail_path` normalises lexically and refuses
   `PATH_OUTSIDE_BINDING`, so a path valid under binding X is refused under
   binding Y even for the same tenant.
3. INV-2: every failure is `GitRefusal(code=GitRefusalCode.*)`; a protected-branch
   push becomes `REMOTE_REJECTED_PROTECTED_BRANCH` with `suggested_mode=pull_request`
   instead of an exception.
4. Audit set is closed (13 `AuditEventType`s, guarded). The publish mode is recorded
   by enriching the executor's single `TOOL_CALL` event via `ModeRecordingAudit`
   (contextvar), keeping one event per attempt.
5. INV-7: `apps/admin_agent` is untouched; `git.*` permissions are granted only via
   `dev_tenant_policy(git=True)` on the separately composed dev surface.

### Guards
`tests/agent_dev/test_git_tools.py` (38, fake transport) and
`tests/agent_dev/test_contracts_r169.py` (15).

### Ref
`docs/r169/CAPABILITY_MAP.md` L67–85; `evidence/r169/A5/`; budget `round_r169` 4/6
(796b0dd git_tools.py, 833a6ce surface.py).

## IMPL-017 — PublishMode read endpoint lives on a separately composed dev router

### Decision
`GET /v1/dev/bindings/{binding_id}/publish-modes` is served by
`apps/agent_dev/http.py::create_dev_router(bindings, *, resolve)` — a new
`APIRouter` that is **not** mounted in `apps/api/app.py` in R169. The response is the
contract type `core.contracts.publish_mode.PublishModesResponse`; `direct_push` is
listed but non-selectable (`direct_push_not_enabled_for_binding`) unless the binding's
`allowed_modes` opts in. Unknown, foreign-tenant and malformed binding ids return one
identical 404 `validation_error` body.

### Why
1. INV-1: the option list, labels and refusal reasons are defined once in contracts and
   consumed verbatim by the router; a future UI reads the same shape.
2. INV-7: no admin-agent registry or permission class widened; the router is a new
   surface composed from `RepoBindingRegistry` and the existing `resolve` seam used by
   `apps/api/admin.py`.
3. `ErrorCode` is a closed 11-value set without `not_found`; the admin router's
   `validation_error`+404 convention is reused, and collapsing absent/foreign/malformed
   ids prevents binding enumeration across tenants.
4. Budget: mounting the router in the composition root would be production change #6
   and was left to the operator (closure report, open decisions).

### Guards
`tests/agent_dev/test_publish_modes_http.py` (10): 401 before lookup, 404 shape parity,
contract parse, enum order, default/opt-in/restricted bindings, no secret or path leakage.

### Ref
`docs/r169/CAPABILITY_MAP.md` L67–85; `evidence/r169/A6/`; budget `round_r169` 5/6
(4ae4e09 `apps/agent_dev/http.py`).

## IMPL-018 — Hardened path denylist is a composition-time policy, not a primitive default (R172 C1)

### Decision
`core/tools/denied_paths.py` owns `DENIED_PATH_PATTERNS` (superset of
`SourceReader.DEFAULT_DENIED_PATTERNS`) and `is_denied_path`. `apps/agent_dev/surface.py::
build_dev_surface` constructs its default `SourceReader`/`SourceWriter` with that list. The
primitives keep their 13-glob defaults; injected readers/writers are not overridden.

### Why
1. The R170 probe (`evidence/r170/denylist_probe.txt`) showed 19/27 EXPECT_DENIED paths
   readable through the composed surface — the gate's own manifest included.
2. Policy belongs at the composition root (INV-1: one list, consumed verbatim by reader and
   writer); the primitives stay reusable and their 42+ existing tests stay untouched.
3. Directive-mandated `*accounts*`/`*password*` globs collide with tracked sources
   (`core/providers/accounts.py`, `infrastructure/security/password.py`). Kept as mandated
   (fail-closed) and documented; narrowing requires an explicit allow-list change, not a
   weaker glob.
4. `.ENV*`/`.Env*` case variants are enumerated as a patch; normalisation is C4.

### Guards
`tests/tools/test_denied_paths_r172.py` (61 passed, 1 xfailed `acco33unts.txt`): consumes
the probe table; required-pattern matrix; surface reader/writer carry the hardened list;
bare primitives unchanged.

### Ref
`evidence/r172/C1/`; budget `round_r172` 1/8.

## IMPL-019 — Binding persistence is an optional, fail-closed store behind the registry (R172 C2)

### Decision
`RepoBindingRegistry` gains an optional `store: BindingStorePort` (`load()`/`save()`). The
reference implementation `core/tools/binding_store.py::JsonBindingStore` writes a versioned
`BindingStoreDocument` (contract in `core/contracts/binding_store.py`) via same-directory temp →
flush → fsync → `os.replace`, dir `0o700`, file `0o600`, and refuses any path inside an
`outside_of` working tree. Load never raises into the tool path: every bad record is skipped and
reported in `BindingStoreLoadReport.skipped`; `source_state` names the outcome.

### Why
1. Discovery D1 (no binding persistence) — a process restart lost every binding, so the dev agent
   could never be "bound" in production.
2. Partial resurrection is worse than none: a half-parsed store silently drops tenant scoping or
   `allowed_modes`. Therefore whole-document failures load nothing (`malformed`/`unreadable`) and
   per-record failures are indexed and reported (`partial`), then purged on the next save.
3. INV-3: only `credential_ref` is serialised; a byte-grep test proves the token never hits disk.
4. Optional parameter keeps the 38 existing git-tool tests byte-identical (INV-6).

### Guards
`tests/agent_dev/test_binding_store_r172.py` (14): dir/file modes, interrupted `os.replace` leaves
prior bytes, round-trip equality, protected-tree refusal, missing/malformed/partial/version/
unreadable states, INV-3 byte-grep, restart survival, tenant scoping after restart, no partial
resurrection.

### Ref
`evidence/r172/C2/`; budget `round_r172` 2/8. Composition wiring (default path + `outside_of`)
deliberately NOT done — owner decision, see notes.md "Open".

## IMPL-020 — Remote trust is explicit, per-(tenant, remote), and checked before any credential resolve (R172 C3)

### Decision
`GitToolset` gains an optional `trust: RemoteTrustPort`. When present, `git.fetch` and every mode of
`git.publish` call `_require_trust(binding)` immediately after the binding lookup and *before*
`_token()`. An untrusted remote returns `GitRefusal(code="remote_not_trusted")` as data; the secret
manager is never consulted. `git.status` and `git.commit` are unaffected. Trust exists only as a
`RemoteTrustGrant` (`trusted: StrictBool`, named `granted_by`, `granted_at`, optional revocation)
keyed by `(tenant_id, remote_url.strip())`; the reference registry/store live in
`core/tools/remote_trust.py` on the shared `core/tools/atomic_json.py` durability primitives.

### Why
1. Discovery D2: nothing distinguished a remote the owner bound deliberately from one an attacker
   swapped in; the token flowed to whatever URL the binding carried.
2. Ordering is the security property: a refusal *after* `resolve` would already have pulled the
   token into process memory and the audit path. Tests count `resolve` calls (must be 0).
3. `StrictBool` + fail-closed load: a `"true"` string, a corrupt store or a registry exception all
   collapse to "untrusted" — never to an exception in the tool path and never to trust.
4. Conservative normalisation (whitespace only): widening equivalence classes widens trust.
5. Optional field + `trust=None` default keeps the 53 R169 git/contract tests byte-identical.

### Guards
`tests/agent_dev/test_remote_trust_r172.py` (19): contract strictness, default-untrusted,
per-tenant/per-remote, revocation, conservative normalisation, store modes + fail-closed
partial/malformed, untrusted fetch/publish(pr, direct_push, dry_run) refused with `resolve_calls == 0`,
status/commit untouched, trusted path resolves once, revoke takes effect immediately, foreign-tenant
grant does not trust, trace code, `trust=None` == R169.

### Ref
`evidence/r172/C3/`; budget `round_r172` 3/8. Composition wiring and the operator "grant" act are
owner decisions — see notes.md "Open".

## IMPL-021 — Source writes are atomic; the deny check matches a normalised spelling too (R172 C4)

### Decision
`SourceWriter` writes through `_atomic_write` (same-directory temp → flush → fsync → `os.replace`),
so an interrupted write leaves the target byte-identical, leaves no temp file, and does not consume
an op; the caller sees the existing `io_error` refusal and its next CAS write against the original
digest succeeds. `SourceReader` gains module-level `normalize_deny_path` / `is_denied`; both reader
and writer route `_denied` through `is_denied`, which matches the raw relative path first and then
the normalised one (NFKC, invisible/zero-width/combining code points removed, `:stream` suffix cut,
trailing dots/spaces removed, casefold). `DEFAULT_DENIED_PATTERNS` is unchanged; C1's explicit case
variants stay as belt and braces.

### Why
1. Discovery D4: `write_bytes` truncates before it writes — a crash mid-write left a half file whose
   digest matched nothing, so the agent's own CAS precondition would then refuse every repair.
2. Discovery D5: the denylist was pure `fnmatch` on the raw spelling; `.ENV`, `.e<ZWJ>nv`,
   `.env::$DATA`, `.env.` and `.env ` all read a credential file. Enumerating spellings (C1) cannot
   close that class; normalising the checked string does.
3. Raw-then-normalised matching can only ADD refusals, never remove one, so no green test can flip.
4. Module functions rather than methods keep both public-surface pin tests (INV-6) untouched, and
   let the writer share the exact same predicate (what cannot be read cannot be written).
5. Cutting at the first `:` may over-deny a POSIX name like `.env:notes` — accepted; fail-closed.

### Guards
`tests/tools/test_source_hardening_r172.py` (39): normaliser table + idempotence; `is_denied`
raw/normalised; reader refuses/hides 8 variants under the DEFAULT list; writer refuses the same 8
with `path_denied` and creates nothing; interrupted overwrite and create; mode preservation; umask;
no temp files on success. Pre-existing reader/writer/denylist suites (122+1) and `tests/admin_agent`
(130) unmodified and green.

### Ref
`evidence/r172/C4/`; budget `round_r172` 4/8 (one commit, two files; manifest guard enforces one log row per item).

## IMPL-022 — Dev-surface writes get a pre-apply checkpoint with typed restore (R172 C5)

### Decision
`core/tools/checkpoint.py` adds `CheckpointStore` (content-addressed blobs `objects/<sha256>` +
`checkpoints.json` index, built on `atomic_json`: directory 0o700, files 0o600, temp+fsync+`os.replace`,
refuses a location inside the protected working tree) and `CheckpointManager` (`begin` → snapshot the
pre-apply bytes, missing file ⇒ `pre_sha256 = None`; `seal(post_sha256)`; `mark_partial`; `restore`).
`checkpointed_write_handler(writer, manager)` wraps `SourceWriter` for the dev surface and
`build_dev_surface(checkpoints=...)` selects it; `DevAgentSurface.checkpoints` exposes the manager.
Restore semantics: current hash `== pre` ⇒ `noop`; `== post` (and state not `partial`) ⇒ `reverted`
(deletes the file when `pre` is `None`); anything else ⇒ `checkpoint_conflict`, file untouched. A blob
that is missing or fails hash verification ⇒ `object_store_corrupt` (reason names the "object store"),
file untouched. Contracts live in `core/contracts/checkpoint.py` (INV-1).

### Why
1. Discovery D5: the dev surface applied `source.write` with no undo — a wrong OVERWRITE/DELETE was
   only recoverable if the tree happened to be under git and clean.
2. Fail closed on the snapshot side: the write is NOT attempted when the snapshot or index write fails
   (typed `io_error` data). The only `begin` failure that falls through is `path_refused`, and the
   manager uses the WRITER's denylist (`denied_patterns=writer.denied_patterns`) so admission cannot
   diverge — the writer then emits its own `path_denied` refusal and no snapshot/blob/`checkpoint_id`
   exists.
3. A writer refusal after the snapshot (e.g. `precondition_mismatch`) leaves exactly one `partial`
   checkpoint whose restore is a `noop` — the file was never touched, and the record proves it.
4. `checkpoints=None` keeps the plain `source_write_handler`; the result key set is byte-identical to
   R169 (`test_dev_surface.py` untouched and green).
5. The manager is NOT wired into `apps/composition/runtime.py` — deciding where the store directory
   lives per deployment is an owner decision (recorded in §9 open items); the seam is the parameter.

### Guards
`tests/agent_dev/test_checkpoint_r172.py` (16): store permissions + inside-tree refusal; begin refuses
`.env` / `../outside`; create→seal→restore deletes; overwrite→restore reverts; drift ⇒ conflict, file
untouched; precondition_mismatch ⇒ one partial, restore noop; path_denied ⇒ no checkpoint; absent
manager ⇒ exact key set; tampered blob ⇒ `object_store_corrupt`; malformed index ⇒ `list()==[]`,
`checkpoint_unknown`; corrupt record skipped ⇒ `partial`; simulated restart (new store+manager over the
same directory) restores. Suites `tests/agent_dev tests/tools tests/verification` 374 passed 1 xfailed;
`tests/admin_agent` 130. ruff + mypy clean. Fail-first: `ModuleNotFoundError core.contracts.checkpoint`
at `73766ab`.

### Ref
`evidence/r172/C5/`; budget `round_r172` 5/8 (one row, one production file `apps/agent_dev/surface.py`).
