# 40 — Engineering Protocol
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-010
SUPERSEDES:
  final_docs_v2/13_MASTER_ENGINEERING_PROTOCOL.md
MIGRATION_TYPE: REWRITE-COMPRESS (defect-justified)
REWRITE_JUSTIFICATION:
  v2 13 was 2385 lines. It duplicated architecture content now owned by
  v3 01–31, and it mandated a legacy multi-file mutable state scheme
  (STATE.md / PROGRESS.md / ACTIVE_TASK.md / BLOCKERS.md / VERIFY.md /
  RECOVERY.md / HANDOFF/) that conflicts with the single-state decision
  D10/D11 (single mutable state = PROJECT_EXECUTION_STATE.md).
DECISION_PRESERVATION:
  Every engineering rule with execution value is retained here verbatim
  in meaning: core engineering principles, reliability model, storage
  roles, authentication baseline, observability rules, production and
  deployment decisions, Kafka policy, testing architecture, architecture
  boundary tests, engineering governance, Definition of Done, ADR
  protocol, Git safety, phase gates, implementation order, change
  management, recovery-from-failure flow, the 22 final architecture
  invariants, and the pre-change checklist.
  The ONLY superseded decisions are the legacy state-file scheme and the
  resume/handoff instructions built on it (v2 13 §39, §40, §41, §50) —
  explicitly superseded by D10/D11, recorded in §11 of this document.
  No decision was changed silently.
RELATED_AUTHORITY:
  Architecture + invariants baseline:  final_docs_v3/02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md
  Implementation plan / phase detail:  final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md (successor of v2 14+15)
  Resume / progress protocol:          final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md (authoritative since T-DOC-012)
  Single mutable project state:        docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
