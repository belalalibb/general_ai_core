# ADMIN AGENT UI/UX MASTER PLAN

**Document A of 4** — the master plan.
Companions:
[B — ADMIN_UI_BACKEND_COVERAGE.md](ADMIN_UI_BACKEND_COVERAGE.md) (coverage matrix),
[C — ADMIN_AGENT_IMPLEMENTATION_PHASES.md](ADMIN_AGENT_IMPLEMENTATION_PHASES.md) (phase roadmap),
[D — ADMIN_AGENT_UI_PRINCIPLES.md](ADMIN_AGENT_UI_PRINCIPLES.md) (IA + design system).

**Status:** PLANNING ONLY. This document authorizes nothing and implements nothing.
**Baseline:** `main` @ `5c1410b592a0e864f83fd204b8ad028f357bd749` (G1–G4 gateway
track merged, ADR-0008 ACCEPTED and CLOSED — not re-litigated here).
**Date:** 2026-08-30.

**Session-verified baseline facts** (every count below reproduced by a command
in the planning session, not copied from any prior document):

| Fact | Value | Command |
|---|---|---|
| main HEAD | `5c1410b592a0e864f83fd204b8ad028f357bd749` | `git rev-parse HEAD` after `git fetch origin`; matches `git ls-remote origin refs/heads/main` |
| Import-linter contracts | **12 kept, 0 broken** | `lint-imports` → "Contracts: 12 kept, 0 broken"; `grep -c '^\[\[tool.importlinter.contracts\]\]' pyproject.toml` → 12 |
| Platform tests | **1620 collected; 1597 passed + 23 skipped** (hermetic, `env -u GSK_API_KEY -u GROQ_API_KEY`) | `python -m pytest` |
| The 23 skips | all env-gated live suites (GensparkLLM 8, Groq 6, gateway-Groq e2e 1, S3 4, Vault 4) | `python -m pytest -rs` |
| Gateway-service tests | **122 passed** | `cd gateway-service && python -m pytest` |
| Alembic migrations | **12** (0001_identity_tenancy … 0012_credentials) | `ls infrastructure/db/migrations/versions` |
| Platform HTTP routes | **20** (6 in `apps/api/app.py` + 14 in `apps/api/admin.py`) | `grep -cE '@(app\|router)\.(get\|post\|put\|patch\|delete)'` on both files |
| Gateway HTTP routes | **5** (`/healthz`, execute, describe, models, health) | same grep on `gateway-service/gateway/routes.py` |
| AdminArea enum | 21 areas; MVP active 4; FINAL active **6** | `core/contracts/admin.py:54–104` |
| AdminAction verbs | **10** | `core/contracts/admin.py:122–142` |
| ProviderOperation values | **11** · ProviderErrorCategory **12** | `core/contracts/provider.py:48–58, 312+` |

> **Correction to the operator brief:** the brief stated "import-linter
> contracts = 11, not 12". At baseline `5c1410b` the session-verified count is
> **12** — commit `0587538` (G2) added contract 12, "Core must not import the
> HTTP client (ADR-0008)". The known-correction of 11 was true *before* the
> gateway track merged; it is stale at this baseline.

**Truth tags used throughout** (per operator §2): **PROVEN** ·
**ARCHITECTURALLY POSSIBLE** · **MISSING** (with search recorded) ·
**RECOMMENDED FUTURE**. A contract, enum, placeholder, or port existing does
NOT make a capability PROVEN.

---

## 1. EXECUTIVE VISION — maximum control, minimum complexity

The Admin Agent is **one conversational control interface** over the whole
platform. It is not a chatbot bolted onto a dashboard; it is the primary way
an administrator monitors, controls, diagnoses, tests, and evolves the
platform — with every consequential action flowing through the platform's own
deterministic gates.

The thesis, stated as a design equation:

```text
CONTROL    = the set of real backend capabilities the admin can observe and act on
COMPLEXITY = surfaces × concepts × workflows the admin must learn
GOAL       : maximize CONTROL / COMPLEXITY
```

Three consequences drive everything in this plan:

1. **The platform already owns the hard part.** The backend at `5c1410b`
   already has: a governed change lifecycle with honest rollback
   (`core/admin/service.py`, 608 lines — Draft→Validate→Preview→Publish→
   Rollback with structurally unskippable audit: "the InMemoryAuditLog
   REJECTS admin events without that record" per the module docstring),
   deny-by-default security (`core/security/firewall.py`), tenant-scoped
   everything, named-reason denials, exact-once usage accounting, and
   per-node/per-attempt execution trails (`core/execution/service.py` —
   `ExecutionReport` / `NodeReport` / `AttemptRecord`). The Admin Agent
   **orchestrates** these; it never duplicates them. There is no "admin
   execution engine" in this plan — the existing `AdminConfigService` +
   `ExecutionService` + registries ARE the engine.

2. **The Agent is a proposer, never an authority** (§3). Every design
   decision below is judged against: does deterministic platform code make
   the final decision? If a screen or workflow would let the model (or the
   UI) decide anything consequential, it is rejected.

3. **Minimum surfaces** (doc D §2): **7 surfaces** — Agent · Overview ·
   Executions · Catalog · Changes & Audit · Tenants & Usage · System. Each
   is justified in doc D against the capability inventory in doc B;
   capabilities are COMBINED rather than split (doc D §3 records every
   combination decision). We explicitly reject one-screen-per-capability:
   21 `AdminArea` values do NOT mean 21 screens — only 6 areas are active
   (`FINAL_ACTIVE_ADMIN_AREAS`, `core/contracts/admin.py:100`), and the
   backend itself refuses to activate areas without bindable machinery
   ("activating an area whose publishes could not touch reality would fake
   control" — `core/contracts/admin.py:93–99`). The UI adopts the same
   honesty.

---

## 2. CURRENT BACKEND REALITY (tagged, evidence-cited)

The prior `PLATFORM_CAPABILITY_ASSESSMENT.md` (commit `5f543ad` on
`origin/feature/platform-capability-assessment`, `docs/architecture/`) is the
reference inventory; this section re-verifies only what this plan **relies
on** and does not reproduce the rest. Full per-capability rows live in
**doc B**.

### 2.1 PROVEN (implementation + passing test, session-verified)

| Capability | Evidence |
|---|---|
| Admin change lifecycle (Draft→Validate→Preview→Publish→Rollback; exact-predecessor enforcement; snapshot-honest rollback; rollback DENIED when no prior state exists) | `core/admin/service.py` (`AdminConfigService`); 7 lifecycle routes `apps/api/admin.py:137–230`; `tests/admin/` in the 1597 passing |
| Admin read surfaces (models incl. disabled, providers incl. templates-marked, tenant plan, routing weights, evaluation records, learning-dashboard placeholder) | `apps/api/admin.py:239–343` (7 GET routes) |
| Deny-by-default admin gate — `is_admin` checked BEFORE parameter parsing so non-admins cannot probe id validity | `apps/api/admin.py` `_gate()` + docstring |
| Execute pipeline (single + pipeline) with full explainability trail | `core/execution/service.py` — `AttemptRecord` (candidate, attempt #, succeeded, normalized error, latency_ms); `ExecutionReport.status_history` |
| Routing with named exclusions + policy snapshot + weights version | `core/contracts/routing.py:121–141` (`RoutingDecision.excluded`, `policy_snapshot`, `weights`) |
| Exact-once usage accounting (reserve/settle/refund/fail, tenant summary) | `core/usage/ports.py:36–77`; `tests/usage/` |
| Evaluation pipeline, verification levels RAW→EVALUATED→VALIDATED→VERIFIED→GOLD; RAW structurally forbids scores | `core/contracts/evaluation.py:54–68,161–169`; `core/evaluation/policy.py`; admin reads `apps/api/admin.py:303,322` |
| Learning gates (eligibility + promotion, signal-driven) | `core/learning/gates.py:99,148`; `tests/learning/` |
| Audit log — append-only port, closed 13-value event set, tenant-scoped read/count | `core/contracts/audit.py:49–69`; `core/audit/ports.py:33–58`; `core/audit/memory.py:42,61` |
| Capability firewall (closed decision set ALLOW/DENY/ALLOW_WITH_LIMIT/REQUIRE_APPROVAL) + tool-call gate (admission only) | `core/security/firewall.py`; `core/tools/gate.py`; `tests/security/`, `tests/tools/` |
| Identity service — register/verify/login/sessions/logout (in-memory, NOT HTTP-bound) | `core/identity/service.py:83–228` |
| Gateway data plane — 5 routes, versioned shared-secret auth, Groq provider, secrecy discipline (G4 leak tests) | `gateway-service/` — 122 tests passed; ADR-0008 CLOSED |
| Provider model discovery exercised by real adapters | `core/providers/ports.py:85` `discover_models`; Groq + GensparkLLM adapters (live tests env-gated, part of the 23 skips) |
| Tenant isolation + anti-enumeration (absent ≡ foreign) | tenant-keyed stores (`apps/api/store.py:51`); admin 404 mapping (`apps/api/admin.py` `_change_not_found`) |

### 2.2 ARCHITECTURALLY POSSIBLE (contract/port exists, not demonstrated)

- `ExecutionStrategy.AGENT` (`core/contracts/execution.py:46`) — vocabulary only.
- `WorkflowRuntimePort` (`core/execution/workflow_ports.py`) — docstring
  records "NO real engine binding exists".
- `ProviderAgentModulePort` (`core/providers/ports.py:126`) — no adapter
  implements it; `RUN_PROVIDER_AGENT` excluded from gateway v1.
- Streaming/async response contracts (`core/contracts/execute.py:147–204` —
  `ExecuteAsyncAccepted`, `DeltaEvent`, …) — the API **rejects**
  `async=true`/`stream=true` with 422 (`apps/api/app.py:449–460`).
- `waiting_approval` execution status + `approval_gate`/`human_input` graph
  node types (`core/contracts/execute.py:38`,
  `core/contracts/execution_graph.py:68–69`) — no approval queue, endpoint,
  or resume path (search: `grep -rn "approve" apps/api/` → admin config
  publish only).
- Injectable idempotency/webhook maps (T-IMPL-072 seams in `build_app`) —
  no Redis/DB binding composed.

### 2.3 MISSING (searched this session; searches recorded)

- **Executions list/search endpoint** — only GET-by-id exists
  (route enumeration of `apps/api/app.py` → 6 routes; none lists executions).
- **Audit read HTTP surface** — the port has `read`/`count`;
  `grep -rn "audit" apps/api/` → no route.
- **HTTP auth endpoints** — `grep -rn "login\|session" apps/api/` → none;
  Principal is composition-injected (the recorded seam,
  `apps/api/admin.py` docstring "the seam a real RBAC binding will fill").
- **Notifications subsystem** — `grep -rin "notification" core/ apps/
  --include='*.py'` → zero hits.
- **Telegram anything** — `grep -rin "telegram" core/ apps/ providers/
  infrastructure/` → zero hits.
- **Scheduler/trigger** — `grep -rn "cron\|schedul" core/ apps/` → only the
  admission FairScheduler.
- **Webhook delivery** — registration only (`POST /v1/webhooks`;
  `core/contracts/webhooks.py` docstring records delivery as not-claimed).
- **Tool executor / agent loop / structured-output enforcement / Postgres
  repositories / semantic retrieval** — absence re-confirmed by module
  listing (`ls core/tools/` → errors/gate/registry only;
  `grep -rln "Repository" infrastructure/` → none); assessment §10 searches
  stand.
- **Project entity** — `grep -rn "class Project" core/ --include='*.py'` →
  none; only `MemoryScope.PROJECT` / `RoleScope` vocabulary.
- **Source-code mutation machinery** — nothing reads/writes repo source as a
  governed operation (`grep -rn "subprocess\|git\b" core/ apps/
  --include='*.py'` → none relevant).
- **Platform-app healthz** — `grep -n "healthz\|health" apps/api/app.py` →
  none (gateway has one; the platform app does not).

### 2.4 RECOMMENDED FUTURE

The ranked generic-primitive roadmap is in **doc C §6** (baseline =
assessment §11 X²-1…X²-6, re-scoped through the Admin-Agent lens).

---

## 3. THE ADMIN AGENT — CONCEPT & SECURITY BOUNDARY

### 3.1 What it is

One internal agent, one conversation surface, that can:

- **Answer** from real platform state (registries, stores, audit, usage,
  evaluations) — read tools.
- **Propose** consequential actions as **drafts in the EXISTING change
  lifecycle** — never direct mutation.
- **Diagnose** from real execution evidence (§7).
- **Test** by running real executions through the real pipeline (billed,
  audited, evaluated like any execution — no simulation mode; §8).
- **Plan** source changes (§4) as reviewable proposals — later phase,
  operator-gated.

### 3.2 The non-negotiable boundary

```text
Admin request
  → Agent reasoning (model — UNTRUSTED for authority)
  → proposed action/tool call (structured, typed, named)
  → platform authZ / policy / entitlement / tenant gates   ← deterministic code
  → execution through EXISTING services                    ← deterministic code
  → verification (read-back of real state)
  → audit (existing AuditLogPort; admin mutations already structurally
    require AdminChangeRecord — core/admin/service.py docstring)
```

Rules, each mapped to an existing platform invariant:

1. **The model never decides authority.** The platform already excludes an
   `llm` actor from authority decisions (20 §1 posture; firewall actor set).
   The Agent's tool dispatcher is deterministic code that re-checks
   `is_admin` + tenant + action legality on EVERY call — the exact posture
   of `apps/api/admin.py` `_gate()`.
2. **The UI is never a security authority.** All enforcement is server-side;
   the UI renders decisions it receives.
3. **No separate admin execution engine.** Agent tools call
   `AdminConfigService`, `ExecutionService`, registries, and ports — the
   SAME instances the platform runs on ("NO PARALLEL STATE",
   `core/admin/service.py` docstring). A new engine is rejected by the
   governing principle: complexity without added control.
4. **Consequential = lifecycle-gated.** Any admin-governed mutation goes
   through Draft→Validate→Preview→Publish. The Agent may draft, validate,
   and preview autonomously; **publish requires an explicit admin approval
   act in the UI** — a backend-verified click, never a chat message the
   model interprets.
5. **Read tools are principal-scoped** exactly like the HTTP surface; the
   Agent gets no read the admin principal could not perform directly.
6. **Gateway secrecy preserved** (§9): no Agent tool ever returns secret
   values, internal provider slugs, route tokens, upstream URLs, or
   credential material. The platform already scrubs these
   (`apps/composition/gateway.py` `[SCRUBBED]` repr; opaque
   `credential_ref`s per 20 §5); Agent tool outputs are built from the same
   scrubbed surfaces only.

### 3.3 Tool taxonomy (risk classes)

| Class | Behavior | Approval | Examples |
|---|---|---|---|
| **R0 READ** | pure read of existing state | none (audit-logged) | list models, read execution report, usage summary, audit read |
| **R1 EXECUTE-TEST** | runs a REAL execution under the admin principal's budget | none, but budget-bounded + labeled via `RequestContext` so it is filterable | test a provider/model through the normal `/v1/execute` path |
| **R2 CONFIG-CHANGE** | drafts/validates/previews in the change lifecycle | Agent may reach PREVIEW; **PUBLISH = explicit admin click** | the 10 `AdminAction` verbs (enable/disable model/provider/skill/tool, set plan, set routing weights) |
| **R3 SOURCE-CHANGE** | proposes a source-change package | full §4 workflow — admin review + approval; applied by the separately-authorized track | fix a bug the Agent diagnosed |
| **R4 FORBIDDEN** | never exposed as a tool | — | secret values, credential resolution, tenant-isolation bypass, direct registry mutation outside the lifecycle, push to main |

This taxonomy is DATA (a closed enum + per-tool class), mirroring how
`ToolManifest`/`ApprovalRequirement` already model tool risk
(`core/contracts/tools.py`) — the concept is reused, not reinvented.

---

## 4. SOURCE-CODE MUTATION — APPROVAL-GATED WORKFLOW

Truth status: **MISSING today** (§2.3) and it stays missing through the early
phases — doc C places it last, design-first, operator-gated.

Required workflow (verbatim from the mandate, mapped to mechanics):

```text
Inspect → Diagnose → Plan → Proposed Change → ADMIN REVIEW → APPROVAL
        → Apply → Test → Verify → Audit
```

| Stage | Mechanics (planned, not built) |
|---|---|
| Inspect / Diagnose | R0 read tools over a repo checkout + execution evidence (§7) |
| Plan / Proposed Change | Agent produces a **Change Proposal object** carrying, mandatorily: affected files · intended change (diff) · reason · expected impact · dependencies · tests to run · rollback path (revert commit) · risk class (LOW / MEDIUM / HIGH / FROZEN-COMPONENT) |
| ADMIN REVIEW | rendered as diff review in the Changes & Audit surface; reject/comment supported |
| APPROVAL | explicit act, backend-verified, audited (`APPROVAL_DECISION` already exists in the closed audit set — `core/contracts/audit.py:64`) |
| Apply | on a branch, never main; commit references the proposal id |
| Test | the repo's own gates (pytest, mypy, ruff, lint-imports, check_repo.sh) — the Agent runs them and attaches raw results as evidence |
| Verify | gate results + the proposal's named "tests to run" |
| Audit | proposal + decision + apply + verification through the existing audit port |

Hard rules:

- A newly-discovered required change is a **NEW proposal**, never a silent
  expansion of an approved one (mandate §4, adopted verbatim).
- Proposals touching FROZEN components (G1–G4 gateway, `ProviderAdapterPort`,
  core invariants, import contracts) are classified FROZEN-COMPONENT and
  **cannot be approved in the UI** — they STOP with FACT / IMPACT / OPTIONS /
  RECOMMENDATION for operator decision (doc C gate-lifecycle rule).
- The Agent never has push-to-main capability under any configuration (R4).
- Source proposals do NOT enter `AdminConfigService` — its `AdminAction` set
  is closed and config-shaped; overloading it would be complexity without
  control. They are a separate ADMIN-ONLY object type reusing the same
  review UX pattern (§11).

---

## 5. CAPABILITY COVERAGE

Complete row-per-capability mapping — every public API route and every
runtime module directory — lives in **doc B**. Nothing is silently dropped;
doc B §4 lists capabilities intentionally NOT exposed and why. Doc B's
terminability criterion was met: all 20 platform routes + 5 gateway routes
mapped; all 20 `core/` module directories plus `apps/`, `infrastructure/`,
`providers/`, `gateway-service/` represented or explicitly classified.
Repository exploration STOPPED there per the mandate.

---

## 6. LIVE-EXECUTION-TRACE MODEL — HONEST

### 6.1 What the backend can truthfully show TODAY

| Trace stage | Backend truth at `5c1410b` | Live? |
|---|---|---|
| auth | Principal is composition-injected — **no per-request auth event exists** | NO — documented gap |
| tenant resolution | implicit in Principal; tenant-scoped stores prove enforcement after the fact | NO live signal |
| authZ (admin gate / firewall) | typed firewall decisions; `PERMISSION_DENIED` audit events | post-hoc via audit |
| entitlement | reserve-before-work; `BudgetExceeded` / `EntitlementNotConfigured` are named errors | post-hoc (error or ledger row) |
| routing | `RoutingDecision` — selected, ranked, fallbacks, **named exclusions**, policy snapshot, weights version | post-hoc, COMPLETE |
| model/provider selection | same object | post-hoc, COMPLETE |
| execution | `ExecutionReport.status_history` + per-node `AttemptRecord` | post-hoc, COMPLETE |
| gateway hop | gateway-side observability fields (closed enum, G1); platform sees the normalized `ProviderError` | post-hoc, PARTIAL — two processes, no correlated trace id surfaced to admin |
| normalization | `ProviderGenerateResponse` / 12-category `ProviderError` | post-hoc, COMPLETE |
| usage settlement | `UsageLedger` states | post-hoc, COMPLETE |
| response | `ExecuteSyncResponse` / `GET /v1/executions/{id}` | COMPLETE |

### 6.2 The honesty rule for the UI

**There is no live streaming of in-flight stages today** (streaming is
contract-only; the API rejects `stream=true` — `apps/api/app.py:455–460`).
Therefore:

- The trace view renders **completed evidence**, stage by stage, from the
  `ExecutionReport` — labelled "as recorded", never "live".
- No progress percentages, no animated in-flight stages, no synthetic
  "processing…" theatrics the backend cannot substantiate.
- An in-flight sync execution shows exactly "running — result pending" (the
  literal `ExecutionStatus.RUNNING`), nothing more granular.
- When streaming lands (doc C §6), the SAME trace view upgrades from
  post-hoc to live — designed for that upgrade, not faking it now.

**Documented gaps (not simulated):** per-request auth/tenant stage events;
correlated platform↔gateway trace ids in admin views; live stage telemetry.

---

## 7. SELF-DIAGNOSIS MODEL — CONFIDENCE-TIERED

Diagnosis derives ONLY from real execution evidence.

**Inputs (all PROVEN data):** failed stage (first node whose `AttemptRecord`
chain ended in error) · last good stage · normalized error category (closed
12-value `ProviderErrorCategory`) · expected vs observed (`OutputSpec` vs
`final_output`) · related config change ("what was published between the last
good execution and this failure?" — answerable from versioned, timestamped
`ConfigChange` records + audit) · provider/credential health probes
(`ProviderHealth`, `CredentialHealth` via adapter calls) · routing exclusion
records.

**Verdict tiers (closed set, rendered verbatim):**

| Tier | Criterion |
|---|---|
| **PROVEN CAUSE** | a deterministic backend record states the cause (e.g. `BudgetExceeded`; an exclusion record naming the reason; `CredentialStatus` ≠ ACTIVE from a live `validate_credential` probe) |
| **LIKELY** | one dominant hypothesis consistent with all evidence, cross-checked by at least one active probe (e.g. `health_check` reproduces the error category) |
| **POSSIBLE** | multiple hypotheses survive; each listed with supporting AND contradicting evidence |
| **UNDETERMINED** | evidence insufficient — stated as such, confidence LOW, with the list of missing evidence that WOULD determine it |

**Never:** invented causality; cause statements without a cited record;
tier promotion without new evidence. The diagnosis output schema requires an
evidence citation per claim — schema-enforced, not prompt-hoped.

---

## 8. LEARNING / EVALUATION / TEST MODEL — STATE DISTINCTIONS

The backend already draws the honest lines; the UI renders them, never blurs
them:

| UI state | Backend truth |
|---|---|
| **Observed** | an `ExecutionReport` exists; `EvaluationRecord` at `RAW` — RAW structurally forbids graders/score/confidence (`core/contracts/evaluation.py:161–169`) |
| **Evaluated** | `EvaluationRecord` ≥ EVALUATED with grader results, score, confidence, evidence_ref |
| **Accepted** | VALIDATED / VERIFIED verification levels |
| **Gold-Trusted** | `VerificationLevel.GOLD` |
| **Learned** | **NOTHING today.** The learning lifecycle is gates-only (`core/learning/gates.py`: TrainingEligibilityGate + PromotionGate over signals; `LearningSample` with sanitization states). The dashboard is a structural placeholder (`LearningDashboard.placeholder: Literal[True]`, honest zeros — `apps/api/admin.py:343`, `core/contracts/admin.py:207–208`). The UI shows "learning pipeline: NOT OPERATIONAL — gates exist, no promotion has occurred" until backend evidence exists. |

"What changed since last review?" is answered with evidence: published
`ConfigChange` records (versioned per area), audit events
(`TRAINING_DATASET_PROMOTED` already exists in the closed set for the
future), and evaluation-record deltas — all queryable today except that
audit lacks an HTTP surface (missing seam AUD-1, doc B).

**Testing model:** an Agent-initiated test IS a real execution — real
routing, real provider, real billing (admin principal's budget), real
evaluation — labeled via `RequestContext` for filtering. No mock mode; a
mock mode would fake control.

**Health honesty:** UNKNOWN never silently becomes HEALTHY. Health states are
exactly what the backend can prove: point-in-time probe results with
timestamps; a never-probed provider shows UNKNOWN; a stale probe shows its
age. No background health polling is invented until a scheduler primitive
exists (doc C §6).

---

## 9. PROVIDER & MODEL MANAGEMENT

**Lifecycle (PROVEN):** registries hold providers/models/bindings
(`core/providers/registry.py`); enable/disable flows through the change
lifecycle (4 of the 10 `AdminAction` verbs); scaffold templates are
structurally non-routable and the admin surface refuses to publish an
enable for one (`core/admin/service.py` docstring); discovery exists
per-adapter (`discover_models`); the gateway adds fleet capacity behind ONE
adapter class (`providers/real/gateway/adapter.py`) — provider count is
configuration, not architecture (ADR-0008, CLOSED).

**Admin Agent interactions:**

- View catalog (disabled + templates included, marked) — R0.
- Probe provider/credential health via adapter calls — R0; results are
  point-in-time (§8 honesty).
- Run discovery and DIFF against registered bindings ("provider now offers
  X; you route to Y") — R0; registering the delta is R2 via the lifecycle.
  **No hard-coded provider/model lists anywhere** — catalog + discovery are
  the only sources (§14).
- Enable/disable — R2 (lifecycle).
- Onboard a new provider — gateway providers are gateway-side work +
  platform config (per the ADR-0008 onboarding doctrine); the Agent can
  PREPARE the platform-side config and, in the source-change phase, propose
  gateway-side code via §4. Runtime registration of providers/accounts is a
  **missing seam** (registries are composition-time data — doc B PRV-4).

**Gateway secrecy (hard rule, ADR-0008/G4):** the Agent/UI never displays or
transmits secret values, secret versions' material, internal provider slugs,
route tokens, upstream URLs, or credential material. Admin-visible identity
= platform-side provider key + display name. Rotation is an operational act
the Agent may *describe and link the runbook for*, never execute in v1.

---

## 10. PROJECT / RESOURCE MANAGEMENT

A "Project" entity is **MISSING** in the runtime (§2.3 search) — only
`MemoryScope.PROJECT` / `RoleScope.project` vocabulary exists. What EXISTS
and is manageable today:

- **Tenants** — plan/units/limits via the `configure_tenant` seam
  (lifecycle-gated `SET_PLAN`); usage summaries per tenant
  (`UsageAccountingPort.summary`).
- **Tenant-bound resources** — executions, usage ledgers, evaluations,
  memory, credentials: all tenant-keyed, readable through existing ports.

Plan: the Tenants & Usage surface manages what exists. A true Project entity
is RECOMMENDED FUTURE (doc C §6): a policy-bound scoping + budgeting +
membership boundary INSIDE a tenant — designed backend-first, never invented
UI-side.

---

## 11. CHANGE MANAGEMENT — MAPPED TO THE EXISTING LIFECYCLE

No duplicate mechanism. The Changes & Audit surface is a straight rendering
of `AdminConfigService` + its 7 routes:

| UI element | Existing backend |
|---|---|
| Change list / detail | `GET /v1/admin/changes`, `GET /v1/admin/changes/{id}` |
| Draft (Agent-proposed or manual form) | `POST /v1/admin/changes` (`AdminDraftRequest`) |
| Validate / Preview | `POST .../validate`, `.../preview` — impact preview text is backend-computed (`_impact_preview`) and rendered verbatim |
| Publish (explicit admin act) | `POST .../publish` — exact-predecessor enforcement lives in core, not in the UI |
| Rollback | `POST .../rollback` — snapshot-honest; first-config rollback DENIED by the backend (`RollbackUnavailable`) and the UI renders that denial verbatim |
| Audit trail | `ADMIN_CONFIG_PUBLISHED` / `ROLLED_BACK` events carrying `AdminChangeRecord` — needs the audit read seam (AUD-1) |

The Agent's R2 tools are thin clients of these routes/services. Active areas
= the FINAL set of 6; the other 15 `AdminArea` values are INERT by backend
design and the UI lists them as INERT — visible, honest, not clickable into
fake workflows.

Source-change proposals (§4) reuse the same review UX pattern as a separate
object type.

---

## 12. NOTIFICATIONS

**Backend today: MISSING entirely** (§2.3 search). Design only:

- **Categories (closed set):** SUCCESS · INFO · WARNING · ERROR · SECURITY ·
  CHANGE. SECURITY and CHANGE derive from existing audit event types
  (`PERMISSION_DENIED`, `CROSS_TENANT_ACCESS_DENIED`,
  `SECURITY_POLICY_CHANGED`; `ADMIN_CONFIG_PUBLISHED`/`ROLLED_BACK`) — a
  read-model over audit, not a new event system.
- **Persistent notification center** (read/unread, category filters, links
  to evidence) vs **transient toasts** (operation feedback only — never the
  only record of anything).
- **Minimal seam (NTF-1, doc B):** a notification read-model + list/ack
  endpoints; producers = audit stream + execution failures + change
  lifecycle events. Poll-based v1 — no pub/sub infrastructure until the
  event primitive exists (doc C §6).

---

## 13. TELEGRAM — FUTURE CHANNEL, SAME ADMIN API

Zero Telegram code exists (§2.3). Design-for, do not implement:

```text
Admin UI ──► Admin API (the ONLY authority surface) ◄── Telegram Bot
```

- The bot is a **second client** of the same Admin API with the same
  Principal/authZ/audit path — never a second backend, never a bypass.
- Channel-appropriate subset: R0 reads + notification delivery + approval
  *prompts* that deep-link into the UI. **R2 publish and R3 approval do NOT
  happen in Telegram v1** — a chat message is too weak an authentication act
  for consequential changes; revisit only with a challenge-response design
  and operator sign-off.
- Prerequisites (why it is FUTURE): the HTTP auth binding (IDN-1) and the
  notification read-model (NTF-1).

**Recommendation: DEFER** until the Phase AA-1 seams exist (doc C); adopt
then as a thin client.

---

## 14. COMMAND PALETTE

A navigation simplifier ONLY: fuzzy-jump to surfaces/entities and pre-fill
Agent prompts ("disable provider X" opens the Agent with a drafted R2
proposal). It executes nothing itself — no second workflow engine, no
palette-only actions. Anything the palette triggers is exactly an Agent tool
or a navigation. (Doc D §5.)

---

## 15. API INTEGRATION STRATEGY

1. **Consume discovery where it exists:** catalog from registries +
   `discover_models`; NO hard-coded provider/model lists in UI code or Agent
   prompts.
2. **Contracts are the interface:** UI types derived from the Pydantic
   contracts (`core/contracts/*` — already `extra=forbid`, closed-enum
   discipline). New platform capabilities that ship contract + route become
   UI-visible via the same derivation path without a UI rebuild.
3. **Closed-set rendering:** statuses, error categories, verification
   levels, lifecycle states render from contract values; an unknown value
   renders loudly as UNKNOWN, never coerced.
4. **The Agent's tool registry is config** — tool name → route/service +
   risk class. Adding a backend capability = adding a tool entry, not
   rebuilding the Agent.
5. **No UI-side state duplicating backend truth** — the UI caches, never
   owns.

---

## 16. MISSING BACKEND SEAMS (summary; full rows in doc B §5)

Each follows: UI requirement → existing backend capability → missing seam →
minimal proposed addition. **None are implemented in this phase.** The set:
auth endpoints (IDN-1) · executions list (EXE-1) · audit read (AUD-1) ·
Admin-Agent service + tool dispatcher (AGT-1) · notification read-model
(NTF-1) · skill-import HTTP surface (SKL-1) · provider/account registration
API (PRV-4) · per-execution usage drill-down (USG-2) · webhook subscription
list/delete (WBH-1) · platform healthz (SYS-1) · source-change proposal
service (SRC-1).

---

## 17. RESPONSIBILITY CLASSIFICATION

Every doc B row carries one of PLATFORM-GENERIC / APPLICATION-SPECIFIC /
ADMIN-ONLY / USER-FACING / INTERNAL / FUTURE. Headline decisions:

- The **Admin Agent service itself is APPLICATION-SPECIFIC** — an app in
  `apps/`, composing core services; it must NOT enter `core/`. Nothing about
  "an admin chat" is a generic platform primitive. Its *tools* consume
  PLATFORM-GENERIC capabilities.
- Change lifecycle, firewall, registries, accounting, evaluation, audit:
  PLATFORM-GENERIC (already are).
- Notification read-model: ADMIN-ONLY v1; may generalize later.
- Telegram bot: APPLICATION-SPECIFIC, FUTURE.
- Source-change proposal service: ADMIN-ONLY, FUTURE, operator-gated.

---

## 18. SELF-CHALLENGE FINDINGS

**Important gaps discovered:**

1. The operator brief's "contracts = 11" correction is itself stale —
   session-verified **12** at this baseline (front-matter note).
2. There is NO HTTP auth binding at all — the hardest prerequisite for ANY
   admin UI is IDN-1, not anything Agent-shaped. Phase AA-1 therefore leads
   with it.
3. The audit log — the spine of every honesty feature here — has no HTTP
   read surface. Without AUD-1, "answer with evidence" cannot cite audit.
4. "Live trace" as commonly imagined is unbuildable today without lying; the
   honest post-hoc trace (§6) is actually STRONGER for diagnosis than a fake
   live view, because every rendered stage is a real record.
5. In-memory runtime stores mean admin views are amnesiac across restarts —
   must be disclosed in-UI ("since process start") until repositories land.

**Unnecessary complexity removed:**

- A separate "admin execution engine" — rejected; existing services suffice.
- A workflow engine for Agent plans — rejected; the Agent's multi-step work
  is a bounded loop in the app-level Agent service.
- One-screen-per-AdminArea (21 screens) — rejected; 7 surfaces (doc D).
- Real-time WebSocket infrastructure in v1 — rejected; poll-based
  read-models match the backend's post-hoc truth.
- Telegram in scope — deferred (§13).
- Mock/simulation test mode — rejected as dishonest; real bounded executions
  instead.

**Assumptions rejected:**

- "The Agent needs its own permission model" — no; Principal.is_admin + the
  existing gates + the R0–R4 tool classes cover it.
- "Learning UI needs charts" — no; until the lifecycle produces evidence,
  the only honest rendering is state + placeholder disclosure.
- "More surfaces = more control" — the inverse is true past the minimum set.

**Capabilities combined (full table doc D §3):** providers + models +
bindings + skills + tools + roles → Catalog; config changes + audit + source
proposals → Changes & Audit; usage + plans + tenants → Tenants & Usage;
health + observability + runtime + system settings → System.

**Generic vs product:** §17. **Smallest architecture supporting the
long-term vision:** Agent service (app-level) + thin API seams + read-models
over existing ports — everything else already exists.

**Highest-leverage improvements (ranked):** 1) IDN-1 auth binding · 2) AGT-1
Agent service with R0 tools · 3) EXE-1 + AUD-1 evidence surfaces · 4) R2
lifecycle tools · 5) async/durable execution (unlocks live trace,
scheduling, real approval waits — assessment X²-1).

