# MASTER VISION v2 — FROZEN EXECUTION ROADMAP

**Status:** FROZEN (per directive §5 — re-order only on new material evidence)
**Derived:** 2026-08-30, from repository state `feature/platform-agent-vision`
@ `077ebc8` (AA-3 tip) + cherry-picked capability assessment (`5f543ad`).
**Authority:** MASTER VISION v2 directive (operator-issued, continuous
execution authorized; STOP only at §6 reserved decisions).

---

## 1. REALITY CHECK RESULT (evidence-verified this session)

| Fact | Evidence | Confidence |
|---|---|---|
| Baseline green: 1712 passed + 23 skipped, hermetic | pytest run this session on 077ebc8 | PROVEN |
| 20 tables + 12 migrations exist; repositories ABSENT | `infrastructure/db/tables.py` (742 lines, incl. `workspaces`, `projects`); `migrations/versions/0001..0012`; no `repositories/` dir | PROVEN |
| Queue/worker/outbox/lease/idempotency machinery real, unridden | `core/runtime/{ports,worker,outbox,admission}.py` read; API rejects async 422 (assessment §10.3) | PROVEN |
| Tool gate = admission only; executor ABSENT | `core/tools/gate.py` header; assessment §10.1 absence search | PROVEN |
| ObjectStoragePort + InMemory + S3 binding real; workspace concept ABSENT | `core/storage/ports.py`, `infrastructure/storage`, t073 tests | PROVEN |
| Prior assessment corroborates ranked primitives + dependency spine X²-5→X²-1→X²-2→X²-3 | `docs/architecture/PLATFORM_CAPABILITY_ASSESSMENT.md` §10/§11 (cherry-picked 5f1452d) | PROVEN |
| Postgres binaries now available in sandbox | `apt-get install postgresql` succeeded; `/usr/lib/postgresql/*/bin/initdb` present | PROVEN |
| `create_app` seams keyword-only, absent seam = absent routes | `apps/api/app.py:333–358` | PROVEN |
| Evaluation/memory/usage/context core packages complete for their contracts | package listings + prior phase records R085–R107 | PROVEN |

## 2. GAP ANALYSIS (vision surface → blocking primitive)

| Vision surface | Blocked by | Notes |
|---|---|---|
| Durable anything (honest Learning, Projects, history) | #1 repositories | schema proven, bindings absent |
| Long-running work, approval-that-waits, schedules | #2 async execution | machinery proven, uncomposed |
| "AI acts" (IDE/marketing/automation actions), Exercise Surface depth | #3 tool executor | gate proven, executor absent |
| Agent platform classification, ExecutionStrategy.AGENT | #4 agent loop (+ #5 structured output, R095 same-commit rule) | contracts proven |
| Context Validation Lab, Projects-with-files, artifacts | #8 Workspace primitive | ObjectStoragePort is the seam |
| Automation triggers, webhook egress | #6 events/scheduler | registration proven, delivery absent |
| Live progress UX | #7 SSE | contract shapes only |
| Capability Catalog / Exercise Surface / Test Scenarios / Regression Center / Self-Review / Impact Simulator | consumers of the above | apps-level composition once primitives land |
| R3 source-change workflow | §14 credential track (5 open items) | **hard STOP gate** |

## 3. GOVERNING INTERPRETATION (recorded for audit — P1 vs §6)

Historical fact: every shared primitive in this repo (17 Lane-B phases)
landed as an **additive new module inside `core/` or `infrastructure/`
through established extension seams**, without touching frozen components
(G1–G4 gateway, `ProviderAdapterPort`, the 12 import contracts, admin
lifecycle semantics, accepted ADRs). This roadmap therefore reads:

- **Ordinary work:** additive new modules (`core/tools/executor.py`,
  `core/agent/`, `core/workspace/`, `infrastructure/db/repositories/`)
  that implement existing ports/contracts or add new ones without
  modifying frozen surfaces. Import-linter must stay 12 kept / 0 broken.
- **STOP (§6):** any change that would *modify* a frozen component,
  an accepted ADR/contract, or alter import topology; any new external
  dependency (needs ADR); the §14 credential gate before R3 shipping;
  destructive actions.

