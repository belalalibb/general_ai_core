# ADMIN AGENT UI PRINCIPLES — MINIMUM-COMPLEXITY IA & DESIGN SYSTEM

**Document D of 4.** Companions:
[A — Master Plan](ADMIN_AGENT_UI_UX_MASTER_PLAN.md) ·
[B — Coverage Matrix](ADMIN_UI_BACKEND_COVERAGE.md) ·
[C — Implementation Phases](ADMIN_AGENT_IMPLEMENTATION_PHASES.md).

**Status:** PLANNING ONLY. No UI is built by this document.
**Governing line:** maximum control with minimum complexity — every surface,
component, and visual decision below is judged by whether it increases real
control over the backend inventory in doc B.

---

## 1. HOW "MAXIMUM CONTROL" IS REACHED WITH MINIMAL SCREENS

The trap this design rejects: one screen per capability. The backend exposes
21 `AdminArea` values, 20+ module directories, and 25 routes — a naive
mapping yields 20+ screens, each shallow, each a place for state to drift
from truth. Instead:

1. **The Agent is the universal deep surface.** Any question or action that
   would justify a niche screen ("show me executions that failed after the
   last routing-weights change") is a conversation, not a screen. Screens
   exist only for what conversation is BAD at: dense scanning, side-by-side
   comparison, review-and-approve ceremonies, and ambient status.
2. **Surfaces group by admin INTENT, not by backend module.** The admin's
   intents are: "talk/act" (Agent), "is everything OK?" (Overview), "what
   happened / why?" (Executions), "what exists and is it enabled?"
   (Catalog), "govern change" (Changes & Audit), "who consumes what?"
   (Tenants & Usage), "is the machine itself healthy?" (System).
3. **Combining is the default; splitting needs evidence.** A capability gets
   its own surface only when its interaction pattern (not its module
   boundary) demands it. §3 records every combination decision.

Result: **7 surfaces** covering 100% of the doc B inventory (every row maps
to exactly one primary surface + the Agent).

---

## 2. THE SEVEN SURFACES

| # | Surface | Primary intent | Backend coverage (doc B rows) | Justification against the inventory |
|---|---|---|---|---|
| 1 | **Agent** | converse, ask, act, diagnose, test | ALL rows via R0/R1/R2 tools (doc A §3.3) | the control interface itself; every other surface deep-links into it and it deep-links back to evidence |
| 2 | **Overview** | ambient status at a glance | derived read-models only: recent executions (EXE-1), unacked notifications (NTF-1), pending changes (A1), provider status (A3 + probes), budget headroom (P5/A4) | a single glance answers "does anything need me?" — strictly derived data, nothing editable here, so it can never drift into a second workflow |
| 3 | **Executions** | inspect what happened and why | P1/P2 + EXE-1; trace view (doc A §6); diagnosis view (doc A §7); evaluations per execution (A6) | the evidence surface — the honest post-hoc trace and tiered diagnosis need dense, structured layout that chat cannot give |
| 4 | **Catalog** | what exists; is it enabled; is it healthy | providers/models/bindings (P4/A2/A3, PRV rows), skills (P3/SKL-1), tools + roles (module rows), templates (marked), INERT areas (listed as INERT) | one registry-shaped interaction pattern (list → detail → status → lifecycle action) fits all six entity kinds; enable/disable buttons draft R2 changes — they never mutate directly |
| 5 | **Changes & Audit** | govern every mutation; review + approve | the 7 lifecycle routes (A1), audit trail (AUD-1), source-change proposals (SRC-1, later) | review-and-approve is a ceremony demanding full-width diff/impact layout; audit lives HERE because "what changed" and "who did what" are one investigation |
| 6 | **Tenants & Usage** | who consumes what; plans & budgets | plans (A4 + SET_PLAN via R2), usage summary (P5), drill-down (USG-2), future Project entity (doc A §10) | consumption questions are cross-tenant comparisons — tabular, sortable, chart-light |
| 7 | **System** | is the machine healthy; runtime & config disclosure | SYS-1 (healthz, runtime gauges, gateway status read-model), observability, webhook subscriptions (WBH-1), device trust (read), in-memory disclosure banner (doc A risk R6) | ops truth belongs in one place; includes the honesty banners ("since process start", UNKNOWN health states) |

**Combinations chosen (and what was NOT split):**

| Combined into | Instead of | Why |
|---|---|---|
| Catalog | separate Providers / Models / Skills / Tools / Roles screens (5) | identical interaction pattern; one mental model; entity-kind is a filter, not a screen |
| Changes & Audit | separate Changes, Audit, Approvals screens (3) | audit is the evidence FOR changes; approvals are a lifecycle state, not a place |
| Executions | separate Executions / Traces / Diagnostics / Evaluations screens (4) | trace, diagnosis, and evaluation are TABS of one execution's evidence, not destinations |
| Tenants & Usage | separate Tenants / Plans / Usage screens (3) | plan and usage are attributes of a tenant |
| System | separate Health / Observability / Webhooks / Devices screens (4) | all are low-frequency ops reads |

Screens rejected outright: a Learning dashboard (renders inside System as a
status line "NOT OPERATIONAL — placeholder", per doc A §8 — a full surface
over `placeholder: true` zeros would be fake control); a Settings screen
(config changes ARE lifecycle changes → Changes & Audit; there is no other
settings backend); a Notifications page (the center is a panel reachable
from every surface, not a destination).

---

## 3. INFORMATION ARCHITECTURE RULES

1. **Evidence-linked everything.** Every fact rendered anywhere carries a
   link to its backend record (execution id, change id, audit event,
   ledger). This is the UI half of doc A §7's "no claim without citation".
2. **Closed sets render closed.** Statuses, categories, levels, lifecycle
   states come from contract enums (doc A §15); unknown values render as a
   loud UNKNOWN badge, never coerced to the nearest known state.
3. **Denials are content.** The backend's named refusals
   (`RollbackUnavailable`, exclusion records, `BudgetExceeded`,
   `device_not_trusted`, …) render verbatim as first-class information —
   they are the platform explaining itself, the core of the control
   experience.
4. **INERT is visible.** Inactive admin areas, contract-only capabilities
   (`ExecutionStrategy.AGENT`, provider-agent port), and placeholder
   surfaces appear labeled INERT/NOT-OPERATIONAL — visible honesty beats
   hidden incompleteness (doc A §11).
5. **The Agent is everywhere.** A persistent Agent panel can be summoned on
   any surface with the current entity as context ("ask about this
   execution"); surface → Agent → evidence → surface is the core loop.
6. **No UI-owned state.** The UI caches and renders; it never holds truth
   the backend doesn't (doc A §15 rule 5).

---

## 4. DESIGN SYSTEM

**Character:** professional operations console. Dark-first, high information
density without clutter, typography-driven hierarchy. Explicitly avoided:
neon/gaming aesthetics, decorative animation, dashboard-widget sprawl,
skeuomorphic chrome.

### 4.1 Foundations

| Token group | Direction |
|---|---|
| Color — base | dark neutral scale (near-black surface, elevated panels by lightness step, not shadow theatrics); light theme as a supported inversion, dark is default |
| Color — status (semantic, maps 1:1 to backend closed sets) | success/green (SUCCEEDED, PUBLISHED, ACTIVE, healthy probe) · error/red (FAILED, REJECTED) · warning/amber (WAITING_APPROVAL, stale probe, budget near limit) · info/blue (RUNNING, QUEUED, DRAFT) · neutral/gray (DISABLED, INERT, CANCELLED) · **distinct violet for UNKNOWN** — unknown is a first-class state, never gray-washed (doc A §8 health honesty) |
| Typography | one UI sans (high x-height, tabular numerals for ledgers/latency) + one mono (ids, diffs, payloads, audit records); scale ~12/13/14/16/20/24; weight carries hierarchy before size |
| Density | compact rows by default (operations console, not marketing site); comfortable mode as a toggle |
| Contrast & a11y | WCAG 2.1 AA minimum for all text and status pairings (status color NEVER the only carrier — always icon/label + color); full keyboard navigation; focus-visible everywhere; reduced-motion respected |
| Motion | functional only: state-change confirmation, panel open/close ≤150ms; zero ambient/looping animation |
| Layout | responsive; primary target is desktop wide (density), degrades to tablet; nav rail collapses; tables become cards below breakpoint |

### 4.2 Core components (the small set that renders everything)

| Component | Renders (doc B mapping) |
|---|---|
| **StatusBadge** | every closed-set enum value, with the UNKNOWN treatment |
| **EvidenceLink** | the §3.1 record link — one component, used thousands of times |
| **RecordTable** | executions, changes, audit, usage, catalog lists — sortable, filterable, virtualized |
| **TraceTimeline** | the doc A §6 post-hoc stage trace — "as recorded" label built into the component so no caller can omit it |
| **DiagnosisCard** | tier badge (PROVEN CAUSE/LIKELY/POSSIBLE/UNDETERMINED) + per-claim evidence citations — the schema of doc A §7 as a component contract |
| **LifecyclePath** | Draft→Validate→Preview→Publish→(Rollback) with the exact-predecessor state visualized; also reused for skill-import steps and (later) source proposals |
| **DiffView** | change payloads, impact previews, (later) source diffs |
| **ApprovalBar** | the explicit publish/approve act — requires rendered impact preview above it (UI-level enforcement mirroring the backend's preview-before-publish) |
| **NotificationItem** | category icon + evidence link + ack |
| **AgentPanel** | conversation, tool-call transcript (every tool call visible — the Agent's actions are never hidden), proposal cards |

### 4.3 The honesty rules as component contracts

Doc A §6/§8 rules are not guidelines; they are BUILT INTO components so
violating them requires deliberately writing a new component:

- `TraceTimeline` has no "percent complete" prop.
- `StatusBadge` throws on values outside the enum union instead of
  defaulting.
- `DiagnosisCard` refuses to render a claim row without an evidence ref.
- Health widgets require a `probed_at` timestamp and render staleness.
- Amnesia banners ("data since process start") are part of the store layer,
  not per-page goodwill.

---

## 5. COMMAND PALETTE (navigation simplifier only)

- Scope: jump to surface/entity by fuzzy match; pre-fill Agent prompts
  ("disable provider groq" → opens Agent with a drafted R2 proposal for
  review). Recent entities and pending approvals surfaced first.
- **Executes nothing itself** — every palette result is a navigation or an
  Agent handoff. No palette-only actions, no second workflow engine
  (doc A §14).

---

## 6. EXTENSIBILITY ARCHITECTURE (UI consumes contracts, not code)

1. UI types derived from the platform's Pydantic contracts; enum/status
   rendering is data-driven, so a new contract value ships to the UI as
   config + generated types.
2. The Agent's tool registry is configuration (doc A §15) — new backend
   capability = new tool entry + (optionally) a Catalog/System row; no UI
   rebuild.
3. Read-models (Overview, System, Notifications) are backend-computed; the
   UI renders whatever rows they emit — new notification categories or
   system facts need no UI release beyond the closed-set update.
4. Surface set is stable by design: future primitives (doc C §7) land INSIDE
   existing surfaces — async executions land in Executions, scheduled work
   lands in System/Executions, projects land in Tenants & Usage. A new
   surface requires the same justification ceremony as §1 — the strongest
   guard against complexity creep.