```

---

## 1. Purpose and Authority Scope

This protocol is the top engineering reference for HOW the platform is built:
principles, quality gates, testing, governance, Git discipline, change
management, and recovery.

WHAT the platform is (architecture, contracts, domain content) is owned by the
v3 architecture documents. This document does not restate them; §3 maps every
architecture subject to its owning document.

Any implementation must comply with this protocol.
Any new decision that conflicts with it is not applied directly; it must pass
Architecture Review and an ADR.

---

## 2. Core Engineering Principles

### 2.1 Contract First

No large implementation starts before a clear contract exists:

```text
Input
Output
Errors
Lifecycle
Version
Invariants
```

### 2.2 Extension Over Modification

Adding a Provider, Model, Skill, Tool, Role, Execution Strategy, Benchmark,
Evaluator, or Credential Type must happen via:

```text
Registry
Plugin / Adapter
Contract
Configuration
```

— never by editing Core logic each time.

### 2.3 Policy Over Hardcoding

Anything that represents business or runtime policy must not be hardcoded.
This includes:

```text
Model Tiers
Routing Weights
Fallback Rules
Task Costs
Plan Limits
Feature Availability
Skill Availability
Evaluation Thresholds
Learning Policies
Provider Preferences
```

Policies are:

```text
Configurable
Versioned
Validated
Audited
Rollbackable
```

### 2.4 Security Invariants Are Not Configurable

Admin configuration may never change:

```text
Tenant isolation mechanisms
Secret storage guarantees
Cryptographic requirements
Core security boundaries
Authentication invariants
Authorization invariants
Audit integrity guarantees
```

**Configurable ≠ Everything.**

### 2.5 Model-Agnostic Core

The Core depends on no specific model.

### 2.6 Provider-Agnostic Core

The Core depends on no specific provider.

### 2.7 Execution-Agnostic Core

The Core never assumes every task executes one way.

### 2.8 At-Least-Once + Idempotency

The system does not rely on global exactly-once delivery. The rule:

```text
At-Least-Once Delivery
+
Idempotent Operations
+
Durable State
+
Leases/Fencing where required
```

### 2.9 Evidence Before Confidence

An observation never becomes a fact without evidence.

### 2.10 Verified Learning Only

Data never enters a Verified/GOLD dataset because it "looks good". Required:

```text
Evidence
Evaluation
Verification
Eligibility
Sanitization
Governance
```

---

## 3. Architecture Authority Map (deduplication)

v2 13 restated large parts of the architecture. Those subjects are owned by
the following authoritative v3 documents; consult them, do not re-derive:

| Subject (v2 13 sections) | Authoritative V3 document |
|---|---|
| System vision, high-level architecture, module boundaries (§2–§4) | `02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md`, `03_DOMAIN_MODEL.md` |
| Model system: registry, selection modes, explicit-model rules (§5) | `11_MODEL_ROUTING_AND_MODEL_CONTROL.md` |
| Provider system, provider contract, provider inventory (§6) | `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md`, `31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md` |
| Accounts, credentials, secret storage, rate limits, health (§7–§9) | `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md` |
| Routing engine, pipeline, bootstrap router (§10) | `11_MODEL_ROUTING_AND_MODEL_CONTROL.md` |
| Execution graph, node contract, workflow ownership (§11) | `12_EXECUTION_GRAPH_AND_AGENT_MODE.md` |
| Personal context engine, memory scope, context composer (§13) | `13_MEMORY_AND_CONTEXT.md` |
| Role system (§14) | `03_DOMAIN_MODEL.md`, `12_EXECUTION_GRAPH_AND_AGENT_MODE.md` |
| Skill system, tool fabric, device trust (§15–§16) | `14_SKILLS_AND_TOOLS.md` |
| Evaluation, verification levels, graders, learning (§17–§18) | `22_EVALUATION_AND_LEARNING.md` |
| Plans, task units, billing flow, cost snapshot (§19) | `21_ADMIN_CONTROL_PLANE.md`, `10_API_CONTRACTS.md` |
| Authorization model, deny-by-default, Capability Firewall (§20, §27–§29) | `20_SECURITY_THREAT_MODEL.md`, `14_SKILLS_AND_TOOLS.md` |
| Multi-tenancy and isolation model (§22) | `20_SECURITY_THREAT_MODEL.md`, `02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md` |
| Admin control plane, config lifecycle, admin limits (§25) | `21_ADMIN_CONTROL_PLANE.md` |
| Public API endpoints and features (§26) | `10_API_CONTRACTS.md` |

The rules in §4–§6 below are engineering decisions from v2 13 that are NOT
owned by another v3 document; they remain authoritative here.

---

## 4. Reliability Engineering Rules

### 4.1 Async Execution Fabric

```text
Durable truth        = PostgreSQL + durable workflow state
Fast/background jobs = Redis Streams
```

### 4.2 Outbox

Any operation needing DB state + event publication:

```text
DB Transaction → Outbox → Publisher → Message Bus
```

### 4.3 Idempotency

Every operation that can run more than once must be logically idempotent
where required.

### 4.4 Leases + Fencing

Used ONLY where an exclusive resource exists, e.g.:

```text
Provider Account
Credential Resource
Exclusive Device Tool
```

Not for every job.

### 4.5 Backpressure

Required support:

```text
Admission Control
Queue Limits
Tenant Concurrency
Provider Concurrency
Fair Scheduling
Priority
Adaptive Scaling
```

### 4.6 Retry

Retry must be error-aware:

```text
Retryable
Non-Retryable
Retry-After
Provider Failover
```

### 4.7 Dead Letter

Terminally failed tasks go to a DLQ / recovery flow. No infinite retry.

---

## 5. Platform Engineering Baselines

### 5.1 Storage Roles

```text
PostgreSQL      = main source of truth
pgvector        = initial semantic retrieval
Redis           = cache, runtime, locks, leases, rate limits, streams,
                  short-lived state — NEVER a source of truth
Object Storage  = images, audio, video, files, datasets, large artifacts,
                  model artifacts
Secrets Manager = provider credentials, user API keys, refresh tokens,
                  other secrets
