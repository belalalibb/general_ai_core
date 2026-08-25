# 41 — Implementation Plan & MVP
## One Plan with Explicit FINAL vs MVP vs FUTURE Separation

```text
STATUS: AUTHORITATIVE (V3)
AUTHORED_BY_TASK: T-DOC-011
SOURCES (V2, now SUPERSEDED):
- final_docs_v2/14_MASTER_IMPLEMENTATION_PLAN.md   (full/final implementation plan)
- final_docs_v2/15_MVP_ROADMAP.md                  (MVP scope and phased roadmap)
AUTHORITY SWITCH: final_docs_v3/00_INDEX.md (MIGRATION STATUS table)
RELATED AUTHORITATIVE DOCS:
- final_docs_v3/40_ENGINEERING_PROTOCOL.md  (engineering rules, gates, DoD, ADR, Git safety)
- docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md (the ONLY mutable state file — D10/D11)
LANGUAGE NOTE: v2 sources mixed Arabic/English narrative; this successor is
normalized to English. All decision blocks are preserved verbatim; narrative
translation changes no decision.
SUPERSEDED SECTIONS: v2 14 §32/§33/§39/§42 and the v2 14 §35/§37 dedicated
ledger files, plus v2 15 legacy "state files / handoff" wording, are
explicitly superseded by D10/D11 (see §Part III and the traceability ledger).
```

This document is the single authority for **what gets built, in what order,
and what the MVP includes**. It merges the FINAL implementation plan (v2 14)
and the MVP roadmap (v2 15) into one plan with explicit separation:

```text
FINAL  = the complete target system (Part I)
MVP    = the smallest slice that proves the architecture (Part II)
FUTURE = explicitly deferred until requirements justify them (Part III)
```

---

# PART I — FINAL IMPLEMENTATION PLAN

---

## 1. Non-Breakable Rules

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

Rules 14–15 are implemented under D10/D11: the recoverable state is the
single mutable state file `PROJECT_EXECUTION_STATE.md`, updated only at
verified checkpoints, and always re-verified against Git at session start.

---

## 2. Repository / Engineering Layout

