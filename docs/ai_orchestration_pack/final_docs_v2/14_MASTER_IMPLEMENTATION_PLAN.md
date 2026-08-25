# MASTER IMPLEMENTATION PLAN
## AI Orchestration Platform — Execution Baseline

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-011)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
NOTE: §32 (Resume Protocol), §33 (NEXT_PLAN.md), §35/§37 (dedicated
FUTURE_IMPROVEMENTS.md / ARCHITECTURE_GAPS.md ledgers), §39 (Handoff files),
and §42 (Static Resume Prompt) reference the legacy multi-state-file scheme
and are explicitly superseded by D10/D11: the single mutable state is
PROJECT_EXECUTION_STATE.md.
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

### حالة الوثيقة

```text
Architecture Status: BASELINED
Implementation Status: READY
Source of Truth: Git Repository
Engineering Method: Incremental / Verified / Committed
```

---

# 1. قواعد لا يجوز كسرها

```text
1. Git committed repository = Trusted Project State
2. Verified + Committed = Trusted Progress
3. Uncommitted work = Recovery Candidate
4. No silent architecture changes
5. No hardcoded business/runtime policy
6. Core remains Provider/Model agnostic
7. Router decides; Execution executes
8. LLM is never a security authority
9. Unknown permissions/capabilities default to DENY
10. New extensibility uses Contracts + Registries
11. Training requires explicit eligibility + verification
12. Every meaningful change is tested
13. Every completed micro-task should produce a focused commit
14. Every session ends with a recoverable state
15. Every new session reconstructs reality from Git before trusting state files
```

---

# 2. Repository / Engineering Layout

من البداية، يكون المشروع منظمًا بحيث الـCore والـInfrastructure والـProviders لا تختلط.

```text
project/
├── apps/
│   ├── api/
│   ├── admin/
│   └── client-runtime/
│
├── core/
│   ├── contracts/
│   ├── orchestration/
│   ├── routing/
│   ├── execution/
│   ├── context/
│   ├── roles/
│   ├── skills/
│   ├── tools/
│   ├── evaluation/
│   ├── learning/
│   ├── usage/
│   └── policies/
│
├── providers/
│   ├── registry/
│   ├── common/
│   └── <provider_modules>/
│
├── infrastructure/
│   ├── db/
│   ├── cache/
│   ├── queues/
│   ├── workflows/
│   ├── object_storage/
│   ├── secrets/
│   └── observability/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   ├── load/
│   ├── chaos/
│   └── regression/
│
├── engineering/
│   ├── MASTER_ENGINEERING_PROTOCOL.md
│   ├── MASTER_IMPLEMENTATION_PLAN.md
│   ├── state/
│   ├── decisions/
│   ├── adr/
│   ├── gates/
│   ├── verification/
│   ├── recovery/
│   └── history/
│
└── docs/
```

هذا **Baseline منطقي** وليس إلزامًا حرفيًا لو المشروع الحالي يفرض تنظيمًا مختلفًا؛ الـAI يطابقه مع الواقع ويستخدم ADR لو احتاج تعديلًا مدروسًا.

---

# 3. Phase 0 — Governance

### الهدف

تثبيت قواعد العمل قبل لمس الـCore.

### المهام

```text
G0-T01
Create engineering protocol

G0-T02
Create state/recovery system

G0-T03
Create ADR system

G0-T04
Create phase/gate templates

G0-T05
Create verification conventions
```

### Exit Criteria

```text
Protocol committed
State system committed
Recovery system committed
ADR templates committed
```

---

# 4. Phase 1 — Contracts First

نبني العقود قبل التنفيذ الكبير.

### Contracts

```text
Request
Response
Error
Provider
Model
Capability
Credential
Account
Role
Skill
Tool
Execution
Node
Evaluation
Verification
Policy
Usage
Webhook
```

### قواعد

لا يوجد Contract يستورد Implementation محدد.

### Exit

```text
contracts compile
schema validation passes
contract tests exist
```

---

# 5. Phase 2 — Identity / Tenant / Security Foundation

### Build

```text
Gmail registration
Email verification
Password hashing
Session system
User
Tenant
Permissions
Entitlements
Authorization
Capability Firewall base
Device identity
Audit hooks
```

### Security

```text
Argon2id
Secure cookies/session
TLS-only
Rate limiting
Anti-enumeration
Re-authentication
Deny-by-default
```

### Exit

```text
Auth tests pass
Tenant isolation tests pass
Authorization tests pass
Security baseline passes
```

---

# 6. Phase 3 — Storage Foundation

### PostgreSQL

Source of truth لـ:

```text
users
tenants
plans
roles
permissions
skills metadata
models
providers
conversations
messages
memory
executions
usage
evaluations
learning metadata
```

### pgvector

Semantic retrieval.

### Redis

```text
cache
short state
streams
locks
rate limits
runtime coordination
```

### Object Storage

```text
files
images
audio
video
datasets
large artifacts
```

### Secrets

Provider/User credentials داخل Secret Manager.

### Required

```text
migrations
indexes
tenant enforcement
backup configuration
```

---

# 7. Phase 4 — Provider Framework

Reference first:

```text
24_FINAL_PROVIDER_ARCHITECTURE_SPEC.md
```


هنا يبدأ تحويل الـProvider Inventory إلى Architecture حقيقية.

### Contracts

```text
Provider
Authentication
Account
Model discovery
Capabilities
Generation
Assets
Errors
Health
Limits
Agent
```

### Provider Adapter

كل Provider implementation مستقل.

### قواعد

```text
No Provider-specific logic in Core
No Provider implementation imported by Router
No hardcoded Provider assumptions
```

---



### If no real Providers exist yet

If `ai_providers` or real provider implementations are missing, Phase 4/5 should create provider framework scaffolding and disabled diverse templates only.

Do not block the project and do not fake provider functionality.

Reference:

```text
23_AI_PROVIDERS_SCAFFOLDING_POLICY.md
```

---

# 8. Phase 5 — Provider Migration

كل Provider على حدة.

```text
Inventory
→ Design mapping
→ Implement adapter
→ Contract tests
→ Capability tests
→ Health tests
→ Error tests
→ Commit
```

### لا يجوز

نقل عدة Providers مرة واحدة ثم اكتشاف المشكلة في النهاية.

كل Provider = وحدة صغيرة قابلة للاسترجاع.

---

# 9. Phase 6 — Model Registry

### Build

```text
Model Registry
Tier Registry
Capability Registry
Modality Registry
Model Profile
Model availability
Model benchmark metadata
```

### Selection

```text
AUTO
TIER
EXPLICIT_MODEL
```

### Exit

نقدر نسأل Registry:

> ما النماذج المؤهلة لمهمة X؟

بدون أي Provider HTTP.

---

# 10. Phase 7 — Credentials / Accounts / Pools

### Platform

```text
Provider
→ Platform Account Pool
```

### User

```text
Tenant/User
→ User Credential
```

### Credential policy

```text
platform_only
user_only
prefer_user
auto
```

### Account lifecycle

```text
READY
COOLDOWN
REFRESH_REQUIRED
AUTH_EXPIRED
INVALID
PENDING
DISABLED
```

### Concurrency

```text
Lease
Fencing
Cooldown
Rate limit
```

### Exit

Account selection يمكن اختباره بالكامل بدون AI.

---

# 11. Phase 8 — Router Engine

### Build

```text
Task Analyzer
Context Resolver
Role Resolver
Capability Resolver
Skill Requirements
Strategy Planner
Eligibility Filter
Scoring Engine
Resource Selector
```

### Bootstrap Router

مسار منفصل لاختيار Router Model نفسه.

### مهم

الـRouter:

```text
DOES:
decide

DOES NOT:
execute
```

### Exit

اختبارات تغطي:

```text
AUTO
TIER
EXPLICIT
Provider fallback
Same-tier fallback
Unavailable model
Unavailable provider
```

---

# 12. Phase 9 — Execution Graph

### Build

```text
Execution Graph
Node Contract
Planner
Durable Workflow Runtime
Node lifecycle
Timeouts
Retries
Recovery
```

### Strategies

```text
single
parallel
pipeline
debate
review/judge
map/reduce
agent
hybrid
```

### Important

Workflow Runtime يملك state.

لا نبني Workflow Engine خاص بنا.

---

# 13. Phase 10 — Async Fabric

### Build

```text
PostgreSQL durable state
Outbox
Redis Streams
Worker runtime
Admission control
Fair scheduling
Backpressure
DLQ
Idempotency
```

### Lease/Fencing فقط للـexclusive resources

ليس لكل Job.

### Exit

اختبارات:

```text
duplicate request
worker crash
lease expiry
stale worker
retry
DLQ
queue flood
```

---

# 14. Phase 11 — Personal Context Engine

### Build

```text
Conversation State
User Profile
Project Context
Learned Preferences
Retriever
Context Composer
```

### Memory rules

```text
Evidence
Confidence
Scope
Relevance
```

### Context hierarchy

```text
Conversation
Project
Workspace
User
Global
```

بحسب الـeffective scope.

### مهم

Memory ≠ Training Data.

---

# 15. Phase 12 — Role System