```

Secrets are never stored plaintext in DB or logs; metadata stores a
`credential_ref`, the secret lives in the Secret Manager / KMS-backed system.

### 5.2 Authentication Baseline

```text
Initial method   = Gmail + Password + Email Verification Code
Password         = Argon2id, unique salt, strong policy,
                   compromised-password checks
Sessions         = TLS, Secure, HttpOnly, SameSite, rotation,
                   re-authentication for sensitive actions
Verification code= one-time, short-lived, single-use, attempt-limited,
                   rate-limited, resend cooldown
Upgrade path     = Passkeys / MFA / TOTP must be addable without changing
                   core auth boundaries
```

### 5.3 Observability

```text
Standard   = OpenTelemetry
Data types = logs, metrics, traces, audit, execution records,
             evaluation evidence
Sampling   = adaptive: normal → reduced; error/slow/high-value/debug → full
```

Security-sensitive audit events are append-only, protected, long-retention,
tamper-evident where necessary. Not every log needs a hash chain.

### 5.4 Production Architecture

```text
Initial   = single region + multi-AZ
API       = stateless + horizontally scalable
Database  = primary + HA standby + backups + PITR
Redis     = HA
Workers   = autoscaled
Region failure = DR region (NOT active/active initially)
Future    = multi-region active/active only if requirements demand it
```

### 5.5 Deployment Philosophy

```text
Architecture stable; deployment topology flexible.
Start = Modular Monolith + Workers + Workflow Runtime.
Do NOT start with full microservices.
```

### 5.6 Kafka Policy

Kafka is not the default. Introduce it later only when event throughput,
replay, partitioning, or consumer scale justify the complexity.

---

## 6. Quality Gates and Testing

### 6.1 Testing Architecture

Unit tests alone are insufficient. Required test types:

```text
Unit
Integration
Contract
Provider
Router
Execution
Security
Tenant Isolation
Quota
Concurrency
Load
Stress
Soak
Chaos
Evaluation Regression
Model Regression
E2E
```

### 6.2 Architecture Boundary Tests

Boundaries must be mechanically checked:

```text
Core cannot import Provider internals
Router cannot execute HTTP
Model Registry cannot execute requests
Skill cannot bypass Tool Gateway
Memory cannot access Secrets
UI cannot access DB directly
```

### 6.3 Engineering Governance

Every new feature requires:

```text
Contract
Implementation
Tests
Security
Observability
Documentation
Rollback
```

### 6.4 Definition of Done

A feature is Done only with:

```text
Code + Tests + Security + Observability + Documentation
+ Compatibility + Rollback
```

---

## 7. Phase Gates and Implementation Order

Phases (detailed elaboration lives in `41_IMPLEMENTATION_PLAN_AND_MVP.md`):

```text
G0  Governance          G1  Contracts        G2  Identity/Security
G3  Storage             G4  Providers        G5  Models
G6  Accounts            G7  Router           G8  Execution
G9  Memory              G10 Roles            G11 Skills
G12 Tools               G13 Evaluation       G14 Billing
G15 Learning            G16 Public API       G17 Admin
G18 Observability       G19 Hardening        G20 Production
G21 Final Validation
```

Every gate defines:

```text
Entry Criteria
Tasks
Tests
Exit Criteria
Artifacts
Risks
```

Implementation order:

```text
Governance → Contracts → Identity/Security → Storage → Providers → Models
→ Accounts/Credentials → Router → Execution → Memory → Roles → Skills
→ Tools → Evaluation → Usage/Plans → Learning → Public API → Admin
→ Observability → Hardening → Production → Final Validation
```

No phase may bypass its gate. Never bypass security, testing, or phase gates.

---

## 8. Change Management and ADR Protocol

### 8.1 ADR Protocol

Every significant architectural decision records:

```text
Context
Alternatives
Decision
Reason
Consequences
Status
```

If a decision changes: `Supersedes ADR-X`.
No significant architecture change is allowed without an ADR.

### 8.2 Change Management Flow

Any architecture modification follows:

```text
Current Decision → Problem/Evidence → Impact Analysis → Alternatives
→ ADR → Approval → Migration Plan → Implementation → Verification
```

---

## 9. Git Safety and Commit Discipline

Before any important mutation:

```text
Inspect → Plan → Modify → Verify → Test → Update State → Commit when approved
```

Forbidden without explicit authorization AND verification:

```text
blind overwrite
force reset
destructive cleanup
assuming a previous command succeeded
```

Commit discipline:

```text
- one focused commit per verified task
- stage only related files
- no DONE without verification + local commit
- Git commit + verification is the only trusted progress
- local-only progress by default; push only when explicitly instructed
```

---

## 10. Recovery From Failure

If any of the following occurs:

```text
Session interruption
Process crash
Partial mutation
Unexpected Git change
Test failure
Build failure
```

do not continue directly. Return to:

```text
Known State → Reality Check → Reconcile → Repair → Verify → Resume
```

Critical rules:

```text
Never assume interrupted work succeeded.
Reality beats documentation: if the state record says one thing and the
filesystem says another, filesystem + Git + tests are the operational
truth — then fix the documentation.
```

---

## 11. Project State and Resume (SUPERSEDED SCHEME — D10/D11)

v2 13 §39 (Project State System), §40 (Resume Protocol), §41 (Session
Handoff), and §50 (Final Resume Command) mandated a multi-file mutable state
scheme:

```text
engineering/ STATE.md, PROGRESS.md, DECISIONS.md, ACTIVE_TASK.md,
BLOCKERS.md, VERIFY.md, RECOVERY.md, HANDOFF/
```

That scheme is EXPLICITLY SUPERSEDED by decisions D10/D11:

```text
- Single mutable project state = docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
- Resume/progress protocol     = final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md
                                 (authoritative since T-DOC-012)
