# 02 — Final Architecture Baseline
## AI Orchestration Platform

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-006)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

---

## 1. Architecture Statement

النظام عبارة عن منصة Orchestration مستقلة، حيث تكون النماذج والمزودون موارد تنفيذ، وليست هي العقل الرئيسي.

```text
External Products
   ↓
Public API
   ↓
Identity / Auth / Tenant Context
   ↓
Authorization + Entitlements + Capability Firewall
   ↓
Core Orchestration
   ↓
Router + Context + Role + Skill Resolver
   ↓
Execution Planner
   ↓
Durable Workflow Runtime
   ↓
Models + Providers + Accounts + Tools
   ↓
Evaluation / Verification
   ↓
Response + Usage + Learning Signals
```

---

## 2. Non-Breakable Architecture Invariants

```text
1. Core remains provider-agnostic.
2. Core remains model-agnostic.
3. Model ≠ Provider ≠ Account.
4. Platform credentials ≠ User-owned credentials.
5. Router decides; Execution executes.
6. Workflow Runtime owns workflow state.
7. LLM is never a security authority.
8. Unknown permission/capability defaults to DENY.
9. Memory is not training data by default.
10. Verified Intelligence requires evaluation and eligibility.
11. Admin configuration cannot break security invariants.
12. Extensibility uses contracts, registries, adapters.
13. Runtime policies are configurable/versioned/audited.
14. Significant architecture changes require ADR.
15. Git commit + verification is the only trusted progress.
```

---

## 3. System Modules

```text
apps/
  api/
  admin/
  client-runtime/

core/
  contracts/
  orchestration/
  routing/
  execution/
  context/
  roles/
  skills/
  tools/
  evaluation/
  learning/
  usage/
  policies/

providers/
  registry/
  common/
  <provider_modules>/

infrastructure/
  db/
  cache/
  queues/
  workflows/
  object_storage/
  secrets/
  observability/

engineering/
  state/
  adr/
  gates/
  recovery/
  handoff/
```

---

## 4. Core Responsibilities

Core may:

- validate normalized requests.
- orchestrate routing and execution.
- compose context.
- apply policies.
- create execution plans.
- record usage/evaluation.

Core must not:

- call provider HTTP directly.
- manage provider cookies directly.
- read raw secrets directly.
- bypass authorization.
- embed provider-specific logic.
- hardcode business policies.

---

## 5. Recommended Initial Technology Shape

```text
Modular Monolith
PostgreSQL as source of truth
pgvector for semantic retrieval
Redis Streams for runtime queues
Durable workflow runtime
Object storage for files/artifacts
Secret Manager/KMS for credentials
OpenTelemetry for observability
Workers for async execution
```

Kafka, full microservices, and active/active multi-region are postponed until justified by scale.

---

## 6. Production Baseline

```text
Single Region + Multi-AZ
Stateless API
HA PostgreSQL + backups + PITR
HA Redis
Object Storage
Autoscaled workers
DR region readiness
```

---

## 7. Architecture Quality Bar

Any new feature must answer:

```text
What contract does it implement?
What registry owns it?
What policy controls it?
What permissions does it require?
What tests prove it?
What audit trail records it?
How is it rolled back?
Does it break any invariant?
```