### System Roles

Admin-controlled.

### Custom Roles

User/Project created.

### Role profile

```text
identity
objective
required capabilities
preferred skills
behavior policies
output contract
runtime override
```

### Security

Custom Role لا يمنح permissions.

---

# 16. Phase 13 — Skill System

### Import sources

```text
https://github.com/mattpocock/skills
https://www.aihero.dev/skills-wayfinder
https://github.com/amElnagdy/review-skills
```

### Import lifecycle

```text
imported
→ scanned
→ validated
→ reviewed
→ approved
→ active
```

### Local copy

كل Skill خارجية تصبح Local Version.

### Resolver

```text
Task
+
Role
+
Context
→ Candidate Skills
→ Compatibility
→ Ranking
→ Selected Skills
```

---

# 17. Phase 14 — Tool Fabric

### Tool contract

```text
id
version
location
permissions
credentials
input schema
output schema
rate limits
sandbox policy
approval policy
```

### Locations

```text
server
client
hybrid
```

### Client Runtime

```text
Browser
Filesystem
Terminal
IDE
Local Project
```

### Device Trust

```text
pair
trust
revoke
rotate
```

### Security

كل Tool Call يمر عبر Capability Firewall.

---

# 18. Phase 15 — Evaluation / Verification

### Build

```text
Deterministic Graders
Model Graders
Pairwise
Skill Graders
Role Graders
Counter Evaluation
Aggregator
Verification
Evidence
```

### Levels

```text
RAW
EVALUATED
VALIDATED
VERIFIED
GOLD
```

### User

يرى نتيجة فقط افتراضيًا.

### Admin

يرى التفاصيل.

---

# 19. Phase 16 — Plans / Usage / Billing

### Units

```text
Simple = 1
Medium = 2
Complex = 3
```

القيمة configuration-driven.

### Flow

```text
Estimate
→ Reserve
→ Execute
→ Settle
```

### Cost Snapshot

يتم تثبيته عند بداية Task.

### Internal retry/failover

لا يضاعف تكلفة المستخدم.

---

# 20. Phase 17 — Learning / Model Evolution

### Pipeline

```text
Verified Data
→ Dataset
→ Sanitization
→ Teacher/Max
→ Training
→ Evaluation
→ Shadow
→ Canary
→ Promotion
```

### Admin dashboard

يعرض:

```text
coverage
gold samples
specialists
quality
accuracy
cost reduction
escalation
teacher agreement
training status
```

### User Feedback

Signal فقط.

### Training eligibility

منفصل عن Feedback.

---

# 21. Phase 18 — Public API

### Main

```text
POST /v1/execute
```

### Supporting

```text
GET /v1/executions/{id}
GET /v1/models
GET /v1/skills
GET /v1/usage
POST /v1/webhooks
```

### Features

```text
API Keys
Scopes
Idempotency
Async
Sync
Streaming
Webhooks
Unified Errors
Versioning
```

---

# 22. Phase 19 — Admin Control Plane

### Admin modules

```text
Overview
Users
Tenants
Plans
Providers
Models
Routing
Execution
Roles
Skills
Tools
Evaluation
Learning
Security
Audit
Observability
Configuration
Feature Flags
```

### Configuration lifecycle

```text
Draft
→ Validate
→ Preview
→ Publish
→ Observe
→ Rollback
```

### Security invariant

Admin config لا يستطيع تعطيل:

```text
tenant isolation
secret guarantees
core crypto rules
security boundaries
audit integrity
```

---

# 23. Phase 20 — Observability

### OpenTelemetry

```text
logs
metrics
traces
```

### Adaptive tracing

```text
normal → reduced
error → full
slow → full
debug → full
high value → full
```

### Audit

Security-sensitive events فقط تحتاج أعلى درجة من protection.

---

# 24. Phase 21 — Security Hardening

### API

```text
TLS
rate limits
size limits
validation
CORS/CSRF where applicable
```

### AI

```text
prompt injection
indirect injection
data exfiltration
excessive agency
output validation
tool abuse
```

### Supply chain

```text
skill provenance
dependency validation
artifact integrity
```

### Tenant

```text
application
data layer
DB enforcement
```

---

# 25. Phase 22 — Testing / Chaos

### Functional

```text
unit
integration
contract
e2e
```

### Architecture

```text
dependency boundaries
forbidden imports
contract validation
```

### Security

```text
auth
IDOR
tenant isolation
SSRF
injection
tool abuse
prompt injection
secret leakage
```

### Reliability

```text
worker crash
provider outage
DB failover
Redis failure
duplicate message
lease expiry
stale worker
queue flood
```