- Decision records             = ADRs + 60_DECISION_LOG.md (successor of v2 18)
- Do not create additional mutable state files.
```

The still-valid intent of those sections is preserved by the successor
protocol: verify Git + filesystem reality before resuming, resume only from
the last verified state, never trust unverified claims, never modify
architecture decisions silently, and hand off by updating the single state
file at a verified checkpoint.

---

## 12. Final Architecture Invariants

These are the project's most important rules and must not be broken
(carried verbatim from v2 13 §47; the 15-invariant baseline in
`02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md` is the architecture-level
formulation; this is the extended engineering formulation — no conflict):

```text
1. Core remains provider-agnostic.
2. Model is separate from Provider.
3. Provider is separate from Account.
4. Platform Credentials are separate from User Credentials.
5. Router decides; Execution executes.
6. Workflow Runtime owns workflow state.
7. Memory is not Verified Intelligence.
8. User Preference is not Truth.
9. Skill is not automatically a Tool.
10. Tool is never trusted by default.
11. LLM is not a Security Authority.
12. Security boundaries are enforced outside the LLM.
13. Training data requires eligibility and verification.
14. Admin configuration cannot break security invariants.
15. All important configuration is versioned.
16. At-least-once + idempotency is the reliability model.
17. Tenant isolation is enforced at multiple layers.
18. Secrets never enter normal logs.
19. Public API hides internal implementation.
20. Significant architecture changes require ADR.
21. Interrupted work must be verified before resume.
22. New extensibility must prefer registries/contracts over Core modification.
```

---

## 13. Engineering Philosophy and Pre-Change Checklist

The project must NOT be "the most complex possible system". It must be:

> **The most capable possible system, with the least necessary complexity.**

Therefore:

```text
Strong Contracts + Simple Runtime Boundaries + Configurable Policies
+ Replaceable Implementations + Strict Security + Measured Evolution
```

Before ANY change, every engineer or AI must be able to answer:

```text
Does this violate a Contract?
Does it break a Boundary?
Does it need Config instead of Hardcode?
Does it need an ADR?
Does it affect Security?
Does it affect Tenant Isolation?
Is there a Test?
Is there a Rollback?
Can the implementation be replaced later?
Was the State updated?
```

If any answer is unknown, **do not start the change**.

---

# V2 → V3 TRACEABILITY AND DECISION LEDGER

| V2 13 Section | Disposition in V3 |
|---|---|
| §0 Purpose | Rewritten as §1 (authority scope clarified; architecture content pointed, not restated) |
| §1 Core Engineering Principles (1.1–1.10) | KEPT — §2, all ten principles preserved |
| §2–§11 System vision, architecture, modules, models, providers, accounts, rate limits, health, routing, execution | DEDUPLICATED — owned by v3 architecture docs; mapped in §3. Secret-storage rule kept in §5.1 |
| §12 Async Execution Fabric (12.1–12.8) | KEPT — §4 (durable truth, outbox, idempotency, leases/fencing, backpressure, retry, DLQ) |
| §13–§20, §22, §25–§29 Context, roles, skills, tools, evaluation, learning, plans, authorization, tenancy, admin, API, security fabric, AI security, Capability Firewall | DEDUPLICATED — owned by v3 docs; mapped in §3 |
| §21 Authentication | KEPT — §5.2 (Argon2id, sessions, verification codes, upgrade path) |
| §23 Storage | KEPT — §5.1 (PostgreSQL SoT, pgvector, Redis not SoT, object storage, secrets manager) |
| §24 Observability | KEPT — §5.3 (OTel, data types, adaptive sampling, append-only security audit) |
| §30 Production Architecture | KEPT — §5.4 (single region multi-AZ, HA DB + PITR, DR not active/active) |
| §31 Deployment Philosophy | KEPT — §5.5 (modular monolith + workers + workflow runtime) |
| §32 Kafka Policy | KEPT — §5.6 (Kafka not default) |
| §33 Testing Architecture | KEPT — §6.1 (all 17 test types) |
| §34 Architecture Tests | KEPT — §6.2 (all 6 boundary checks) |
| §35 Engineering Governance | KEPT — §6.3 |
| §36 Definition of Done | KEPT — §6.4 |
| §37 ADR Protocol | KEPT — §8.1 |
| §38 Git Safety Protocol | KEPT — §9 (incl. forbidden operations) |
| §39 Project State System | SUPERSEDED by D10/D11 — recorded in §11 (single state = PROJECT_EXECUTION_STATE.md) |
| §40 Resume Protocol | SUPERSEDED by D10/D11 — intent preserved via successor protocol; recorded in §11 |
| §41 Session Handoff | SUPERSEDED by D10/D11 — handoff = state-file update at verified checkpoint; recorded in §11 |
| §42 Phase Gates | KEPT — §7 (all gates G0–G21 + gate contract) |
| §43 Implementation Order | KEPT — §7 (full order preserved) |
| §44 Change Management | KEPT — §8.2 (full flow) |
| §45 Recovery From Failure | KEPT — §10 (full flow) |
| §46 Final Engineering Rule ("Reality beats documentation") | KEPT — §10 critical rules |
| §47 Final Architecture Invariants (22) | KEPT VERBATIM — §12 |
| §48 Final Project Philosophy | KEPT — §13 |
| §49 Final Engineering Standard (pre-change checklist) | KEPT — §13 (all 10 questions) |
| §50 Final Resume Command | SUPERSEDED by D10/D11 — references legacy state files; successor = resume protocol + README contract; recorded in §11 |
| Closing postscript ("three layers" / next-step narrative) | REMOVED_AS_NO_EXECUTION_VALUE — historical narrative; the implementation-plan step it announced is realized as v3 41 |

REWRITE-COMPRESS migration: 2385 lines → this document. No engineering rule
with execution value was dropped; no decision changed silently; the only
supersessions are §39/§40/§41/§50 under D10/D11, recorded above and in §11.
