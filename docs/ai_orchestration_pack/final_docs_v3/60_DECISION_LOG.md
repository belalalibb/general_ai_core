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

## IMPL-023 — Approval ↔ payload binding for write-class dev-surface calls, opt-in (R172 C6)

### Decision
- NEW `core/tools/payload_binding.py`: canonical JSON form (sorted keys, `(",", ":")` separators,
  UTF-8, `allow_nan=False`, floats and non-JSON types refused via `NonCanonicalPayload`),
  `payload_hash` (sha256 hex), `check_payload_binding` (canonicalise → missing hash → constant-time
  compare).
- NEW `core/contracts/approval_binding.py`: `ApprovalBindingRefusalCode`
  (`approval_hash_required`, `approval_payload_mismatch`, `payload_not_canonicalisable`) and
  `ApprovalBindingRefusal` (typed data, never an exception).
- `apps/agent_dev/surface.py`: `payload_binding: bool = False` flag; `call(...,
  approved_payload_hash=None)`; when the flag is on and the permission is in
  `PAYLOAD_BOUND_PERMISSIONS` = {`source.write`, `git.commit`, `git.publish`} and
  `approval_state == "approved"`, the check runs BEFORE the gate/executor; refusal is an
  executor-shaped `ToolCallRecord(status="refused", error=TOOL_APPROVAL_REQUIRED,
  error_detail=<refusal JSON>)` plus one `TOOL_CALL` audit event. `ErrorCode` not widened.

### Owner decision — boundary
- `core/tools/gate.py` is NOT modified; the gate remains non-binding (string approval state only),
  pinned by `test_gate_admit_has_no_payload_parameter_pin`.
- Binding is opt-in, default off, and NOT enabled in the production composition. The
  approval-issuing side (UI/admin) is frozen under INV-7 this round and does not yet carry the
  payload hash; enabling binding without it would refuse every approved write. Tracked as an open
  item in `docs/r172/BACKEND_STATE_OF_TRUTH.md`.

### Why
- HARVEST row 6: an approval issued for payload A must not admit payload B (swap attack).
- Enforcing in the surface layer keeps the gate contract and its 23 approved call sites untouched.
- Floats are refused rather than canonicalised (no cross-language stable float form).
- Read-class calls are never bound; unapproved writes still fall through to the gate unchanged.
- Default `False` keeps every existing test and caller green (INV-6).

### Guards
- 17 tests in `tests/agent_dev/test_payload_binding_r172.py` (canonical form ×4, verdicts, gate
  pin, default non-binding, scope, missing hash, mismatch, correct hash, key order, float,
  non-write unaffected, unapproved fall-through, git.commit/publish bound, detail is data).
- Slice `tests/agent_dev tests/tools tests/verification` 391 passed / 1 xfailed; `tests/admin_agent`
  130 passed; ruff / mypy --strict / import-linter (13 kept) clean.
- Fail-first captured at cc04872 (ImportError `PAYLOAD_BOUND_PERMISSIONS`).

### Ref
- `evidence/r172/C6/{fail_first.txt,after_fix.txt,notes.md}`; budget row 6/8 in `green_manifest.json`.

## IMPL-024 — Mount the R169 A6 `/v1/dev` router behind an opt-in `dev_bindings` seam (R172 C7)

### Decision
- `apps.api.app.create_app(..., dev_bindings: RepoBindingRegistry | None = None)`. When a
  registry is passed, `create_dev_router(dev_bindings, resolve=_principal)` is included and
  `GET /v1/dev/bindings/{binding_id}/publish-modes` resolves (200, four `PublishModeOption`s,
  `default=pull_request`). Unknown, malformed and foreign-tenant binding ids all return the SAME
  typed 404 (`validation_error`, `details={"binding_id": ...}`) — no existence oracle.
- `dev.publish_modes` added to the closed `CAPABILITY_IDS` (16 → 17); the catalog row derives
  `available` from `dev_bindings is not None`, so the catalog never claims a route that is not
  mounted.
- The router import is performed at composition time inside the `if dev_bindings is not None:`
  block: `apps.agent_dev.http → apps.api.errors → apps.api.__init__ → apps.api.app` is a cycle,
  and a module-level import in `app.py` breaks the http-first import order (finding recorded;
  both orders verified).

### Owner decision — boundary
- Flag, NOT always-on. Always-on would need a registry the production composition does not build;
  an empty always-on registry would advertise a capability that can never resolve — a hidden claim.
- `apps/composition/runtime.py` does NOT pass `dev_bindings=` — production stays inert; pinned by
  `test_default_runtime_profile_does_not_compose_the_dev_seam`. Wiring is tracked as an open item in
  `docs/r172/BACKEND_STATE_OF_TRUTH.md`.
- `ui/**` and `apps/admin_agent/**` untouched (diffs verified empty); UI route guard (`tests/ui`,
  14 passed) did not trip.

### Why
- Discovery D3: the R169 A6 router existed but was never mounted — a dead surface the CAPABILITY_MAP
  had to describe as inert. Mounting it through an explicit seam closes the gap without widening
  the default runtime.
- Honesty rule (INV-4): a capability row must reflect the composed app, hence `available` derives
  from the same seam that performs the mount.
- One typed 404 for unknown/malformed/foreign ids keeps tenant boundaries opaque (INV-2/INV-3).

### Guards
- 11 tests in `tests/api/test_dev_router_mount_r172.py` (closed-id membership; composed: 200 + four
  modes, route table via `app.openapi()` + dispatch check, capability available, unknown/malformed/
  foreign → same 404, own binding beside foreign; absent: route 404, capability inert, runtime does
  not compose).
- `tests/api` 473 passed; `tests/ui` 14; slice `tests/agent_dev tests/tools tests/verification`
  391 passed / 1 xfailed; `tests/admin_agent` 130; ruff / ruff format / mypy (195 files) /
  import-linter (13 kept) clean.
- Fail-first captured at bde7276: 9 failed / 2 passed.
- FastAPI 0.141 / Starlette 1.6.0 finding: included routers appear in `app.routes` as
  `_IncludedRouter` without `.path`; route-table assertions go through `app.openapi()["paths"]`.

### Ref
- `evidence/r172/C7/{fail_first.txt,after_fix.txt,notes.md}`; `docs/r169/CAPABILITY_MAP.md`
  updated (17 ids); budget row 7/8 in `green_manifest.json`.

## IMPL-025 — REST-only GitHub transport + env-gated live transport proof (R172 C8)

### Decision
- `apps/agent_dev/github_transport.py` (NEW): `GitHubRestTransport` implements the R169
  `GitTransportPort` over the GitHub Git Data / Pulls REST API with httpx. No subprocess, no
  shell, no hooks, no local `.git`. `commit()` stages a content-addressed in-memory snapshot of
  the jailed paths (no token, no network); `push()` uploads blobs → tree → commit and creates or
  non-force-moves `refs/heads/<branch>`; `open_pull_request()` returns the PR `html_url`.
  `parse_github_remote` admits only `https://github.com/{owner}/{repo}[.git][/]`.
- Error mapping feeds the existing `GitToolset` refusal codes unchanged: HTTP 422 whose message
  names a pull-request / protected-branch rule → `ProtectedBranchRejected`
  (→ `remote_rejected_protected_branch` + `suggested_mode="pull_request"`); other 4xx →
  `RemoteRejected`; network / malformed / missing ref → `TransportError`; nothing staged →
  `NothingToCommit`. `GitRefusalCode` and `ErrorCode` NOT widened.
- The token arrives per call, rides only the `Authorization` header of that call, is never stored
  on the instance and never appears in results, exceptions or `repr`.
- Live proof lives in `tests_live/r172/test_live_transport.py` — OUTSIDE `pyproject::testpaths`
  and outside every `green_manifest.json` slice, so the hermetic verifier never collects it and the
  skip budget is untouched. Every live test skips unless `GROQ_API_KEY_n` / `GITHUB_TOKEN` +
  `R172_LIVE_GITHUB_REPO` are in the environment; secrets are read from `os.environ` only and
  routed through `InMemorySecretManager` credential_refs; the suite refuses any remote naming
  `general_ai_core`.

### Owner decision — boundary
- REST over the `git` CLI: the CLI would violate the R172 no-subprocess rule and needs a per-binding
  checkout the sandbox does not have. Trade-off: no local history/merge; `status.head` is the
  staging-snapshot id until `push()` succeeds.
- `GitHubRestTransport` is NOT wired into `apps/composition/runtime.py`; no production composition
  builds a `GitToolset` yet (same posture as C2 store, C3 trust registry, C5 checkpoints, C6
  payload binding, C7 dev seam). Tracked in `docs/r172/BACKEND_STATE_OF_TRUTH.md`.
- Live runs create real branches / PRs on the throwaway repository only
  (`belalalibb/r172-live-transport-throwaway-48b263`, main protected PR-only, enforce_admins).

### Why
- "live git transport NOT EVALUATED" had been open since R169 (only a test fake behind the port);
  a real transport plus a real run is the only way to close it without over-claiming.
- INV-3 (opaque credential): header-only token; `test_credential_never_in_artifacts` + hermetic
  `repr`/exception assertions.
- INV-5 (human authority): DIRECT_PUSH refusals and the protected-branch mapping were proven live —
  the remote head stayed at the auto-init commit throughout.

### Guards
- 25 hermetic tests in `tests/agent_dev/test_github_transport_r172.py` (remote parsing, fetch,
  status/commit locality, path jail, content addressing, push object flow, protected 422,
  non-fast-forward, PR open, unknown head, no-subprocess source scan).
- 13 live tests passed on 2026-09-04 (`evidence/r172/live_transport.txt`): real PR URL; DIRECT_PUSH
  not allowed → `publish_mode_not_allowed`; DIRECT_PUSH onto protected `main` →
  `remote_rejected_protected_branch` + `suggested_mode=pull_request`; untrusted binding →
  `remote_not_trusted` with `secrets.resolve` called 0 times; Groq: all four supplied keys are
  `organization_restricted` → typed `invalid_credential` / non-retryable (no completion obtainable
  — recorded, not claimed); bogus key → `invalid_credential`; `timeout_ms=1` → `timeout`/retryable;
  429 not observed; adapter performs no retry itself (finding — retries belong to ExecutionService).
- Slice 391 → 416 passed / 1 xfailed; api 473; ui 14; admin_agent 130; providers 312 passed /
  9 skipped (unchanged); ruff / ruff format / mypy (195 + module) / import-linter (13 kept) clean.
- Fail-first at 6d09e56: `ModuleNotFoundError: apps.agent_dev.github_transport`.

### Findings recorded
- GitHub signals a protected-branch refusal on the Git Data API as HTTP 422
  "Changes must be made through a pull request." (not 403).
- `GroqAdapter`'s pooled client is bound to the loop that created it; live harness must run
  `generate()`+`aclose()` in one `asyncio.run` (first attempt: "Event loop is closed", test-side).

### Ref
- `evidence/r172/C8/{fail_first.txt,after_fix.txt,notes.md}`, `evidence/r172/live_transport.txt`;
  budget row 8/8 in `green_manifest.json`.

## R177-DEC-01 — Precedence for Memory / Soul / Knowledge paths: CONFIRMED, no new model (R177 A05/A06)

### Status
CONFIRMED (verification entry, not a new design). Append-only; supersedes nothing.

### Decision
- The operator-stated precedence "Core policy > operator approval > application configuration, most-restrictive-wins" is the
  EXISTING semantics: `core/security/firewall.py` (deny-by-default, approved-but-ungranted stays DENY), `core/tools/gate.py`
  ("both authorities must consent", tightening only), `core/contracts/tools.py DEFAULT_APPROVAL_REQUIREMENT = ALWAYS`,
  `core/contracts/security.py approval_state: Literal["approved"] | None`.
- Memory / personalization / knowledge paths (`core/memory/*`, `core/context/composer.py`, `core/learning/lifecycle.py`) are governed
  by their OWN closed gates — sensitivity (HIGH refused unless the *application* sets `allow_high_sensitivity`; never caller-settable),
  scope priority (13 §4), confidence, the secret boundary guard, tenant-scoped keys, and the learning gates — not by the firewall
  vocabulary. No divergence from most-restrictive-wins was found; NO second precedence model exists or is introduced.
- "Soul" is operator vocabulary for durable, tenant-scoped personalization expressed through existing memory types + preferences +
  composer. It is NOT a component, package, contract term, or claim of emotion/consciousness. Any literalisation requires approval.
- "Teacher" is the evaluation/review ROLE (ModelJudgePort + PromotionGate.admin_approved), not an owner of the learning lifecycle.

### Ref
- `evidence/r177/A05_approval/approval_policy_map.md`, `evidence/r177/A06_vocabulary/vocabulary_mapping.md`,
  `docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md` §4–§5.

## R177-DEFER-01 — Ideas assessed in R177 and NOT adopted in this round (append-only register; 41 §31 / D10-D11)

### Status
RECORDED. Each item is either DEFERRED (may return as an approved R177-FIX-nn) or REJECTED-AS-PARALLEL (would duplicate an existing
primitive). None is implemented. Legacy files ARCHITECTURE_GAPS.md / FUTURE_IMPROVEMENTS.md are NOT used (gate-forbidden).

### Register
| idea | ruling | reason / where it lives instead |
|---|---|---|
| `core/soul/` package or `SoulProfile` contract | REJECTED-AS-PARALLEL | duplicates MemoryItem + preferences + composer (R177-DEC-01) |
| `MemoryType` enum in `core/contracts/memory.py` | DEFERRED (needs approval — new closed set) | convention scope×source pinned by test is the minimum (R177-FIX-05) |
| Separate "knowledge base" store | REJECTED-AS-PARALLEL | GOLD MemoryItems + ask_learned/learned_keys already are the knowledge store |
| `TeacherService` owning learning | REJECTED-AS-PARALLEL | inverts 22's design; Teacher = ModelJudgePort binding + selection policy (R177-FIX-09) |
| Relationship/episodic graph subsystem | REJECTED-AS-PARALLEL | MemoryItem `source="episode"` + `expires_at` suffices |
| tree-sitter / graph DB inside core/ | REJECTED (layering) | import-linter; any parser lives in providers/ or apps/composition/ (R177-FIX-06) |
| New ErrorCode / VerificationLevel members (e.g. "CANDIDATE") | REJECTED | closed sets; follow FIX-05 precedent (reuse code + details.reason) |
| Widening gate secret-scan patterns | DEFERRED (governance change; separate approval + failing-first test) | see assessment §2; not conflated with FIX-06 |
| New `not_evaluated` items | REJECTED | ceiling 2/2 full; report UNVERIFIED in round docs instead |
| Learning observability unified view | DEFERRED | data exists across admin routes (G-A07-5) |
| Application-scoped credentials (F-R176-10) | DEFERRED (DEC-03 open) | separate round if authorized |
| UI changes for any of the above | DEFERRED | §15 backend-first; ui/ frozen (r173) |

