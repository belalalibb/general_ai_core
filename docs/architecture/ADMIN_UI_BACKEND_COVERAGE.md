# ADMIN UI BACKEND COVERAGE MATRIX

**Document B of 4.** Companions:
[A — Master Plan](ADMIN_AGENT_UI_UX_MASTER_PLAN.md) ·
[C — Implementation Phases](ADMIN_AGENT_IMPLEMENTATION_PHASES.md) ·
[D — UI Principles](ADMIN_AGENT_UI_PRINCIPLES.md).

**Status:** PLANNING ONLY. **Baseline:** `main` @ `5c1410b…` (see doc A
front-matter for session-verified counts and commands).

**Purpose:** one row per backend capability — the whole platform, nothing
dropped. Columns: Backend capability · Evidence · Truth tag · Current API ·
Admin interaction (Agent tool class per doc A §3.3: R0 read / R1 test /
R2 config-change / R3 source-change) · View/Edit/Test · Diagnostics · Audit ·
Responsibility class · Missing seam.

**Truth tags:** PROVEN / ARCH-POSSIBLE / MISSING / REC-FUTURE (doc A §2).
**Responsibility classes:** PLATFORM-GENERIC (PG) / APPLICATION-SPECIFIC (AS)
/ ADMIN-ONLY (AO) / USER-FACING (UF) / INTERNAL (INT) / FUTURE (FUT).

**Terminability check (mandate §7):** §1 maps all **20 platform routes** and
all **5 gateway routes** (route lists reproduced by grep in-session, doc A
front-matter). §2 covers every runtime module directory: `core/` has exactly
20 module dirs (`ls core/` → admin, audit, context, contracts, evaluation,
execution, identity, learning, memory, providers, roles, routing, runtime,
secrets, security, skills, storage, tools, usage + contracts counted once),
plus `apps/`, `infrastructure/`, `providers/`, `gateway-service/`. Every
directory appears in a row or in §4. Exploration STOPPED at that point.

---

## 1. ROUTE-LEVEL COVERAGE (every public HTTP route)

### 1.1 Platform public routes (`apps/api/app.py` — 6)

| # | Route | Backend capability | Evidence | Tag | Admin interaction | View/Edit/Test | Diagnostics | Audit | Class | Missing seam |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | `POST /v1/execute` (:426) | full execute pipeline: role admission → idempotent replay → context → routing → entitlement reserve → provider exec w/ retry+failover → settle → evaluate | `core/execution/service.py`; suite passes in the 1597 | PROVEN | R1 EXECUTE-TEST (labeled via `RequestContext`); the Agent's test verb | View result; Test = the verb itself | attempt trail is diagnosis input (doc A §7) | execution recorded; usage ledger | PG | streaming/async rejected (422, app.py:449–460) — REC-FUTURE, doc C §6 |
| P2 | `GET /v1/executions/{id}` (:781) | tenant-scoped execution status/result read | app.py:781–825; IDOR fix T-IMPL-033 | PROVEN | R0 | View | primary evidence read for trace view | n/a (read) | PG | **EXE-1**: no LIST/search endpoint — see §5 |
| P3 | `GET /v1/skills` (:670) | selectable-skill catalog | route + `core/roles/registry.py` SkillRegistry | PROVEN | R0 | View | — | n/a | PG/UF | **SKL-1**: import-lifecycle machinery (`core/skills/importing.py`) has NO HTTP surface — §5 |
| P4 | `GET /v1/models` (:694) | model catalog (routable) | route + ModelRegistry | PROVEN | R0 | View | — | n/a | PG/UF | admin variant exists (A2); binding management API missing → PRV-4 |
| P5 | `GET /v1/usage` (:719) | tenant usage summary | route + `UsageAccountingPort.summary` | PROVEN | R0 | View | budget-exceeded diagnosis input | ledger IS the audit | PG | **USG-2**: per-execution usage drill-down endpoint — §5 |
| P6 | `POST /v1/webhooks` (:746) | webhook subscription registration | route; `core/contracts/webhooks.py` | PROVEN (registration only) | R0 (list is missing) | Edit(create) | — | n/a | PG | **WBH-1**: list/delete subscriptions; delivery itself MISSING (docstring records not-claimed) — §5 + doc C §6 |