From the start, the project is organized so Core, Infrastructure, and
Providers never mix.

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
│   ├── decisions/
│   ├── adr/
│   ├── gates/
│   ├── verification/
│   └── history/
│
└── docs/
```

This is a **logical baseline**, not a literal mandate: if the actual project
imposes a different organization, the Agent reconciles with reality and uses
an ADR for any deliberate deviation. (Per D10/D11 the legacy
`engineering/state/` directory is removed from the baseline: the single
mutable state file is `PROJECT_EXECUTION_STATE.md`.)

---

## 3. Phase 0 — Governance

Goal: fix the working rules before touching the Core.

Tasks:

```text
G0-T01  Create engineering protocol
G0-T02  Create state/recovery system
G0-T03  Create ADR system
G0-T04  Create phase/gate templates
G0-T05  Create verification conventions
```

Exit criteria:

```text
Protocol committed
State system committed
Recovery system committed
ADR templates committed
```

The "state/recovery system" here is D10/D11-conformant: one state file,
recovery rules per `40_ENGINEERING_PROTOCOL.md` §10–§11.

---

## 4. Phase 1 — Contracts First

Contracts are built before large implementation.

Contracts:

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

Rule: no Contract imports a specific Implementation.

Exit:

```text
contracts compile
schema validation passes
contract tests exist
```

---

## 5. Phase 2 — Identity / Tenant / Security Foundation

Build:

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

Security:

```text
Argon2id
Secure cookies/session
TLS-only
Rate limiting
Anti-enumeration
Re-authentication
Deny-by-default
```

Exit:

```text
Auth tests pass
Tenant isolation tests pass
Authorization tests pass
Security baseline passes
```

---

## 6. Phase 3 — Storage Foundation

PostgreSQL is source of truth for:

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

pgvector: semantic retrieval.

Redis:

```text
cache
short state
streams
locks
rate limits
runtime coordination
```

Object Storage:

```text
files
images
audio
video
datasets
large artifacts
```

Secrets: Provider/User credentials live in the Secret Manager.

Required:

```text
migrations
indexes
tenant enforcement
backup configuration
```

---

## 7. Phase 4 — Provider Framework

Reference first: `final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md`.

This is where the Provider Inventory becomes real architecture.

Contracts:

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

Provider Adapter: every provider implementation is independent.

Rules:

```text
No Provider-specific logic in Core
No Provider implementation imported by Router
No hardcoded Provider assumptions
```

### If no real Providers exist yet

If `ai_providers` or real provider implementations are missing, Phase 4/5
creates provider framework scaffolding and disabled diverse templates only.
Do not block the project and do not fake provider functionality.

Reference: `final_docs_v3/31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md`.

---

## 8. Phase 5 — Provider Migration

One provider at a time:

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

Forbidden: migrating several providers at once and discovering the problem
at the end. Each Provider = a small recoverable unit.

---

## 9. Phase 6 — Model Registry

Build:

```text
Model Registry
Tier Registry
Capability Registry
Modality Registry
Model Profile
Model availability
Model benchmark metadata
```

Selection:

```text
AUTO
TIER
EXPLICIT_MODEL
```

Exit: the Registry can answer

> "Which models are eligible for task X?"

without any Provider HTTP.

---

## 10. Phase 7 — Credentials / Accounts / Pools

Platform:

```text
Provider
→ Platform Account Pool
```

User:

```text
Tenant/User
→ User Credential
```

Credential policy:

```text
platform_only
user_only
prefer_user
auto
```

Account lifecycle:

```text
READY
COOLDOWN
REFRESH_REQUIRED
AUTH_EXPIRED
INVALID
PENDING
DISABLED
```

Concurrency:

```text
Lease
Fencing
Cooldown
Rate limit
```

Exit: account selection is fully testable without AI.

---

## 11. Phase 8 — Router Engine

Build:

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

Bootstrap Router: a separate path for selecting the Router Model itself.

Important — the Router:

```text
DOES:
decide

