# PLATFORM CAPABILITY ASSESSMENT

**Date:** 2026-08-30
**Assessed state:** `main` @ `5c1410b592a0e864f83fd204b8ad028f357bd749`
(G1–G4 Remote Provider Gateway merged; FINAL Plan Lane B complete per
`docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md` R098–R101).
**Method:** direct repository inspection (files, contracts, tests, ADRs).
Every substantive claim cites a repository location. This document is
analysis only — it changes no runtime behavior and authorizes nothing.

**Evidence classes used throughout:**

| Tag | Meaning |
|---|---|
| **PROVEN** | Directly demonstrated by implementation + passing tests in this repo |
| **IMPLIED** | Architecture/contract supports it; not demonstrated end-to-end |
| **MISSING** | Not implemented anywhere in the repo (search locations recorded) |
| **PRODUCT-LEVEL** | Deliberately belongs to applications, not the generic platform |

Baseline verification facts (run at assessment time, this branch):
1605 passed + 15 skipped platform tests, 122 gateway-service tests,
mypy clean (110 files), 12 import-linter contracts kept
(`pyproject.toml` `[tool.importlinter]`, lines 80–161).

---

## 1. EXECUTIVE VERDICT

The repository implements a **multi-tenant AI orchestration and execution
control plane** — a governed kernel that routes AI work to providers,
executes it with billing/entitlement/failover discipline, and records
evaluable evidence. It is **not yet an agent runtime**: the contracts,
lifecycle states, and security gates for agentic execution exist and are
tested, but there is **no loop that lets a model's output cause a next
action** (no tool executor, no plan-act-observe cycle, no durable
workflow engine binding).

Its strongest asset is the **boundary discipline**: 12 machine-enforced
import contracts keep `core/` free of every infrastructure concern, every
provider crosses one port (`ProviderAdapterPort`), every tenant-scoped
object is physically keyed by tenant, and every denial is named data. This
is precisely the shape that lets an agent runtime be **added as a layer**
rather than a rewrite — the assessment's central finding.

What it is today, in one sentence: **a production-grade "AI execution
kernel" (routing + execution + governance + accounting + evaluation over
pluggable providers) with agent-shaped contracts waiting for an agent
runtime, tool execution, and durable workflow bindings.**

---

## 2. CURRENT PLATFORM CLASSIFICATION

### 2.1 The four candidate labels, tested against evidence

**(a) Chatbot / chat-completion platform — UNDERSELLS IT.**
Chat exists: conversations/messages with tenant+user isolation
(`core/memory/memory.py`, `core/contracts/conversation.py`; wired in
`apps/api/app.py` execute handler — auto-create conversation, append user
turn, append assistant turn on success). But chat is one *feature* of the
execute pipeline, optional (`conversations=None` legal), and nothing else
in the architecture is chat-shaped. The single API verb is `/v1/execute`
("ask"), not `/v1/chat/completions`.

**(b) AI orchestration platform — ACCURATE for what is PROVEN.**
The implemented pipeline is: request → role admission → idempotent replay
→ context composition → routing decision → entitlement reservation →
provider execution with error-aware retry/failover → usage settlement →
evaluation seam → audit/webhook contracts. Each stage is a real, tested
module:

- Routing: `core/routing/router.py` (`SimpleScoringRouter`, 474 lines) —
  eligibility filtering with **named exclusions** (11 §14 posture),
  scoring weights, fallback candidates; strategy planning in
  `core/routing/planner.py`.
- Execution: `core/execution/service.py` (641 lines) — `execute_single` +
  `execute_pipeline` (lines 264, 302); consumes RoutingDecision verbatim
  ("Router decides; Execution executes", 02 §2 invariant 5); error-aware
  retry/failover per the 12-category normalized `ProviderError`;
  usage reserve-before-work / settle-exactly-once.
- Providers: `ProviderAdapterPort` (`core/providers/ports.py:57`) with
  three real adapters (`providers/real/groq/`, `providers/real/
  genspark_llm/`, `providers/real/gateway/`) and 12 capability templates
  (`providers/templates/`).
- Governance: capability firewall (`core/security/firewall.py`,
  deny-by-default closed decision set), tool-call gate
  (`core/tools/gate.py`), admin change lifecycle draft→validate→preview→
  publish→rollback (`core/admin/service.py`, 608 lines).
- Accounting: `core/usage/` reservation ledger with
  reserve/settle/refund/fail (`core/usage/ports.py:36`).
- Evaluation: `core/evaluation/policy.py` — deterministic graders +
  optional model judge → score/confidence/evidence → verification level.