## 4. THE FROZEN PHASE SEQUENCE (minimum finite — 9 phases)

Dependency spine respected: repositories → async → tool-runtime → agent
loop; workspace before Context Lab; events/streaming after async.

### V1 — Persistence Repository Layer (X²-5)
`infrastructure/db/repositories/` — Postgres bindings for the ports the
composition root already speaks (executions+nodes, usage ledger,
conversations/messages, memory, identity, audit, idempotency, admin
changes, skills/roles/models/providers registry persistence where
port-shaped). Hermetic gates stay hermetic; live-Postgres integration
tests env-gated (same pattern as S3/Vault smoke) using the now-available
sandbox Postgres. **Also resolves PRV-4** (the AA-3 STOP: registry
persistence design) per its recorded "ties to repositories" conditional.
Consumers: every durable surface; Learning honesty; multi-replica truth.

### V2 — Asynchronous Durable Execution (X²-1)
Flip the async path in `apps/api`: enqueue via existing outbox/QueuePort;
worker consumes and calls the existing `ExecutionService`; status via
existing `GET /v1/executions/{id}`. Zero core contract changes (assessment
X²-1). Durable-workflow-engine binding NOT in scope (would need ADR).

### V3 — Tool Execution Runtime (X²-2)
`core/tools/executor.py`: single execution path that (1) requires a gate
ALLOW verdict, (2) dispatches to handlers registered at composition
(handlers = apps/providers territory, never core), (3) normalizes
results/errors as data, (4) audits + accounts. Security-critical: "every
call passes the gate" as a structural property.

### V4 — Agent Execution Loop + Structured-Output Enforcement (X²-3 + #5)
Bounded plan→act→observe: model proposes structured output → platform
validates (R095 attach-at-surface validators land in the same commit) →
gate admits → executor runs → observation appended; bounded by
budget/step-count/admission. Model proposes; deterministic code disposes.
`ExecutionStrategy.AGENT` stops being vocabulary.

### V5 — Workspace Primitive + Projects First-Class (#8)
`core/workspace/` over ObjectStoragePort (files, listing, manifests) +
repositories for the existing `workspaces`/`projects` tables (V1 made
them durable). Shared primitive — serves IDE/marketing/research/Agent/
future apps; NOT the source-edit area; NOT admin-owned. Resource Control
rides existing usage seams (reuse, P2).

### V6 — Events, Scheduler, Webhook Delivery + SSE (X²-4 + X²-6)
Outbox→worker delivery loop for webhooks (SSRF URL-validation duty
attaches same-commit, R095 rule); schedule = worker that enqueues
executions on time policy; SSE progress at the API surface.

### V7 — Platform Surfaces (consumers)
Capability Catalog (honest closed-set Available/Inert/Unavailable) +
Capability Exercise Surface; Test Scenarios (saved, replayable) →
Regression Center pack; Context Validation Lab (workspace + async +
core/evaluation verdicts); Learning observability ("what changed since
last review" with evidence); Self-Review + Change Impact Simulator
(evidence-backed proposals, never auto-apply). Agent gains the
corresponding tools (P3: tools, not pages).

### V8 — R3 Source-Change Workflow — **§14 STOP EXPECTED**
Isolated proposed-change workspace → patch+tests+verification → admin
review → explicit approval → apply → verify → audit. **Gated on the 5
open credential items — surface the STOP before shipping.**

### V9 — Full Validation → Final Documentation (one doc, §13) → Final
Completion Report (§11) → STOP.

## 5. PER-PHASE GATES (every chunk)
`env -u GSK_API_KEY -u GROQ_API_KEY python -m pytest` · `ruff check` ·
`mypy` (recorded scopes) · `lint-imports` (12 kept / 0 broken) ·
secret/leak scan · Admin-Agent adversarial suites. Chunk lifecycle per
directive §8; state file updated per chunk; commit → push →
verify-remote (P9). Never on main; no merge to main without explicit
authorization.

## 6. STANDING STOP-WATCH LIST
1. New external dependency (e.g. a workflow engine) → ADR STOP.
2. Any frozen-component modification → STOP.
3. Import-linter topology change → STOP + ADR.
4. §14 credential track before V8 ships → STOP.
5. Destructive/data-loss operations → STOP.