### Load

```text
normal
peak
burst
soak
stress
```

---

# 26. Phase 23 — Production

### Initial topology

```text
Single Region
Multi-AZ
Stateless API
HA PostgreSQL
HA Redis
Object Storage
Workers
Durable Workflow Runtime
DR Region
```

### Scaling

```text
API → horizontal
Workers → queue-driven
Provider pools → capacity-driven
Evaluation → separate worker pool
Learning → isolated compute
```

### Multi-region

DR أولًا.

Active/Active فقط عندما تبرره المتطلبات.

---

# 27. Phase 24 — Final Validation

هذه ليست "تشغيل Tests وخلاص".

لازم نثبت:

```text
Architecture
Security
Isolation
Providers
Routing
Execution
Memory
Skills
Tools
Evaluation
Learning
Usage
API
Admin
Observability
Recovery
Scalability
```

ثم:

```text
Production Readiness = PASS
```

---

# 28. Micro-task Protocol

أهم قاعدة للتنفيذ اليومي.

كل مهمة يجب أن تكون:

```text
T-{phase}-{number}
```

مثال:

```text
T-04-017
Create provider health contract
```

ويكون لها:

```text
objective
dependencies
files expected
verification command
acceptance criteria
commit message
```

### لا يوجد:

> "أعمل Provider System."

يوجد:

> "Create provider health contract and its validation tests."

---

# 29. Task Output Contract

بعد كل Micro-task:

```text
TASK RESULT
Status:
Implementation:
Files:
Tests:
Verification:
Commit:
Uncommitted:
Next Task:
Risks:
```

ولا تستخدم كلمة `DONE` إلا بعد Commit ناجح.

---

# 30. Commit Protocol

كل Micro-task مؤهلة للإغلاق:

```text
Implement
→ Test
→ Verify
→ Commit
→ Verify commit
→ Update state
→ Generate next plan
```

### Commit verification

بعد commit:

```text
git rev-parse HEAD
git status
git show --stat HEAD
```

لا نكتفي بأن `git commit` رجع success.

---

# 31. Interrupt Protocol

لو الجلسة انقطعت **قبل commit**:

```text
Trusted state = previous commit
```

والـworking tree:

```text
Recovery Candidate
```

لا يعتبر تقدمًا موثوقًا.

---

# 32. Resume Protocol النهائي

في كل Session:

```text
READ PROTOCOL
↓
READ STATE FILES
↓
GIT STATUS
↓
GIT HEAD
↓
GIT DIFF
↓
IDENTIFY LAST TRUSTED COMMIT
↓
CLASSIFY UNCOMMITTED WORK
↓
VERIFY
↓
RECOVER / COMPLETE / DISCARD ONLY WITH EVIDENCE
↓
GENERATE NEXT MICRO-TASK
↓
IMPLEMENT
```

---

# 33. Next Plan Generation

في نهاية كل Session أو Task:

```text
NEXT_PLAN.md
```

يجب أن يحتوي:

```text
Last trusted commit
Current phase
Current gate
Completed micro-task
Verified state
Remaining tasks
Next micro-task
Dependencies
Expected files
Tests
Risks
```

لكن:

> `NEXT_PLAN.md` ليس Source of Truth.

هو **خطة استئناف** فقط.

---

# 34. Uncommitted Work Protocol

لو فيه تغييرات غير committed:

```text
DO NOT:
git reset --hard
git checkout .
rm files
overwrite
```

قبل معرفة مصدرها.

يجب:

```text
inspect
classify
verify
preserve
```

ثم:

```text
complete
or
discard with explicit evidence
```

---

# 35. Scope Control

لو AI اكتشف improvement خارج المهمة:

```text
Record in FUTURE_IMPROVEMENTS.md
Do not implement
```

إلا لو هو Blocker يمنع المهمة الحالية.

---

# 36. Architecture Change Protocol

لو احتجنا تعديل قرار:

```text
STOP
↓
Problem
↓
Evidence
↓
Alternatives
↓
Impact
↓
ADR
↓
Approval
↓
Migration
↓
Tests
↓
Commit
```

ولا يوجد:

> "أنا عدلتها لأنها أفضل."

بدون ADR.

---

# 37. Future Improvements

يحتفظ النظام بـ:

```text
FUTURE_IMPROVEMENTS.md
ARCHITECTURE_GAPS.md
```

بحيث المشروع يتطور دون Scope Creep.

---

# 38. Gate System

كل Gate:

```text
Entry
→ Build
→ Verify
→ Exit
```

ولا ننتقل إلى المرحلة التالية لو:

```text
critical tests fail
security gate fails
contract incomplete
uncommitted critical work exists
```