**(c) Agentic execution platform — NOT YET; contracts only.**
Agent *vocabulary* is fully contracted: `ExecutionStrategy.AGENT`
(`core/contracts/execution.py:46`), an 11-node-type execution graph with
`approval_gate`/`human_input`/`provider_agent_call` node types
(`core/contracts/execution_graph.py`), `waiting_approval` in the
execution lifecycle (`core/contracts/execute.py:38`), and
`ProviderAgentModulePort` for provider-native agents
(`core/providers/ports.py:126`). But: the graph planner generates only
single/pipeline/parallel/debate topologies (`core/execution/
graph_planner.py` — "For review_judge / map_reduce / agent / hybrid the
docs define NO topology template… the planner does NOT generate those");
`WorkflowRuntimePort` explicitly records "NO real engine binding exists
in this repo" (`core/execution/workflow_ports.py` docstring); and there
is **no tool executor anywhere** (§4 below, absence evidence recorded).

**(d) Broad AI application/runtime foundation — DIRECTIONALLY TRUE,
structurally prepared, not yet demonstrated.** The port/adapter/
composition-root pattern (imports enforced by contract) means arbitrary
applications *can* compose the kernel. But only one application exists
(`apps/api`), so multi-product reuse is IMPLIED, not PROVEN.

### 2.2 Verdict

> **Classification: AI ORCHESTRATION PLATFORM (multi-tenant execution
> control plane) with agent-ready contracts.**
> It has outgrown "chatbot" (evidence above), has not yet earned
> "agentic execution platform" (no action loop, no tool execution,
> no durable runtime binding), and is a credible *candidate* foundation
> for a broader application runtime (boundaries are proven; multi-product
> reuse is not).

---

## 3. CAPABILITY MATRIX (what exists, with evidence)

| Capability | Status | Evidence |
|---|---|---|
| Unified execute API (`POST /v1/execute`) | **PROVEN** | `apps/api/app.py:426`; `tests/api/` (103 tests per FINAL_VALIDATION) |
| Sync single-model execution w/ retry+failover | **PROVEN** | `core/execution/service.py:264`; `tests/execution/` (66 tests) |
| Pipeline (multi-stage) execution | **PROVEN** | `core/execution/service.py:302` (`execute_pipeline`) |
| Model routing w/ eligibility + named exclusions | **PROVEN** | `core/routing/router.py`; `tests/routing/` (56 tests) |
| Strategy planning (explicit-wins; needs_agent→agent) | **PROVEN** (mapping); AGENT execution itself MISSING | `core/routing/planner.py` |
| Execution-graph spec (11 node types, 8 lifecycles, 6 edge conditions) | **PROVEN as contract**; runtime MISSING | `core/contracts/execution_graph.py`; `core/execution/graph_planner.py` |
| Provider plugin system (manifest, capabilities, health, error normalization) | **PROVEN** | `core/providers/ports.py`, `core/providers/registry.py`; `tests/providers/` (179+) |
| Real providers: Groq, Genspark LLM, Remote Gateway | **PROVEN** (hermetic contract tests; live e2e = 15 skipped tests pending operator GSK key) | `providers/real/{groq,genspark_llm,gateway}/`; `tests/providers/test_gateway_groq_live_e2e.py` |
| Remote Provider Gateway (separate data plane, secret lifecycle, rotation) | **PROVEN** | `gateway-service/` (122 tests), ADR-0008, G1–G4 commits `5a7f66b..5c1410b` |
| Provider account pools (leases, cooldown, LRU selection) | **PROVEN** | `core/providers/accounts.py` (30 §10.3–10.5) |
| Multi-tenant isolation (physical keying, anti-enumeration) | **PROVEN** | every store keyed `(tenant_id, id)` e.g. `core/memory/memory.py`; IDOR suites `tests/security/test_hardening_t033.py`; DB: 12 migrations all carry `tenant_id` (`infrastructure/db/migrations/versions/`) |
| Capability firewall (deny-by-default, closed verdict set) | **PROVEN** | `core/security/firewall.py`; `tests/security/test_capability_firewall.py` |
| Tool-call gate (status/permission/device-trust/approval composition) | **PROVEN as admission**; execution MISSING | `core/tools/gate.py` (189 lines) |
| Tool + skill registries, skill import lifecycle w/ checksum provenance | **PROVEN** | `core/tools/registry.py`, `core/skills/importing.py`, `core/skills/resolver.py` |
| Conversation + memory stores (6 scopes, secret rejection) | **PROVEN** | `core/memory/memory.py`; `core/contracts/memory.py:45` (global/tenant/workspace/project/conversation/role) |
| Deterministic context composer (budget, scope priority, named exclusions) | **PROVEN** | `core/context/composer.py` (308 lines) |
| Usage accounting (reserve/settle/refund/fail; budget denial pre-work) | **PROVEN** | `core/usage/ports.py`, `core/usage/memory.py`; BudgetExceeded path in execute handler (`apps/api/app.py`, `except BudgetExceeded`) |
| Plans/entitlements catalog | **PROVEN as data + admin read** | `core/contracts/plan.py`; `GET /v1/admin/plans/{tenant}` (`apps/api/admin.py:271`) |
| Evaluation pipeline (graders → aggregate → verification level) | **PROVEN** | `core/evaluation/policy.py` (368 lines); `tests/evaluation/` (75 tests) |
| Learning gates (training eligibility, promotion gates) | **PROVEN as gates**; no training runtime | `core/learning/gates.py` (22 §9/§11 conditions) |
| Admin control plane (config change lifecycle + read surfaces) | **PROVEN** | `core/admin/service.py`; 14 routes `apps/api/admin.py:137–343` |
| Identity (register/verify/login/sessions) + device trust | **PROVEN (in-memory binding)** | `core/identity/service.py`, `core/identity/devices.py` |
| Audit log (closed event set, append-only, no mutation surface) | **PROVEN** | `core/audit/ports.py:33`; `tests/audit/test_audit_log.py` (`test_no_mutation_surface_exists`) |
| Secrets custody (opaque refs end-to-end; Vault binding) | **PROVEN** | `core/secrets/ports.py`, `infrastructure/secrets/vault.py` (ADR-0007); leak suites `tests/security/test_log_secret_leakage.py` |
| Queue/worker runtime (at-least-once, dedup, DLQ, stale-claim recovery) | **PROVEN (in-memory + Redis binding)** | `core/runtime/worker.py`, `core/runtime/ports.py`, `infrastructure/redis/binding.py` (ADR-0003); chaos suite `tests/runtime/test_chaos_transport_t071.py` |
| Transactional outbox | **PROVEN (port + in-memory; relay semantics tested)** | `core/runtime/outbox.py` |
| Admission control / fair scheduling / concurrency limits | **PROVEN** | `core/runtime/admission.py` (`AdmissionController`, `ConcurrencyLimiter`, `FairScheduler`) |
| API rate limiting (per-tenant, zero-residue 429) | **PROVEN** | `apps/api/app.py:433` (T-IMPL-070); `tests/security/test_api_rate_limit_t070.py` |
| Idempotent replay (Idempotency-Key; cross-replica seams) | **PROVEN** | idempotent replay block in execute handler (`apps/api/app.py`); `tests/api/test_stateless_api_t072.py` |
| Observability (structlog + scrubbing, traces, adaptive sampling, metrics provider) | **PROVEN (in-process; OTLP export deferred by ADR-0004)** | `apps/observability/` (config/logs/sampler/setup/metrics) |
| Persistence schema (12 Alembic migrations, schema↔contract parity tests) | **PROVEN as schema**; repository layer MISSING | `infrastructure/db/migrations/versions/0001..0012`; `tests/db/test_schema_contract_parity.py` |
| Webhook registration | **PROVEN (registration only)** | `apps/api/app.py:746`; `core/contracts/webhooks.py` — delivery explicitly NOT claimed (docstring) |
| Async execution / streaming | **MISSING (explicitly rejected at API)** | `apps/api/app.py:449–460` — 422 "not available on this deployment slice" |

---

## 4. AGENT-READINESS MATRIX (Core Question 3)

For each capability required by a real agent:

| Capability | Verdict | Evidence / where searched |
|---|---|---|
| **Tool execution** | **ABSENT** | Searched: `grep -rn "def execute" core/tools/ core/skills/` → none; `grep -rln "subprocess|sandbox" core/ apps/` → only *data* fields (`sandbox_policy: JsonObject` in `core/contracts/tools.py:153,205`) and gate docs. `core/contracts/tools.py` header is explicit: "DATA ONLY. No tool execution… that machinery is FINAL Phase 14 (Tool Fabric)" — the Fabric's *gate* landed (`core/tools/gate.py`), the *executor* did not. |
| **Action selection** | **ABSENT** (as model-driven selection) | No module consumes model output to choose an action. Model output is returned as text only — pinned by design decision R094/R095 ("the six open §7 contexts have no consuming surface") and t033 structural tests. |
| **Multi-step execution** | **PARTIAL** | Deterministic pipeline execution PROVEN (`execute_pipeline`). Graph topologies parallel/debate plannable (`graph_planner.py`). Model-directed multi-step (agent mode) ABSENT. |
| **Task decomposition** | **PARTIAL (contract + trivial mapping)** | `TaskAnalysis` contract (`core/contracts/routing.py:40`, carries `needs_agent`, `capabilities_required`, `tools_required`); `StrategyPlanner` maps `needs_agent→AGENT`; no decomposer that *produces* TaskAnalysis from an ask exists (recorded in planner docstring: no heuristic invented). |
| **Context/state handling** | **IMPLEMENTED** | `core/context/composer.py` — deterministic role+memory+history+ask composition with budget and named exclusions. |
| **Memory** | **IMPLEMENTED (structured KV; semantic retrieval deferred)** | `core/memory/` — 6 scopes, confidence, sensitivity, secret rejection; `composer.py` records "semantic similarity deferred, R044 (c)". `pgvector` dependency present in `pyproject.toml` but unused by any module (searched `grep -rn pgvector core/ infrastructure/` → dependency only). |
| **Skill/tool registry** | **IMPLEMENTED** | `core/skills/` (registry, import lifecycle w/ SHA-256 provenance, resolver chain Task+Role+Context→Selected), `core/tools/registry.py`. |
| **Planning** | **PARTIAL** | Graph planner builds documented topologies; strategy planner selects strategy. No plan *object produced by a model* and no plan revision loop. |
| **Execution loops** | **ABSENT** | Searched `grep -rn "agent_loop|while.*step" core/` → no loop construct; `execute_single/execute_pipeline` are single-pass traversals of a routing decision. |
| **Observation/result handling** | **PARTIAL** | Execution reports carry per-node outputs/errors as data (`core/contracts/execution.py`); evaluation consumes traces (`core/evaluation/policy.py`). No observe→re-plan feedback into a running execution. |
| **Retries/recovery** | **IMPLEMENTED** | Error-aware bounded retry + provider failover (`core/execution/service.py` docstring rules); worker stale-claim recovery + DLQ (`core/runtime/worker.py`); chaos-tested (`tests/runtime/test_chaos_transport_t071.py`). |
| **Structured outputs** | **PARTIAL** | `OutputSpec.schema_` accepted as request data (`core/contracts/execute.py`); no schema *enforcement/validation* of model output exists (R095: attach-at-surface rule — validator must land with the consuming surface). |
| **Long-running work** | **PARTIAL (machinery, no binding)** | Queue/worker/lease/outbox all PROVEN; but `/v1/execute` rejects `async=true` (`apps/api/app.py:449`) and no execution rides the queue yet. |
| **Asynchronous execution** | **ABSENT at API** | Explicit 422 (`apps/api/app.py:449–454`); contracts for async accepted response exist (10 §4 shapes in `core/contracts/execute.py`). |
| **Durable state** | **PARTIAL** | Schema for executions/usage/evaluations exists (migrations 0008–0010); `WorkflowRuntimePort` defined (`core/execution/workflow_ports.py`) with recorded "NO real engine binding exists"; runtime stores are in-memory with injectable seams (T-IMPL-072). Repository layer (rows↔contracts) not implemented — searched `grep -rln "Repository" infrastructure/` → none. |
| **Human approval/intervention** | **PARTIAL (states + verdicts, no workflow)** | `REQUIRE_APPROVAL` firewall verdict (`core/security/firewall.py`); `waiting_approval` status + `approval_gate`/`human_input` node types (`core/contracts/execution_graph.py`); `signal_approval` on WorkflowRuntimePort. No approval queue/endpoint/resume path exists (searched `grep -rn "approve" apps/api/` → admin config-change publish only). |
| **Permissions/entitlements** | **IMPLEMENTED** | Firewall grants/entitlements (deny-by-default); task-unit budgets denied pre-work (`EntitlementNotConfigured`/`BudgetExceeded` paths in execute handler); plan catalog. |
| **Tenant isolation** | **IMPLEMENTED** | §3 row above; adversarial suites t033/t034. |
| **Auditability** | **IMPLEMENTED (security events)** | `core/audit/` closed event set, append-only port; execution trail via Execution/ExecutionNode records + `GET /v1/executions/{id}` (`apps/api/app.py:781`). |
| **Evaluation and verification** | **IMPLEMENTED** | `core/evaluation/` full pipeline + admin read surfaces (`/v1/admin/evaluations/...`, `apps/api/admin.py:303,322`). |
| **Provider-native agents (externalized agency)** | **EXTERNALIZED (contract ready, no implementation)** | `ProviderAgentModulePort` (`core/providers/ports.py:126`), normalized 7-event set (`core/contracts/provider_agent.py`); `RUN_PROVIDER_AGENT` operation excluded from gateway v1 (OPEN-2, `providers/real/gateway/adapter.py`). No adapter implements it. |

**Agent verdict:** the platform provides the *governance half* of an agent
(admission, permissions, budgets, audit, evaluation, lifecycle states) —
which is the half most platforms get wrong — but not the *action half*
(tool execution, action selection, loops, durable long-running runs).
It is an **agent-governance kernel awaiting an agent runtime**.

---

## 5. LARGE-PRODUCT SUITABILITY MATRIX (Core Question 2)

Legend: **READY NOW** (compose existing pieces) / **READY WITH
CONFIGURATION** (data/bindings/deployment only, no new platform code) /
**REQUIRES NEW PLATFORM CAPABILITY** (new generic primitive needed).

| Product class | Verdict | What's missing (platform-side) |
|---|---|---|
| Multi-provider AI applications (unified execute over many models w/ governance) | **READY NOW** | — (this is exactly what's built; add providers via `providers/templates/` + doc 31 onboarding) |
| Internal enterprise AI tools (governed prompt→answer, per-team budgets, audit) | **READY WITH CONFIGURATION** | Real identity binding at the Principal seam (`apps/api/app.py:162` — "the seam the auth phase will fill"), Postgres repositories for durability; both are bindings behind existing ports |
| Content-generation systems (text now; image/audio contracted) | **READY WITH CONFIGURATION** (text) | Non-text operations are contract-complete (`ProviderOperation` closed set, 12 provider templates) but no real non-text adapter exists; gateway v1 excludes them (OPEN-2). Needs: adapters only — no new architecture |
| Analysis & decision-support products | **READY WITH CONFIGURATION** (single/pipeline) | Parallel/debate topologies plannable but no graph *executor* beyond linear pipeline → REQUIRES workflow execution for graph strategies |
| Chat/assistant products | **READY NOW** (sync) | Streaming ABSENT (explicit 422) — REQUIRES streaming capability for competitive UX |
| Research systems (long multi-stage investigations) | **REQUIRES NEW PLATFORM CAPABILITY** | Async execution + durable workflow binding + agent loop (§7) |
| Automation products (triggers, schedules, unattended runs) | **REQUIRES NEW PLATFORM CAPABILITY** | No scheduler/trigger primitive exists (searched `grep -rn "cron|schedul" core/ apps/` → only admission FairScheduler + device metadata); webhook *delivery* also missing |
| Agentic developer tools / IDEs | **REQUIRES NEW PLATFORM CAPABILITY** | Tool execution, workspace/artifact abstraction, agent loop — see §6 |
| Marketing platforms | **REQUIRES NEW PLATFORM CAPABILITY** (platform primitives) + PRODUCT-LEVEL logic | See §7 |

---

## 6. IDE / DEVELOPER-TOOL FEASIBILITY (Product Fit A)

**What the platform already provides an IDE product (PROVEN):**

- Multi-provider model access with routing/failover/budgets — the IDE
  never talks to a provider directly (`ProviderAdapterPort` + gateway).
- The security chassis an IDE agent needs: tool-call admission with
  **device trust** (client/hybrid tools require a trusted device —
  `core/tools/gate.py` device rule; `core/identity/devices.py`),
  capability firewall, per-permission approval requirements
  (`ApprovalRequirement.BEFORE_ACTION` — `core/contracts/tools.py`),
  and `ClientRuntimeKind` already enumerating BROWSER / FILESYSTEM /
  TERMINAL / IDE / LOCAL_PROJECT (`core/contracts/tools.py`).
- Conversation/memory/context for session continuity; skills for
  reusable coding procedures; evaluation for verification levels on
  agent output; usage accounting for seat/plan billing.

**What is missing and belongs in the GENERIC PLATFORM:**

1. **Tool executor** — dispatch an admitted tool call to a server-side
   handler or a client runtime, capture normalized results (ABSENT, §4).
2. **Client runtime transport** — the channel by which a `client`
   -located tool executes on the developer's machine; the contract
   anticipates it ("client-runtime transport is not built in core" —
   `core/contracts/tools.py` docstring).
3. **Agent execution loop** — plan → gated tool call → observe → continue
   (ABSENT).
4. **Async/long-running execution** + workflow runtime binding — an IDE
   task ("refactor this package") outlives an HTTP request.
5. **Artifact/workspace abstraction** — `ObjectStoragePort` exists
   (`core/storage/ports.py:45`, tenant-prefixed S3 binding
   `infrastructure/storage/s3.py`) and `ExecutionResult.artifacts` is
   already a field (`core/contracts/execute.py`); a *workspace* concept
   (mutable tree + diff/patch semantics) does not exist anywhere.
6. **Streaming** — token/progress streaming for editor UX (contract
   shapes exist per 10 §11 in `core/contracts/execute.py`; no transport).

**What belongs in the IDE APPLICATION (PRODUCT-LEVEL, must NOT enter core):**

- Editor integration, LSP, UI; repo/VCS operations; language-specific
  patch application and build/test commands (these are *tools* registered
  in the tool registry + client runtime — data + app handlers, not core
  code); coding-agent prompts/roles (data via role registry); project
  indexing.

**Can coding-agent behavior sit above the current platform without
modifying core?** **Yes — structurally.** The gate takes tool calls from
any caller and core takes no dependency on what a tool *does*; an IDE app
could today implement its own loop application-side calling `/v1/execute`
per step and executing tools itself. But then tool execution bypasses
platform custody (audit/usage/approval enforcement of actual execution
stays app-side). That is exactly why the tool executor and loop should be
the platform's next generic primitives (§11).

---

## 7. MARKETING-PLATFORM FEASIBILITY (Product Fit B)

**Platform already provides generically (PROVEN):** multi-provider
content generation (text now; image via new adapters — contracts ready);
plans/entitlements/budgets per tenant/team; roles as personas ("brand
voice" = role registry data, `core/roles/registry.py`); skills as
campaign procedures; memory scopes WORKSPACE/PROJECT fit
brand/campaign context (`core/contracts/memory.py:45`); evaluation for
content QA; admin change lifecycle for governed config; audit.

**Missing GENERIC platform primitives it would need:**

1. **Scheduled/triggered execution** — "publish Tuesday 9am", "re-run on
   metrics drop". No scheduler/trigger exists (searched, §5). Generic:
   many products need timed/evented runs.
2. **Webhook delivery + event model** — registration exists; delivery is
   recorded as not-claimed (`core/contracts/webhooks.py` docstring;
   `apps/api/app.py` header comment). Generic.
3. **Async + durable workflows** — campaign generation is multi-stage and
   long-running. Generic (same primitive as §6 item 4).
4. **Artifact storage surface** — generated assets need a first-class
   artifact API above `ObjectStoragePort`. Generic.
5. **Human approval workflow** — "manager approves before publishing" is
   `REQUIRE_APPROVAL`/`waiting_approval`/`signal_approval` made
   operational (states exist; queue/endpoints don't). Generic.

**PRODUCT-LEVEL (stays in the marketing application):** channel
integrations (Meta/Google/X publishing APIs — implemented as registered
*tools* with per-permission approval, or app services); campaign domain
model (briefs, calendars, audiences); analytics ingestion and KPI logic;
iteration policies ("regenerate if CTR < x" — app policy that *calls*
the platform); team UX.

**Orthogonality check:** every missing primitive above attaches at
existing seams (queue/worker for scheduling+delivery, WorkflowRuntimePort
for durability, tool registry+gate for channel actions, ObjectStoragePort
for artifacts) — **no restructuring of the current core is required.**

---

## 8. GENERAL APPLICATION-PLATFORM ANALYSIS (Product Fit C + Core Question 4)

### 8.1 The architectural boundary, as actually enforced

```text
AI MODEL            — entirely outside; reached only through ProviderAdapterPort
                      (core/providers/ports.py). Untrusted for authority
                      decisions (20 §1; firewall excludes an "llm" actor).
AGENT RUNTIME       — DOES NOT EXIST YET. Its slot is contracted:
                      ExecutionStrategy.AGENT, graph node types,
                      WorkflowRuntimePort, ProviderAgentModulePort.
APPLICATION LOGIC   — apps/ (composition roots + API). Only one app today.
                      Import-linter guarantees core never imports apps.
PLATFORM SERVICES   — core/ (pure domain: routing, execution, governance,
                      accounting, evaluation, memory, skills, tools-as-data)
                      + infrastructure/ bindings (Postgres/Redis/Vault/S3)
                      + gateway-service/ (separate provider data plane).
```

Enforcement is not convention — it is 12 import-linter contracts run in CI
gates (`pyproject.toml:80–161`; `engineering/verification/check_repo.sh`):
core imports no web framework, no DB toolchain, no Redis, no telemetry
stack, no HTTP client, no crypto, no cloud SDKs; contracts import no
implementation; providers/infrastructure/apps have one-way arrows.

### 8.2 What the platform provides generically vs. what products implement

**Generic (provided today):** provider selection/routing; execution with
retry/failover; usage/billing accounting; entitlements + budgets; tenant
isolation; secrets custody; security gates (firewall, tool admission);
evaluation; audit; identity/device primitives; admin change governance;
queue/worker/outbox machinery; observability pipeline.

**A product still implements:** its domain model and workflows; its tools'
actual handlers; its UI; its triggers/schedules (until the platform grows
that primitive); its interpretation of results.

### 8.3 Reusable AI/Agent kernel verdict

**Yes — the platform can serve as a reusable kernel without embedding
product logic in core**, with evidence that this posture is already
enforced rather than aspirational: providers plug in via manifest-trusted
adapters (30 §4.2, `core/providers/registry.py`); tools/skills/roles/plans
are **data** in registries, not code in core; every place a product would
attach (auth, stores, adapters, policies, budgets) is an injected
constructor parameter of `build_app` (`apps/api/app.py`) or a port.
The one qualification: "kernel for many products" is **IMPLIED** — exactly
one application exists; the claim graduates to PROVEN when a second,
differently-shaped app composes the same core.

---

## 9. CURRENT EXTENSION POINTS (the architectural safety inventory)

| Seam | Location | What can attach without core changes |
|---|---|---|
| `ProviderAdapterPort` | `core/providers/ports.py:57` | Any provider; proven 3× incl. remote gateway |
| Remote Gateway contract | `gateway-service/docs/CONTRACT.md`; `providers/real/gateway/adapter.py` | Whole fleets of remote providers behind one adapter class |
| `ProviderAgentModulePort` | `core/providers/ports.py:126` | Provider-native agents (Assistants-style) |
| `WorkflowRuntimePort` | `core/execution/workflow_ports.py` | Durable engine (e.g. Temporal) — port shape fixed, binding = ADR |
| Queue/Lease/Cache/RateLimit ports | `core/runtime/ports.py` | Redis binding exists; any equivalent substitutable |
| `OutboxPort` | `core/runtime/outbox.py` | Transactional event publication |
| `SecretManagerPort` | `core/secrets/ports.py:37` | Vault bound; KMS substitutable |
| `ObjectStoragePort` | `core/storage/ports.py:45` | S3-compatible bound; artifact layer can build on it |
| `UsageAccountingPort` / `UsageConfigurationPort` | `core/usage/ports.py`, `core/admin/service.py:80` | Real billing backends |
| `AuditLogPort` / `EvaluationStorePort` | `core/audit/ports.py`, `core/evaluation/ports.py` | Durable stores |
| Principal seam | `apps/api/app.py:162` | Real authn (sessions exist in `core/identity/service.py`, not yet wired to HTTP) |
| Injectable idempotency/webhook maps | `apps/api/app.py` `build_app` params (T-IMPL-072) | Redis/DB-backed cross-replica state |
| Tool/Skill/Role registries + gate | `core/tools/`, `core/skills/`, `core/roles/` | Product capabilities as data |
| Composition roots | `apps/composition/` (gateway/secrets/storage) | Env-driven binding pattern to copy for new bindings |
| Provider scaffolding | `providers/templates/` (12), `gateway-service/providers/_template/` | New-provider onboarding per doc 31 |

---

## 10. MISSING GENERIC PRIMITIVES (consolidated, with absence evidence)

1. **Tool execution runtime** — no executor module; gate stops at
   admission (`core/tools/gate.py` returns a decision object; nothing
   consumes it to *run* anything). Searched `core/tools/`, `core/skills/`,
   `apps/` for execution surfaces.
2. **Agent loop / model-directed action selection** — no consuming
   surface for model output beyond text return (R094/R095 records;
   t033 structural tests).
3. **Async execution + background jobs for executions** — API rejects
   async/stream (`apps/api/app.py:449–460`); worker machinery exists but
   no execution rides it.
4. **Durable workflow engine binding** — port only
   (`core/execution/workflow_ports.py`: "NO real engine binding exists").
5. **Graph strategy execution** — planner/validator only; only
   single+pipeline execute (`core/execution/service.py`).
6. **Streaming** — contract shapes only.
7. **Webhook delivery / event bus egress** — registration only.
8. **Scheduler / trigger primitive** — nothing found (search recorded §5).
9. **Human-approval operational workflow** — states/verdicts only; no
   queue, endpoints, or resume.
10. **Persistence repository layer** — schema + parity tests exist;
    no row↔contract repositories (search recorded §4 "Durable state").
11. **HTTP authn binding** — identity service exists in-memory; Principal
    injected at composition, not derived from request credentials.
12. **Semantic retrieval** — deferred by R044(c); pgvector dep unused.
13. **Structured-output enforcement** — schema accepted, not enforced
    (R095 attach-at-surface rule governs when it must land).
14. **Workspace/artifact abstraction** — object storage only.

---

## 11. X² CAPABILITY RECOMMENDATIONS (the smallest set with the largest multiplier)

Ranked. Each: current status → why it matters → unlocks → additive? →
impact → dependencies → risks → placement.

### X²-1. Asynchronous Durable Execution (async API + queue-backed runs + workflow binding)
**Priority: HIGH · Capability multiplier: ×× (the single biggest unlock)**
- **Status:** all ingredients PROVEN separately (queue/worker/lease/outbox/
  admission; `waiting_approval` status; async response contracts); nothing
  composed; API rejects async.
- **Why:** every serious product class blocked in §5 (research, automation,
  IDE tasks, marketing campaigns) is blocked *first* on "work that
  outlives a request".
- **Unlocks:** long-running anything; retries that survive crashes;
  approval gates that actually wait; scheduled work (X²-4) has somewhere
  to land.
- **Additive?** Yes: flip the async path in `apps/api` to enqueue via
  existing `QueuePort`/outbox; workers call the existing
  `ExecutionService`; status already served by `GET /v1/executions/{id}`.
  Durable engine binds behind `WorkflowRuntimePort` later (ADR required —
  new dependency).
- **Impact:** zero core contract changes for the queue-backed slice; one
  ADR for the engine binding.
- **Dependencies:** persistence repositories (X²-5) for honest durability.
- **Risks:** double-billing on replay (mitigated: idempotency + reserve/
  settle ledger already exact-once by test); operational complexity.
- **Placement:** GENERIC PLATFORM.

### X²-2. First-class Tool Execution Runtime (server-side first, client transport later)
**Priority: HIGH · Multiplier: ××**
- **Status:** admission PROVEN (`core/tools/gate.py`), execution ABSENT.
- **Why:** tools are the boundary between "AI answers" and "AI acts"; the
  hard part (deny-by-default admission, device trust, approval
  composition) is already built and tested — the runtime is the missing
  thin half.
- **Unlocks:** IDE tools, marketing channel actions, automation actions;
  makes the agent loop (X²-3) meaningful.
- **Additive?** Yes: an executor that (1) requires a gate ALLOW verdict,
  (2) dispatches to a handler registered per tool id (handlers live in
  apps/providers — never core), (3) normalizes results/errors as data,
  (4) audits + accounts. Contracts (`ToolManifest`, sandbox/rate/approval
  policies) already carry the needed fields.
- **Impact:** new core module + registry of handlers at composition; no
  existing contract breaks.
- **Dependencies:** none hard; async (X²-1) for long tools; client
  transport is a separate later ADR.
- **Risks:** THE security-critical surface — must preserve "every call
  passes the gate" as a structural property (single execution path, same
  posture as the gate's no-skill-parameter rule).
- **Placement:** runtime GENERIC; tool *handlers* PRODUCT-LEVEL.

### X²-3. Agent Execution Loop (bounded plan→act→observe under existing governance)
**Priority: HIGH · Multiplier: ×× (but strictly after X²-1/X²-2)**
- **Status:** ABSENT; all governance surfaces it must obey are PROVEN
  (firewall, gate, budgets, admission, lifecycle states, graph contracts).
- **Why:** converts the classification from "orchestration platform" to
  "agent platform" honestly.
- **Unlocks:** agentic products across §5; `ExecutionStrategy.AGENT`
  stops being vocabulary.
- **Additive?** Yes: a loop driver inside execution that per step: model
  proposes (structured output) → platform validates (this is where the
  R095 attach-at-surface validator duty triggers — same commit) → gate
  admits → executor runs → observation appended → bounded by budget/
  step-count/admission. The model proposes; deterministic code disposes —
  the invariant the whole security model already assumes.
- **Impact:** new core module + the six §7 output-validation contexts
  gain their consuming surface (validators land with it, R095 binding
  rule).
- **Dependencies:** X²-2 (hard), X²-1 (for non-trivial runs), structured-
  output validation (part of this work).
- **Risks:** highest of the three; mitigated by the pre-built cage.
- **Placement:** GENERIC PLATFORM (loop mechanics); prompts/policies
  PRODUCT-LEVEL data.

### X²-4. Event & Schedule Primitive (webhook delivery + triggers)
**Priority: MEDIUM · Multiplier: ×**
- **Status:** registration PROVEN; delivery/schedule ABSENT.
- **Why/unlocks:** automation + marketing classes; operational visibility.
- **Additive?** Yes: outbox→worker delivery loop (machinery exists);
  schedule = a worker that enqueues executions on time policy.
- **Dependencies:** X²-1. **Risks:** SSRF surface appears with outbound
  delivery — URL validation duty attaches (R095 rule, again same-commit).
- **Placement:** GENERIC.

### X²-5. Persistence Repository Layer (Postgres bindings for the port set)
**Priority: MEDIUM (prerequisite-shaped) · Multiplier: enabling, not
headline**
- **Status:** schema PROVEN (12 migrations + parity tests); repositories
  ABSENT; every consumer already speaks ports.
- **Why:** durability honesty for everything above; multi-replica truth.
- **Additive?** Maximally — the definition of the existing seams.
- **Risks:** low; parity tests already pin shapes.
- **Placement:** GENERIC (infrastructure/).

### X²-6. Streaming (SSE progress/tokens)
**Priority: MEDIUM · Multiplier: × (UX-critical for chat/IDE, not
capability-creating)**
- Contracts exist (10 §11 shapes); additive at API + adapter capability
  flag; per-provider support varies. GENERIC.

### Explicitly NOT recommended now
- **Policy engine / richer RBAC** — firewall + plan/entitlement data
  cover current needs; adding a generic policy engine before a second
  application exists would speculate on requirements.
- **More providers for their own sake** — the gateway (G1–G4) already
  made provider count a configuration/deployment concern, not
  architecture.
- **Semantic memory** — valuable, but it multiplies *quality*, not
  *capability class*; R044(c) deferral stands until a product pulls it.

**Dependency spine:** X²-5 → X²-1 → X²-2 → X²-3, with X²-4/X²-6 hanging
off X²-1. The first three HIGH items are the X²: with them, every product
class in §5 moves to READY NOW / READY WITH CONFIGURATION.

---

## 12. WHAT MUST REMAIN OUTSIDE CORE (non-negotiables, from existing invariants)

1. **Provider specifics** — adapters/gateway only; core consumes
   normalized manifests/errors (30 §4.2/§14; import contracts).
2. **Tool handlers and client runtimes** — core admits and (future)
   dispatches; what a tool *does* is app/provider territory
   (`core/contracts/tools.py` scope boundary).
3. **Product domain logic** — campaigns, repos, tickets: applications.
4. **Prompts/personas/procedures** — data via role/skill registries.
5. **Infrastructure clients** — Postgres/Redis/Vault/S3/HTTP stay in
   `infrastructure/`+`apps/` (import contracts 5–12).
6. **The web framework** — FastAPI is apps-only (contract 8); core stays
   framework-free.
7. **Secret material** — opaque refs only inside the platform (20 §5;
   proven end-to-end incl. gateway BYOK custody).
8. **Authority decisions by the model** — the LLM never decides
   permissions (20 §1; firewall actor set excludes `llm`). The agent loop
   (X²-3) must preserve this: models propose, code disposes.

---

## 13. RECOMMENDED FUTURE PHASES (for operator decision — nothing here is authorized)

| Phase | Content | Gate |
|---|---|---|
| P-A | UI/UX phase on current surface (see §14 — sufficient for a real management UI now) | already authorized-adjacent |
| P-B | Persistence repositories (X²-5) + HTTP authn binding at the Principal seam | no ADR needed (deps exist) |
| P-C | Async durable execution (X²-1, queue-backed slice) | ADR only when engine binds |
| P-D | Tool execution runtime (X²-2, server-side) | security review mandatory |
| P-E | Agent loop (X²-3) + structured-output validators (R095 same-commit duty) | operator design ADR |
| P-F | Events/schedules + webhook delivery (X²-4); streaming (X²-6) | SSRF validator same-commit |

Any single phase is independently shippable; none rewrites prior work.

---

## 14. UI/UX READINESS

### 14.1 Seam map

```text
CURRENT BACKEND CAPABILITY → API SURFACE → UI SURFACE → MISSING SEAM
```

| Backend capability | API surface (exists) | UI it supports | Missing seam |
|---|---|---|---|
| Execute + history | `POST /v1/execute`, `GET /v1/executions/{id}` (`apps/api/app.py:426,781`) | Ask console; execution detail w/ per-node trail, cost snapshot, named routing exclusions | List/search executions endpoint (only GET-by-id exists); streaming for live progress |
| Models & providers | `GET /v1/models` (:694); admin `GET /v1/admin/models`, `/providers` (`admin.py:239,255`) | Model catalog; provider status board | Provider CRUD/registration API (registries are composition-time data); model binding management endpoints |
| Usage & plans | `GET /v1/usage` (:719); admin `GET /v1/admin/plans/{tenant}` (:271) | Usage dashboards; plan/quota views | Plan CRUD; per-execution usage drill-down endpoint |
| Admin config governance | 7 change-lifecycle routes (`admin.py:137–230`) | Change-request UI with validate/preview/publish/rollback — a genuinely strong control-plane UX foundation | — |
| Evaluations | admin `GET /v1/admin/evaluations/{id}`, `/executions/{id}/evaluations` (:303,322) | Quality/verification dashboards | Tenant-facing (non-admin) evaluation read, if desired |
| Learning | admin `GET /v1/admin/learning/dashboard` (:343) | Learning ops view | — |
| Skills | `GET /v1/skills` (:670) | Skill catalog | Skill import/review lifecycle API (machinery exists in `core/skills/importing.py`, no HTTP surface) |
| Webhooks | `POST /v1/webhooks` (:746) | Notification settings (register) | List/delete subscriptions; delivery status (needs X²-4) |
| Routing weights | admin `GET /v1/admin/routing/weights` (:292) | Routing tuning view (read) | Write path goes through change lifecycle (exists) — UI just needs to compose it |
| Identity/sessions | `core/identity/service.py` (register/login/sessions) | Login/account UI | **The one hard gap: no HTTP auth endpoints; Principal is composition-injected** (`apps/api/app.py:162`) |
| Health/ops | gateway `/healthz` + `/v1/health` (`gateway-service/gateway/routes.py:96,216`); metrics/traces providers | Ops status page | Platform-app healthz/readiness endpoint; metrics export (OTLP deferred by ADR-0004) |
| Audit | `core/audit/ports.py` read/count | Audit trail viewer | No HTTP surface for audit reads |

### 14.2 Readiness verdict

**Sufficient to begin a serious management UI now.** The admin
control-plane surface (14 routes incl. the full change-governance
lifecycle) plus execute/models/usage/skills/executions covers the core
management scenarios. Three seams should be treated as UI-phase
*companions* (thin, additive, no architecture impact — each is surfacing
existing core machinery over HTTP): **(1)** auth endpoints binding
`InMemoryIdentityService` sessions to the Principal seam, **(2)** an
executions *list* endpoint, **(3)** an audit read endpoint. None blocks
starting; all three are PRODUCT-LEVEL API surfacing of PROVEN core
machinery, not new platform capability.

---

## 15. RISKS / CONSTRAINTS

1. **In-memory truth by default** — durable bindings exist for
   secrets/queue/storage but the execution/usage/evaluation stores run
   in-memory unless composed otherwise; multi-replica honesty needs X²-5.
2. **Single application proof-point** — kernel reuse is IMPLIED (§8.3).
3. **Live-provider e2e blocked** — 15 skipped tests await a fresh
   operator GSK key (standing item since R058/R060; also Groq key
   rotation and PAT revocation remain open per state file).
4. **Deployment surfaces open (Lane C)** — TLS at ingress, HA topology,
   OTLP collector, load/capacity testing: all recorded opens in
   `engineering/verification/FINAL_VALIDATION.md` §19, none code gaps.
5. **Agent-phase security duties are pre-committed** — R095 binding rule:
   any surface consuming model output for the six open validation
   contexts MUST land its validator in the same commit. X²-2/X²-3/X²-4
   all trigger it.
6. **Anti-hype discipline** — this platform must not be described as
   "enterprise-ready", "full autonomous agent", or "can do anything";
   the honest claims are exactly the PROVEN rows of §3.

---

## 16. FINAL VERDICT

**What the platform IS:** a rigorously-bounded, multi-tenant AI
orchestration kernel — unified execute API, policy-driven routing with
named exclusions, disciplined provider plugin architecture (including a
hardened remote gateway data plane), exact-once usage accounting,
deny-by-default security gates, evaluation with verification levels, and
a governed admin control plane — all hermetically tested (1605+122 tests)
with machine-enforced architecture boundaries.

**What it is NOT (yet):** an agent platform (no tool execution, no action
loop, no async/durable runs, no streaming); a durable multi-replica
deployment (repositories/bindings pending); a proven multi-product
foundation (one app exists); anything resembling "runs arbitrary business
workflows".

**What it can BECOME without architectural destruction:** a genuine
general-purpose Agent Platform — because every missing capability in §10
attaches at an existing, tested seam (§9): async execution rides the
existing queue/worker/outbox; tool execution completes the existing gate;
the agent loop runs inside the existing budget/firewall/lifecycle cage;
durability binds behind existing ports. No finding in this assessment
requires rewriting `core/`, breaking `ProviderAdapterPort`, breaking the
Gateway contract, moving provider logic into core, duplicating billing,
or weakening tenant isolation/authorization. The X² path (§11) is
additive end-to-end.

**Recommended next step:** proceed to the UI/UX phase on the current
surface (with the three thin companion endpoints noted in §14.2), and
schedule X²-5 → X²-1 → X²-2 → X²-3 as the capability track behind it —
subject to operator authorization.