### 1.2 Admin routes (`apps/api/admin.py` — 14)

All gated by `_gate()` (deny-by-default `is_admin` before parsing — PROVEN).

| # | Route | Backend capability | Evidence | Tag | Admin interaction | View/Edit/Test | Diagnostics | Audit | Class | Missing seam |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | `POST /v1/admin/changes` (:137) + `GET /changes` (:155) + `GET /changes/{id}` (:168) + `POST .../validate` (:209) + `.../preview` (:216) + `.../publish` (:223) + `.../rollback` (:230) — 7 routes | governed config lifecycle over the 10 `AdminAction` verbs across 6 active areas | `core/admin/service.py` (608 lines); `tests/admin/` | PROVEN | **R2** — Agent drafts/validates/previews; PUBLISH = explicit admin click (doc A §3.2 rule 4) | View + Edit (lifecycle-gated) | impact preview backend-computed | ADMIN_CONFIG_* events structurally required | PG (lifecycle) / AO (surface) | — (this is the strongest existing surface) |
| A2 | `GET /v1/admin/models` (:239) | model catalog incl. DISABLED | route reads ModelRegistry directly | PROVEN | R0 | View; Edit via A1 | disabled-model exclusions cross-ref | via A1 on change | AO | — |
| A3 | `GET /v1/admin/providers` (:255) | provider catalog incl. templates (marked, never routable) | route + registry eligibility layer | PROVEN | R0 | View; Edit via A1 | provider-down diagnosis input | via A1 | AO | **PRV-4**: runtime provider/account registration API — registries are composition-time data — §5 |
| A4 | `GET /v1/admin/plans/{tenant_id}` (:271) | tenant plan/limits view | route + usage seam | PROVEN | R0; SET_PLAN via A1 (R2) | View; Edit via A1 | budget diagnosis input | via A1 | AO | plan CATALOG (list all plans) not exposed — minor, folds into USG-2 design |
| A5 | `GET /v1/admin/routing/weights` (:292) | current default scoring weights | route + RoutingWeightsPort | PROVEN | R0; SET_ROUTING_WEIGHTS via A1 (R2) | View; Edit via A1 | routing-change vs failure correlation | via A1 | AO | — |
| A6 | `GET /v1/admin/evaluations/{id}` (:303) + `GET /executions/{id}/evaluations` (:322) | evaluation records w/ score/confidence/evidence_ref — admin-only by 22 §7 | routes + `EvaluationStorePort` | PROVEN | R0 | View | quality diagnosis input | n/a | AO | tenant-facing eval read = deliberate non-exposure (§4) |
| A7 | `GET /v1/admin/learning/dashboard` (:343) | learning dashboard — STRUCTURAL PLACEHOLDER (`placeholder: Literal[True]`, honest zeros) | `core/contracts/admin.py:199–208` | PROVEN (as placeholder) | R0 — UI must render "NOT OPERATIONAL" (doc A §8) | View only | — | n/a | AO | learning lifecycle itself — REC-FUTURE (doc C §6); the UI must NOT fabricate metrics |

### 1.3 Gateway-service routes (5) — separate data plane, ADR-0008 CLOSED

| # | Route | Capability | Evidence | Tag | Admin interaction | Class | Missing seam |
|---|---|---|---|---|---|---|---|
| G1 | `GET /healthz` (routes.py:96) | gateway liveness | 122 gateway tests pass | PROVEN | R0 via platform-side proxy read ONLY (admin UI never talks to the gateway directly — secrecy boundary, doc A §9) | INT | platform-side gateway-status read-model (part of SYS-1) |
| G2 | `POST {prefix}/execute` (:101) | provider execution data plane | G3 Groq provider; settlement tests | PROVEN | never direct — reached only through `RemoteGatewayAdapter` | INT | — |
| G3 | `GET {prefix}/describe` (:190) | provider description | tests | PROVEN | consumed by platform adapter | INT | — |
| G4 | `GET {prefix}/models` (:203) | model discovery | tests | PROVEN | surfaces through platform discovery (R0) | INT | — |
| G5 | `GET {prefix}/health` (:216) | provider health | tests | PROVEN | surfaces through platform health probes (R0) | INT | — |