---

# 39. Human/AI Handoff

أي شخص جديد يستطيع البدء من:

```text
MASTER_ENGINEERING_PROTOCOL
CURRENT_STATE
HANDOFF
PHASE_STATE
ACTIVE_TASK
DECISIONS
LAST_TRUSTED_COMMIT
```

ثم يعمل Git verification.

---

# 40. Definition of Done النهائي

```text
Code exists
+
Tests pass
+
Security checks pass
+
Observability exists
+
Docs updated
+
ADR if needed
+
Git commit exists
+
Commit verified
+
State updated
+
Next task generated
```

---

# 41. معيار نجاح المشروع النهائي

المشروع لن يعتبر ناجحًا لمجرد:

> "API شغالة."

بل يجب أن يكون:

```text
Provider-extensible
Model-agnostic
Router-driven
Execution-graph capable
Memory-aware
Role-driven
Skill-extensible
Tool-safe
Tenant-isolated
Evaluation-backed
Learning-capable
Admin-configurable
Observable
Recoverable
Scalable
Tested
Production-ready
```

---

# 42. Static Resume Prompt النهائي

هذا هو النص الثابت الذي يستخدم في بداية **كل Session جديدة**:

```text
RESUME ENGINEERED PROJECT

You are continuing an existing production-oriented codebase.

SOURCE OF TRUTH:
The Git repository is the only authoritative source of trusted project progress.

Trusted progress requires:
VERIFIED IMPLEMENTATION + SUCCESSFUL COMMIT.

Do NOT treat:
- previous conversation
- STATE.md
- PROGRESS.md
- HANDOFF.md
- previous AI claims
- previous plans

as proof of completion.

STEP 1 — READ
Read:
- MASTER_ENGINEERING_PROTOCOL.md
- MASTER_IMPLEMENTATION_PLAN.md
- engineering/state/*
- current phase/gate
- relevant ADRs

STEP 2 — VERIFY REALITY
Inspect:
- git HEAD
- git status
- git diff
- current files
- relevant tests
- latest verified commit

STEP 3 — RECOVER
Determine:
- last trusted commit
- current phase
- current gate
- current task
- uncommitted work
- whether uncommitted work belongs to the active task

Never delete or reset uncommitted work blindly.

STEP 4 — RECONCILE
If documentation conflicts with Git:
Git wins.

If uncommitted work exists:
treat it as untrusted recovery material until verified.

STEP 5 — CONTINUE
Resume only from the last verified project state.

Choose the smallest valid next micro-task.

Do not expand scope.

Do not silently change architecture.

If a new architectural decision is required:
STOP → analyze → create/update ADR → verify impact → then continue.

STEP 6 — AFTER EACH MICRO-TASK
- implement
- run targeted tests
- verify result
- commit the completed logical unit
- verify the commit
- update state
- update handoff
- generate the next micro-task plan

STEP 7 — SESSION END
Before voluntarily ending:
- leave no unexplained working-tree changes
- record exact last trusted commit
- record current task status
- generate NEXT_PLAN
- update HANDOFF

Never claim DONE without a verified commit.
Never assume interrupted work succeeded.
Never use conversation memory as project truth.
```

# 43. والـMaster Build Prompt نفسه يجب أن يفرض هذه القاعدة

الـAI الذي سيبدأ بناء المشروع ليس مطلوبًا منه فقط:

> "ابني النظام."

بل:

> **"اعمل طبقًا للـMASTER ENGINEERING PROTOCOL وMASTER IMPLEMENTATION PLAN، بوحدات صغيرة، وكل وحدة تنتهي بــ verification + commit + next-plan."**

وده الفرق بين AI يكتب كود كثير، وAI يدير **عملية هندسية قابلة للاستئناف والمراجعة والتوسع**.

---

## نقطة مهمة قبل أن تبدأ التنفيذ الفعلي

أنا أعتبر الآن أن لدينا **Baseline كافية لبدء بناء المشروع**، ولا أرى سؤالًا معماريًا يجب أن يوقفنا.

لكن عند التنفيذ الفعلي، لا نستخدم الوثائق كبديل عن الواقع:

```text
Git → الحقيقة
Tests → الدليل
Protocol → القواعد
State → الملاحة
Next Plan → الخطوة القادمة
```

وبالتالي حتى لو حصل:

```text
انقطاع
بدون commit
جلسة جديدة
AI جديد
مهندس جديد
```

يظل المشروع قابلًا للاستكمال من **آخر Commit موثوق** مع فحص أي تغييرات معلقة بدل فقدها أو البناء فوق افتراضات خاطئة.