DOES NOT:
execute
```

Exit — tests cover:

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

## 12. Phase 9 — Execution Graph

Build:

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

Strategies:

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

Important: the Workflow Runtime owns state. We do not build our own
Workflow Engine.

---

## 13. Phase 10 — Async Fabric

Build:

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

Lease/Fencing is only for exclusive resources — not for every Job.

Exit — tests:

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

## 14. Phase 11 — Personal Context Engine

Build:

```text
Conversation State
User Profile
Project Context
Learned Preferences
Retriever
Context Composer
```

Memory rules:

```text
Evidence
Confidence
Scope
Relevance
```

Context hierarchy (by effective scope):

```text
Conversation
Project
Workspace
User
Global
```

Important: Memory ≠ Training Data.

---

## 15. Phase 12 — Role System

System Roles: admin-controlled.
Custom Roles: user/project created.

Role profile:

```text
identity
objective
required capabilities
preferred skills
behavior policies
output contract
runtime override
```

Security: a Custom Role never grants permissions.

---

## 16. Phase 13 — Skill System

Import sources:

```text
https://github.com/mattpocock/skills
https://www.aihero.dev/skills-wayfinder
https://github.com/amElnagdy/review-skills
```

Import lifecycle:

```text
imported
→ scanned
→ validated
→ reviewed
→ approved
→ active
```

Local copy: every external Skill becomes a Local Version.

Resolver:

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

## 17. Phase 14 — Tool Fabric

Tool contract:

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

Locations:

```text
server
client
hybrid
```

Client Runtime:

```text
Browser
Filesystem
Terminal
IDE
Local Project
```

Device Trust:

```text
pair
trust
revoke
rotate
```

Security: every Tool Call passes through the Capability Firewall.

---

## 18. Phase 15 — Evaluation / Verification

Build:

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

Levels:

```text
RAW
EVALUATED
VALIDATED
VERIFIED
GOLD
```

User: sees the result only, by default.
Admin: sees the details.

---

## 19. Phase 16 — Plans / Usage / Billing

Units:

```text
Simple = 1
Medium = 2
Complex = 3
```

Values are configuration-driven.

Flow:

```text
Estimate
→ Reserve
→ Execute
→ Settle
```

Cost Snapshot: fixed at Task start.

Internal retry/failover never multiplies the user's cost.

---

## 20. Phase 17 — Learning / Model Evolution

Pipeline:

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

Admin dashboard shows:

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

User Feedback: signal only.
Training eligibility: separate from Feedback.

---

## 21. Phase 18 — Public API

Main:

```text
POST /v1/execute
```

Supporting:

```text
GET /v1/executions/{id}
GET /v1/models
GET /v1/skills
GET /v1/usage
POST /v1/webhooks
```

Features:

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

## 22. Phase 19 — Admin Control Plane

Admin modules:

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

Configuration lifecycle:

```text
Draft
→ Validate
→ Preview
→ Publish
→ Observe
→ Rollback
```

Security invariant — Admin config can never disable:

```text
tenant isolation
secret guarantees
core crypto rules
security boundaries
audit integrity
```

---

## 23. Phase 20 — Observability

OpenTelemetry:

```text
logs
metrics
traces
```

Adaptive tracing:

```text
normal → reduced
error → full
slow → full
debug → full
high value → full
```

Audit: only security-sensitive events require the highest protection level.

---

## 24. Phase 21 — Security Hardening

API:

```text
TLS
rate limits
size limits
validation
CORS/CSRF where applicable
```

AI:

```text
prompt injection
indirect injection
data exfiltration
excessive agency
output validation
tool abuse
```

Supply chain:

```text
skill provenance
dependency validation
artifact integrity
```

Tenant:

```text
application
data layer
DB enforcement
```

---

## 25. Phase 22 — Testing / Chaos

Functional:

```text
unit
integration
contract
e2e
```

Architecture:

```text
dependency boundaries
forbidden imports
contract validation
```

Security:

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

Reliability:

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

Load:

```text
normal
peak
burst
soak
stress
```

---

## 26. Phase 23 — Production

Initial topology:

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

Scaling:

```text
API → horizontal
Workers → queue-driven
Provider pools → capacity-driven
Evaluation → separate worker pool
Learning → isolated compute
```

Multi-region: DR first. Active/Active only when requirements justify it.

---

## 27. Phase 24 — Final Validation

This is not "run tests and done". We must prove:

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

Then:

```text
Production Readiness = PASS
```

---

## 28. Micro-task Protocol

The most important daily execution rule. Every task must be:

```text
T-{phase}-{number}
```

Example:

```text
T-04-017
Create provider health contract
```

And it must have:

```text
objective
dependencies
files expected
verification command
acceptance criteria
commit message
```

There is no:

> "Build the Provider System."

There is:

> "Create provider health contract and its validation tests."

---

## 29. Task Output Contract

After every micro-task:

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

Never use the word `DONE` before a successful, verified commit.

---

## 30. Commit / Interrupt / Recovery Discipline

The full commit protocol, commit verification commands, interrupt protocol,
uncommitted-work protocol, and recovery-from-failure flow are owned by
`final_docs_v3/40_ENGINEERING_PROTOCOL.md` §9–§10 and are not restated here.
Summary for planning purposes:

```text
Implement → Test → Verify → Commit → Verify commit → Update state → Generate next plan
Interrupted before commit ⇒ trusted state = previous commit; working tree = Recovery Candidate
Never reset/checkout/delete uncommitted work before inspect/classify/verify/preserve
```

"Update state" and "generate next plan" both mean: update
`PROJECT_EXECUTION_STATE.md` at the verified checkpoint (D10/D11). The next
task lives inside the state file (`NEXT_TASK` block) — not in a separate
`NEXT_PLAN.md`.

---

## 31. Scope Control

If the Agent discovers an improvement outside the current task:

```text
Record it — do not implement it
```

unless it is a blocker for the current task.

Recording target (per D10/D11 — no extra mutable ledger files): append the
improvement/gap to `final_docs_v3/60_DECISION_LOG.md` (once it exists; until
then, the SESSION NOTES block of `PROJECT_EXECUTION_STATE.md`). The v2 rule
itself (record, don't implement, blocker exception) is unchanged.

---

## 32. Architecture Change Protocol

If a decision must change:

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

There is no:

> "I changed it because it is better."

without an ADR. (Full ADR protocol: `40_ENGINEERING_PROTOCOL.md` §8.)

---

## 33. Gate System

Every Gate:

```text
Entry
→ Build
→ Verify
→ Exit
```

We never advance to the next phase if:

```text
critical tests fail
security gate fails
contract incomplete
uncommitted critical work exists
```

(Full G0–G21 gate list and the gate contract: `40_ENGINEERING_PROTOCOL.md` §7.)

---

## 34. Definition of Done (Final)

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

## 35. Final Project Success Criteria

The project is not successful merely because "the API works". It must be:

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

## 36. Build Prompt Requirement

The Agent that builds the project is not merely asked to "build the system",
but to:

> **Work per the Engineering Protocol and this Implementation Plan, in small
> units, where every unit ends with verification + commit + state update.**

That is the difference between an AI that writes a lot of code and an AI
that runs a **resumable, reviewable, extensible engineering process**.
(The authoritative build prompt: `final_docs_v3/50_AGENT_EXECUTION_PROMPT.md`.)

Before actual implementation starts, this baseline is considered sufficient;
no open architectural question blocks the start. During implementation the
documents never replace reality:

```text
Git → the truth
Tests → the evidence
Protocol → the rules
State → the navigation
Next task (in state file) → the next step
```

Even after an interruption without commit, a new session, a new AI, or a new
engineer, the project remains resumable from the **last trusted commit**,
inspecting any pending changes instead of losing them or building on false
assumptions.

---

# PART II — MVP ROADMAP

---

## 37. MVP Philosophy

Build the smallest system that proves the architecture without overbuilding.

MVP must validate:

```text
unified API
provider abstraction
model registry
basic routing
execution records
memory basics
admin config basics
usage accounting
security boundaries
recovery protocol
```

---

## 38. MVP Scope

### Include

```text
Auth: email/password + verification
Tenant: personal tenant per user
API: POST /v1/execute + execution status
Provider framework: 1-2 providers
Model registry: static + admin editable
Router: simple policy + tier + explicit model
Execution: single + pipeline basics
Memory: conversation + user preference basics
Roles: system roles only
Skills: local approved skills only
Tools: GitHub read-only optional
Evaluation: basic deterministic + model judge
Usage: task units estimate/reserve/settle
Admin: users/plans/models/providers/routing basics
Observability: logs + traces + audit events
Recovery: Git + single-state-file protocol (D10/D11)
```

### Exclude Initially

```text
full client runtime
terminal/local filesystem tools
automatic training promotion
complex workflow designer
multi-region active/active
Kafka
full skill marketplace
advanced billing payments integration
```

---

## 39. MVP Phase 0 — Repo / Governance

Deliver:

```text
engineering protocol
implementation plan
ADR templates
single state file (PROJECT_EXECUTION_STATE.md)
CI basic checks
```

Exit:

```text
repo initialized
first commit
state system works
```

---

## 40. MVP Phase 1 — Contracts

Deliver:

```text
API schemas
core domain types
provider contract
model contract
execution contract
error contract
```

Exit:

```text
contract tests pass
schemas validated
```

---

## 41. MVP Phase 2 — Identity / Tenant / Security

Deliver:

```text
user registration
email verification
login/session
personal tenant
basic RBAC/entitlements
capability firewall skeleton
```

Exit:

```text
auth tests pass
tenant isolation tests pass
```

---

## 42. MVP Phase 3 — Storage / Observability

Deliver:

```text
PostgreSQL migrations
Redis setup
object storage abstraction
secret manager abstraction
basic audit logs
OpenTelemetry setup
```

---

## 43. MVP Phase 4 — Provider + Model MVP

Deliver:

```text
provider registry
one provider adapter
model registry
provider-model binding
credential reference
health checks
```

---

## 44. MVP Phase 5 — Routing + Execution MVP

Deliver:

```text
POST /v1/execute
router simple scoring
single execution
pipeline execution
execution status endpoint
usage reservation/settlement
```

---

## 45. MVP Phase 6 — Context / Roles / Skills MVP

Deliver:

```text
conversation history
basic user preferences
system roles
local skills
context composer
```

---

## 46. MVP Phase 7 — Evaluation + Admin MVP

Deliver:

```text
basic evaluation policy
model judge optional
admin models/providers/plans/routing
learning dashboard placeholder
```

---

## 47. MVP Phase 8 — Hardening

Deliver:

```text
security tests
provider failure tests
rate limit tests
queue/retry tests
secret redaction tests
load smoke tests
```

---

## 48. MVP Definition of Done

```text
API can execute a request end-to-end.
At least one provider works through adapter contract.
Router chooses model/provider via policy.
Execution is recorded and recoverable.
Usage is reserved and settled.
Basic evaluation record exists.
Admin can enable/disable model/provider and adjust plan.
Tenant isolation tests pass.
No secrets in logs.
Every phase committed and documented.
```

---

## 49. If No Real AI Providers Exist Yet

The MVP may begin with provider scaffolding only if real provider details
are not ready.

Allowed:

```text
Provider contracts
Provider registry
Manifest schema
Common provider errors/capabilities
Disabled diverse provider templates
Scaffold validation tests
Pending real providers list
```

Forbidden:

```text
Fake working providers
Invented credentials
Invented live model names
Templates marked active
Provider-specific shortcuts inside Core
```

Use: `final_docs_v3/31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md`.

End-to-end AI execution is not considered complete until at least one real
provider is implemented and verified.

---

# PART III — FINAL vs MVP vs FUTURE MAP

---

## 50. Explicit Separation

| Capability area | MVP (Part II) | FINAL (Part I) | FUTURE (deferred, requirements-gated) |
|---|---|---|---|
| Auth / Tenant | email/password + verification, personal tenant | full identity, device identity, entitlements | SSO/enterprise IdP if required |
| Providers | 1–2 adapters (or scaffold-only) | full provider migration, pools, credential policies | provider marketplace |
| Models | static registry + admin edits | full registries (tier/capability/modality/profile) | automated benchmark ingestion |
| Routing | simple policy + tier + explicit | full Router Engine + bootstrap router + fallbacks | learned routing optimization |
| Execution | single + pipeline | all strategies incl. debate/map-reduce/agent/hybrid | complex workflow designer |
| Async fabric | queue/retry basics | full outbox/DLQ/backpressure/fair scheduling | Kafka (only at proven scale — see 40 §5) |
| Memory | conversation + preferences | full Personal Context Engine + hierarchy | — |
| Roles | system roles only | custom roles + runtime override | — |
| Skills | local approved only | import lifecycle + resolver | full skill marketplace |
| Tools | GitHub read-only optional | full Tool Fabric + Client Runtime + Device Trust | terminal/local filesystem tools (client runtime GA) |
| Evaluation | deterministic + optional judge | all graders + counter-evaluation + levels | — |
| Learning | dashboard placeholder | full pipeline shadow/canary/promotion | automatic training promotion |
| Usage/Billing | units estimate/reserve/settle | plans + cost snapshots + failover cost rules | advanced payments integration |
| API | execute + status | full public API surface + webhooks | — |
| Admin | basics (users/plans/models/providers/routing) | all modules + config lifecycle | — |
| Deployment | single region | multi-AZ HA + DR region | multi-region active/active |

Rule: an item moves from FUTURE to a plan phase only through the
Architecture Change Protocol (§32) with an ADR — never silently.

---

## 51. Traceability (V2 → V3) and Decision Ledger

```text
v2 14 §1        → §1  (15 non-breakable rules, verbatim; D10/D11 note for rules 14–15)
v2 14 §2        → §2  (repo layout; engineering/state/ removed per D10/D11 — explicit)
v2 14 §3–§27    → §3–§27 (Phases 0–24, all content preserved; provider refs
                  repointed to v3 successors 30/31 — same targets post-migration)