### Ref
- `docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md` §10–§12; `evidence/r177_state_ledger.md`.

### R177-DEC-06 — change-budget unit for round_r177 = one approved FIX item (2026-09-08)
- Context: DEC-05 approved `round_r177` with ceiling 12 while the assessment §12 estimated ≈20 production files across FIX-02..11.
  Per-file counting would exhaust the ceiling mid-round without any item exceeding its approved scope.
- Decision: one `log` entry per approved R177-FIX item; the entry lists every production file it touched (`file` joined by ` + `,
  `files` = count) so file-level transparency is preserved. Precedent: `round_r172` entry C4 (two files, one entry).
  The ceiling (12) and the item list are unchanged; the gate still checks `changes_used == len(log)`, roots, and scheduled items.
- Evidence: `engineering/verification/green_manifest.json` `change_budget.round_r177.note`; `evidence/r177_state_ledger.md` row B-08.

### R177-DEC-07 — capability_proposal is a backend-only admin change kind this round (2026-09-09)
- Context: R177-FIX-03 (approved) adds `AdminAction.CAPABILITY_PROPOSAL` (area TOOLS, 21 §4 "approval rules"). The admin console
  (`ui/admin/app.js` `ADMIN_ACTIONS`) is pinned to equal the enum, but `ui/` is a frozen tree in R177 (R177-DEFER-01: "UI changes
  DEFERRED — §15 backend-first"). Editing the UI would break the freeze; leaving the pin unchanged would fail the gate.
- Decision: the console does NOT offer `capability_proposal`; the operator path is the existing API (`POST /v1/admin/changes` →
  validate → preview → publish) and the admin agent. The UI pin (`tests/admin_agent/test_aa2_admin_agent.py`) now asserts
  `offered == enum − {"capability_proposal"}` — a bounded, named exception that cannot grow silently. Rulings are evidence:
  rollback of a published proposal record is refused (`RollbackUnavailable` → 409, existing mapping); reversal = a new record.
  Also recorded: the shipped runtime now passes `FINAL_ACTIVE_ADMIN_AREAS` (the T-IMPL-068 recorded intent), so SKILLS/TOOLS
  kinds are reachable; absent seams still fail validation with a named reason.
- Follow-up (DEFERRED, ui/ thaw required): add the kind to the console select and a §7 sheet form.
- Evidence: `evidence/r177_state_ledger.md` row B-03; `evidence/r177/B03_fix03/`.

### R178-ACK — R178 closed and merged (2026-09-11)
- R178 (`main` f5cbe48c via PR #14): evaluation duplicate contract (FIX-01), immutable promotion evidence (DEC-01), external-evidence subject/receipt (P01), tenant-policy custody with revocations + legacy hold (DEC-03, migration 0020). Acknowledged here as the baseline R179 measured against; no R178 decision is reopened.

### R179-DEC-01 — durability correction = composition seam only (2026-09-12)
- Context: 4.4 measured with a real SIGKILL (`evidence/r179/durability_measured_before.json`): memory and conversations died with the process; `execute`+`conversation_id` answered 500 in the durable profile (FK to a `conversations` table the runtime never wrote).
- Decision: bind the EXISTING Postgres repositories (migrations 0002/0007) via `apps/composition/memory.py` in the `DATABASE_URL` branch only; in-memory profile byte-identical. No schema, route, dependency or contract change. Re-measured: P1 memory 1→1, P2 conversation 200/200/200 (`durability_measured.json`). F-R179-01/-03 CLOSED.
- DEC-B (audit/usage durability) stays DEFERRED and visible: P3 audit 1→0, P4 usage 5.0→2.0 (F-R179-04); `docs/OPERATIONS.md` §13 states it.

### R179-DEC-02 — one authorized shelf widening: `learning.custody_governance` (22 → 23) (2026-09-12)
- The DEC-03 governance routes were mounted with no shelf row. The row is DERIVED from the same seam variables that mount them (admin + memory + custody port + audit); the pin moved 22→23 with written justification; the shelf coverage test now fails on any mounted `/v1/admin` family without a specific owning row.

### R179-DEC-03 — action discovery is derived from `ACTION_AREA`; payload-schema half stays DEC-A design-only (2026-09-12)
- `GET /v1/admin/capabilities/actions` is a pure function of `core.contracts.admin.ACTION_AREA` + `FINAL_ACTIVE_ADMIN_AREAS` (one owner per action, no hand-maintained names, drift impossible by construction). Separate route so the V7 row shape `{id,state,evidence}` and the frozen UI/agent consumers stay untouched (route-surface pins 73→74, conscious). The payload-schema half is NOT exposed (imperative checks in `core/admin/service.py` remain the authority; DEC-A).

### R179-DEC-04 — old writers are stopped by procedure, not by schema (F-R179-05) (2026-09-12)
- Live rolling pair: a pre-0020 binary restarted on a 0020 database lands custody rows under the legacy hold (201) while the new binary is refused (404). A schema-level guard needs a new migration (forbidden this round). Recorded as OPEN in the decision queue; `docs/OPERATIONS.md` §8.1 procedure is the only mitigation today.

### R179-DEC-05 — operator visibility contract (2026-09-12)
- `GET /v1/admin/learning/custody/holds` is read-only (not audited); `release-legacy-hold` answers `outcome ∈ {released, already_released, no_hold}` derived from durable state before/after + audit history and refuses (409) on contradiction; intake distinguishes a per-row custody refusal (refused row, batch continues, 201) from a durable-layer fault (batch stops, 503 retryable, landed rows + `not_attempted` reported). Conscious pin updates in R178 tests are named in `evidence/r179_state_ledger.md`.

### R179-DEC-06 — change-budget unit for round_r179 = one production FILE; ceiling 6 → 8 → 9 (2026-09-12)
- Declared 6; elastic 8 when 4.5 triggered; absolute 9 with the 4.7 design note committed (60d09d95) BEFORE the 4.7 production commit (ccfa9a7d). Final 9/9 distinct files; a file edited twice is ONE change with both edits described in its log summary.

### R179-DEC-07 — rulings round: Q1 audit durable, usage blocked by MEASURED F-R179-06 → Q6 (2026-09-12)
- Operator ruling Q1 (DEC-B) executed with the 4.5 seam pattern. Audit binds durably (P3 1→1→1 across SIGKILL). Binding the durable usage ledger made every `/v1/execute` fail (`usage_ledger.execution_id` NOT NULL FK → `executions.id`; the execution service reserves BEFORE the row exists; tool calls never have one). Decision: usage stays process-local in BOTH profiles until the operator rules Q6 (reserve-after-row vs. schema change); the durable adapter is composed, not bound. Audit/usage screens still do not ship.

### R179-DEC-08 — Q3 resolved by CAPABILITY: SECURITY grader activated, promote 201/409 over HTTP (2026-09-12)
- `GraderType.SECURITY` joins `FINAL_ACTIVE_GRADER_TYPES` with a real implementing grader (`SecretMaterialGrader`: the 13 §7 credential sanitizer over the graded output — non-vacuous, never echoes matches). Reaches the pipeline through the new injectable `output_graders` step (default empty; MVP posture byte-identical). `POST …/evaluate` returns `evaluation_id`; `POST …/promote` answers 201 when a GOLD item is created; 409 stays the governed refusal. The promote gate condition is UNCHANGED (no relaxation). Live: promote 201, GOLD survives restart. Supersedes the F-R179-02 "policy-gated by design" posture of R179-DEC-02/-03.

### R179-DEC-09 — Q4: ONE declared payload field-rule source (DEC-A approved) (2026-09-12)
- `core.admin.service.PAYLOAD_FIELD_RULES` (closed `FieldRule` rows per every `AdminAction`) is read by BOTH the validator (`field_rule_problem` runs first; inline presence/shape checks removed) and the shelf (`admin_actions_json` publishes `fields`). Semantic checks stay imperative after the declared rules hold. Supersedes the "payload half stays imperative" clause of R179-DEC-03.

### R179-DEC-10 — Q2: structural guard against stale writers, NO trigger (supersedes R179-DEC-04) (2026-09-12)
- Migration 0021 adds `learning_sample_custody.custody_schema_generation SMALLINT NOT NULL` (backfill 1, server default dropped); the metadata supplies 2 client-side. An old writer's INSERT omits the column and the database refuses it (measured live: 500 / `NotNullViolationError`, zero rows). No trigger, no function, no policy logic in DDL; the column records the writer's metadata generation. The stop-old-writers procedure (OPERATIONS §8.1) remains as hygiene.

### R179-DEC-11 — rulings budget: ceiling 8 → 10 with history; merge by MERGE COMMIT (2026-09-12)
- `round_r179_rulings` declared 8 before the first production commit; raised to 10 with the Q3 design note committed before the Q3 production commit (Q3 = 4 files by the designed activation path). Final 10/10 distinct production files; diff == log table in `R179_READINESS.md` Part 4. Operator instruction: merge with a merge commit (no squash) so per-item SHAs stay resolvable; the gate is re-run on the merge commit.

### R180-DEC-01 — Q5 thaw: the console reads admin verbs from discovery; the hand-list is gone (2026-09-13)
- Per R179 ruling Q5, `ui/` and `apps/admin_agent/` are thawed for exactly this item. `ui/admin/app.js` populates the change-form verb set from `GET /v1/admin/capabilities/actions` (R179 4.3 / Q4): rows of ACTIVE areas, server order, per-action `fields` rendered as a hint naming `field_rules`; a refused read renders the unified error and offers no verb. The read runs in the Changes surface loader after sign-in (F-R180-01, measured live). `ADMIN_ACTIONS` is deleted; the R177-DEC-07 "console does not offer `capability_proposal`" exception ends with the freeze that caused it — the server decides what is offered. N0 arithmetic binding held: `/v1/` count stays 73 (one comment-only occurrence gave way to the served literal). F-R179-07 closed in the same thaw: `AgentToolSurface.usage: UsageAccountingPort`. Budget `round_r180` 1/1 (`apps/admin_agent/tools.py`); `ui/` is outside the counted roots.

### R180-DEC-02 — operator rulings ratified: admin_agent thaw scope is EXACTLY the port annotation; ui/ thaw + budget model confirmed; Q6/Q7/Provider deferred (2026-09-13)
- Ruling 1 RATIFIED: the ONLY edit under `apps/admin_agent/` in R180 is `tools.py` `AgentToolSurface.usage: UsageAccountingPort` (+ its import), required by Q5 / F-R179-07. Measured against base 5b78f467: `apps/admin_agent/` diff = `tools.py` +6/−2, no other file. This thaw does NOT generalize to any other file under `apps/admin_agent/`; the tree stays frozen otherwise. Pinned by `tests/ui/test_q5_thaw_action_discovery_r180.py::TestR180RulingScope` (tools.py references the port exactly twice; no other admin_agent module carries an R180 marker).
- Ruling 2 RATIFIED: `ui/` is thawed for R180 under the existing budget model — `ui/` stays OUTSIDE the counted production roots (`core/ apps/ infrastructure/`) and is judged by its own tests (`tests/ui`, `tests/admin_agent` UI pins) and render/live evidence (`evidence/r180/q5_live_dom_probe.txt`). `round_r180` stays 1/1.
- Merge posture: merge COMMIT, no squash (as R179-DEC-11), only once the round's own exit conditions hold (gate PASS on the PR head, diff == log, frozen trees zero-diff, findings dispositioned).
- Q6 (durable usage contract), Q7 and the Provider slice remain DEFERRED; no reordering.

### R181-DEC-01 — backend closure before UI: Q6 closed by option (b); Q7 / Provider slice recorded UNDEFINED; no UI work (2026-09-13)
- Operator directive: close every backend/core carry-over item that is DEFINED and ACTIONABLE in the repository before the UI phase; invent no scope; do not touch `ui/`.
- Q6 (F-R179-06) CLOSED by option (b): migration `0022_usage_ledger_key.py` drops ONLY `fk_usage_ledger_execution_id_executions`; `execution_id` stays NOT NULL + UNIQUE (one ledger row per execution/call id). Option (a) (reserve after the `executions` row) was rejected because it would change the 03 §7 refuse-before-work ordering AND still leave tool-call reservations (`call_id`, never an executions row) unbindable. Runtime binds the already-composed `DurableUsageAccounting` in the `DATABASE_URL` profile (the one-name flip documented at the R179 decision point); in-memory profile byte-identical. Budget `round_r181_backend_closure` 3/3 (declared BEFORE the production commit). Measured live on PostgreSQL 17.11: P4 `used` 6.0 → 8.0 across a real SIGKILL (`evidence/r181/durability_measured_7a41caff.json`); deploy truth head 0022 forward/backward through the real tool; FK transcript `evidence/r181/q6_live_fk_verification_7a41caff.txt` (orphan insert OK, duplicate refused, NULL refused, downgrade fails closed on orphan rows, restores the FK when empty).
- F-R175-04 CLOSED (ops-only, outside the counted roots): `check_repo.sh` step 1b fails closed with the install path when `python3` lacks pytest/mypy/ruff, instead of reporting misleading collection errors; pinned by `tests/engineering/test_check_repo_interpreter_guard_r181.py`.
- Manifest `deferred_out_of_gate` (mypy `apps.admin_agent`) CLOSED: admitted to the `--strict` gate after re-measuring 0 errors / 7 files (215 files clean); the tree stays frozen (type-checking reads, never edits). Guard-test exact-set pin consciously grown.
- Q7 and the Provider slice: searched every ledger, handoff, decision, readiness, manifest and doc — NO repository definition exists beyond the R180-DEC-02 echo (the `## Q7` in the v2/v3 QA logs is an unrelated 2025 memory question). Recorded UNDEFINED / DEFERRED; no speculative work created. Defining them is an operator act.
- D-11 residue (`CREDENTIAL_CREATED/REVOKED` — no route exists; `PROVIDER_ACCOUNT_USED` — `ResourceSelector.complete()` has no consumer and every candidate composes with `account_id=None`, so an emitter would be a no-op) and in-process engineering tickets/grants (no table exists) are FEATURE SCOPE, not defects: recorded, not worked.
- UI phase NOT started. Merge posture unchanged: merge COMMIT, no squash, gate re-run on the merge commit — on operator instruction only.

### R182-DEC-01 — UI round opened by DECLARATION on the post-R181 base; R181 merged by merge commit; ceiling 0 on frozen trees (2026-09-14)
- PR #20 (R181) was verified open / mergeable / clean with no branch protection, 0 status checks, 0 check-runs, 0 workflows ("no CI / no required status checks; the canonical gate is the verification") and merged by MERGE COMMIT → `743e203f` (parents `ed61f7e6`, `05e12882`). Gate re-run in a fresh clone of the merge commit: PASS 3632/0/0/64, mypy 215 files; gateway 194. Evidence: `evidence/r182/gate_merge_743e203f.txt`, `evidence/r182/gateway_merge_743e203f.txt` (tracked). PRs #13/#15/#16/#17 untouched.
- R182 is a READINESS round, not implementation: branch `genspark_ai_developer_r182` from post-R181 `main`; `ui/` thawed for the coming R182-IMPL; `core/ apps/ infrastructure/` FROZEN, ceiling 0 comments included. `round_r182` declared in `green_manifest.json` in the existing format (ceiling 0 / changes_used 0 / empty log) with a note that `ui/` lies outside `counts_production_code_under`, so UI work is governed by `ui_static_check` (exact-file equality, `v1_count_ceiling_N0` = 73 with zero headroom, `exception_count_ceiling` = 0) and not by the change budget.
- Governance frame MEASURED, not path-asserted (`evidence/r182/governance_frame_743e203f.txt`): `pytest.gate.min_passed` 3504 NOT ratcheted (no authorization); `not_evaluated` ceiling 2 / 2 items; secret-scan 5/5 exceptions; inherited transport policy holds — `EventSource` / `WebSocket` prohibited in `ui/admin`, single-fetch posture; 0 `package.json`, playwright ABSENT (`ModuleNotFoundError`; no install performed).
- Served contract PROBED live on the merge commit (`evidence/r182/served_contract_probe_743e203f.txt`, 44 probes, 83 OpenAPI paths) and turned into the authoritative BACKED / INERT / MISSING / DECORATIVE-ONLY inventory in `docs/ai_orchestration_pack/R182_READINESS.md` §4 (BACKED 24, INERT 3, MISSING 6, DECORATIVE 4). `DeltaEvent` is never emitted and `execute.token_streaming` is unavailable — any typing/streaming animation would be a fabricated state and is forbidden.
- ADR-0013 (UI front-end stack and serving posture) created at `PROPOSED — AWAITING OPERATOR DECISION`; nothing installed, no stack chosen. Operating default: vanilla static under the existing `/app` mount at `ui/app/command/` (zero production change); any new mount or React/three dependency requires an operator decision (D-1 stack, D-3 serving) because both mounts live in frozen `apps/composition/`.
- APEX-UI inspected live and on GitHub (`evidence/r182/apex_reference_inspection.txt`): MIT code, Apex name/branding excluded; components classified reuse-as-pattern / rebuild / discard; `ROSTER` of 18 agents and `idle|thinking|speaking` orb states are DECORATIVE-ONLY and are not to be copied; `CREDITS.md` placeholder attributions leave provenance UNRESOLVED (F-R182-04) → rebuild or discard, never vendor.
- F-R182-01: `infrastructure/db/tables.py:140-141` doc still says "UNIQUE + FK" after migration 0022 dropped the FK — DEFERRED (frozen tree, ceiling 0), owner R183. Q7 / Provider slice remain UNDEFINED → R183.
- App Factory boundary: NOT READY — 5 missing (4 factory contracts + API-key management route); UI readiness: no — 2 blockers (D-1, D-3).
- First red test for R182-IMPL: `tests/ui/test_command_center_topology_r182.py::test_capability_nodes_derive_from_served_contract_not_a_roster`; first milestone M1 "Honest topology". Implementation contract: `docs/ai_orchestration_pack/R182_HANDOFF.md` (20 items). No UI code written in R182.

### R182-DEC-02 — operator rulings D-1..D-6 accepted; R182-IMPL opened on the post-R182 merge; M1 "Honest topology" delivered with browser proof (2026-09-14)
- Governing text (operator, verbatim summary): D-1 ADR-0013 ACCEPTED on **Alternative C** — vanilla ES modules, no framework/build/runtime dependency; the hand-drawn layer is optional and enters M1 only with a clean collapse under `prefers-reduced-motion`/unsupported contexts; B/D rejected today. D-3 **(b)** — `ui/app/command/` on the existing `/app` mount, ceiling stays 0, no ceiling raise, no R183 deferral. D-2 as written in R182_HANDOFF §2/§14 (the §9 D-2 line is interpretive): same place, guarded as an independent unit (`ui_command_static_check`: declared files, `command.js` ceiling = the count measured at first GREEN of M1 and down only, exceptions 0, one `fetch` inside `api()`, `EventSource`/`WebSocket`/`XMLHttpRequest`/`axios` banned, no quoted `CAPABILITY_IDS`). D-4 yes inside R182-IMPL only — `pyproject [dev]` + an actual run removes NE #1; if the environment cannot run it the dependency is withdrawn, never left beside a "missing dependency" line; a third NE line refused either way. D-5 yes in M1 — two titles + three pins in one commit; tree title `QEVION Control Plane — Command Center`. D-6 ratchet only at the round's gate of record, measured number + ledger line — not in readiness. Also confirmed: F-R182-06 disposition; new rule — evidence cites FILE:LINE, never the matched value (OPERATIONS §14).
- Merge: PR #21 (R182 readiness) merged by MERGE COMMIT (no squash) → `main` **12e83444** (parents 743e203f + 7414684b); no CI / no required status checks — the canonical gate is the verification; fresh-clone gate on the merge commit PASS 3632/0/0/64, gateway 194 (`evidence/r182/gate_merge_12e83444.txt`, `gateway_merge_12e83444.txt`). R182-IMPL continues on the SAME round id `round_r182` (ceiling 0/0) from the new main, branch `genspark_ai_developer_r182_impl`.
- Order as constraint: FIRST act = the red test file `tests/ui/test_command_center_topology_r182.py::test_capability_nodes_derive_from_served_contract_not_a_roster` → RED commit `92baaa21` (`FileNotFoundError`, no UI file existed). Then ADR-0013 status flipped to ACCEPTED by pasting the operator's text (alternatives untouched); `ui_command_static_check` declared with `v1_count_ceiling_command_js: null` (fails closed) BEFORE any Command Center file; branding in one commit (`a3e6ad0e`); M1 GREEN (`f41d6ee8`).
- M1 delivered: `ui/app/command/{index.html,command.js,command.css}` served at `/app/command/` with ZERO production change (`git diff origin/main..HEAD -- core apps infrastructure` empty). Nodes = the records of `GET /v1/admin/capabilities` (iterated, keyed by `capability.id`; no roster; no quoted ids); node vocabulary = `CapabilityState` ∪ loud `UNKNOWN`; Core vocabulary = HANDOFF §8 set derived from `ExecutionStatus` + reachability; scope badge = server `scope` verbatim; keyboard mirror list, aria, reduced-motion collapse; no canvas/WebGL layer in M1; no fabricated states, no token typing, no waveform. `command.js` `/v1/` count measured **12** at first GREEN → ceiling set once (down only).
- D-4 executed: `playwright>=1.45` declared dev-only; Chromium + system libs installed; `tests/ui/test_command_center_browser_r182.py` starts `python3 -m apps.main` (in-memory, `ADMIN_EMAILS`), reads the console verification token from the subprocess stdout (tmp, never evidence), signs in through the UI form and proves served 23 = rendered graph 23 = mirror list 23, states equal the served records, core `idle`, `scope: process`, 0 console errors, every request same-origin to a served route (`evidence/r182_impl/browser_proof_m1.json`, `command_center_m1.png`). The proof found one real defect (`display:grid` beat `[hidden]`) — fixed in `command.css`. NOT-EVALUATED #1 REMOVED (2 → 1; ceiling 2 untouched; pin updated to 1; no third line, no exception added).
- Budget: `round_r182` 0/0 unchanged; `ui/admin/app.js` = 73 = N0 unchanged; secret-scan exceptions 5/5 unchanged; `min_passed` NOT ratcheted here (D-6: only at the round's gate of record with the measured number).
- Verdict update effective at the first IMPL commit (R182_READINESS §12): QEVION UI readiness **yes — blockers 0**; AI Apps Factory **NOT READY — missing 5** (Factory contract definition is an operator decision). Token rotation deferred by the operator to after R182-IMPL.

### R182-DEC-03 — R182-IMPL closed at M2 by operator merge authorization; PR #22 merged by merge commit; `min_passed` 3666 (2026-09-14)
- Operator text: "PR #22 merge is authorized … apply the repository's existing recorded merge procedure and exit conditions exactly as defined … Do not invent or assume M3." Procedure applied in the recorded order: gate of record on the PR head `f1d289c2` in a fresh clone (`env -i`) → PASS 3666/0/0/64, gateway 194 (`evidence/r182_impl/gate_head_f1d289c2.txt`); D-6 ratchet `pytest.gate.min_passed` 3658 → **3666** by the measured number with ledger line (`evidence/r182_impl_state_ledger.md` row 33); exit conditions (gate PASS on the PR head, diff == log, frozen trees zero-diff, findings dispositioned F-R182I-01..05) verified (row 34).
- Merge: PR #22 verified open / mergeable / clean, branch protection 404, 0 statuses, 0 check-runs, 0 workflows ("no CI / no required status checks; the canonical gate is the verification") → MERGE COMMIT, no squash → `main` **f5b89cea** (parents 12e83444 + 1c8525dc). Gate + gateway re-run on the merge commit: PASS 3666/0/0/64 (floor holds exactly), not_evaluated=1, `round_r182=0/0`; gateway 194 (`evidence/r182_impl/gate_merge_f5b89cea.txt`, `gateway_merge_f5b89cea.txt`).
- On `main` now: QEVION Command Center `ui/app/command/` (M1 honest topology + M2 execution graph / progress / fetch-read SSE of the five emitted types / conversation with verification counts), browser-proven against `python3 -m apps.main`; `ui_command_static_check` guard (files exact, `command.js` `/v1/` ceiling 12 = fully spent, exceptions 0); ADR-0013 ACCEPTED on Alternative C; NOT-EVALUATED 2 → 1; branding `QEVION Control Plane`. Frozen `core/ apps/ infrastructure/`: **0 production files across the entire R182 round**.
- Not done, by the records: HANDOFF §10 BACKED rows 4, 12-14, 17-23, 26-registration, 28, 33 and INERT rows 16, 27 un-rendered; MISSING rows (13-verification, 15/Q7, 24 App Factory, 25 API keys, 26-delivery) unrepresented; F-R182-01 and Q7 / Provider slice → R183. **No M3 exists in any record** — the next milestone is an operator declaration (row set, first red test, gate condition). Token rotation: operator-deferred to after R182-IMPL, which is now closed.

### R183-DEC-01 — R183 opened by DECLARATION as a carry-forward closure round; F-R182-01 closed; Q7 / Provider / MISSING areas remain UNDEFINED (2026-09-15)
- Operator text: "Declare R183 now, using only scope that is already supported by existing records. Do not invent new architecture, product scope, milestones, requirements, or operator decisions … Stop only when the next step requires a genuinely new operator decision." Base: `main` **e23abb23** (= MERGE COMMIT of PR #24, records-only; R182 formally CLOSED, R182-DEC-03). Branch `genspark_ai_developer_r183` from `genspark_ai_developer_r182_close3` (b25000d1) so the PR #24 post-merge gate evidence (`evidence/r182_impl/gate_merge_e23abb23.txt` PASS 3666/0/0/64, gateway 194) reaches `main` with this round, per the R182-IMPL ledger row 43 rule.
- Inventory fixed from the records only (`evidence/r183_state_ledger.md` row 2): DEFINED + ACTIONABLE = **F-R182-01** alone. UNDEFINED (no contract, acceptance or files anywhere in the repository — re-searched): Q7, Provider slice / provider verification (R182_READINESS row 13), App Factory (row 24), API keys (row 25), webhook delivery (row 26). The R182 pointers "→ R183" named the earliest hosting round, not a definition (R181-DEC-01: "Defining them is an operator act"). Nothing speculative created.
- Budget `round_r183` declared BEFORE the production commit: ceiling **1** (one production FILE, doc-only), `items` = F-R182-01, thaw = `infrastructure/db/tables.py` docstring only; FROZEN `core/ apps/ ui/ core/tools/gate.py PROJECT_EXECUTION_STATE.md final_docs_v3` (this log append-only). Spent **1/1**: RED test `tests/db/test_tables_usage_ledger_doc_r183.py` (3 failed at 5c7e42ab) → docstring `UNIQUE + FK (RESTRICT …)` → `NOT NULL + UNIQUE; NOT a foreign key (migration 0022, R181 Q6, F-R179-06)` with the reserve-before-work / tool `call_id` reason (+6/-2) → GREEN; `diff == log`. F-R182-01 CLOSED in `evidence/r182_findings_ledger.md`.
- Records: `docs/ai_orchestration_pack/R183_HANDOFF.md`, `evidence/r183_state_ledger.md`, `evidence/r183_findings_ledger.md` (no new finding), `evidence/r183/`. `min_passed` 3666 not ratcheted here — D-6: only at the gate of record by the measured number with a ledger line.
- Operator-only decisions left open (R183_HANDOFF §7): merge of the R183 PR; definition or explicit out-of-scope closure of Q7 / Provider / App Factory / API keys / webhook delivery; baseline re-capture (F-R182-03); merged-branch deletion and stale PRs #13/#15/#16/#17; GitHub token rotation (overdue).

### R183-DEC-02 — R183 closed: PR #25 merged by merge commit; hygiene executed; Q7 stops at a contract boundary (2026-09-15)
- Operator text: "Proceed with all accepted R183 recommendations in sequence … Treat the accepted recommendations as explicit operator authorization … For the UNDEFINED set, do not invent contracts. Execute the recommended Q7 path only when its existing contract/records are sufficient; otherwise record the precise decision boundary."
- Merge: PR #25 verified open / mergeable / clean, branch protection 404, 0 statuses / check-runs / workflows → MERGE COMMIT `main` **1dd55934** (parents `e23abb23`, `5b9e87f6`), no squash. Fresh-clone gate on the merge commit: PASS **3669/0/0/64** (floor 3669 from the R183 gate of record, D-6), not_evaluated 1, `round_r183` **1/1**, gateway 194 (`evidence/r183/gate_merge_1dd55934.txt`, `gateway_merge_1dd55934.txt`). Frozen trees zero-diff; the only production diff of the round is `infrastructure/db/tables.py` +6/-2 (docstring).
- Hygiene (D-R183-4): 21 remote branches deleted only after a per-branch GitHub `compare` confirmed full containment in `main`; 5 unmerged branches kept; stale PRs #13/#15/#16/#17 closed unmerged with comments (`evidence/r183/hygiene_actions.txt`). Repository now: `main` + 5 unmerged branches, 0 open PRs.
- Q7 (D-R183-2, recommended path): NOT executable from the records. `VerificationLevel.RAW` describes a record that exists; the evaluation list returns `[]` for "no evaluations" and for unknown/foreign executions by recorded design (20 §6 anti-enumeration, `core/evaluation/ports.py`). A distinguishing served field needs a new contract AND a ruling on whether 20 §6 applies to the ADMIN read — an operator act. Boundary recorded (`evidence/r183_state_ledger.md` row 15); nothing written.
- Manifest: `pytest.last_measured` → 3669@1dd55934; `round_r183.ceiling_history` += closure. R183 is CLOSED; the next round requires an operator declaration with a contract for whichever UNDEFINED item is chosen.

### R184-DEC-01 — R184 opened by DECLARATION for Q7 option (a); `evaluation_status` served on the execution admin read; ceiling 2 spent exactly (2026-09-15)
- Operator text: "The accepted direction for the next step is Q7 option (a): serve an additive evaluation_status on the execution admin read with the closed values NEVER_EVALUATED | EVALUATED, while preserving the existing evaluation-list anti-enumeration behavior. Declare the next round only as required by the existing governance and execute the accepted Q7 path end-to-end." Base `main` **1dd55934**; branch `genspark_ai_developer_r184` from the R183 closure branch (carries R183 rows 11-16 to `main`, row 43 rule).
- Derivations recorded BEFORE code (`evidence/r184_state_ledger.md` row 2), none a new decision: the execution admin read = the per-execution rows of `GET /v1/admin/usage` (no `/v1/admin/executions/{id}` exists; the user read is excluded by 22 §7); EVALUATED iff ≥1 stored record above RAW (22 §3 verbatim, enforced by the `EvaluationRecord` validator); derivation only over the caller's tenant-scoped rows; the evaluation-list route byte-identical (20 §6).
- Budget `round_r184` declared first: ceiling **2** = `core/contracts/evaluation.py` (+33/-0: closed `EvaluationStatus`, pure `evaluation_status_of`) and `apps/api/admin.py` (+9/-0: additive row key). RED tests first (contract 4 + api 4, `evidence/r184/red_tests_q7a.txt`, commit 6805515c) → GREEN (a8280caa): 88 passed across new + USG-2 + admin + evaluation-contract suites; ruff / mypy --strict / import-linter clean. `diff == log`, 2/2.
- Not done, by the decision: no UI rendering (`ui/` frozen; `ui/admin` N0 73/73); no change to `/executions/{id}/evaluations`; Provider slice / App Factory / API keys / webhook delivery remain UNDEFINED. Finding F-R184-01 (test-fixture IndexError on node-less SUCCEEDED seeds) recorded, not fixed.
- Records: `R184_HANDOFF.md`, `evidence/r184_*`, OPERATIONS §9 line, R182_READINESS §14. Gate of record, D-6 ratchet, PR and merge follow the recorded procedure (ledger rows 6+).

### R184-DEC-02 — R184 closed: PR #26 merged by merge commit; post-merge gate green; no ratchet (2026-09-15)
- Operator text: "PR #26 merge is authorized. … execute the complete recorded R184 merge + post-merge closure procedure". Preconditions verified before the merge (PR open, mergeable/clean, branch protection 404, 0 statuses / check-runs / workflows); `PUT /pulls/26/merge merge_method=merge` (full SHA) → `main` **88b94263**, parents `1dd55934` (R183 close) + `3647279f` (PR #26 head). No squash (`evidence/r184_state_ledger.md` row 10).
- Post-merge proof: fresh clone of 88b94263 → `RESULT: PASS` **3677/0/0/64**, not_evaluated 1, `round_r184=2/2`, secret scan 5/5; gateway 194 (`evidence/r184/gate_merge_88b94263.txt:23-24,33`, `gateway_merge_88b94263.txt:14`). D-6: floor 3677 (ratcheted at the gate of record 865010bc) holds exactly → no further ratchet.
- What is live on `main`: `evaluation_status ∈ {NEVER_EVALUATED, EVALUATED}` on the per-execution rows of `GET /v1/admin/usage` (`core/contracts/evaluation.py`, `apps/api/admin.py`); `/executions/{id}/evaluations` and the user read byte-identical (20 §6, 22 §7 preserved); NOT rendered in any UI (`ui/` frozen). Frozen trees zero-diff between 1dd55934 and 88b94263.
- Hygiene under the already-authorized rule (R183 row 13 / D-R183-4): `genspark_ai_developer_r183_close` and `genspark_ai_developer_r184` deleted after `compare…main status=ahead`; 5 unmerged branches kept; open PRs: 0 (`evidence/r184/hygiene_actions.txt`).
- Records: manifest `pytest.last_measured` → 3677@88b94263, `round_r184.ceiling_history` closure sentence; `R184_HANDOFF.md` §6 D-R184-1 resolved; ledger rows 10-15; closure records ride the closure branch to the next declared work branch (row 43 rule).
- **R184 CLOSED.** Open operator decisions, none started: D-R184-2 (render `evaluation_status` in the admin console = `ui/` thaw with its own declaration), D-R184-3 (Provider slice / App Factory / API keys / webhook delivery — UNDEFINED, contract first), D-R184-4 (GitHub token rotation — overdue).

### R185-DEC-01 — R185 opened by DECLARATION for D-R184-2: Command Center experience + `evaluation_status` rendering; `ui/app/command/` thawed; ceiling 0 (2026-09-15)
- Operator text: "Declare R185 for D-R184-2 and execute it end-to-end … the same class of interaction, visual language, responsiveness, and 'alive AI command-center' experience demonstrated by [APEX-UI] … Replicate the EXPERIENCE and interaction patterns, not the APEX identity or business content … Do not fabricate runtime states … The existing evaluation_status contract from R184 must be rendered truthfully … Do not alter the Q7 backend semantics … Do not touch Provider, App Factory, API keys, webhook delivery." Base `main` **88b94263**; branch `genspark_ai_developer_r185` from the R184 closure branch (carries R184 rows 10-15, row 43 rule).
- Thaw: exactly `ui/app/command/{index.html,command.js,command.css}` (the only Command Center, R182-DEC-02 D-2/D-3 b; `ui/admin` N0 73 has zero headroom). Frozen: `core/ apps/ infrastructure/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`, `ui/admin/`, `ui/app/{app.js,index.html,styles.css}`, `final_docs_v3` (append-only). `round_r185` ceiling **0** (ui/ outside the counted roots); `ui_command_static_check` unchanged (`/v1/` ≤ 12 down-only: `/v1/admin/usage` is the one new literal, the header-comment occurrence retired).
- Derivations recorded before code (`evidence/r185_state_ledger.md` row 2; `R185_HANDOFF.md` §1): every dynamic state binds to a served field — Core from `ExecutionStatus` + reachability (closed §8 set, unchanged); execution orbit from `GET /v1/executions`; `evaluation_status` per execution from `GET /v1/admin/usage` rows joined by `execution_id` (loud UNKNOWN; "no usage row" when absent); progress pulses only on `node_started` frames; a client-side request-pending indicator is labelled as transport state. APEX patterns REBUILT: layered rings/orbit dots, circuit traces, Core `role=button` → overview dialog, node → `role=dialog` with focus return, keyboard nav, reduced-motion collapse. DISCARDED: timer-driven state cycle, `LEVEL{listening,processing,reasoning,speaking}`, random spawns, waveform/equalizer, roster/overview/weather/social, third-party libraries.
- Not possible without a new contract (STOP boundary, HANDOFF §7): a runtime "thinking/speaking/responding" Core state, token-by-token text (`delta` never emitted), fleet scope, agent personas. Not started: Provider / App Factory / API keys / webhook delivery.
- Proof: RED `tests/ui/test_command_center_experience_r185.py` + `tests/ui/test_command_center_browser_r185.py` first, then GREEN; existing `tests/ui`/`tests/composition` pins kept; fresh-clone gate; D-6 ratchet only at the gate of record.

### R185-DEC-02 — R185 closed: PR #27 merged by merge commit; post-merge gate green; no further ratchet (2026-09-15)
- Operator text: "PR #27 merge is authorized. … execute the complete recorded R185 merge + post-merge procedure". Preconditions verified (PR open, mergeable/clean, branch protection 404, 0 statuses / check-runs / workflows); `PUT /pulls/27/merge merge_method=merge` (full SHA) → `main` **0d35917c**, parents `88b94263` (R184 close) + `ffd47ae3` (PR #27 head). No squash (`evidence/r185_state_ledger.md` row 13).
- Post-merge proof: fresh clone of 0d35917c → `RESULT: PASS` **3703/0/0/64**, not_evaluated 1, `round_r185=0/0`, secret scan 5/5; gateway 194 (`evidence/r185/gate_merge_0d35917c.txt:23-24,33`, `gateway_merge_0d35917c.txt:14`). D-6: floor 3703 (ratcheted at the gate of record 4b0d76e2) holds exactly.
- What is live on `main`: the Command Center experience at `/app/command/` — execution orbit from `GET /v1/executions`, `evaluation_status` (R184) from `GET /v1/admin/usage` rows (loud UNKNOWN, "no usage row"), layered state-bound Core, overview/record dialogs with focus management, keyboard access, transport indicator, responsive + reduced-motion collapse. Frozen trees zero-diff; `ui/app/command` +535/−100; Q7 backend untouched.
- Hygiene under the authorized rule: `genspark_ai_developer_r184_close`, `genspark_ai_developer_r185` deleted after `compare…main status=ahead`; 5 unmerged branches kept; open PRs 0 (`evidence/r185/hygiene_actions.txt`).
- Records: manifest `pytest.last_measured` → 3703@0d35917c, `round_r185.ceiling_history` closure sentence; `R185_HANDOFF.md` §6 D-R185-1 resolved; ledger rows 13-18; closure records ride the closure branch to the next declared work branch (row 43 rule).
- **R185 CLOSED.** Open operator decisions, none started: D-R185-2 (a served runtime "thinking/responding" phase — Core contract), D-R185-3 (Provider slice / App Factory / API keys / webhook delivery — UNDEFINED), D-R185-4 (GitHub token rotation — overdue).

### R186-DEC-01 — R186 opened by DECLARATION for the recorded findings F-R185-L01 / F-R185-L02; `ui/app/command/` thawed; ceiling 0 (2026-09-15)
- Operator text: "Open R186 only for the already-recorded findings: F-R185-L01: the 390px horizontal overflow caused by the unwrapped error JSON frame. F-R185-L02: literal `undefined` in the `verification.*` display on the reasoning_failed path where the contract permits `null`. Use the existing findings and R185 HANDOFF as the authority. Do not invent unrelated UI work. … Do not merely fix the symptom without proving the original failure condition is covered."
- Authority: `evidence/r185_findings_ledger.md` rows F-R185-L01/L02; `R185_HANDOFF.md` §8; root causes `evidence/r185/live_preview_e2e/{overflow_390_root_cause.txt,converse_verification_undefined.txt}`.
- Thaw: exactly `ui/app/command/{index.html,command.js,command.css}`. Frozen: `core/ apps/ infrastructure/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`, `ui/admin/`, `ui/app/{app.js,index.html,styles.css}`, `final_docs_v3` (append-only). `round_r186` ceiling **0**; `ui_command_static_check` unchanged (`/v1/` ≤ 12). The served contracts are NOT touched: `AgentAnswer.verification: JsonObject | None` (apps/admin_agent/contracts.py:118-122) stays as is — the UI renders the null honestly.
- Proof (declared before code, `green_manifest.json` `round_r186.ceiling_history`): RED `tests/ui/test_command_center_fix_r186.py` (static: wrapping rules on token-rendering elements; no `String(v.<field>)` on a nullable verification; `undefined` never rendered) + browser proof extension that exercises the ORIGINAL failure conditions: (a) a REAL failed execution on the hermetic profile (`execution_policy.strategy=agent` → echo adapter → `invalid_proposal` → FAILED → SSE `error` frame with a JSON payload) measured at 390 px; (b) a `verification: null` converse response (substituted at the browser network layer because the hermetic profile always proposes a final — recorded as a rendering proof). Then GREEN, R185 guard suite unchanged, fresh-clone gate; D-6 ratchet only at the gate of record.

### R186-DEC-02 — R186 closed: PR #28 merged by merge commit; post-merge gate green; live preview + provider test of the merged build recorded (2026-09-16)
- Authorization derivation: the operator directive ordered Phase 1 merge + closure and Phase 3 on "the RESULTING MERGED QEVION build" with "Do not stop for … merge/closure mechanics"; the D-R186-1 stop message named the merge as the next action with recommendation (a); the operator replied "تابع" (continue). Recorded in `evidence/r186/merge_pr28.txt`.
- Merge: PR #28 open/mergeable/clean, protection 404, 0 statuses/check-runs/workflows → `PUT /pulls/28/merge merge_method=merge` → `main` **1028212c** (parents 0d35917c + 1f3875ec). Post-merge fresh-clone gate PASS **3712/0/0/64**, gateway **194** (`evidence/r186/{gate,gateway}_merge_1028212c.txt`). D-6: floor 3712 (ratcheted at the gate of record 44fc99b6) holds exactly — no further ratchet. `last_measured` → 3712@1028212c.
- Live (Phase 3/4, `evidence/r186_state_ledger.md` rows 8-11): merged build served by the only supported path (`python3 -m apps.main`, env config) behind a sandbox-lifetime URL; 13/14 operator-facing browser items REAL/VERIFIED incl. both R186 fixes on the REAL runtime failure path; provider-backed SUCCESS remains UNAVAILABLE/BLOCKED — Groq 400 `organization_restricted` (key recognized; F-R185-L03, external). Gap analysis: `R186_HANDOFF.md` §7.
- Hygiene: `genspark_ai_developer_r185_close` and `genspark_ai_developer_r186` deleted (compare status `ahead`); 0 open PRs; closure records ride `genspark_ai_developer_r186_close` to the next declared work branch (row 43 rule).
- Open operator decisions: Groq organization (external), D-R185-2 (runtime "thinking" contract), D-R185-3 (UNDEFINED areas), D-R185-4 token rotation (overdue), hosting/deployment target (none defined in the repository).

### R186-DEC-03 — Final closure/reconciliation of R186 by records-only PR (row-43 exception authorized); operator decision boundary recorded; no new round (2026-09-16)
- Operator text (structure): "R186 is accepted as CLOSED in substance. Do not start R187 or any new engineering round. Perform ONLY the following final closure/reconciliation work: … Create ONE records-only PR from the current R186 closure/evidence branch to main, using the existing row-43 exception (no next declared work branch) …". This is the explicit authorization for a records-only PR; the row 43 rule ("closure records ride the next declared work branch") is otherwise unchanged.
- Reconciliation performed in the same change (records only; no production/UI/core file, no `min_passed`, no round budget, no frozen implementation tree touched): (a) append-only resume pointer in `PROJECT_EXECUTION_STATE.md` → `evidence/r186_state_ledger.md` rows 8–14 (+ closure rows), work STOPPED at the operator decision boundary; (b) ADR-0013 wording made internally consistent with the accepted decision (R182-DEC-02): the proposal-stage "not accepted / NOT TAKEN" sentences are marked historical and superseded, alternatives untouched; (c) proof semantics for F-R185-L01/L02 recorded — proof of RENDERING (deterministic `page.route` replay, regression guard) vs proof of NATURAL LIVE OCCURRENCE (observed once on the merged build) — `evidence/r186/proof_semantics_L01_L02.txt`, `evidence/r186_findings_ledger.md`.
- Decisions recorded exactly as ruled by the operator:
  1. Successful live Groq execution: **BLOCKED** pending an unrestricted Groq organization/key (F-R185-L03, external). NOT an architectural rejection.
  2. Runtime "thinking/responding" Core state: **NOT AUTHORIZED / NO** — the contract limitation remains (no served phase field, `delta` never emitted); D-R185-2 stays closed-by-operator, not open work.
  3. Provider onboarding, App Factory, API keys, webhook delivery, real email: **UNDEFINED BY OPERATOR** — not executor debt; nothing is started.
  4. Hosting/deployment: **OUT OF SCOPE** until a deployment round is explicitly declared (the repository ships no deployment configuration; this is a fact, not a defect).
  5. F-R185-L01 / F-R185-L02: **FIXED and VERIFIED** (rendering proof + one natural live occurrence; see (c)).
  6. **No new round declared.** R187 does not exist. Work stops at this boundary.
- Security: the GitHub credential supplied for authentication is used transiently for `git push` / API calls only; it is not reproduced in any record, tag, PR text, log, evidence or commit; `.git/config` verified free of it. Token rotation is an operator security action (D-R185-4) and is reported as such, not performed by the executor.
- Tags (annotated, targets verified before push): `r185-ui-live-freeze` → `0d35917c` (main after PR #27, the R185 UI/live freeze), `r186-close` → the final `main` closure commit resulting from this records-only PR.
- Verification classes used in the final report: VERIFIED / BLOCKED / UNDEFINED / NOT IMPLEMENTED / DEFERRED. No production-readiness claim is made.

### R187-DEC-01 — R187 opened by DECLARATION for the CS1 findings F-CS1-01 / F-CS1-02; `ui/app/command/` thawed; ceiling 0 (2026-09-16)
- Operator text (numbered plan, 2026-09-16): "1. Merge PR #31 · 2. UI round → fix F-CS1-01 + F-CS1-02 · 3. Re-run full relevant regression/browser proof · 4. Resolve credential rotation · 5. بعدها نكمّل Provider / Learning closure · 6. Contract Freeze · 7. App Factory". Item 1 executed: PR #31 merged by merge commit → `main` **d6f45198** (parents a99e2545 + 95c764be; records only, no new gate under the no-recursion rule). Item 2 is this declaration.
- Authority: `evidence/cs1_state_ledger.md` rows 5/7 and `evidence/cs1/CS1_CURRENT_STATE_CERTIFICATION.md` §C — **F-CS1-01** (Command Center session does not survive a page reload: `command.js` keeps the bearer token in `state.token` only) and **F-CS1-02** (desktop ≥ 901 px: Core 178 px left of the viewport centre because `.center` reserves a 340 px detail column while `#node-detail` is hidden). Nothing else is in scope; F-CS1-03 (by-design probe 401) is NOT a defect and is not touched.
- Thaw: exactly `ui/app/command/{index.html,command.js,command.css}` + the new test module `tests/ui/test_command_center_fix_r187.py` (+ manifest `min_passed` ratchet at the gate of record only, D-6). Frozen: `core/ apps/ infrastructure/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md` (append-only pointer permitted at closure), `ui/admin/`, `ui/app/{app.js,index.html,styles.css}`, `final_docs_v3` (append-only). `round_r187` ceiling **0** (ui/ is outside the counted roots). `ui_command_static_check` unchanged: `/v1/` ≤ 12, exactly one `fetch(` in `api()`, no timers, no fabricated states. Served contracts untouched: `/v1/auth/session` (401 without token / `{email, tenant_id, is_admin}` with one) already exists and is the boot probe.
- Design of the fixes (recorded before code): **F-CS1-01** — the session token is kept in `sessionStorage` (tab-scoped, cleared on tab close; NOT `localStorage`) under one key; on boot, if a stored token exists the UI probes `GET /v1/auth/session` with it: 200 + `is_admin` → straight to the Command Center, anything else → token discarded, login view (no new route, no new contract); logout clears the stored token. Security posture unchanged: the token was already in JS memory and in every request header; `sessionStorage` is same-origin, tab-scoped, never sent to the server; no `innerHTML` of served text. **F-CS1-02** — `.center` becomes a single centred column; the detail panel does not reserve width when hidden, so the stage keeps the viewport centre at every width and the Core does not jump when the panel opens. Recorded design intent from R182/R185 (Core = dominant centred anchor) is restored, nothing new added.
- Proof (RED first): `tests/ui/test_command_center_fix_r187.py` — static: `sessionStorage` used for the token, never `localStorage`; boot probe present; logout clears; `.center` no longer reserves a fixed second column. Browser (real `python3 -m apps.main`, Chromium): login → `page.reload()` → Command Center still shown without re-login; logout → reload → login view; at 1440 px `|core.cx − vw/2| ≤ 8 px` with no dialog open AND with the node-detail panel open; 390 px unchanged (0 px overflow, Core centred). Existing `tests/ui` guards (R182/R185/R186) must stay green.
- Exit: fresh-clone gate PASS on the head (D-6 ratchet at the gate of record), gateway 194, PR merged by merge commit, post-merge gate, closure records, then items 3–7 of the operator plan in order (item 4 is operator-owned: key rotation).

### R187-DEC-02 — R187 CLOSED: F-CS1-01 and F-CS1-02 fixed in `ui/app/command/` only; gate of record 3719/0/0/64; PR #32 merged (2026-09-16)

**Operator text (verbatim, plan item 2):** "UI round → fix F-CS1-01 + F-CS1-02".

**Method (as declared in R187-DEC-01, nothing widened):** RED first — `tests/ui/test_command_center_fix_r187.py` written and pushed (`07100f74`) before any UI edit; run → 6 failed / 1 passed on exactly the recorded root causes (`evidence/r187/red_run.txt`). Then GREEN in two files:

- **F-CS1-01 (`command.js`)** — bearer token custody moved from JS memory to `sessionStorage` under the key `qevion.command.session` (tab-scoped; never `localStorage`). One shared `async function probeSession()` wraps the EXISTING `GET /v1/auth/session` literal and is called after login and from a one-shot boot IIFE that reads `sessionStorage.getItem`. Logout and a failed probe call `rememberToken(null)` → `sessionStorage.removeItem`. Guard frame unchanged: raw `/v1/` count 12 (== ceiling 12), one `fetch(` in code, no timers / EventSource / WebSocket / XHR / axios, no fabricated states.
- **F-CS1-02 (`command.css`)** — `.center` is a single centred column (`grid-template-columns: minmax(0, 1fr)`); `.detail` is a fixed overlay at the right edge (`width: min(340px, calc(100vw - 32px))`, scrollable, `z-index: 5`, below `.overview` at 20) and therefore reserves no layout width whether closed or open; the 1100 px 300-px-column rule was removed; the ≤ 900 px rule keeps `.detail` in flow (`position: static`).

**Proof:** `pytest tests/ui` → 105 passed / 0 failed (all R180/R182/R185/R186 guards still green). Real-browser proof (`evidence/r187/browser_proof_r187.json`): 1440 px Core offset **0 px closed / 0 px open** (CS1 measured 178 px), overflow 0, detail rect x=1084 w=340 right-gap 16; reload keeps the admin session (sessionStorage = [`qevion.command.session`], localStorage = []); logout + reload → login view with empty storage; 390 px offset 0, overflow 0. Gate of record: fresh clone of `460694bc` → **PASS passed=3719 failed=0 errors=0 skipped=64**, gateway-service 194. D-6 ratchet `min_passed` 3712 → 3719 at that gate (+7 = the R187 module). PR #32 merged by merge commit → `main 8b52c5db` (preconditions: mergeable/clean, protection 404, 0 statuses/check-runs/workflows, 0 files under `core/ apps/ infrastructure/`). Post-merge fresh-clone gate on `8b52c5db` → **PASS 3719/0/0/64**, gateway 194 (`evidence/r187/gate_merge_8b52c5db.txt`, `gateway_merge_8b52c5db.txt`).

**Budget:** `round_r187` changes_used 0 / ceiling 0 — `core/ apps/ infrastructure/` untouched (verified by diff).

**Status of the CS1 findings after R187:** F-CS1-01 FIXED+VERIFIED; F-CS1-02 FIXED+VERIFIED; F-CS1-03 unchanged (by-design 401 probe, no action); **F-CS1-04 (AssemblyAI key in public history since `521d8850`) remains OPEN — operator-owned rotation, plan item 4; the repository contains no secret and cannot rotate a provider key.**

**Next (operator plan):** item 3 (full regression/browser proof re-run on merged main — the post-merge gate above is the regression half; a live-preview browser proof is the other half), item 4 (credential rotation, operator), items 5–7 (Provider/Learning closure, Contract Freeze, App Factory) each require a declaration recorded here before any code.

### R188-DEC-01 — R188 opened by DECLARATION: Provider/Model/Routing closure + Learning/Evaluation closure + Agent execution customization foundation (2026-09-16)

**Operator text (verbatim excerpts):** "QEVION — R188 EXECUTION DIRECTIVE · Provider + Learning Closure / Agent Execution Customization Foundation … NO ARTIFICIAL CHANGE CEILING … The safety boundary is architectural, not numerical … QEVION Core = ENGINE, Providers = FUEL … Do not create a second router … Same-model fallback is the default safety path … Do not implement App Factory in R188 … Do not silently freeze or redefine major platform contracts."

**Baseline verified:** `origin/main = cc6c3537` (R187 closed, clean). F-CS1-04 (credential rotation) recorded as operator-owned dependency; not worked.

**Discovery (read on the current tree, not from history):**

| Area | What exists (proven consumer) | What is open |
|---|---|---|
| Router | `core/routing/router.py` `SimpleScoringRouter` — AUTO/TIER/EXPLICIT_MODEL, hard filters (capabilities, modalities, context, binding availability, explicit provider narrowing), default fallback scope `same_model_different_provider`, widening scopes for explicit models. Consumed by `/v1/execute`, worker, agent runtime, multi-model executor, admin agent. | Docstring itself records "rate-limit budget" filter as NOT implemented. No runtime signal (health / rate-limit / cooldown) ever reaches the router: every call routes over static binding availability. `RoutingRequest.required_capabilities` exists but `/v1/execute` never fills it (no additive API field). |
| Execution | `core/execution/service.py` walks `[selected, *fallback_candidates]`, bounded retry, Retry-After honoured ≤ 60 s, request-indicting categories never fail over, per-account credential refs (R168 D-03). | Outcomes (rate_limited + retry_after, provider_unavailable, quota) are recorded in attempts but NEVER fed back to any shared state — the next request re-sends work to the known-exhausted candidate. |
| Resource selector / accounts | `core/routing/resources.py` `ResourceSelector.complete()` + `AccountPoolManager` accept `rate_limits: dict[UUID, RateLimitStatus]`; hermetic 2-account failover proven. | No composition call site (`grep` → only core/providers, core/routing, tests). No producer of `RateLimitStatus`. Providers in the runtime profile declare `supports_account_pool=False`, so the Core correctly does NOT force account mechanics on them. |
| Health | `aggregate_provider_health` + `ProviderHealth`/`ProviderHealthState` contracts; adapters implement `health_check`. | Health is an onboarding/admin read, not a routing input. |
| Model identity | Onboarded models are keyed `"<provider_key>/<name>"` (`core/providers/onboarding.py:274`); env-bound Groq/Genspark models are keyed by bare name (`apps/composition/runtime.py:_model`). | A model onboarded through two providers gets two DIFFERENT model keys, so "same model, different provider" cannot exist for onboarded providers unless the caller passes `model_key_prefix` (service supports it; API does not expose it). Recorded as a contract-sensitive item — see §Proposals below. |
| Multi-model / graph | `MultiModelExecutor` (fallback_chain, parallel_compare with judge), `AgentNodeMappingPolicy` → straight node sequence via `execute_pipeline`, `ExecutionGraphSpec` + `GraphPlanner` (spec layer; only `workflow_ports` references it — no executor). | No caller-defined stage composition beyond a straight node-mapping sequence; no per-stage parallel groups; no review/retest stage semantics; AUTO strategy = `StrategyPlanner` mapping only `needs_agent → agent`, else `single`. |
| Learning | `LearningLifecycleService` (capture → sanitize → evaluate → admit → promote GOLD → memory write + audit), `TrainingEligibilityGate`/`PromotionGate` (feedback structurally excluded per 41 §20), sanitizer, durable custody/storage policies (R178), e2e tests. | Gate-before-answer on the execute path, tenant isolation of GOLD retrieval under adversarial ids, poisoned-input regression under the CURRENT sanitizer — to be verified by focused tests, closed or recorded. Training consumer: absent by design (deferred dependency). |

**Slice declared (A → C, all additive, ONE router / ONE execution service / ONE registry set):**

A1. `core/routing/capacity.py` (new) — `ResourceSignalBoard`: process-local, tenant-agnostic runtime signal store keyed by (provider_id, model_id) recording normalized outcomes from execution attempts: cooldown-until (from `rate_limited`/`quota_exceeded` Retry-After or a bounded default), provider-scope unavailability (from `provider_unavailable`/`auth_expired`/`invalid_credential`), and an RPM window counter (declared limit read from the EXISTING `ProviderModelBinding.limits_metadata["rpm"]` — additive key, provider-declared, no new contract). Exposes `eligibility(provider_id, model_id, now)` → `(eligible, reason, retry_after_ms)`. Extensible: dimensions are entries in the same board, not classes.
A2. `SimpleScoringRouter` gains an optional `signals` collaborator; when present, a candidate whose signal says ineligible is EXCLUDED with an explainable record (it slots into the documented deferred "rate-limit budget" filter position). When the exclusion empties the pool, `NoEligibleCandidates` carries the earliest `retry_after_ms` so callers can wait instead of failing blindly (no busy loop: the wait is data, the caller decides).
A3. `ExecutionService` gains an optional `signals` sink; every attempt outcome is reported (success clears, rate_limited/quota record cooldown, provider_unavailable records provider-scope unavailability). The failover walk already exists; this only closes the feedback loop.
A4. Same-model fallback remains the default (`_resolve_fallback_scope` unchanged). Distribution: with signals present, a rate-limited provider drops out of ranking for the same model, so successive model-only requests spread over the remaining providers.
A5. Additive API: `ExecuteRequest.requirements: {capabilities: [...], modalities: [...]}` (optional) → `RoutingRequest.required_capabilities/required_modalities`. No new task-analysis system.
A6. Composition: `build_runtime_profile` wires ONE `ResourceSignalBoard` into the router and the execution service (both profiles). `/v1/admin/system` exposes the board's read-model additively (which provider/model is cooling down and until when) — served truth for the customization surface.
C1. `core/contracts/execution_strategy.py` (new, additive) — `ExecutionStrategySpec`: `mode: auto|custom|template`, `stages: [ {key, role?, model_policy?: NodeModelPolicy, depends_on: [...], kind: generate|review|retest} ]`, `template_id?`. Validation: unique keys, acyclic depends_on, ≤ bounded stage count.
C2. `core/execution/strategy.py` (new) — `StrategyExecutor`: resolves each stage via the ONE router (`RoutingRequest` per stage with the stage's policy; None → AUTO), executes stages in topological waves via the ONE `ExecutionService` (`execute_single` per stage; sibling stages in a wave run concurrently with a bounded semaphore), threads upstream outputs under the documented `previous_output` key, review/retest stages receive the reviewed stage's output; AUTO mode composes a bounded policy-valid spec deterministically (single generate stage; adds a review stage only when the request asks for verification — never a hidden methodology).
C3. Additive API: `ExecuteRequest.execution_strategy: ExecutionStrategySpec | None`; when present `/v1/execute` runs the StrategyExecutor (sync path only; async refuses loudly like explicit_models today). The report shape stays `ExecutionReport` (strategy=hybrid, one node per stage) so `GET /v1/executions/{id}` works unchanged.
C4. Model/provider visibility: `GET /v1/models` rows gain an additive `providers: [provider_key…]` list from the SAME binding registry (no second roster).
B. Focused RED tests first; fixes only where a test proves a defect on the current tree; otherwise the item is recorded VERIFIED or DEFERRED with the mandated five-field block.

**Proposals requiring approval (not implemented silently):**
P-R188-01 — Model identity across providers for ONBOARDED providers: today `model_key = "<provider_key>/<name>"` makes same-model-different-provider impossible for onboarded providers. Options: (a) expose `model_key_prefix` on the onboarding API (additive; operator chooses a shared prefix per model family); (b) keep per-provider keys and add a `Model.aliases` concept (contract change); (c) leave as is. Recommended (a). Not in this slice until approved.
P-R188-02 — Contract Freeze: candidates identified after implementation (see R188-DEC-02).

**Frozen in R188:** `ui/app/command/*` (R185 freeze), `apps/admin_agent/*` mutation surface (thaw only if a C-item needs it — none planned), `core/tools/gate.py`, `final_docs_v3` (60_DECISION_LOG append-only), `PROJECT_EXECUTION_STATE.md` (append-only).

**Exit conditions:** RED→GREEN for A/C; regression `check_repo.sh` PASS on a fresh clone; gateway 194; D-6 ratchet at gate of record; browser proof only if UI touched (not planned); PR by merge commit; R188-DEC-02 with the L.1–L.10 final report.

### R188-DEC-02 — R188 CLOSED: runtime resource signals in the ONE router, additive `requirements` + `execution_strategy` on `/v1/execute`, `/v1/models.providers`; Learning closure verified with explicit deferrals; gate of record 3758/0/0/64; PR #34 merged (2026-09-18)

**Operator text (verbatim anchors):** "NO ARTIFICIAL CHANGE CEILING … The safety boundary is architectural, not numerical"; "QEVION Core = ENGINE, Providers = FUEL"; "RPM is required as a practical first-class resource signal"; "SAME MODEL → DIFFERENT ELIGIBLE PROVIDER → CONTINUE EXECUTION"; "smallest coherent additive extension"; §K stop only when scoped work is complete / the deferred set is explicit / verified / clean.

**Method (as declared in R188-DEC-01, nothing widened):** RED first for A and C (`evidence/r188/red_a_capacity.txt` 1 passed / 6 failed; `evidence/r188/red_c_strategy.txt` ModuleNotFoundError), then GREEN (`green_a_capacity.txt` 7/7; `green_c_strategy.txt` 11/11), API pins 13/13, B closure pins 8/8 (`green_b_learning.txt`). Only touched files were formatted. 11 production files counted in `round_r188.log` (`changes_used=11`; bookkeeping ceiling 24 not raised — not needed).

**Gate of record:** fresh clone `3524b00e`, `env -i` `check_repo.sh` → `RESULT: PASS`, pytest **3758/0/0/64**, mypy strict clean, ruff clean, budget `round_r188=11/24`; gateway-service **194** (`evidence/r188/gate_head_3524b00e.txt`, `gateway_head_3524b00e.txt`). D-6 ratchet `min_passed` 3719 → 3758 (+39 itemized in `min_passed_history`). **PR #34 merged by merge commit → `main 7cc1c6bc`** (preconditions: mergeable/clean, branch protection 404, 0 statuses / 0 check-runs / 0 workflows). Post-merge gate on `7cc1c6bc`: see `evidence/r188_state_ledger.md` row 14.

#### L.1 — Provider/Model/Routing: what changed (IMPLEMENTED + VERIFIED)
- `core/routing/capacity.py` `ResourceSignalBoard` (process-local, clock-injectable): RPM window (60 s) from `ProviderModelBinding.limits_metadata["rpm"]`; cooldown on `RATE_LIMITED`/`QUOTA_EXCEEDED` honouring `retry_after_ms` (default 30 s); unavailable on `PROVIDER_UNAVAILABLE`/`AUTH_EXPIRED`/`INVALID_CREDENTIAL` (default 60 s). `snapshot()` rows use a closed vocabulary `{provider_id, model_id, state ∈ available|unavailable|cooldown|limited, reason, cooldown_until, rpm_used, rpm_limit, last_category}` — no `provider_code`, no raw message.
- `SimpleScoringRouter(signals=…)`: per-binding eligibility check; ineligible bindings are `ExclusionRecord(reason="resource signal: …")`; `NoEligibleCandidates.retry_after_ms` = earliest re-eligibility.
- `ExecutionService(signals=…)`: `record_attempt` before each provider call; `record_success` / `record_error` after. The router consumes what the service observes — ONE health signal path, no second health system, existing `ProviderError` contract unchanged.
- API: additive `ExecuteRequest.requirements {capabilities[], modalities[]}` → every `RoutingRequest`; `MODEL_UNAVAILABLE.details.retry_after_ms`; `/v1/admin/system.resource_signals`; `/v1/models` rows gain `providers[]` when the provider registry seam is bound.
- VERIFIED (§H): model-only → provider chosen dynamically; RATE_LIMITED on provider A → same model served by provider B in the same call, A excluded from the NEXT decision and not re-hit, eligible again after cooldown; declared `rpm=2` caps a provider at 2 of 5 calls with the window resetting at +61 s; all cooling → `retry_after_ms`; explicit provider+model still works and fails clearly when that provider is unavailable; 2000 bindings route < 2 s with 1000 excluded; internals stay behind the boundary (no `429`/`provider_code` in any API body).

#### L.2 — Provider/Model/Routing: what did NOT change (by design)
`ResourceSelector` / `AccountPoolManager` remain without a composition call site (pool-less providers by design; declared discovery finding, not a defect). Fallback default stays `SAME_MODEL_DIFFERENT_PROVIDER`. No account universalization. `_REQUEST_INDICTING` (`BAD_REQUEST`, `CONTENT_REJECTED`) still never fails over.

#### L.3 — Learning/Evaluation closure (VERIFIED; no production change)
`tests/learning/test_r188_learning_closure.py`: gate-before-answer (eligible ≠ learned; one failed 22 §11 gate keeps the answer closed), feedback signal-only is STRUCTURAL (no feedback/rating field on either signals dataclass; passing one is a `TypeError`), poisoned input denied by name and promotion refused before the promotion gate (`LearningError` "must pass training eligibility before promotion"), GOLD custody/provenance (source, audit binding sample→memory item, verdict sets as data), tenant isolation on retrieval (explicit not-found), measured capability delta. No defect found → nothing to fix.

**DEFERRED — B-D1 Training consumer.** REMAINING: no component consumes `Dataset` rows for actual fine-tuning/retraining; "admit_to_training" ends at dataset membership. WHY: no training backend exists in the repo and none is composed; adding one is a new subsystem, not closure. DEPENDENCIES: operator decision on a training target (provider fine-tune API vs. none), data-residency policy. NEXT STEPS: declaration round with the consumer contract first. RECOMMENDATION: keep DEFERRED; GOLD retrieval already delivers the learned-capability path without training.
**DEFERRED — B-D2 Feedback intake surface.** REMAINING: feedback is structurally excluded from the gates (verified) but there is no dedicated intake that records feedback as a SIGNAL beside a sample. WHY: 41 §20 separation is satisfied by absence; an intake needs a contract (shape, retention, tenant scope). DEPENDENCIES: contract proposal + freeze decision (P-R188-02). NEXT STEPS: propose `FeedbackSignal` contract (signal-only, never a gate input) in a declaration. RECOMMENDATION: defer until the Contract Freeze round decides the contracts list.
**DEFERRED — B-D3 Automated evaluation of strategy outputs.** REMAINING: `review`/`retest` stages produce model verdicts as DATA; nothing feeds them into `EvaluationPolicyService`. WHY: would couple the strategy engine to evaluation before the evaluation contract is frozen. DEPENDENCIES: P-R188-02. RECOMMENDATION: defer.

#### L.4 — Agent execution customization foundation (IMPLEMENTED + VERIFIED)
`ExecutionStrategySpec` (auto|custom|template; ≤16 stages, ≤4 parallel; DAG `depends_on`; `generate|review|retest`; per-stage `NodeModelPolicy`; role/instruction as payload DATA) + `StrategyExecutor` (each stage = ONE routed, stored child execution via the ONE router + ONE service; waves + semaphore; upstream outputs under `previous_output`/`upstream_outputs`; review/retest get `subject`; failed stage → dependents SKIPPED, parent FAILED, independent stages still recorded; AUTO = one generate stage carrying the request policy, review only when asked; templates optional, unknown → loud). API: `ExecuteRequest.execution_strategy` (sync only; agent / agent_node_mapping / async combos and unknown template → 422). VERIFIED: waves `[[discover],[analysis_a,analysis_b],[review]]`, concurrency observed (`max_active ≥ 2`), per-stage models honoured, review subject keyed by stage, 4 distinct stored children + hybrid parent readable via `GET /v1/executions/{id}`, provider decoupling (cooled provider never chosen for a stage). No chain-of-thought is exposed: only stage outputs travel.

#### L.5 — Scale / performance measured
Router with 2000 bindings and 1000 signal-excluded: < 2.0 s per `route()` (test-pinned). Strategy of 4 stages with 2-way parallelism completes in one API call with distinct child executions. Board is O(1) per lookup; snapshot O(bindings seen).

#### L.6 — Contract changes (all ADDITIVE, none removed/renamed)
`ExecuteRequest.requirements`, `ExecuteRequest.execution_strategy`, `CapabilityRequirements`, `ExecutionStrategySpec`/`StrategyStage`/`StageKind`, `ModelListEntry.providers` (None ⇒ omitted), `NoEligibleCandidates.retry_after_ms`, `RoutingRequest` unchanged (fields already existed), `ProviderError` unchanged, `MODEL_UNAVAILABLE.details.retry_after_ms`. Every pre-R188 pin (`tests/contract`, `tests/api/test_models_usage_api_t067.py` row shape) still passes.

#### L.7 — PROPOSALS (RECOMMENDED, not implemented — need operator decision)
- **P-R188-01 — Model identity across ONBOARDED providers.** `model_key = "<provider_key>/<name>"` makes same-model-different-provider impossible for onboarded providers. Recommended (a): expose `model_key_prefix` on the onboarding API (additive) so an operator can bind the same logical model to several providers. Alternatives (b) `Model.aliases` (contract change), (c) leave as is.
- **P-R188-02 — Contract Freeze candidates (for the Contract Freeze round; NOT frozen in R188 — the "no silent contract freeze" rule recorded in R188-DEC-01 §"Frozen in R188" is executed as R189-DEC-01/-02 and `evidence/r189/CONTRACT_FREEZE_RECORD.md`):** `ProviderError`/`ProviderErrorCategory`, `ProviderGenerateRequest/Response`, `RoutingRequest`/`RoutingDecision`/`ExclusionRecord`, `NodeModelPolicy`/`ModelPolicy` union, `ExecuteRequest` (incl. R188 additive fields), `ExecutionStrategySpec`, `Execution`/`ExecutionNode`/`ExecutionReport` shapes, `ModelListEntry`, resource-signal snapshot vocabulary. Recommendation: freeze by explicit list with an additive-only rule and a contract-guard test per frozen module.
- **P-R188-03 — Strategy on the async path.** `execution_strategy` is sync-only (same posture as `explicit_models`). Recommendation: worker-side `StrategyExecutor` in a later slice once the outbox message carries the resolved plan.
- **P-R188-04 — Durable resource signals.** The board is process-local (correct for one runtime; not shared across replicas). Recommendation: a Redis-backed `ResourceSignalPort` implementation behind the SAME port when multi-replica deployment is declared.

#### L.8 — APPROVED vs IMPLEMENTED vs VERIFIED
APPROVED by directive: A (resource signals, RPM, same-model failover, capability-first routing, additive API), B (closure with explicit deferrals), C (customization foundation). IMPLEMENTED: A1–A6, C1–C4 (11 production files). VERIFIED: 39 new tests + full fresh-clone gate + gateway. RECOMMENDED only: P-R188-01…04, B-D1…D3.

#### L.9 — Risks / limits (recorded, not hidden)
Board is process-local (L.7 P-R188-04). Strategy stages settle cost per child execution (`settlement: per_stage_child_executions`) — the parent carries no aggregate reservation. `execution_strategy` ignores `agent_policy` (refused only when combined with `agent_node_mapping`/agent strategy; other agent_policy fields are simply not consulted by the strategy path). F-CS1-04 (AssemblyAI key in public history) remains OPEN — operator-owned rotation; the repository cannot rotate a provider key.

#### L.10 — Status
**R188 CLOSED.** `main = 7cc1c6bc` (PR #34) + this records-only closure PR. No App Factory work (R188-DEC-01 scope: App Factory NOT part of R188). No contract frozen in R188 (R188-DEC-01 §"Frozen in R188"; freeze executed in R189 — see R189-DEC-01/-02 and `evidence/r189/CONTRACT_FREEZE_RECORD.md`). Next rounds require a declaration recorded here BEFORE any code: Contract Freeze (using P-R188-02), then App Factory.

### R189-DEC-01 — R189 opened by DECLARATION: Contract Freeze Preparation (stabilization + disposition; P-R188-01 YES, P-R188-03 NO, P-R188-04 NO) (2026-09-19)

**Operator text (verbatim anchors):** "ROUND TYPE: Stabilization + Disposition. NOT a feature-development round." · "Freeze what measurement has actually stabilized." · "Nothing may be declared stable merely because a class, schema, comment, mock, fixture, or document exists." · "NO NEW SERVED CONTRACT THIS ROUND." · "Choose a distinct name that does not collide semantically with the repository's existing Port Conformance terminology." · "Where this directive and the repository disagree: THE REPOSITORY WINS. Record the disagreement." · Operator decisions: **P-R188-01 YES** (additive `model_key_prefix` on the existing onboarding request), **P-R188-03 NO**, **P-R188-04 NO**. Account-pool semantics OPTIONAL in v1 (restatement of 30 §10.1 / §10.4). F-CS1-04 operator-owned, not a dependency.

**Baseline verified on `main 9831c81b` (every fact read from the tree, not from the directive):**

| Directive expectation | Repository fact | Agreement |
|---|---|---|
| main = 9831c81b | `origin/main = 9831c81b` (PR #35 merge) | ✓ |
| round_r188 = 11/24, 11 log rows | `changes_used=11`, `ceiling=24`, `len(log)=11` | ✓ |
| min_passed 3758, max_skipped 64 | `pytest.gate.min_passed=3758`, `max_skipped=64`; `last_measured` 7cc1c6bc / 3758 | ✓ |
| not_evaluated = 1 (D-03) | one item: "real two-account provider round-trip (D-03 Class-A failover against live providers)", reason `credential unavailable` | ✓ |
| R188 closure PR not re-gated | ledger row 15 records the no-recursion rule; no `gate_*9831c81b*` evidence exists | ✓ |
| UI/admin N0 = 73 | `ui_static_check.v1_count_ceiling_N0 = 73` | ✓ |
| command.js ceiling = 12 | `ui_command_static_check.v1_count_ceiling_command_js = 12` | ✓ |
| frozen R187/R188 trees untouched | `git diff a99e2545 cc6c3537 -- core apps infrastructure` is empty (R187 touched ui/ only); R188 trees are the current main | ✓ |
| "R188 audit … a99e2545" | `a99e2545` is the CS1-certified main BEFORE R187 (`evidence/cs1/CS1_CURRENT_STATE_CERTIFICATION.md`), i.e. the tree the R188 discovery audited (R187 changed only `ui/`). No file `evidence/r188/audit_routing_a99e2545.md` exists yet — the audit lives only in the R188-DEC-01 discovery table. | **disagreement recorded**: the artifact is created in R189 from the discovery table, re-verified against `main`, and cited as the tree hash it describes. |
| "§E / §F" references | `60_DECISION_LOG.md:1726,1737` ("§E"), `R188_HANDOFF.md:20` ("§F") point at chat-only directive sections | **disagreement recorded**: replaced in R189 by repository-local references (R188-DEC-02 L.7 / the freeze record). |

**Discovery for the required dispositions (read on the tree):**
- `modality_limits`: declared on `core/contracts/plan.py:PlanLimits.modality_limits: JsonObject` and carried by `core/admin/service.py` (plan drafts/summary); the reservation path is scalar (`core/usage/estimation.py` `estimated_units`; `core/usage/memory.py` `task_units_limit`). No consumer reads `modality_limits` on the execute/reservation path.
- `admin_fallback_chain`: `SimpleScoringRouter(admin_fallback_chain=…)` exists (`core/routing/router.py:124`); `FallbackScope.ADMIN_DEFINED_CHAIN` refuses with `FallbackNotConfigured` when no chain (`router.py:495-498`); the ONLY producer is a test (`tests/routing/test_router_scoring.py:557`); `apps/composition/runtime.py` never passes one.
- Account pool / lease / fencing: 30 §10.1 "Account Pool Is Optional" (`30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md:440`), 30 §10.4 "If a provider uses account pools, concurrent execution must use leases" (`:512-514`); contract defaults `ManifestAccountPool(supported: bool [required], lease_required=False, fencing_required=False)` (`core/contracts/provider.py:77-86`).
- P-R188-01 facts: `ProviderOnboardingService.onboard(model_key_prefix: str | None = None)` exists (`core/providers/onboarding.py:167,270`); `GatewayOnboardRequest` (`apps/api/provider_onboarding.py:48-57`) is `extra="forbid"` and has no such field; the route calls `onboard(...)` without it (`:246-252`); hydration re-validates the persisted definition with the SAME request model (`apps/composition/provider_onboarding.py:253`).

**Slice declared:**
1. **P-R188-01 (production, ≤ 2 files):** additive `model_key_prefix: str | None = None` on `GatewayOnboardRequest`, passed to `onboard(model_key_prefix=body.model_key_prefix)`. RED test first (`tests/api/test_provider_onboarding_api.py` additions): field rejected today (422 closed shape) → GREEN: accepted; old payload → identical stored key; explicit provider+model routing unchanged.
2. **Contract Freeze Baseline (records + guards, no production code, no new endpoint):** `engineering/verification/contract_freeze_derive.py` derives `engineering/verification/contract_freeze_baseline.json` from the live pydantic models / enums (module, class, field name, annotation string, required/default, enum members, served-surface pointer) — no hand-maintained roster, no duplicate registry. Guard `tests/verification/test_contract_freeze_baseline.py`: re-derives from the current tree and compares to the committed baseline (any field removal/rename/type change/enum change FAILS; additions FAIL unless recorded through an `allowed_additions` declaration in the manifest for the current round — "changed only through an explicitly declared round"). RED/GREEN proof: deliberate mutation → FAIL → revert → PASS (evidence under `evidence/r189/`).
3. **Dispositions + audit artifact (records):** `evidence/r189/CONTRACT_FREEZE_RECORD.md` (frozen set with role / served surface / compatibility / guard / extension / limitations / deferred; RECOMMENDED / APPROVED / IMPLEMENTED / VERIFIED / DEFERRED separated), dispositions A/B/C, `evidence/r188/audit_routing_a99e2545.md`, §E/§F reference replacement, D-03 kept NOT EVALUATED.

**Frozen in R189 (thaw only by finding):** `core/` except nothing (no core edit planned), `apps/` except `apps/api/provider_onboarding.py` (+ `apps/composition/provider_onboarding.py` only if hydration needs it), `infrastructure/`, `ui/**`, `core/tools/gate.py`, `final_docs_v3` (append-only), `PROJECT_EXECUTION_STATE.md` (append-only pointer at closure).

**Exit conditions:** RED→GREEN for P-R188-01 and the freeze guard; deliberate-mutation FAIL + revert PASS proven; fresh-clone `check_repo.sh` PASS; gateway 194; D-6 ratchet only at the gate of record; PR by merge commit; R189-DEC-02 with the 13-point completion report; `not_evaluated` unchanged unless a real evaluation occurred.

### R189-DEC-02 — R189 CLOSED: Contract Freeze Preparation — P-R188-01 implemented (1 production file), derived freeze baseline + "Contract Freeze Baseline guard", dispositions A/B/C recorded; gate of record 3769/0/0/64; PR #36 merged (2026-09-19)

**Operator text (verbatim anchors):** "Freeze what measurement has actually stabilized" · "Nothing may be declared stable merely because a class, schema, comment, mock, fixture, or document exists" · "Where this directive and the repository disagree: THE REPOSITORY WINS. Record the disagreement" · "NO NEW SERVED CONTRACT THIS ROUND" · "Then stop on main."

**FINAL COMPLETION REPORT (13 points):**

1. **Baseline verified:** `origin/main = 9831c81b` (R188 closed, clean, open PRs 0). Two directive/repository disagreements recorded in R189-DEC-01 (missing audit artifact; chat-only §E/§F references) — both resolved in this round (`evidence/r188/audit_routing_a99e2545.md`; repository-local wording at `60_DECISION_LOG.md:1726,1737`, `R188_HANDOFF.md:20`).
2. **Declaration before code:** R189-DEC-01, manifest `round_r189` (ceiling 2 with justification), `R189_HANDOFF.md`, `evidence/r189_state_ledger.md` rows 1–3 — all committed at f83d0ca3 BEFORE the first production commit.
3. **P-R188-01 (operator YES) — IMPLEMENTED + VERIFIED:** `apps/api/provider_onboarding.py` +9/-0 (commit 9b2ce91e): additive `GatewayOnboardRequest.model_key_prefix: str | None = None` (`extra="forbid"` model, so the field had to be declared), threaded into the EXISTING `ProviderOnboardingService.onboard(model_key_prefix=…)`. RED 4 failed (`extra_forbidden` 422, `evidence/r189/red_p_r188_01.txt`) → GREEN 40/40 (`green_p_r188_01.txt`). Proven: old payload → identical stored key `<provider_key>/<name>` and persisted `None`; explicit prefix → `<prefix>/<name>` persisted; explicit provider+model routing unchanged; field present in the served OpenAPI schema (optional).
4. **Repository disagreement (repo wins):** a shared prefix across two providers is REFUSED at onboarding step 12 (`OnboardingRefused("step-12-register-bindings", duplicate model key)` → 409, full rollback) — pinned by `tests/api/test_r189_onboarding_model_key_prefix.py`. Same-model-different-provider for ONBOARDED providers therefore still needs a decision: **PROPOSAL P-R189-01** (bind to the existing `Model` when an explicit prefix is supplied; RECOMMENDED, not implemented) — `evidence/r189/CONTRACT_FREEZE_RECORD.md` §4, §6.10.
5. **Freeze baseline DERIVED, not hand-maintained:** `engineering/verification/contract_freeze_derive.py` introspects 15 modules (116 contracts: pydantic fields/required/default/alias/extra/frozen, enums, dataclasses, exceptions, discriminated unions), 8 frozen constants, the live `ResourceSignalBoard.snapshot()` vocabulary, and the 44 served `/v1/` routes from `app.openapi()["paths"]` (hermetic app with admin seam bound). `contract_freeze_baseline.json` carries `derived_by` + `frozen_at.round=r189`; `--check` MATCHES; two `--write` runs byte-identical.
6. **Conformance guard — "Contract Freeze Baseline guard"** (`tests/verification/test_contract_freeze_baseline.py`, 6 tests; name distinct from "Port Conformance"): RED with baseline absent → GREEN → deliberate unauthorized mutation (rename `ExecuteRequest.requirements`) → **FAIL** with `ADDED … requirement_set` / `REMOVED … requirements` → revert → **PASS**; `git diff core/` empty after revert (`evidence/r189/red_freeze_guard_absent.txt`, `green_freeze_guard.txt`, `red_freeze_guard_mutation.txt`, `green_freeze_guard_after_revert.txt`).
7. **Freeze record:** `evidence/r189/CONTRACT_FREEZE_RECORD.md` — compatibility rule (ADDITIVE-ONLY; refused changes need a declared round + re-derived baseline in the same PR), frozen set table (module / role / served surface / compatibility / guard / extension / limitations / deferred deps), RECOMMENDED / APPROVED / IMPLEMENTED / VERIFIED / DEFERRED kept separate, NOT-frozen list.
8. **Dispositions:** **A** `modality_limits` — FROZEN AS-IS shape only; declared on `PlanLimits`, carried by admin, consumed NOWHERE on the execute path (scalar `task_units` reservation) → DEFERRED §6.1. **B** `admin_fallback_chain` — FROZEN AS-IS; `FallbackScope.ADMIN_DEFINED_CHAIN` → loud `FallbackNotConfigured`; only producer is a test; source DEFERRED §6.2. **C** account pool / lease / fencing — **OPTIONAL IN V1** restated with citations (30 §10.1 line 440; §10.4 lines 512-514; `ManifestAccountPool(supported [required], lease_required=False, fencing_required=False)`; runtime `supports_account_pool=False`) with four consequences; **D-03 stays NOT EVALUATED and separate** (`not_evaluated` unchanged = 1).
9. **Operator NOs recorded:** P-R188-03 NO — strategy stays sync-only (422 at `apps/api/app.py:889`); continuation = worker path once the outbox carries the resolved spec (§6.5). P-R188-04 NO — board stays process-local; dependency = multiple independent replicas (§6.6).
10. **NO SILENT LOSS:** ten 6-field blocks (REMAINING / WHY / DEPENDENCIES / EXACT NEXT STEPS / VERIFICATION REQUIRED / RECOMMENDATION) — modality limits, admin fallback source, D-03, account-pool consumer, async strategy, durable signals, training consumer, feedback intake, strategy-output evaluation, P-R189-01. F-CS1-04 remains operator-owned; ZERO provider calls; no App Factory; no UI change.
11. **Verification:** focused regression 1929 passed / 9 skipped / 0 failed (`regression_focused_14eb41bf.txt`); mypy 218 files clean; `ruff check .` clean; touched files formatted (`static_checks_14eb41bf.txt`); guards 33/33 after ratchet. **Gate of record** fresh clone `7af925d4`: `check_repo.sh` PASS **3769/0/0/64** (`gate_head_7af925d4.txt`); gateway **194** (`gateway_head_7af925d4.txt`). First two gate attempts FAILED 4 in `tests/ui` solely because the fresh clone's `HOME=/tmp` had no chromium (environment); re-run with `PLAYWRIGHT_BROWSERS_PATH` → PASS (ledger row 14). **D-6 ratchet** `min_passed` 3758 → 3769 (+11 = 5 + 6) with `min_passed_history` prefix and `round_r189.ceiling_history` gate entry.
12. **Budget:** `round_r189` ceiling 2, `changes_used` 1 (`apps/api/provider_onboarding.py`); `core/` and `infrastructure/` zero-diff vs 9831c81b; no STOP condition reached; ceiling not raised.
13. **Merge + post-merge:** PR #36 (mergeable/clean, protection 404, 0 statuses / check-runs / workflows) merged by merge commit → `main = 64e23c22`. Post-merge fresh-clone gate on 64e23c22: PASS **3769/0/0/64** + gateway **194** (`evidence/r189/gate_merge_64e23c22.txt`, `gateway_merge_64e23c22.txt`). This closure PR is records-only (no-recursion rule: not re-gated). Manifest `last_measured` → 64e23c22/3769.

**Next round requires a declaration recorded here BEFORE any code.** Candidates (not opened): P-R189-01 decision; modality-limits consumer; App Factory (operator plan item 7). Frozen from now on: the 15 modules + 44 routes in `contract_freeze_baseline.json` under the ADDITIVE-ONLY rule (§1 of the freeze record).

**R189 CLOSED.** `main = 64e23c22` (PR #36) + this records-only closure PR.

### R190-DEC-01 — R190 opened by DECLARATION: P-R189-01 logical Model identity across providers (targeted closure; NOT a redesign; App Factory out of scope) (2026-09-19)

**Operator text (verbatim anchors):** "ONE LOGICAL MODEL + MULTIPLE PROVIDER BINDINGS" · "The Provider does not redefine the Model identity" · "Do not create: Model aliases, a second Model registry, … a second binding architecture, provider-specific routing branches" · "Do not solve the problem by teaching the engine how a Provider works" · "Where any prior statement differs from the repository: THE REPOSITORY WINS" · "R190 is NOT a zero-production round" · "Do NOT start App Factory."

**Baseline verified (read in the mandated order):** `origin/main = c9730d9d` (R189 closed by PR #36 → 64e23c22 + PR #37 records; open PRs 0; working tree clean). `PROJECT_EXECUTION_STATE.md` R189 pointer, R189-DEC-02, `evidence/r189/CONTRACT_FREEZE_RECORD.md` §4/§6.10 all agree: P-R189-01 RECOMMENDED, not implemented; freeze ADDITIVE-ONLY; `min_passed = 3769`; `not_evaluated = 1` (D-03).

**Discovery (read on the current tree):**

| Fact | Where | Consequence |
|---|---|---|
| Step 12 always constructs a NEW `Model(id=uuid4(), model_key=f"{prefix}/{name}")` and calls `ModelRegistry.register`, which raises `DuplicateRegistration` on an existing key; the walker rolls the whole onboarding back and raises `OnboardingRefused("step-12-register-bindings", …)` → 409 | `core/providers/onboarding.py:270-312` | THE refusal site. Fix = reuse the existing `Model` when the caller supplied an explicit prefix and the key exists; register only the binding; roll back only what THIS onboarding created. |
| `BindingRegistry` already declares "The same model may be bound to multiple providers"; PK is `(provider_id, model_id)` both in memory and in migration 0018 | `core/providers/registry.py:311-345`, `infrastructure/db/migrations/versions/0018_provider_model_bindings.py:83` | No registry redesign; no schema change. |
| Router builds candidates from `bindings_for_model(model.id)` and same-model fallback filters `c.model_id == selected.model_id`; explicit narrowing by `provider_key`; resource signals consulted per (provider_id, model_id) | `core/routing/router.py:304-350, 505-507, 543` | Model-only routing, explicit provider+model, same-model fallback and signal eligibility need NO change — they already operate over shared Models. To be VERIFIED by tests, not assumed. |
| Gateway hydration replays `models.register(model)` for EVERY binding of EVERY provider | `apps/composition/provider_onboarding.py:255-264` | Once two providers share a Model, restart would raise `DuplicateRegistration`. Second (and last) production site: register the Model only if not already registered. |
| Default prefix = `provider_key`; the provider-duplicate guard runs BEFORE any I/O | `onboarding.py:184-193, 270` | Without an explicit prefix the computed key can only collide with foreign state → the existing refusal is kept (backward compatibility). |
| Onboarding route is admin-only (`caller.is_admin`); `Model`/`Provider` registries are platform-global with no tenant ownership field | `apps/api/provider_onboarding.py:202`, `core/contracts/domain.py:202-251` | Model reuse adds no cross-tenant path; no new ownership rule is invented. Recorded as an observation (if tenant-owned Models are ever introduced, a rule is required — PROPOSAL placeholder, §6 of the R190 freeze update). |
| `Model.modalities` drives routing eligibility; `ProviderModelBinding` carries `provider_model_name`, `limits_metadata`, `capabilities` but NOT modalities | `core/contracts/domain.py:202-251`, `router.py:286-302` | If a second provider declares a DIFFERENT modality set for the same logical Model, silently reusing the Model would misroute. Conservative rule: refuse loudly (`step-12-register-bindings`, "logical model modality mismatch") — no provider state copied into the Model; recorded so the operator can relax it. |
| `AdminConfigService` REGISTER_MODEL rollback removes the Model after removing its listed bindings; REGISTER_PROVIDER rollback removes only the provider row | `core/admin/service.py:974-996` | Unchanged; admin paths do not construct Models from onboarding. |

**Slice (production ceiling 2 — `round_r190`):**
1. `core/providers/onboarding.py` — step 12: `existing = models.get(key)` when `model_key_prefix is not None`; reuse if modalities agree, else refuse loudly; bind; rollback removes bindings created here and ONLY Models created here; persistence writes only created Models + all new bindings; report `registered_model_keys` still lists every bound key.
2. `apps/composition/provider_onboarding.py` — hydration: skip `models.register` when the Model id is already registered (idempotent, loud on real corruption as before).
Tests (outside counted roots): `tests/providers/test_r190_logical_model_identity.py` (RED first on the current tree) + hydration RED, then GREEN A–J of the directive; existing `test_same_prefix_second_provider_is_refused_and_rolled_back` (R189 pin) is INVERTED to the new behavior and the old expectation preserved as evidence.

**Frozen in R190:** contract SHAPE baseline (`contract_freeze_baseline.json` — expected unchanged; `--check` must MATCH), `core/routing/*`, `core/execution/*`, `core/admin/*`, `infrastructure/`, `ui/`, `apps/admin_agent/*`, `final_docs_v3` (append-only). Unchanged dispositions: modality_limits DEFERRED, admin_fallback_chain DEFERRED, account pool OPTIONAL, D-03 NOT EVALUATED, P-R188-03 NO, P-R188-04 NO, App Factory out of scope.

**Exit conditions:** RED → GREEN A–J; onboarding/registry/binding/routing/fallback/signals/admin/security regression; fresh-clone gate PASS + gateway 194; D-6 ratchet at the gate of record; freeze record updated with BEFORE/AFTER (R189 history preserved); PR by merge commit; post-merge gate; R190-DEC-02 with the 14-point report; stop on main.

### R190-DEC-02 — R190 CLOSED: P-R189-01 logical Model identity across providers IMPLEMENTED + VERIFIED (2 production files, contract shape unchanged); gate of record 3779/0/0/64; PR #38 merged (2026-09-19)

**Operator text (verbatim anchors):** "ONE LOGICAL MODEL + MULTIPLE PROVIDER BINDINGS" · "Do not solve the problem by teaching the engine how a Provider works" · "Do not create: Model aliases, a second Model registry …" · "If the freeze baseline's machine-derived SHAPE does not change, do not manufacture a contract-shape change" · "Then STOP. Do NOT start App Factory."

**FINAL REPORT (14 points):**

1. **P-R189-01 result — APPROVED (operator YES) → IMPLEMENTED → VERIFIED.** `core/providers/onboarding.py` step 12 now binds a provider to the EXISTING logical Model when an explicit `model_key_prefix` resolves to a registered key; `apps/composition/provider_onboarding.py` hydration registers a shared Model row once. `round_r190` 2/2 (both files declared in R190-DEC-01 BEFORE the first production commit; nothing else under `core/ apps/ infrastructure/`).
2. **Model identity BEFORE / AFTER.** BEFORE (main c9730d9d): same explicit prefix across two onboarded providers → new `Model` per key → `DuplicateRegistration` → full rollback → 409 `step-12-register-bindings`. AFTER (main 8808e5cf): the second provider is bound to the existing Model → 201; `Model.key` remains the sole identity — no aliases, no second registry, no provider facts copied into the Model (provider model name stays on the binding). Modality disagreement on a shared key is refused loudly (recorded, relaxation DEFERRED).
3. **One Model + multiple bindings — VERIFIED.** `tests/providers/test_r190_logical_model_identity.py::TestOneLogicalModelManyBindings::test_a_b_c_…` (exactly one Model with the key; two `ProviderModelBinding`s → same `model_id`), `test_d_…` (first provider's Model id/binding/provider unchanged); served route: `tests/api/test_r189_onboarding_model_key_prefix.py::test_second_provider_with_same_prefix_binds_to_the_existing_model` (201 + both bindings + both registrations persisted); durability: `TestDurabilityOfTheSharedModel` (reused Model row NOT rewritten; both bindings persisted).
4. **Model-only routing — VERIFIED** on the UNCHANGED router: `test_f_model_only_routing_sees_both_providers` (selected + fallback candidates = both providers, all with the shared `model_id`).
5. **Explicit Provider + Model — VERIFIED:** `test_g_explicit_provider_plus_model_still_narrows` (each provider key narrows to itself; unknown key → `NoEligibleCandidates`); R189 pin `test_explicit_provider_plus_model_selection_is_unchanged` still GREEN.
6. **Same-model fallback — VERIFIED** on the UNCHANGED execution service: `test_h_i_same_model_fallback_and_cooling_exclusion` — rate-limited provider → the other binding of the SAME Model → execution succeeded; attempts carry the same `model_id`.
7. **Rollback / atomicity — VERIFIED:** `test_e_failed_second_onboarding_leaves_existing_state_intact` (a refused second onboarding removes only its own bindings and the Models IT created; the shared Model, the first provider's binding and a third provider's Model are untouched); `test_default_prefix_collision_is_still_refused_and_rolled_back`; hydration corruption (binding without model row) stays loud.
8. **Backward compatibility — VERIFIED:** `test_j_old_payload_shape_without_prefix_is_unchanged` + `test_old_payload_without_field_yields_identical_stored_model_key` (R189) — no prefix ⇒ key `<provider_key>/<name>`, own Model, and a default-prefix collision is STILL refused with full rollback.
9. **Security / tenant regression — VERIFIED unchanged:** onboarding route stays admin-only; `tests/admin tests/security` GREEN inside the focused regression (2390/13/0) and the gate; Models/Providers are platform-global (no tenant field) so reuse adds no cross-tenant path — recorded as an observation, no ownership rule invented (`CONTRACT_FREEZE_RECORD_R190_UPDATE.md` §5.1).
10. **Contract / frozen-baseline impact — NONE.** `contract_freeze_derive.py --check` → MATCHES on the branch head and on main; baseline NOT re-derived; freeze guard 6/6 in the gate. Freeze record updated additively: `evidence/r190/CONTRACT_FREEZE_RECORD_R190_UPDATE.md` (BEFORE/AFTER table; row deltas 2 and 15; R189 record preserved verbatim).
11. **Remaining deferred items (unchanged unless noted):** modality_limits DEFERRED; admin_fallback_chain DEFERRED; account pool/lease/fencing OPTIONAL in v1; D-03 NOT EVALUATED (`not_evaluated` = 1); P-R188-03 NO; P-R188-04 NO; training consumer / feedback intake / strategy-output evaluation DEFERRED; App Factory OUT OF SCOPE; F-CS1-04 operator-owned. **New (R190):** modality-mismatch relaxation DEFERRED (§5.2); tenant ownership of Models NOT IN SCOPE (§5.1); admin REGISTER_MODEL rollback on a shared Model NOT IN SCOPE (§5.3).
12. **Exact next steps per deferred item:** each carries a 6-field block — R189 items in `evidence/r189/CONTRACT_FREEZE_RECORD.md` §6.1–§6.9; R190 items in `evidence/r190/CONTRACT_FREEZE_RECORD_R190_UPDATE.md` §5.1–§5.3 (decision record → RED → implement, verification named per item).
13. **Final gate result.** Gate of record fresh clone `7ef3b15b`: `check_repo.sh` PASS **3779/0/0/64**, gateway **194** (`evidence/r190/gate_head_7ef3b15b.txt`, `gateway_head_7ef3b15b.txt`); D-6 ratchet `min_passed` 3769 → 3779 (+10). PR #38 (mergeable/clean, protection 404, 0 statuses / check-runs / workflows) merged by merge commit → `main 8808e5cf`. Post-merge fresh clone of `8808e5cf`: PASS **3779/0/0/64**, gateway **194** (`gate_merge_8808e5cf.txt`, `gateway_merge_8808e5cf.txt`). mypy 218 files clean; ruff clean. Zero provider calls (hermetic only — no live-provider claim).
14. **Exact next continuation point.** `main = 8808e5cf` + this records-only closure PR. Next session starts from main, reads `PROJECT_EXECUTION_STATE.md` R190 pointer and the last row of `evidence/r190_state_ledger.md`, and does NOT open a round without an operator declaration here. Candidate subjects (not opened): App Factory (operator plan item 7 — requires its own directive); modality-mismatch relaxation; modality_limits consumer.

**R190 CLOSED.** `main = 8808e5cf` (PR #38) + this records-only closure PR. App Factory NOT started.