---

## 2. MODULE-LEVEL COVERAGE (every runtime module directory)

| Module | Capability (headline) | Evidence | Tag | Current API | Admin interaction | Diagnostics | Audit | Class | Missing seam |
|---|---|---|---|---|---|---|---|---|---|
| `core/admin/` | config lifecycle service | §1.2 A1 | PROVEN | 7 routes | R2 | impact preview | structural | PG | — |
| `core/audit/` | append-only audit log; closed 13-value event set; tenant-scoped read/count | `core/audit/{ports,memory}.py`; `tests/audit/` | PROVEN | **NONE** | R0 (once surfaced) | change-vs-failure correlation | it IS the audit | PG | **AUD-1** — §5 |
| `core/context/` | context composition (roles/memory/skills into prompt context) | `core/context/composer.py`; `tests/context/` | PROVEN | inside P1 | R0 view of composed-context metadata in execution detail | context-stage diagnosis | n/a | PG | none needed for v1 (rendered from execution evidence) |
| `core/contracts/` | 31 contract modules — the typed vocabulary (closed enums, extra=forbid) | `ls core/contracts` → 31 files; `tests/contract/` | PROVEN | n/a (definitions) | UI types derived from these (doc A §15) | closed-set rendering | n/a | PG | — |
| `core/evaluation/` | graders (deterministic + model judge), policy service, verification levels | §1.2 A6; `core/evaluation/policy.py` | PROVEN | A6 reads | R0; R1 (evaluation happens on real executions) | quality diagnosis | n/a | PG | — |
| `core/execution/` | single+pipeline execution, graph planner (plan/validate only), workflow ports (no binding) | `service.py`, `graph_planner.py`, `workflow_ports.py` | PROVEN (single/pipeline) / ARCH-POSSIBLE (graph strategies, workflow port) | P1/P2 | R0+R1 | attempt trail | execution records | PG | graph EXECUTION and workflow binding — REC-FUTURE (doc C §6) |
| `core/identity/` | users/sessions/devices — register/verify/login/resolve/logout; device trust state machine | `service.py:83–228`, `devices.py`; `tests/identity/` | PROVEN (in-memory, not HTTP-bound) | **NONE** | login IS the admin's entry | auth-stage gap (doc A §6) | LOGIN/LOGOUT audit types exist | PG | **IDN-1** — §5 (the hardest prerequisite) |
| `core/learning/` | eligibility + promotion gates over signals | `gates.py`; `tests/learning/` | PROVEN (gates only — no operating lifecycle) | A7 placeholder | R0 with NOT-OPERATIONAL disclosure | — | TRAINING_DATASET_PROMOTED type reserved | PG | lifecycle machinery — REC-FUTURE |
| `core/memory/` | conversations/messages + memory scopes + preferences, tenant+user isolated | `memory.py`, `preferences.py`; `tests/memory/` | PROVEN | inside P1 (auto-conversation) | R0 view within execution detail | context diagnosis | n/a | PG | admin memory browser = deliberate non-exposure v1 (§4 — privacy posture) |
| `core/providers/` | provider/model/binding registries; account pools w/ lease+cooldown; ports | `registry.py`, `accounts.py`, `ports.py`; `tests/providers/` (largest suite) | PROVEN | P4/A2/A3 | R0 catalog + probes; R2 enable/disable | health probes | via A1 | PG | PRV-4 — §5 |
| `core/roles/` | role registry (ACTIVE-only selection), governance (system vs custom scopes) | `registry.py`, `governance.py`; `tests/roles/` | PROVEN | **no direct route** (roles ride execute via `RoleSelector`) | R0 view in Catalog | role-admission diagnosis | n/a | PG | role read/manage API — folded into Catalog design, thin read seam rides AGT-1 tool set (no separate seam id: read-only over registry) |
| `core/routing/` | scoring router w/ named exclusions, planner, bootstrap, resources | `router.py`, `planner.py`; `tests/routing/` | PROVEN | A5 (weights); decisions inside P1 | R0; R2 weights | exclusion records = key diagnosis input | via A1 | PG | — |
| `core/runtime/` | queue/worker/lease/DLQ/outbox/admission/rate-limits (machinery; no execution rides it) | `worker.py`, `admission.py`, `outbox.py`; `tests/runtime/` incl. chaos t071 | PROVEN (machinery) | **NONE** | R0 runtime gauges (once SYS-1 exists) | queue-depth/DLQ views | n/a | PG | async execution path — REC-FUTURE (doc C §6); runtime read-model part of SYS-1 |
| `core/secrets/` | SecretManagerPort (store/resolve/revoke/exists, opaque refs) | `ports.py:37–65`; `tests/secrets/` | PROVEN | NONE (by design) | **R4 FORBIDDEN** — never a UI/Agent surface for values; existence/health only via provider credential probes | credential-status diagnosis (status only) | CREDENTIAL_* audit types | PG | deliberate non-exposure (§4) |
| `core/security/` | capability firewall — deny-by-default, closed decision set | `firewall.py`; `tests/security/` (incl. t033/t034 adversarial) | PROVEN | inside execution path | R0 view of decisions (via audit once AUD-1) | PERMISSION_DENIED evidence | audit types exist | PG | — |
| `core/skills/` | import lifecycle (allowlist, checksum, scan→validate→review→approve→activate) + resolver | `importing.py`, `resolver.py`; `tests/skills/` | PROVEN (machinery, hermetic-by-design) | P3 (catalog only) | R0 catalog; R2 enable/disable; import review = FUTURE surface on SKL-1 | scan-findings evidence | n/a | PG | **SKL-1** — §5 |
| `core/storage/` | ObjectStoragePort, tenant-prefixed | `ports.py`; S3 binding `infrastructure/storage/s3.py`; live smoke passed (R101) | PROVEN | NONE | none in v1 | — | n/a | PG | artifact surface — REC-FUTURE (rides the workspace primitive, doc C §6) |
| `core/tools/` | tool registry + call gate (admission ONLY — executes nothing) | `registry.py`, `gate.py`; `tests/tools/` | PROVEN (admission) / MISSING (execution — `ls core/tools/` shows no executor) | NONE | R0 catalog; R2 enable/disable | gate-decision evidence | TOOL_CALL audit type | PG | tool EXECUTOR — REC-FUTURE (doc C §6) |
| `core/usage/` | reservation ledger + estimation + summary | `ports.py`, `estimation.py`; `tests/usage/` | PROVEN | P5/A4 | R0 | settlement diagnosis | ledger | PG | USG-2 — §5 |
| `apps/api/` | HTTP surface + error mapping + in-memory execution store | app.py/admin.py/errors.py/store.py | PROVEN | §1 | — | — | — | AS | IDN-1/EXE-1/AUD-1 attach here |
| `apps/composition/` | env-driven binding roots (gateway/secrets/storage) — the ONLY boto3/hvac/gateway construction sites; credential-scrubbed reprs | `apps/composition/*`; 16 hermetic tests (R101) | PROVEN | n/a | INT | misconfig = named error | n/a | AS/INT | — |
| `apps/observability/` | logs/metrics/traces providers, sampler, config (console/no-op exporters; OTLP deferred by ADR-0004) | `apps/observability/*`; `tests/observability/` | PROVEN (pipeline) — no collector | NONE | R0 (SYS-1 read-model) | — | n/a | INT | **SYS-1** — §5 |
| `infrastructure/db/` | SQLAlchemy tables + 12 migrations + parity tests; NO repositories | `tables.py`, `migrations/versions/` (12); `tests/db/` | PROVEN (schema) / MISSING (repositories — search recorded) | n/a | INT | — | n/a | PG | repositories — REC-FUTURE #1 (doc C §6) |
| `infrastructure/redis/` | queue/lease/cache/rate-limit bindings (ADR-0003) | `binding.py` | PROVEN | n/a | INT | — | n/a | PG | — |
| `infrastructure/secrets/` `infrastructure/security/` `infrastructure/storage/` | Vault binding (ADR-0007) · Argon2id hashing (ADR-0005) · S3 binding (ADR-0006) | respective modules + tests + live smoke (R100/R101) | PROVEN | n/a | INT | — | n/a | PG | — |
| `providers/real/` + `providers/templates/` + `providers/registry/` + `providers/common/` | 3 real adapters (groq, genspark_llm, gateway) + 12 capability templates + registration helpers | `ls providers/real providers/templates`; `tests/providers/` | PROVEN (3 real) / templates = scaffolds (non-routable, structurally) | via execution + catalog | R0/R1/R2 per §1 | — | — | PG | — |
| `gateway-service/` | remote provider data plane (G1–G4): auth w/ secret versioning + rotation drill, route tokens, Groq, failure containment, leak-tested | 122 tests; §1.3 | PROVEN | 5 routes (INT) | via platform only | — | gateway-side observability enum | INT | platform-side status read-model (in SYS-1) |

