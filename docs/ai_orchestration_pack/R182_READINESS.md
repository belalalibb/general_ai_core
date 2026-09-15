# R182 READINESS — QEVION UI inventory and readiness analysis (authoritative)

Round: **R182 — UI readiness / round opening**. NOT implementation. Branch `genspark_ai_developer_r182`, base `main` **743e203f** (merge commit of PR #20 = R181; parents ed61f7e6 + 05e12882). Everything below is derived from committed evidence under `evidence/r182/`; nothing is claimed that a probe, test or measurement did not show. Precedence: repository state > git state > protocol/ADR > manifests/ledgers > operator decisions in the R182 brief > brief defaults > inference.

## 1. Base and boundaries (measured)

| item | observed | evidence |
|---|---|---|
| PR #20 before acting | `open`, `mergeable=true`, `mergeable_state=clean`; branch protection 404 (none); status checks 0; check-runs 0; workflows 0; no `.github/` | `evidence/r182_state_ledger.md` row 1 |
| CI | **none — no CI / no required status checks; the canonical gate is the verification** | same |
| Merge | `merge_method=merge` (no squash, no force, no rewrite) → `main` **743e203f**, parents `ed61f7e6 05e12882` | row 2 |
| Gate on merge commit | fresh clone, `env -i`: **3632 / 0 / 0 / 64**, mypy 215 files, ruff, import-linter, secret scan 5/5, budgets incl. r181 3/3, not_evaluated=2, `RESULT: PASS`; gateway **194** | `evidence/r182/gate_merge_743e203f.txt`, `gateway_merge_743e203f.txt` |
| R181 on main | 0022 migration present; `runtime.py:755` binds durable usage; OPERATIONS §13 "durable on the DATABASE_URL profile"; `evidence/r181/` 9 files; frozen-tree diff 05e12882→HEAD empty | `evidence/r182/governance_frame_743e203f.txt` |
| PRs #13 #15 #16 #17 | open, untouched | row 5 |
| THAWED | `ui/` | brief §2 |
| FROZEN, ceiling **0** | `core/`, `apps/` (incl. `apps/admin_agent/`), `infrastructure/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`, `final_docs_v3` (decision log append-only ≤45 lines) | manifest `round_r182` |
| Frozen-tree collision rule | STOP → name the missing contract → name the owning round (R183) → do not implement | brief §2 |

## 2. Governance frame (values, not paths)

| knob | configured | measured now | R182-IMPL rule |
|---|---|---|---|
| `ui_static_check.files` | 3 (ui/admin only; exact equality with the directory) | 3 | adding a file under `ui/admin/` requires the manifest list edit in the same commit |
| `ui_static_check.v1_count_ceiling_N0` | **73** | `ui/admin/app.js` = **73** (zero headroom); `ui/admin/index.html` 15 (guard = no wired routes; not counted); `ui/app/app.js` 21 (no N0 guard) | N0 may only move DOWN; pay-down = deleting a real call; string tricks = governance finding |
| `ui_static_check.exception_count_ceiling` | **0** | 0 | unchanged |
| `baseline.head` / `baseline.ui.v1_count_N0` | 2f1a0e9f… / **73** | manifest and baseline synchronized (73 = 73) | any N0 change is a manifest+baseline PAIR edit, operator-authorized only |
| `baseline.ui.bytes` | app.js 79351 / index.html 32385 / styles.css 16392 | on disk 80789 / 32456 / 16392 (drift since R180; no test consumes bytes) | recorded as data; NOT mutated (F-R182-03) |
| `not_evaluated_count_ceiling` | **2** | 2 (`browser automation — missing dependency`; `two-account provider round-trip — credential unavailable`) | browser proof REPLACES #1 (2→1); never a third; never a raise |
| `secret_scan.exception_count_ceiling` | **5** | 5 (grep reproduces exactly the 5 declared lines) | no growth; new UI assets are scanned — no encoded fixtures with secret-shaped strings |
| `pytest.gate.min_passed` | **3504** | 3632 measured | candidate ratchet 3632 reported; NOT applied (no authorization) |
| counted production roots | `core/ apps/ infrastructure/` | `round_r182` 0/0 | `ui/` outside by design (manifest note) |
| guarded UI trees | `ui/admin` (manifest + `tests/ui` 20 checks + Q5 pins) | `ui/app` guarded ONLY by its own 11 `test_ui_app_pd2` tests + title pin | a new Command Center tree gets its own declared guard block BEFORE code |
| transport | `ui/admin`: one `fetch(` inside `api()`; `EventSource(`/`WebSocket(`/`XMLHttpRequest`/`axios` banned | `ui/app` reads SSE by `fetch` of `/v1/executions/{id}/events` | inherited unchanged; Command Center follows the `ui/app` pattern (fetch-read SSE); no EventSource/WebSocket |
| browser dependency | manifest `non_test_items.live-suite` = playwright | `import playwright` → ModuleNotFoundError | not installed in R182 (F-R182-05) |

## 3. Architecture / ADR

`40_ENGINEERING_PROTOCOL.md` §8.1: "No significant architecture change is allowed without an ADR." ADR-0001 (ACCEPTED) deferred the client stack to "a future ADR when those apps start". Introducing Next.js/React/three (the APEX stack) or any build step IS that deferred decision → **`engineering/adr/ADR-0013-ui-front-end-stack-and-serving-posture.md`, status `PROPOSED — AWAITING OPERATOR DECISION`**; index row with the same status. Nothing installed; `package.json`/lockfile/`node_modules` = 0 present. Operating default for this analysis: **Alternative C** (vanilla ES modules + hand-written SVG/CSS + optional hand-written WebGL2; no framework, no build; existing `StaticFiles` posture).

Serving-posture fact: a new tree's mount line lives in `apps/composition/` (frozen, ceiling 0) → **the Command Center cannot get its own `/command` mount in R182**; see decision D-3 (§9).

## 4. Inventory — BACKED / INERT / MISSING / DECORATIVE-ONLY (contract → visual proof)

Source of truth for every row: `evidence/r182/served_contract_probe_743e203f.txt` (hermetic in-memory profile, admin session, 83 OpenAPI paths) and the closed enums in `core/contracts/` and `apps/api/capabilities.py`. Legend: **B** BACKED · **I** INERT · **M** MISSING · **D** DECORATIVE-ONLY.

| # | UI element | status | route / contract → exact field/state | allowed visual behaviour | proof source |
|---|---|---|---|---|---|
| 1 | QEVION Core (central orb) — semantic runtime surface | **B** (derived) | `GET /v1/executions` rows `.status` ∈ `ExecutionStatus{queued,running,waiting_approval,succeeded,failed,cancelled}`; `GET /v1/admin/system.profile`; `GET /healthz`; `GET /v1/auth/session` | Core states exactly: `idle` (no running/queued), `running` (≥1 running/queued), `waiting_approval`, `failed` (latest terminal = failed), `unreachable` (healthz/session fetch failed). **No `thinking`/`speaking`/`listening`** — no contract exists | `core/contracts/execute.py:33-41`; probe |
| 2 | Core tap "energize" cycle (APEX) | **D → DISCARD** | none | a tap may open/focus panels; it may NOT change the Core's runtime state | APEX `ApexWorld.tsx:243` (timer-driven) |
| 3 | Capability shelf / topology nodes | **B** | `GET /v1/admin/capabilities` → `capabilities[]{id, state, evidence}`, `scope`; ids = closed `CAPABILITY_IDS` (23); `state` ∈ `CapabilityState{available,inert,unavailable}` | one node per served row; label = `id`; ring class = `state` (3 classes + loud `UNKNOWN`); tooltip = `evidence` verbatim. **No manual roster; ids never quoted in source** (existing `tests/ui` guard) | probe: 23 rows {available 19, inert 3, unavailable 1}; `apps/api/capabilities.py:48-60` |
| 4 | Capability "exercise" affordance | **B** | `GET /v1/admin/capabilities/exercisable` → `exercisable[]` (4 ids); `POST /v1/admin/capabilities/{id}/exercise` | control only on listed ids; result = returned evidence JSON verbatim | probe |
| 5 | Node states `inert` / `unavailable` | **I** / **B** | `state:"inert"` (dev.publish_modes, learning.custody_governance, rate_limits.execute); `state:"unavailable"` (execute.token_streaming) | inert = dimmed + `evidence` text (names the env gate); unavailable = struck; neither animates as active | probe |
| 6 | Evidence panel | **B** | `capabilities[].evidence`; `GET /v1/agent/executions/{id}/diagnosis` → `tier`, `claims[]{text, evidence[]{kind,ref}}`, `missing_evidence[]` | strings/refs verbatim; `missing_evidence` shown as missing | probe |
| 7 | Process scope | **B** | `GET /v1/admin/system` → `profile`, `identity_mode`, `provider_keys[]`, `admin_emails_configured`, `scope:"process"` | badge "scope: process"; never imply fleet scope | probe |
| 8 | Execution graph (stages) | **B** | `GET /v1/agent/executions/{id}/trace` → `strategy`, `stages[]{node_key, status, attempts[]{attempt, model_key, provider_key, succeeded, latency_ms}}`, `ledger{status,units_reserved,units_settled}`, `as_recorded` | nodes = stages; edges = order; attempt badges; `as_recorded` shown | probe |
| 9 | Execution connections (live) | **B (progress only)** | `GET /v1/executions/{id}/events` SSE, closed types `execution_started`, `node_started`, `node_completed`, `final`, `error`; `DeltaEvent` exists in the contract but is **never emitted** (`execute.token_streaming` unavailable) | animate edge on `node_started`→`node_completed`; stop on `final`/`error`. **No token typing, no speaking waveform, no partial text** | `apps/api/streaming.py:51,74-103`; probe frames |
| 10 | Runtime indicators | **B** | `GET /v1/executions/{id}` → `status`, `progress{current_stage, percent}`; `GET /v1/executions` | bar + stage label from these fields only | probe |
| 11 | Conversation | **B** | `POST /v1/agent/converse {message}` → `claims[]`, `tool_calls[]`, `reasoning_execution_ids[]`, `rounds`, `stop_reason`, `verification{verified, claims_admitted, claims_refused, tool_calls_ok, tool_calls_total}`, `reasoning_trace[]`; `POST /v1/execute {ask}` → `execution_id, status, result{type,content,artifacts[]}, usage` | request/response turns; `verification` as counts; **no streaming transcript** | probe |
| 12 | Models | **B** | `GET /v1/models` → `models[]{id,name,tier,modalities[],capabilities[],availability∈BindingAvailability{available,unavailable,degraded}}`; `GET /v1/admin/models` adds 4 scores + `status` | cards; availability badge = 3 classes + UNKNOWN | probe; `core/contracts/domain.py:83-89` |
| 13 | Providers | **B (read)** / **M (verification)** | `GET /v1/admin/providers` → `providers[]{id, provider_key, display_name, status, auth_types[], supports_account_pool, is_template, is_routable}` | list + `is_routable`/`status` badges. **MISSING**: live account verification / selection enforcement — Provider slice, **R183**; no "verified" badge | probe; brief §15 |
| 14 | Routing | **B** | `GET /v1/admin/routing/weights` → `version` + 6 weights | read-only | probe |
| 15 | Evaluation | **B (records)** / **M (distinction = Q7)** | `GET /v1/admin/executions/{id}/evaluations` → `evaluations[]` (**`[]` for a plain execute**); `GET /v1/admin/evaluations/{id}` → `EvaluationRecord{level∈{RAW,EVALUATED,VALIDATED,VERIFIED,GOLD}, score|null, confidence|null, graders[]}` | `[]` ⇒ render **"not evaluated"** as its own state; never a score/default bar. Q7 (served field distinguishing "never evaluated" from "evaluated: none") → **R183** | probe; `core/contracts/evaluation.py:55-69` |
| 16 | Learning / internal education | **I** | `GET /v1/admin/learning/dashboard` → **`placeholder: true`**, zeros, empty arrays | while `placeholder`: one honest placeholder panel; **no charts/trends/progress**; lifecycle `/samples/*` routes are BACKED actions | probe |
| 17 | Memory | **B** | `GET /v1/memory/preferences` → `preferences[]`; `DELETE …/{id}`; `result.artifacts[type=context_provenance]{blocks_total, memory_blocks[], gold_blocks, excluded}` | list + delete; provenance counts from the artifact only | probe |
| 18 | Usage | **B** | `GET /v1/usage` → `plan`, `task_units{limit,used,remaining}`, `modality_limits{}`; `GET /v1/admin/usage` → `usage[]{execution_id, status, created_at, ledger{…}}` | numbers verbatim. Post-0022 `ledger.execution_id` is a **key, not an FK**: a ledger row may have no execution (tool `call_id`) — render "no execution record", never fabricate the link | probe; migration 0022 |
| 19 | Attestations / promotion evidence | **B** | `unverified[]`, `refused_unbacked[]`, `resolved{}` (`apps/api/admin.py:290-316`) | `unverified` rendered as unverified; never promoted | source |
| 20 | Admin actions | **B** | `GET /v1/admin/capabilities/actions` → `actions[]{action, area, fields[]{name,kind,required,contract}}`; `/v1/admin/changes` lifecycle | verbs from discovery (R180 Q5 posture); forms from `fields[]` | probe |
| 21 | Notifications | **B** | `GET /v1/admin/notifications` → `notifications[]{id, category, title, occurred_at, evidence{kind,ref}, read}`, `unread`; `POST …/{id}/ack` | list + unread | probe |
| 22 | Audit | **B** | `GET /v1/admin/audit` → `events[]`, `total_recorded` | list | probe |
| 23 | Projects / Workspaces | **B (thin)** | `POST/GET /v1/projects` → `{project_id, workspace_id|null, name, metadata{}}`; `/v1/workspaces` → `{workspace_id, name}`; DB columns id/tenant_id/workspace_id/name/metadata | name + free-form `metadata`; **no repository/branch/commit/preview fields exist** — not invented | probe; `core/contracts/identity.py:95-102` |
| 24 | App Factory | **M** | no route, table, contract or doc defines generated-project state, VCS metadata, preview URLs, build/deploy state (repo search: one unrelated test string) | **no panel may imply generation, preview or deployment**; at most row 23. Owning round undefined — operator-defined contract needed first | governance frame |
| 25 | API keys / scopes | **M** | `/v1/api-keys`, `/v1/keys`, `/v1/admin/api-keys` → 404; sessions = bearer from `/v1/auth/login` | no key-management UI | probe |
| 26 | Webhooks | **B (registration)** / **M (delivery)** | `GET/POST /v1/webhooks` → `WebhookSubscription{id, tenant_id, url, events[]}`; no delivery-log route | registration list; **no delivery/attempt status** | probe; `core/contracts/webhooks.py:48-54` |
| 27 | Engineering workspace | **I** (env-gated) | `/v1/admin/engineering/status` → 404 without `AGENT_WORKSPACE_ROOT` | "route absent" (existing console posture) | probe |
| 28 | Skills | **B** | `GET /v1/skills` → `skills[]`; `GET /v1/admin/skills/imports` → `imports[]`, `allowed_sources[]` | lists | probe |
| 29 | Background effects (plasma/particles) | **D (ambient)** | none | decoration only; never varies with a claimed runtime value; off under `prefers-reduced-motion`; APEX ShaderBackground REBUILD/DISCARD (F-R182-04) | APEX inspection |
| 30 | Orbit dots / ring breathe | **D (ambient)**; reactive variant only bound to rows 1/9 | rows 1, 9 | ambient by default; may speed up ONLY on `node_started` frames | — |
| 31 | Status bar (APEX STANDBY + equalizer) | **REBUILD as B** | row 1 Core state + `system.profile` | text = row 1 vocabulary; **no equalizer implying audio** | APEX `OrbStatusBar.jsx` |
| 32 | Overview panel (APEX clock/weather/social) | **D → DISCARD** | none (APEX: `/api/weather` → open-meteo + 3 social links) | no external calls; a QEVION overview = row 7 fields | APEX inspection |
| 33 | Controls | **B** | only routes in the 83-path OpenAPI; single `api()` transport | every control maps to a served route; 404 ⇒ "route absent" | `tests/ui` route-literal pattern |
| 34 | Accessibility | **B (requirement)** | n/a | keyboard-navigable node list mirroring the graph (APEX `.visually-hidden` REUSE-CONCEPTUALLY); `aria-label` on Core/nodes; `role="dialog"` on panels; `prefers-reduced-motion` disables ambient motion and WebGL | APEX `ApexHeroOrb.tsx:25-33`, `ApexWorld.tsx:257,312` |
| 35 | Branding | **M (planned)** | titles `Admin Console — AI Orchestration Platform` / `AI Orchestration Platform`; `QEVION` 0 in `ui/` | canonical `QEVION` / `QEVION Control Plane`; 2 html + 3 pins in one commit (§7); not in readiness | governance frame |

**Counts** (one primary status per row): BACKED **23** (1,3,4,6,7,8,9,10,11,12,13,14,17,18,19,20,21,22,23,26,28,31,33,34 → 24 rows; row 13's primary is B-read) — recorded as **24 BACKED**; INERT **3** (5, 16, 27); **MISSING 6** (15 Q7-distinction, 24 App Factory, 25 API keys, 35 branding, plus the M-halves of 13 provider-verification and 26 delivery); DECORATIVE-ONLY **4** (2, 29, 30, 32).

Effect classes (brief §16): ambient = 29, 30; structural = 3, 8; reactive = 9, 30-variant; state-driven = 1, 5, 10, 31; interactive = 4, 11, 20, 33. Only state-driven/reactive rows may imply live system state.

## 5. APEX reference analysis (`evidence/r182/apex_reference_inspection.txt`)

Live demo reachable (HTTP 200, 23 259 B; server-rendered HTML inspected: title "APEX-UI — Autonomous-agent orb interface", 18-agent roster text, `STANDBY`, hint "TAP THE CORE · CLICK AN AGENT · SCROLL FOR THE STORY", classes `orb-*`, aria "Apex core - tap to energize", 3 `<svg>`, 1 `<canvas>`). GitHub commit a8732fad (2026-09-11). Source outranks README.

| component | actual dependency | classification | QEVION contract | must NOT survive |
|---|---|---|---|---|
| `ApexOrb.jsx` (SVG ring, waveform, orbit dots) | none (SVG/CSS) | **REUSE-CONCEPTUALLY → REBUILD** | row 1 Core state; row 30 ambient | waveform (implies audio) |
| `ApexCore3D.jsx` (particle core, 504 lines) | `three`, `@react-three/fiber`, `@react-three/postprocessing` | **REBUILD** (hand-written 2D-canvas/WebGL2 under ADR-0013 default C) / **DISCARD** under reduced motion | row 1; ambient otherwise | the library trio (only under ADR-0013 B) |
| `ApexHeroOrb.tsx` (stack + tap cycle + 8 s timer) | react | **REBUILD** (composition) / **DISCARD** (tap cycle) | row 1 | `idle→thinking→speaking` timer state machine |
| `ReasoningWeb.jsx` (18-node constellation, circuit traces, `LEVEL`) | none | **REUSE-CONCEPTUALLY → REBUILD** | rows 3, 5, 8, 9 (nodes = served capabilities/stages) | `ROSTER` (18 business agents), `LEVEL{standby,listening,processing,reasoning,speaking}` |
| `OrbStatusBar.jsx` (equalizer + STANDBY) | none | **REBUILD** | row 31 | equalizer bars |
| `ShaderBackground.jsx` (WebGL plasma) | none (raw WebGL); 21st.dev MIT, attribution UNRESOLVED | **REBUILD or DISCARD, never copy** | row 29 ambient | the source itself (provenance) |
| `ApexWorld.tsx` (composer; `ROSTER`, `INFO`) | react | **REBUILD** | rows 3, 6 | `ROSTER`, `INFO` (`status: online/standby/integration`), Apex copy |
| `ApexOverviewPanel.tsx` (clock, weather, social) | `lucide-react`; 21st.dev lamp, attribution UNRESOLVED | **DISCARD** | row 7 replaces it | `/api/weather` → open-meteo; facebook/instagram/linkedin links; `setInterval` 30 s / 20 min |
| `apex-orb.css`, `globals.css` | none | **REUSE-CONCEPTUALLY** (dark palette, breathe/orbit keyframes) | rows 29-30 | Apex colour identity as branding |
| `LICENSE` / `CREDITS.md` | MIT (code); "the name Apex and the Reznikov Engineering branding are not part of this license"; two attribution placeholders | provenance **UNRESOLVED for 2 components** (F-R182-04) | — | Apex name/branding; unattributed components |

Dependency metadata vs imports: `package.json` lists exactly the imported packages (consistent). README claim "no 3D libraries" is contradicted by `ApexCore3D.jsx` imports → README wording recorded as inaccurate/unverified. Live page CSS has no `prefers-reduced-motion` rule; the JS honours `matchMedia` (skips the 3D core) — accessibility claim partially verified.

## 6. Boundary audit (brief §15)

| boundary | measured | UI rule |
|---|---|---|
| Learning `placeholder` | `true` | no charts/metrics/progress (row 16) |
| Evaluation absent | `evaluations: []` for a plain execute | "not evaluated" distinct state; no score (row 15); Q7 → R183 |
| Usage post-0022 | ledger keyed by `execution_id`, no FK | tolerate missing execution; never fabricate link (row 18) |
| Attestations | `unverified[]` served | preserve `unverified` (row 19) |
| Projects | columns id/tenant_id/workspace_id/name/metadata | no VCS/preview metadata (row 23) |
| API keys/scopes | 404 | no UI (row 25) |
| Webhooks | registration only | registration ≠ delivery (row 26) |
| App Factory | no persistence/VCS/preview/deploy contract | MISSING (row 24) |
| Provider slice | read-only list | no verification/enforcement (row 13) → R183 |
| Q7 | gap documented | not solved → R183 |

## 7. Branding / pin audit

Current: `ui/admin/index.html:6` `<title>Admin Console — AI Orchestration Platform</title>`, `:44 <h1>Admin Console</h1>`; `ui/app/index.html:6` `<title>AI Orchestration Platform</title>`, `:46 <h1>`. Pins: `tests/composition/test_admin_console_runtime.py:80` ("Admin Console"), `:146` ("AI Orchestration Platform"), `tests/composition/test_ui_app_pd2.py:83` ("AI Orchestration Platform"). `QEVION` in `ui/`: 0. Apex branding in repo: 0 files. Required synchronized change (R182-IMPL M1, not readiness): the 2 html `<title>`/`<h1>` → `QEVION Control Plane` ("Admin Console" may remain a section label) and the 3 pins, one commit; zero counted budget (ui/ + tests/); N0 unaffected.

## 8. Test / live-proof readiness

Static UI checks: `tests/ui` (20) + Q5 pins in slice `rest`; composition UI tests in `tests/composition`. Browser/live: NOT-EVALUATED #1, playwright absent, **not installed in R182**. R182-IMPL acceptance for browser proof: a real Playwright run against the served Command Center over the in-memory profile, evidence committed (tracked, never `raw_*`), which **replaces** NOT-EVALUATED #1 (2→1); dependency declared in the IMPL round under `pyproject [dev]`; no third item; ceiling unchanged. Encoded-asset risk: no base64/binary fixtures enter `ui/` (secret scan covers `*.js *.html *.css *.json`).

## 9. Operator-only decisions (A repository-determined / B governance-determined / C operator-only)

Resolved from evidence (A/B): base = 743e203f (A); ceiling 0 (B); `ui/` outside counted roots (B); N0 73 zero headroom → new tree (B); transport = fetch-only, SSE by fetch, no EventSource/WebSocket (B); browser proof replaces NE #1 (B); Q7/Provider → R183 (B); App Factory MISSING (A).

**D-1 — Front-end stack (ADR-0013)**
DECISION: accept ADR-0013 with one alternative.
OPTIONS: A vanilla ES modules · **C vanilla + optional hand-written WebGL2** · B Next/React/three (APEX-identical) · D React/Vite export.
OPERATING DEFAULT: C.
BLOCKING EFFECT: R182-IMPL may not write the first production UI file until the ADR is ACCEPTED by operator text. B/D additionally block on toolchain/lockfile/build-proof/guard-frame declarations (ADR-0013 §Decision).

**D-2 — Command Center tree**
DECISION: which directory holds the Command Center.
OPTIONS: (a) new `ui/command/` (own manifest guard block, own literal ceiling; needs a mount) · (b) inside `ui/app/` (existing `/app` mount; extend `test_ui_app_pd2` pins; no manifest block today).
OPERATING DEFAULT: (a) `ui/command/`.
BLOCKING EFFECT: (a) is served only after D-3; (b) starts immediately but inherits `ui/app`'s weaker guard frame and its 21 unguarded literals — a guard block for `ui/app` must then be declared first.

**D-3 — Serving the new tree under a frozen composition root**
DECISION: how `ui/command/` is served while `apps/` is frozen (ceiling 0).
OPTIONS: (a) raise `round_r182` ceiling 0→1 for exactly `apps/composition/runtime.py` (one guarded `StaticFiles` mount, `is_dir()` posture) · (b) keep 0; place the files at `ui/app/command/` — a sub-directory of the already-mounted `/app` tree (`StaticFiles` serves nested paths) — while declaring and guarding it as its own unit · (c) defer the mount to R183.
OPERATING DEFAULT: (b) — zero production change.
BLOCKING EFFECT: (a) is a conscious ceiling raise (declared BEFORE the commit, with history); (c) = no served Command Center until R183 (source pins only).

**D-4 — Browser proof dependency**
DECISION: install Playwright in R182-IMPL.
OPTIONS: yes (dev-only, declared in `pyproject [dev]`, replaces NE #1) · no (NE #1 stays; proof = ASGI + source pins).
OPERATING DEFAULT: yes, in R182-IMPL, never in R182.
BLOCKING EFFECT: without it no browser-rendered proof; NE count stays 2.

**D-5 — Branding switch timing**
DECISION: apply `QEVION` / `QEVION Control Plane` in R182-IMPL M1.
OPTIONS: yes (2 html + 3 pins, one commit) · defer.
OPERATING DEFAULT: yes.
BLOCKING EFFECT: pins only.

**D-6 — min_passed ratchet 3504 → 3632**
DECISION: ratchet the floor.
OPTIONS: yes · no.
OPERATING DEFAULT: no (reported only).
BLOCKING EFFECT: none.

## 10. First red test and first milestone

**First red test** — `tests/ui/test_command_center_topology_r182.py::test_capability_nodes_derive_from_served_contract_not_a_roster`
Invariant: the Command Center's node set equals the `id` set of `GET /v1/admin/capabilities` from the served in-memory profile (admin session), rendered from the response at runtime; the source contains **no quoted `CAPABILITY_IDS` literal, no roster array, no hand-written state machine** (`thinking|speaking|listening` absent); node state classes ⊆ `CapabilityState`; Core state vocabulary ⊆ `ExecutionStatus ∪ {idle, unreachable}`.
Why first: every other surface depends on it (rows 1, 3, 5); it is exactly what APEX gets structurally wrong (`ROSTER`); it encodes the anti-fabrication rule.
Expected initial failure: the tree/file does not exist → `FileNotFoundError` on the source read (RED).
Gates **M1 — "Honest topology"**: Command Center shell + Core (row 1 states) + capability nodes from the served contract (rows 3, 5, 6, 7) + status bar (row 31) + a11y (row 34) + branding (§7); no execution graph or conversation yet. Proof: red test GREEN; `tests/ui` + Q5 pins GREEN; canonical gate PASS with `ui_static_check` unchanged for `ui/admin`, a declared guard block for the new tree, N0 = 73 untouched.
Not created in R182: the repository's opening convention is declaration-first; the R181 precedent created the RED test as the first act of the implementation step.

## 11. Readiness verdict

Operator-only blockers: **D-1** (ADR-0013 acceptance) and **D-3** (serving under ceiling 0; D-2 follows from it). D-4/D-5/D-6 do not block M1.

- QEVION UI readiness: **no** until D-1 and D-3 are answered — base, budget, guard frame, contracts, inventory, first test and milestone are ready and recorded.
- AI Apps Factory: **NOT READY** — MISSING (row 24): generated-project persistence, VCS metadata, preview URL, build/deploy state; plus row 25 API keys → **5** missing contracts; owning round undefined until the operator defines the contract (backend, not R182).

## 12. Verdict update — R182-IMPL opened (operator rulings 2026-09-14; R182-DEC-02)

The operator answered every §9 decision (text recorded verbatim in ADR-0013 §Status and `60_DECISION_LOG.md` R182-DEC-02): D-1 ADR-0013 ACCEPTED on Alternative C; D-2 per §2/§14 of the handoff (the §9 D-2 line is interpretive); D-3 (b) `ui/app/command/` on the existing mount, ceiling stays 0, no R183 deferral; D-4 yes inside R182-IMPL (dependency withdrawn if the environment cannot run it — never left beside a "missing dependency" line, never a third NE line); D-5 yes in M1 (two titles + three pins, one commit; tree title `QEVION Control Plane — Command Center`); D-6 ratchet allowed only at the round's gate of record, with the measured number and a ledger line.

Measurement update, effective at the first R182-IMPL commit (`92baaa21`, the RED test):

- QEVION UI readiness: **yes — blockers: 0** (D-1 and D-3 answered by the operator; base, budget 0/0, guard frame `ui_command_static_check`, contracts, inventory, first red test and M1 all in force).
- AI Apps Factory: **NOT READY — missing: 5** (unchanged: the Factory contract definition is an operator decision, not R182 work).

## 13. Pointer reconciliation — what "→ R183" meant, as resolved by R183 (2026-09-15; R183-DEC-01)

The "→ R183" pointers in §4 rows 13/15, §6 and §8 named the earliest round that could host those items, not a definition of them. R183 (declared on `main` e23abb23) re-searched the repository and found no contract, acceptance or files for Q7, the Provider slice / provider verification, App Factory (row 24), API keys (row 25) or webhook delivery (row 26) — they remain **UNDEFINED** (R181-DEC-01: "Defining them is an operator act") and were **not worked**. R183 closed the only DEFINED + ACTIONABLE carry-over, F-R182-01 (`infrastructure/db/tables.py` docstring vs migration 0022), under `round_r183` ceiling 1/1. See `R183_HANDOFF.md` §1/§7 and `evidence/r183_state_ledger.md` row 2.

## 14. Q7 resolution (R184, option (a) — operator-accepted 2026-09-15; R184-DEC-01)

Row 15's MISSING half ("served field distinguishing never-evaluated from evaluated: none") is now served **on the execution admin read**, not on the evaluation list: every `GET /v1/admin/usage` row carries `evaluation_status` ∈ {`NEVER_EVALUATED`, `EVALUATED`} (EVALUATED iff ≥1 record above RAW, 22 §3). The evaluation list `GET /v1/admin/executions/{id}/evaluations` is byte-identical (`[]` for no-evaluations and for unknown/foreign ids — 20 §6 preserved), and the user read is untouched (22 §7). UI rendering of the new field is **not** part of the accepted decision (`ui/` frozen in R184). Records: `R184_HANDOFF.md`, `evidence/r184_state_ledger.md`.
