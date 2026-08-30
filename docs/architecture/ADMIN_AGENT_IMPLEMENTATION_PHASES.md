# ADMIN AGENT IMPLEMENTATION PHASES

**Document C of 4.** Companions:
[A — Master Plan](ADMIN_AGENT_UI_UX_MASTER_PLAN.md) ·
[B — Coverage Matrix](ADMIN_UI_BACKEND_COVERAGE.md) ·
[D — UI Principles](ADMIN_AGENT_UI_PRINCIPLES.md).

**Status:** PLANNING ONLY. Nothing in this document is authorized to build.
Each phase requires separate operator authorization ("CONTINUE") before any
work starts. **Baseline:** `main` @ `5c1410b…`.

---

## 1. PHASE COUNT AND ITS JUSTIFICATION

**Four phases.** Why exactly four, and not more or fewer:

- **Fewer than 4 is dishonest scoping:** auth + evidence seams (AA-1) are
  backend work in `apps/`; the Agent + UI shell (AA-2) is frontend + a new
  app service; write-path governance (AA-3) changes the risk class from
  read to mutate; the source-change track (AA-4) requires a NEW operator
  authorization by mandate §4 and design review before any code. These four
  boundaries are real risk/authorization boundaries, not arbitrary slices.
- **More than 4 would be artificial:** e.g. splitting "Agent R0" from
  "Agent R1" adds a phase boundary with no new risk class (R1 is a real
  execution through an already-tested path under the same principal budget);
  splitting each seam into its own phase multiplies gate ceremony without
  changing what is reviewable. The mandate demands the *minimum practical*
  count; four is where every boundary earns its ceremony.

Dependency chain: **AA-1 → AA-2 → AA-3 → AA-4** (strict; no parallelism
needed at this scale, and serial phases keep the review gates meaningful).

---

## 2. UNIVERSAL GATE LIFECYCLE (applies to every phase)

```text
Reality Check → Implement → Test → Review → (fix in-scope) → Re-test
→ Update PROJECT_EXECUTION_STATE.md → Commit → Fetch → Push
→ Verify Remote → Short Report → WAIT FOR OPERATOR "CONTINUE"
```

- **Reality Check** = re-verify on the live repo every fact the phase relies
  on (the doc A discipline: counts by command, not memory).
- **In-scope failure** → classify → fix → re-test.
- **Failure requiring a frozen-component change, scope expansion, or
  architectural reinterpretation** →
  **STOP → FACT / IMPACT / OPTIONS / RECOMMENDATION / OPERATOR DECISION.**
- Frozen components (never touched by any phase): G1–G4 gateway,
  `ProviderAdapterPort`, the 12 import-linter contracts, core invariants,
  the existing admin change lifecycle semantics.
- Standing verification for every phase: full hermetic pytest green, mypy
  strict on touched packages, ruff clean, `lint-imports` 12 kept,
  `check_repo.sh` PASS (where present), plus the phase's own acceptance
  criteria.

---

## 3. PHASE AA-1 — API SEAMS (auth + evidence + system surfaces)

| Field | Content |
|---|---|
| **Objective** | Make an admin UI *possible* and *honest*: per-request identity, and HTTP access to the evidence stores every honesty feature depends on. |
| **Scope (closed)** | IDN-1 (auth endpoints binding `InMemoryIdentityService` sessions → per-request Principal), EXE-1 (executions list), AUD-1 (admin audit read), SYS-1 (platform healthz + system read-model), USG-2 (usage drill-down read), WBH-1 (webhook subscription list/delete). All are thin surfacings of PROVEN core machinery (doc B §5). |
| **Explicit non-scope** | No new core modules. No persistence repositories. No notification model (that is AA-3). No Agent. No UI. |
| **Dependencies** | none (first phase). |
| **Allowed files/modules** | `apps/api/**` (new routes + store protocol extension per the T-IMPL-072 injectable pattern), `apps/composition/**` (wiring), `tests/api/**`, `tests/identity/**` (HTTP-binding tests), state file. `core/` untouched except NO-OP (if a core change appears necessary → STOP rule). |
| **Acceptance criteria** | (1) login→session→Principal round-trip proven by test; non-admin principals denied on all `/v1/admin/*` exactly as today; (2) executions list is tenant-scoped, filterable, anti-enumeration preserved; (3) audit read surfaces the port verbatim, admin-gated; (4) healthz reports only process-local truths, labeled; (5) every new route has deny-by-default tests in the t033/t034 adversarial style; (6) full suite green; route count delta documented by command. |
| **Verification** | route enumeration grep before/after; hermetic suite; adversarial tests pass; no import-contract change (still 12). |
| **DONE** | all criteria + gate lifecycle completed + operator report delivered. |

---

## 4. PHASE AA-2 — ADMIN AGENT SERVICE (R0+R1) + UI SHELL

