# R177-A04 — Composition-surface map (as implemented at HEAD 13be858d)

## 1. `create_app(...)` seams — 37 keyword parameters (`apps/api/app.py` signature)
router execution_service store principal auth skills roles conversations memory composer context_budget admin models bindings usage
webhooks rate_limits execute_rate_limit execute_rate_window_seconds outbox execute_stream idempotency_index webhook_subscriptions
system_info healthz sse sse_poll_interval_seconds sse_timeout_seconds sse_sleeper source_proposals workspaces projects source_snapshots
agent engineering_admin public_paths dev_bindings

KNOWN: directive said "~35"; real count **37** (several are tuning knobs, not capability seams: `context_budget`, `execute_rate_limit`,
`execute_rate_window_seconds`, `execute_stream`, `sse_*`, `public_paths`, `system_info`).

Absent-seam semantics observed in code (three distinct postures — important for §6 "optional/composable" claims):
- **Mount-time gating** (true absence → 404): `if agent is not None:` (app.py:1454) mounts `/v1/agent/*`; `if admin is not None and memory is not None:` (2084) mounts learning admin routes; admin router only when `admin` given (docstring :80 "absent seam ⇒ HTTP 404").
- **Defaults-in-place** (NOT absence): `skills`/`roles` → empty registries (604-605); `projects`/`workspaces` → in-memory stores (720-723); `source_proposals`/`source_snapshots` → in-memory (2112-2115); `idempotency_index` → process dict (608-609). These capabilities are ALWAYS present in-process; the seam controls *durability*, not existence.
- **Response-shape gating**: `usage` absent ⇒ the `usage` block is absent from responses, never faked (:34, :348).

## 2. Published catalog — `GET /v1/admin/capabilities` over `CAPABILITY_IDS` (17, closed by test; `apps/api/capabilities.py:58-78`)
| capability id | state rule (app.py 1847-1920) | seam(s) | route(s) |
|---|---|---|---|
| execute.sync | always AVAILABLE | — | POST /v1/execute |
| execute.async | `outbox is not None` | outbox, execute_stream | POST /v1/execute (async) → GET /v1/executions/{id} |
| execute.token_streaming | recorded UNAVAILABLE | — | — |
| executions.progress_sse | `sse` | sse, sse_* | GET /v1/executions/{id}/events |
| conversations.persistence | `conversations is not None` | conversations | inside /v1/execute |
| context.composition | `composer is not None` | composer, context_budget, memory | inside /v1/execute |
| models.listing | `models and bindings` | models, bindings | GET /v1/models |
| skills.listing | always AVAILABLE | skills | GET /v1/skills |
| usage.reporting | `usage is not None` | usage | GET /v1/usage |
| webhooks.registration | webhooks | webhooks, webhook_subscriptions | GET/POST/DELETE /v1/webhooks |
| webhooks.delivery_staging | `webhooks and outbox` | outbox | staging only (no relay composed — R176 F-R176-11 latent) |
| admin.control_plane | `admin is not None` | admin | /v1/admin/* (57 routes) |
| learning.lifecycle | `admin and memory` | admin, memory | /v1/admin/learning/* (12 routes) |
| rate_limits.execute | `rate_limits and execute_rate_limit > 0` | rate_limits | inside /v1/execute (429) |
| auth.sessions | `auth is not None` | auth, principal | /v1/auth/{register,verify,login,logout,session} |
| health.liveness | `healthz` | healthz | GET /healthz |
| dev.publish_modes | `dev_bindings is not None` | dev_bindings | /v1/dev/* (not in the env profile → absent from the 79-route list) |

## 3. Real HTTP surface of the env-composed profile — 79 routes (`apps.cli routes` → `routes_env_composed.json`)
admin control plane **57** (`/v1/admin/*`: audit; capabilities + exercisable + exercise; changes propose/validate/preview/publish/rollback;
context-lab; evaluations; learning ×12 (samples list/get/scan/sanitize/evaluate/admit/promote, ask, learned, dashboard,
changes-since-review, mark-reviewed, capability-retest); models/providers/plans/routing-weights; notifications + ack; scenarios +
regression-pack + replay; self-review; skills import ×7 (import, list, scan, validate, review, approve, activate); source-changes ×8
(list/create, snapshots, get, verify, approve, reject, apply, rollback); system; usage) · agent **5** (`/v1/agent/converse`,
`/v1/agent/tools`, `/v1/agent-tools`, executions `{id}/trace` + `{id}/diagnosis`) · auth **5** · execute/executions **4** · models/skills/usage
**3** · webhooks **3** · workspaces **2** · projects **2** · healthz **1**.

## 4. Which seam / route each operator-desired capability (§6) touches today
| operator capability | seam(s) | route(s) | catalog id | note |
|---|---|---|---|---|
| Identity | auth, principal | /v1/auth/* | auth.sessions | DEVICE/session identity (core/identity/devices.py), not persona |
| Memory (13 §2 six types) | memory, conversations, composer | inside /v1/execute; admin learning/learned | context.composition, conversations.persistence | no end-user memory CRUD route; memory reaches the user only through composition |
| Knowledge (GOLD memory) | memory + admin | POST /v1/admin/learning/ask, GET …/learned | learning.lifecycle | admin-only read surface |
| Soul / personalization | memory (preferences gate) | none dedicated | — | NEW VOCABULARY → A06 |
| Learning | memory + admin | /v1/admin/learning/* | learning.lifecycle | present |
| Evaluation | admin (evaluation store) | /v1/admin/evaluations/*, /executions/{id}/evaluations, scenarios | admin.control_plane | present |
| Tools | agent | /v1/agent-tools, /v1/agent/tools | (none) | mounted, not named in catalog |
| Skills | skills, admin | /v1/skills, /v1/admin/skills/* | skills.listing | present |
| Repository understanding | agent (+workspaces, engineering_admin) | via agent tools (ws_*/source_*) | (none) | tools exist; no persisted "project map" artefact → A08 |
| Context/session state | composer, context_budget, conversations | inside /v1/execute | context.composition | present |

**Catalog completeness observation (KNOWN)**: the agent runtime, source-change workflow, skills import, workspaces/projects and
evaluation are mounted and exercised (57 admin + 5 agent routes) but have **no row** in the closed `CAPABILITY_IDS`. Not a runtime
defect; extending the catalog is a closed-set edit that needs approval (§3.7) → candidate R177-FIX in A12.