v2 14 §28       → §28 (micro-task protocol, verbatim)
v2 14 §29       → §29 (task output contract, verbatim)
v2 14 §30–§31, §34 → §30 (summary + pointer to 40 §9–§10, the owning authority;
                  no rule changed)
v2 14 §32       → SUPERSEDED by D10/D11 (legacy resume flow reading multiple
                  state files) — successor: 40 §11 + PROJECT_EXECUTION_STATE.md
                  resume protocol; recorded here and in the v2 banner
v2 14 §33       → SUPERSEDED by D10/D11 (NEXT_PLAN.md as separate mutable
                  file) — next task lives in the state file NEXT_TASK block (§30)
v2 14 §35       → §31 (scope control rule preserved; FUTURE_IMPROVEMENTS.md
                  file target superseded by D10/D11 → 60_DECISION_LOG.md /
                  state notes — explicit, not silent)
v2 14 §36       → §32 (architecture change protocol, verbatim)
v2 14 §37       → SUPERSEDED by D10/D11 (dedicated FUTURE_IMPROVEMENTS.md /
                  ARCHITECTURE_GAPS.md mutable ledgers) — the evolution-without-
                  scope-creep intent is preserved via §31
v2 14 §38       → §33 (gate system, verbatim + pointer to 40 §7)
v2 14 §39       → SUPERSEDED by D10/D11 (handoff via CURRENT_STATE/HANDOFF/
                  PHASE_STATE/ACTIVE_TASK files) — handoff = state-file update
                  at verified checkpoint (40 §11)