| Field | Content |
|---|---|
| **Objective** | The conversational control interface exists: Agent answers from real state and runs real labeled tests; the 7-surface UI shell renders evidence honestly. |
| **Scope (closed)** | AGT-1: new `apps/admin_agent/` service — conversation loop, typed tool registry (config data), deterministic dispatcher enforcing tool classes R0/R1 only (R2/R3 tools NOT registered this phase); model access **through the platform's own execute path** (the Agent is itself a governed consumer — no side-channel LLM calls). UI: the 7 surfaces of doc D §2 in read-only + Agent + R1 test mode; live-trace view per doc A §6 (post-hoc, "as recorded"); diagnosis rendering per doc A §7 (tiered, evidence-cited). |
| **Explicit non-scope** | No mutations of any kind (no R2). No notifications. No Telegram. No source-change anything. No streaming/async backend work. |
| **Dependencies** | AA-1 (identity + evidence routes). |
| **Allowed files/modules** | `apps/admin_agent/**` (new), UI project directory (new, location decided at phase start — outside `core/`/`providers/`/`infrastructure/`), `apps/composition/**`, `tests/admin_agent/**`, state file. |
| **Acceptance criteria** | (1) every Agent answer that states a platform fact carries a machine-checkable evidence reference (schema-enforced); (2) R1 executions are real, budget-bounded, labeled via `RequestContext`, and appear in the executions list; (3) prompt-injection suite: adversarial tool outputs cannot cause a tool call outside the registered R0/R1 set (deterministic dispatcher test, not prompt test); (4) secrecy suite: Agent outputs scanned for the R4-forbidden classes (slugs/tokens/URLs/secret material) — G4 leak-test pattern extended; (5) UI renders ONLY backend-substantiated states — a checklist review maps every rendered status to a contract value (doc A §6/§8 honesty rules as testable criteria); (6) full suite green. |
| **Verification** | dispatcher unit tests; leak scan; honesty checklist review recorded in the phase report. |
| **DONE** | all criteria + gate lifecycle + operator report. |

---

## 5. PHASE AA-3 — GOVERNED WRITE PATH (R2) + NOTIFICATIONS

| Field | Content |
|---|---|
| **Objective** | The Agent (and forms) can propose config changes through the EXISTING lifecycle; publish stays an explicit admin act; the admin is proactively informed. |
| **Scope (closed)** | R2 tools over the existing 7 lifecycle routes (draft/validate/preview; publish button UI-side calling the existing publish route); NTF-1 poll-based notification read-model (6 categories, doc A §12) + center UI + toasts; Changes & Audit surface completed (lifecycle timeline + audit trail via AUD-1); SKL-1 (skill-import review surface over the existing pipeline) and PRV-4 **only if** its persistence question is answerable without the repositories primitive — otherwise PRV-4 STOPS with the options report. |
| **Explicit non-scope** | No new lifecycle mechanics (the core service is used verbatim). No delivery/push notifications (poll only). No source changes. |
| **Dependencies** | AA-2. |
| **Allowed files/modules** | `apps/admin_agent/**`, `apps/api/**` (NTF-1/SKL-1 routes), UI, tests, state file. `core/admin/` READ-ONLY — any change desired there = STOP rule. |
| **Acceptance criteria** | (1) an Agent-drafted change is indistinguishable in the lifecycle from a form-drafted one (same records, same audit); (2) publish is impossible without the explicit UI act — proven by test that the Agent's tool registry contains no publish tool; (3) rollback UX renders backend denials (`RollbackUnavailable`) verbatim; (4) every notification links to its evidence record; zero notifications exist without a backing record; (5) full suite green. |
| **Verification** | lifecycle round-trip tests; audit-record assertions; notification-derivation tests (each category ← its source record type). |
| **DONE** | all criteria + gate lifecycle + operator report. |

---

## 6. PHASE AA-4 — SOURCE-CHANGE TRACK (design-first, operator-gated)

| Field | Content |
|---|---|
| **Objective** | The doc A §4 workflow becomes real: Inspect → Diagnose → Plan → Proposal → ADMIN REVIEW → APPROVAL → Apply → Test → Verify → Audit. |
| **Scope (gate 0 = design)** | This phase BEGINS with a design deliverable (SRC-1 service design: proposal object schema, branch/apply mechanics, gate-runner integration, FROZEN-COMPONENT stop mechanics, audit shape) submitted for **new operator authorization** before any implementation — the mandate's §4 requirement made structural. Implementation scope after authorization: proposal service + review UI + apply-on-branch + gate-runner evidence attachment. |
| **Explicit non-scope** | Push to main (never, R4). Auto-apply (never). Expanding an approved proposal (never — new proposal). |
| **Dependencies** | AA-3 (review UX pattern + notifications + audit surfaces). |
| **Allowed files/modules** | decided in the authorized design; candidate: `apps/source_change/**`, UI, tests, state file. |
| **Acceptance criteria (implementation gate)** | (1) a proposal cannot reach Apply without a recorded admin approval (audit `APPROVAL_DECISION`); (2) FROZEN-COMPONENT proposals are structurally unapprovable in the UI and produce the FACT/IMPACT/OPTIONS/RECOMMENDATION report; (3) Apply happens only on a branch; the revert path is part of the proposal record; (4) gate results (pytest/mypy/ruff/lint-imports) attach as raw evidence; (5) full suite green. |
| **DONE** | all criteria + gate lifecycle + operator report. |