---

## 19. RISK REGISTER

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | Agent proposes harmful config change; admin rubber-stamps | M | H | backend impact preview rendered verbatim; lifecycle already enforces exact-predecessor (preview before publish); rollback path always shown first |
| R2 | Prompt injection via platform data (e.g. a provider error string steering the Agent) | M | H | tool dispatcher validates typed schemas; R2+ never auto-executes; tool output is data, never instructions; the authority boundary caps blast radius at "a draft was created" |
| R3 | UI drifts into simulating backend states (the honesty failure) | M | H | §6/§8 rules are phase acceptance criteria (doc C); review gate checks every rendered state against a backend record |
| R4 | Seam creep — thin endpoints grow into a parallel backend | M | M | each seam is a read-model or a surfacing of existing core machinery, minimally defined in doc B §5; phase scopes are closed |
| R5 | Secrecy leak through Agent verbosity (slugs/tokens/URLs in traces) | L | H | R4-forbidden list enforced in tool output schemas; the G4 leak-test pattern (`tests/security/test_log_secret_leakage.py`) extended to Agent outputs at build time |
| R6 | In-memory stores → amnesiac admin views across restarts | H | M | disclosed in-UI; durable repositories are the top future primitive (doc C §6) |
| R7 | Model unavailability makes the Agent surface dead | M | M | every Agent capability is also reachable through direct UI on the same API — the Agent is the preferred path, not the only path |
| R8 | Scope reopening of G1–G4 during build | L | H | FROZEN-COMPONENT classification (§4) forces STOP + operator decision |

---

## 20. FINAL READINESS VERDICT

**READY TO PLAN THE BUILD — with three preconditions inside the first
implementation phase** (IDN-1 auth binding, EXE-1 executions list, AUD-1
audit read — each a thin surfacing of PROVEN core machinery). The admin
control plane the Agent needs most — the governed change lifecycle — is the
single most complete, most tested part of the platform surface. The Agent
architecture adds **one application-level service and zero core changes**.
Phase count and sequence: **4 phases** (doc C) — seams → Agent R0+R1 →
R2 governance + notifications → source-change track (operator-gated).

The plan honors the governing line: the largest real control gained is
mostly *exposure of what already exists*, which is exactly why the
complexity budget stays small.