v2 14 §40       → §34 (definition of done, verbatim)
v2 14 §41       → §35 (success criteria, verbatim)
v2 14 §42       → SUPERSEDED by D10/D11 (static resume prompt referencing
                  engineering/state/*, HANDOFF, NEXT_PLAN) — successor:
                  52_RESUME_AND_PROGRESS_PROTOCOL.md (pending T-DOC-012) +
                  README resume contract; the still-valid core rules (Git =
                  only truth; verified+commit = progress; never reset blindly)
                  already live in 40 §9–§11
v2 14 §43 + closing note → §36 (build prompt requirement + reality-over-docs
                  closing, preserved; NEXT_PLAN reference replaced per D10/D11)
v2 15 §1        → §37 (MVP philosophy, verbatim)
v2 15 §2        → §38 (include/exclude, verbatim; "Recovery: Git/state/handoff
                  protocol" rewritten to D10/D11 wording — explicit)
v2 15 §3–§11    → §39–§47 (MVP phases 0–8; Phase 0 "state files" → single
                  state file per D10/D11 — explicit)
v2 15 §12       → §48 (MVP DoD, verbatim)
v2 15 §13       → §49 (scaffold-only start, verbatim; policy ref repointed to
                  v3 31, its authoritative successor)
Language: Arabic narrative normalized to English; all decision blocks verbatim.
No phase, scope decision, exclusion, DoD item, or rule was dropped.
All supersessions are D10/D11-scoped and recorded here + in the v2 banners.
```