---

## 3. NON-HTTP CAPABILITY ROWS (capabilities without any route, called out so nothing silently disappears)

| Capability | Evidence | Tag | Disposition |
|---|---|---|---|
| Idempotent replay (Idempotency-Key on execute) | `apps/api/app.py` idempotency_index (T-IMPL-072 injectable) | PROVEN | rendered in execution detail ("replayed") — no new seam |
| Webhook payload contracts + 6 event types | `core/contracts/execute.py:220–231` | PROVEN (shapes) | WBH-1 list/delete; delivery REC-FUTURE |
| Execution graph planning/validation (11 node types) | `core/contracts/execution_graph.py:61–71`; `core/execution/graph_planner.py` | PROVEN (plan/validate) | View-only render of planned graphs when present; graph EXECUTION is REC-FUTURE |
| Provider agent events (7-event normalized set) | `core/contracts/provider_agent.py`; `ProviderAgentModulePort` | ARCH-POSSIBLE | listed as INERT in Catalog; no UI workflow until an adapter exists |
| Device trust lifecycle (pair/trust/expire/revoke/compromise) | `core/identity/devices.py`; `tests/identity/` | PROVEN | System surface read-model (rides IDN-1 design); client-runtime transport REC-FUTURE |
| Model policy / model listing / plan contracts | `core/contracts/{model_policy,model_listing,plan}.py` | PROVEN (as consumed by router/usage) | rendered inside routing decisions + plan views; no separate surface |
| Structured output spec (`OutputSpec.schema_`) | `core/contracts/execute.py:84` | ARCH-POSSIBLE (accepted, NOT enforced — R095 attach-at-surface rule) | execution detail renders "schema declared, enforcement pending" honestly |