---

## 7. RANKED FUTURE GENERIC-PRIMITIVE ROADMAP

Baseline = the assessment's X² ranking (`PLATFORM_CAPABILITY_ASSESSMENT.md`
§10–§11, commit `5f543ad`), re-scored through the Admin-Agent lens. **Nothing
here is authorized or implemented by this plan.** All are ADDITIVE at
existing seams per the assessment's orthogonality findings.

| Rank | Primitive | Current state (session-verified) | Why it matters to the Admin Agent | What it unlocks | Additive? | Arch impact | Dependencies | Priority | Recommended phase |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Postgres repositories** | schema PROVEN (12 migrations + parity tests); repositories MISSING (`grep -rln "Repository" infrastructure/` → none) | admin views stop being amnesiac (doc A risk R6); durable audit/exec/usage truth | multi-replica honesty; PRV-4 persistence; everything below | maximally — the definition of the existing port seams | none (bindings behind ports) | none | HIGH (prerequisite-shaped) | first post-AA capability phase |
| 2 | **Async/durable execution** (queue-backed runs; workflow binding later by ADR) | machinery PROVEN separately (queue/worker/lease/outbox/admission); API rejects async (422, `apps/api/app.py:449`); `WorkflowRuntimePort` unbound | live trace upgrades from post-hoc; approval gates can actually WAIT; long diagnostics runs | scheduled work; long-running anything; real `waiting_approval` | yes — enqueue at `apps/api`, workers drive existing `ExecutionService` | zero core-contract change for the queue slice; ADR when an engine binds | #1 for honest durability | HIGH | next |
| 3 | **Tool-execution runtime** (server-side first) | admission PROVEN (`core/tools/gate.py`); executor MISSING | Agent's R1/R2 reach grows to real actions under the existing deny-by-default cage | IDE/automation/product tools; makes the agent loop meaningful | yes — executor consumes gate verdicts; handlers live in apps/providers | new core module; no contract breaks; security review mandatory | #2 for long tools | HIGH | after #2 |
| 4 | **Agent loop** (bounded plan→act→observe) | MISSING; all governance surfaces it must obey PROVEN | converts platform classification honestly to "agent platform"; the Admin Agent itself could later ride it | agentic products; `ExecutionStrategy.AGENT` stops being vocabulary | yes — loop inside execution; model proposes, code disposes | new core module + structured-output validators land same-commit (R095 rule) | #3 hard, #2 for non-trivial runs | HIGH (strictly after 2–3) | after #3 |
| 5 | **Structured-output enforcement** | `OutputSpec.schema_` accepted, not enforced | Agent diagnosis/proposal schemas get platform-level enforcement | reliable machine-consumable model output everywhere | yes | validators attach at consuming surfaces (R095 binding rule) | lands WITH #4's surfaces | MEDIUM (bundled) | with #4 |
| 6 | **Event/scheduler primitive + webhook delivery** | registration PROVEN; delivery/schedule MISSING | notifications upgrade from poll to push; health probes become scheduled; Telegram delivery channel | automation products; NTF push; background health (doc A §8 honesty upgrade) | yes — outbox→worker delivery; schedule = worker enqueuing on time policy | SSRF validation duty attaches same-commit | #2 | MEDIUM | after #4 |
| 7 | **Streaming (SSE)** | contract shapes only; API rejects `stream=true` | live trace becomes truly live; Agent responses stream | chat/IDE UX competitiveness | yes — API + adapter capability flag | per-provider variance | none hard | MEDIUM | flexible |
| 8 | **Artifact/workspace abstraction** | `ObjectStoragePort` + S3 binding PROVEN; workspace concept MISSING | Agent test artifacts; source-change workspaces | IDE/content products | yes — layer above the port | new core surface | #1 | LOW-MEDIUM | later |
| 9 | **Richer approval workflow** (queue/endpoints/resume for `waiting_approval`) | states + verdicts PROVEN; operational workflow MISSING | approval gates inside executions complement the AA-3 publish gate | human-in-the-loop products | yes — queue + resume via `signal_approval` port shape | rides #2 | #2 | MEDIUM | with/after #6 |
| 10 | **Project entity** (policy-bound scoping/budget/membership inside a tenant) | vocabulary only (doc A §10) | Tenants & Usage surface gains true project management | project-scoped budgets/roles/memory | yes — new entity + policy wiring | design decision first (backend-first, never UI-invented) | #1 | LOW | operator-triggered |

**Dependency spine (unchanged from the assessment, re-affirmed):**
repositories → async → tool-runtime → agent-loop; events/streaming hang off
async. The Admin Agent (AA-1…AA-4) deliberately requires NONE of these — it
is built on what is PROVEN today, which is what makes the 4-phase plan small
and honest.