---

## 4. DELIBERATE NON-EXPOSURES (intentional, with reasons)

| Capability | Why not exposed to the Admin UI/Agent |
|---|---|
| Secret VALUES / credential material / resolution | 20 §5 custody: opaque refs only; R4-forbidden (doc A §3.3). Status/existence surfaces via credential-health probes only. |
| Gateway internals (slugs, route tokens, upstream URLs, secret versions) | ADR-0008/G4 secrecy doctrine; admin identity = platform-side provider key + display name (doc A §9). |
| Direct gateway HTTP access from UI | single custody path through `RemoteGatewayAdapter`; a second client would bypass platform accounting/audit. |
| User conversation/memory content browser | privacy posture: admin sees execution *records* and evaluation *evidence*, not a free browse of tenant user content; revisit only with an explicit operator policy decision. |
| Tenant-facing evaluation reads | 22 §7: "User sees the result only, by default. Admin sees the details." — deliberate asymmetry kept. |
| The 15 INERT AdminArea values as workflows | backend refuses areas without bindable machinery; UI lists them as INERT, never as clickable fake workflows (doc A §11). |
| Learning metrics/charts | dashboard is a structural placeholder; rendering charts over `placeholder: true` zeros would fabricate a lifecycle (doc A §8). |
| Mock/simulation execution mode | fake control; R1 tests are real bounded executions (doc A §8). |

---

## 5. MISSING SEAMS (UI requirement → existing capability → missing seam → minimal addition)

**None of these are implemented in this phase.** Each is the SMALLEST
addition that connects a UI requirement to PROVEN core machinery. Phase
placement in doc C.

| ID | UI requirement | Existing backend capability (PROVEN) | Missing seam | Minimal proposed addition |
|---|---|---|---|---|
| **IDN-1** | admin signs in; per-request Principal | `InMemoryIdentityService` register/login/sessions (`core/identity/service.py`); Principal seam (`apps/api`) | no HTTP auth endpoints; Principal composition-injected | login/logout/session routes in `apps/api` binding sessions → Principal per request; `is_admin` from identity. No new core code. |
| **EXE-1** | executions list/filter (tenant, status, time, `initiated_by`) | execution store holds tenant-keyed reports (`apps/api/store.py`) | GET-by-id only | `GET /v1/executions?filters` over the existing store; add a `list` method to the store protocol (apps-level, T-IMPL-072 pattern). |
| **AUD-1** | evidence citations; Changes surface trail; SECURITY/CHANGE notifications | `AuditLogPort.read/count` fully implemented | no HTTP surface | `GET /v1/admin/audit?filters` surfacing the port read, admin-gated. |
| **AGT-1** | the Admin Agent itself | ALL R0/R1/R2 target services exist | no agent service, no tool dispatcher | new `apps/admin_agent/` service: conversation loop + typed tool registry (config) + deterministic dispatcher enforcing R0–R4 classes; calls existing services/routes. APPLICATION-SPECIFIC; zero core changes. |
| **NTF-1** | notification center (6 categories) | audit events, execution failures, change lifecycle records | no notification model | poll-based read-model deriving notifications from audit + execution + change records; list/ack endpoints. No pub/sub. |
| **SKL-1** | skill import review workflow | full import pipeline (`core/skills/importing.py` — scan→validate→review→approve→activate) | no HTTP surface | admin routes surfacing the pipeline steps verbatim (each step already refuses out-of-order transitions in core). |
| **PRV-4** | register provider/account/binding at runtime | registries + account pools + template scaffolding | registries are composition-time data | admin registration routes over existing registry `register` methods, lifecycle-gated where config-shaped; needs a design decision on persistence (ties to repositories primitive). |
| **USG-2** | usage drill-down per execution / per model / per provider | `UsageLedger` per execution; summary per tenant | only tenant summary + per-execution ledger inside reports | `GET /v1/admin/usage?filters` read-model over ledgers. |
| **WBH-1** | manage webhook subscriptions | registration + injectable subscription map | no list/delete | list/delete routes over the existing map. |
| **SYS-1** | System surface: platform health, runtime gauges, gateway status, config disclosure | gateway `/healthz`; queue-depth gauge, DLQ, admission stats; observability providers | no platform healthz; no runtime/ops read-model | `GET /healthz` + `GET /v1/admin/system` read-model (process-local truths labeled as such). |
| **SRC-1** | source-change proposals (doc A §4) | audit types (`APPROVAL_DECISION`); repo gates (check_repo.sh) | everything else | design-first service in the final phase; operator-gated; FROZEN-COMPONENT stop rule. |

---

## 6. COVERAGE COMPLETENESS STATEMENT

- Rows in this matrix: **25 route rows (§1) + 28 module rows (§2) + 7
  non-HTTP capability rows (§3) + 8 deliberate non-exposures (§4) + 12
  missing seams (§5)**.
- Every public API route (20 platform + 5 gateway) appears in §1.
- Every runtime module directory appears in §2 (or §4 by reference).
- No capability was silently dropped: capabilities not exposed are in §4
  with reasons; capabilities that need seams are in §5 with minimal
  additions; nothing else exists at this baseline per the session searches
  recorded in doc A §2.3.
