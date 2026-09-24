# QEVION_MASTER_COMPLETION_AUDIT_V2

**Base:** `main 7d9524eb` (post-R202 closure). **Read-only audit** — zero production changes. Evidence: branch `audit_v2_evidence`, `evidence/audit_v2/` (probe scripts as `.py.txt`, JSON results, PNG screenshots). Evidence hierarchy applied: real runtime/browser → source → tests → docs → history. Unmeasured items are marked **NOT VERIFIED**.

Evidence index: `probe_api_hermetic.json` (in-memory profile, API incl. full learning lifecycle attempt), `probe_api_live.json` (real `genspark_llm` key present in env), `probe_journeys.json` + `probe_journeys_bd.json` (real Chromium, journeys A–E), screenshots `jA_result.png jA_runs.png jB_runs.png jB_project_runs.png jC_template.png jC_command_tenant.png jD_error.png jD_async_timeline.png jE_admin.png jE_command.png`.

---

## 1. EXECUTIVE PRODUCT STATE

QEVION today is a **secure, honest, well-gated multi-tenant execution platform with a thin end-user product on top**. Backend authorities are real and singular (one Router, one StrategyExecutor, one TemplateRegistry, one tool chain, one identity/tenancy path); 85 served routes; tenancy and admin boundaries hold under real requests; nothing observed fabricates a result. The end-user product is **not yet something a normal person can use end to end**:

- **Entry is blocked for anyone but the operator**: registration needs a verification token that exists only on the server console (documented honest scope; still blocks Journey A for a real user).
- **A run's result is raw JSON** (`{"context_blocks":…,"echo":…,"note":…}`), not an answer.
- **Runs carry no project / workspace / template reference**; `project_id` is validated for tenancy and then **dropped** (never on the record, list, or context) — "continue my work" is impossible from Runs.
- **Agent, tools, skills, App Factory (beyond one planning template) are unreachable from any tenant UI**; a tenant cannot read the trace of its own agent run (403).
- **Learning is a governed pipeline, not a loop**: nothing from real use produces a sample; promotion is (correctly) refused without artefact evidence; no promoted knowledge was observed reaching a later execution (`gold_blocks: 0`).
- **Provider truth is honest, but the only live key present is plan-refused** (403 `entitlement_exceeded`, "no tokens were consumed") so every live path fails; the template failure surfaces as an opaque "Execution failed." (stage error lost).
- **Session is memory-only**: every reload or cross-surface link forces a re-login.

Classification: **LOCAL DEMO usable by the operator; DEV-USABLE for engineers; NOT user-ready.** Production-ready is correctly not claimed (D-03 open).

## 2. CURRENT USER-READY CAPABILITIES (FULLY USABLE, measured)

| capability | evidence |
|---|---|
| Sign in with a verified account; session probe; sign out | journeys A/B/E |
| Sync execution through the ONE router/execution path (hermetic provider); id + result; usage settled | `exec_sync` 200, `units_settled 1`; jA_result.png |
| Async execution: 202 → in-process worker → real SSE frames → final | `D_async_timeline` = accepted → execution_started → node_started/completed: single → final |
| Runs list + detail (record verbatim); Command → Workbench `&execution=` deep link | jA_runs.png; `C_command_as_tenant_after_login` |
| Workspaces/projects CRUD (tenant-scoped); project selectable; view/ws/project/template restored after re-login (sessionStorage) | `B_*`; `B_context_after_roundtrip.project_value_nonempty true` |
| Template picker + served template detail (R202-A) | `C_template_options`; jC_template.png |
| Models view (served catalog) | `C_models_view` |
| Tenant isolation: foreign execution/workspace/project → 404 (same shape); tenant → `/v1/admin/*` 403; `/v1/agent/*` admin-only | `exec_get_by_other_tenant 404`, `ws_other_tenant`, `exec_foreign_project 404`, `admin_system_as_tenant 403` |
| Admin console: 15 surfaces reading real routes; Command Center topology (24 capabilities, honest states) | jE_admin.png; jE_command.png |
| Hardening headers, 401-before-body, closed contracts (freeze MATCHES) | inherited gates |

## 3. PARTIAL / DISCONNECTED CAPABILITIES

| id | capability | status | exact missing edge |
|---|---|---|---|
| P-1 | Self-registration | **BLOCKED** (non-operators) | verification token only on server console; no in-product path (email out of scope by decision) |
| P-2 | Result presentation | **PARTIALLY IMPLEMENTED** | `renderResult` prints `result.content` verbatim (a JSON string); no answer view, no provenance badge |
| P-3 | Project/workspace context in execution | **UI ONLY** | `project_id` checked for ownership then dropped (`apps/api/app.py:885–905`); absent from record/list/composer; `?project_id=` ignored |
| P-4 | Template (App Factory plan) run visibility | **BACKEND ONLY** | 3 child stage executions exist; UI shows one payload; sync path never opens SSE (R202-F1 / R188 C3) |
| P-5 | Agent for tenants | **BACKEND ONLY** | API-only (`execution_policy.strategy=agent`); deny-by-default tools need env; trace/diagnosis 403 for the owning tenant |
| P-6 | Skills | **BACKEND ONLY / DATA-only (AD-4)** | `/v1/skills` empty by default; admin import pipeline; no tenant surface |
| P-7 | Session continuity | **PARTIALLY IMPLEMENTED** | token memory-only → `B_reload_requires_login true`, `B_command_needs_login true` |
| P-8 | Memory/preferences/conversations | **BACKEND ONLY** | routes + `conversation_id` exist; UI references: 0 |
| P-9 | Webhooks | **BACKEND ONLY** | tenant routes served (closed event set); no tenant UI; subscriptions are a process-local dict even on durable |
| P-10 | Learning | **LEARNING INFRASTRUCTURE ONLY** | §10 |
| P-11 | Live provider | **PARTIALLY IMPLEMENTED (honest)** | binding/discovery (8 models)/routing/error normalisation work; present key plan-refused → no live inference observed |
| P-12 | Root `/` | **MISSING** | 404; no redirect to `/app/` |
| P-13 | Orientation | **MISSING** | no "what is QEVION / start here" (`A_orientation` all false); placeholder is the only guidance |
| P-14 | Error recovery guidance | **PARTIALLY IMPLEMENTED** | verbatim `code: message`, no next step; empty ask → raw contract-validation text |

## 4. FALSELY COMPLETE CAPABILITIES (red-team hits)

| # | pattern | finding | evidence |
|---|---|---|---|
| F-1 | 18 context shown but unused | project selected + sent; server checks ownership then discards; user believes the run is "in" the project | `B_execute_body` has `project_id`; record keys `execution_id,status,progress,result` |
| F-2 | 8 success ≠ business action | template run = one echo payload; on live key → opaque `Execution failed.` (child stage error reduced to `{"reason":"stage execution failed"}`, `core/execution/strategy.py:322`) | `exec_template_echo`, `exec_template_live` |
| F-3 | 14 learning = storage/dashboard | dashboard `placeholder:true`; full lifecycle → `promoted:false` (correct) → `gold_blocks 0` | `learning_loop.*` |
| F-4 | 7 works only for admin | agent trace/diagnosis/converse admin-only; tenant cannot inspect its own failed agent run | `agent_trace_as_tenant 403` |
| F-5 | 20 hidden engineering knowledge | registration needs console access; agent needs env + JSON policy; templates need ref syntax | `A_after_register`; OPERATIONS §5 |
| F-6 | 17 provider claims from config | 8 live models listed `available` while every inference is plan-refused — availability is a catalog fact, not health | `models_names`, `exec_sync_live 403` |
| F-7 | 10 state lost after restart | on durable: provider/model registries, webhook subscriptions, engineering tickets, rate-limit state are process-local | `runtime.py` InMemory* inventory; OPERATIONS §13 |
| F-8 | 12 unusable errors | `Execution failed.` for strategy runs; `Request body failed contract validation.` for empty ask | `D_empty_ask`, `exec_template_live` |
| F-9 | UX trap | creating a workspace auto-selects it; clicking the selected node toggles it OFF (detail disappears) | `B_click_selected_toggles_off true` |

Clean on the in-memory profile: patterns 5 (authz), 6 (cross-tenant), 9 (persisted), 11 (completion state). Durable restart survival **NOT re-verified** here (measured R179/R181/R198).

## 5. FRONTEND FINDINGS
- `ui/app` (23 `/v1/` literals) consumes session/auth/execute/executions(+events)/workspaces/projects/templates(+detail)/models/usage/healthz; never memory, webhooks, skills, agent-tools, conversations.
- Result panel: badge + id + "Open in Runs" + `<pre>` raw content; no text rendering of `type=message`.
- Runs: id prefix, status, timestamp; detail raw JSON; no project/template/strategy columns (record has none).
- Auth view honest about console token; no orientation; three trees = three login forms, three `api()` helpers.
- Console errors: only expected 401/404 probes; no JS exceptions.
- Command Center (12 literals) admin-only, honest for tenants; Admin console (73 literals) 15 surfaces, "route absent" when a seam is not composed; learning panel drives lifecycle routes by hand.

## 6. BACKEND / RUNTIME FINDINGS
- Bootstrap `apps/main.py` lifespan = API + outbox relay + exec worker; `build_runtime_profile(environ)` sole config site; in-memory default; durable with `DATABASE_URL` (30 tables).
- Auth→tenant→authz→entitlement: middleware 401 before body; admin iff email ∈ `ADMIN_EMAILS` on a real session; reserve-before-work, settle on success (0 on provider failure). **Holds.**
- Execution paths: single → Router → ExecutionService; template → StrategyExecutor (child records); agent → AgentRuntime over AgentLoop (echo → honest 502 with stop reason). **One path each; no duplicate authority found.**
- Strategy failure projection loses the child provider error (F-2).
- `project_id` ownership-only (F-1); `conversation_id` supported, unused by UI.
- SSE replay serves node events per stage for template runs (tenant-reachable) — the Workbench just never reads it after a sync 200.
- Webhooks closed event set; process-local map. Capability catalog 24 ids (`execute.token_streaming` unavailable; custody/dev.publish_modes/rate_limits inert here).

## 7. REQUIREMENT COVERAGE MATRIX

| # | requirement | status | evidence | missing edge | reuse | minimum change | acceptance |
|---|---|---|---|---|---|---|---|
| R1 enter | MISSING | `/` 404 | no landing | StaticFiles mount | redirect `/`→`/app/` | GET / lands on /app/ |
| R2 understand | MISSING | `A_orientation` | no copy | index.html | orientation block (auth + empty home) | visible pre-login and first home |
| R3 where to start | PARTIALLY | placeholder | no first-run state | index.html | empty-state card | visible when no runs |
| R4 authenticate | BLOCKED (non-operator) | `A_after_register` | console token | register/verify routes | **D-1** | new user completes signup on the stated path |
| R5 reach main | FULLY USABLE after login | `A_main_visible` | reload → re-login | session tokens | **D-2** | reload keeps session |
| R6 discover | PARTIALLY | Cmd-K only | agent/skills hidden | `/v1/agent-tools`, `/v1/skills`, `/v1/templates`, `/v1/models` | home "what you can run" from served facts | facts shown, none invented |
| R7 choose | PARTIALLY | project/template selects | no agent choice | `execution_policy.strategy` | **D-3** | tenant runs agent + reads own trace |
| R8 execute | FULLY USABLE hermetic / PARTIAL live | `exec_sync`, `exec_sync_live 403` | key refused | provider chain | none (operator key) | one live 200 on record |
| R9 meaningful result | PARTIALLY | raw JSON | no rendering | `result.type/content`, echo `note` | render text + provenance badge | answer readable without JSON |
| R10 understand what happened | PARTIALLY | status/id | no stages/provider | `/events` replay | read replay after template run | 3 stage rows |
| R11 inspect | PARTIALLY | raw JSON | same | same | same | — |
| R12 continue | PARTIALLY | context restore | runs lack project | record contract | **D-4** additive fields | Runs filter by project |
| R13 preserve context | PARTIALLY | `B_context_after_roundtrip` | token | see R5 | — | — |
| R14 move between capabilities | FULLY USABLE (re-login cost) | shell links | P-7 | — | — | — |
| R15 recover | PARTIALLY | verbatim errors | no hints; opaque strategy error | error `code/details`; child reports | UI hints + project child error (1 core file) | failure names stage + category |
| R16 return to main | FULLY USABLE | shell links | — | — | — | — |
| R17 learning loop | LEARNING INFRASTRUCTURE ONLY | §10 | intake, evidence producers, effect | lifecycle/evaluation/memory GOLD | **D-5** | see §10 |
| R18 provider/model truth | PARTIALLY | F-6 | availability ≠ health | `resource_signals` | tenant-safe degraded state in `/v1/models` | refused model not plainly "available" |

## 8. PROVIDER / MODEL FINDINGS
Chain: env key → composition → `credential_ref` → adapter → `GET /models` discovery → ModelRegistry → Router AUTO → adapter → normalised `ProviderError{category,safe_message,retryable}` → unified error. **Single and real.** Hermetic `local_echo` labelled in every payload. Live `genspark_llm`: discovery 8 models; every inference `quota_exceeded/plan_refusal_200` → 403, usage settled 0 → **production-capable inference NOT VERIFIED**. Groq/gateway **NOT VERIFIED** (no keys). Explicit model policy exists and is honoured (unknown → 503 with reason); UI exposes no selector (correct: template mode ignores request policy). Failover across providers **NOT VERIFIED** (one provider).

## 9. AGENT / TEMPLATE / APP FACTORY FINDINGS

| item | user-reachable | runtime-wired | backend-backed | persistent | security-bound | useful today |
|---|---|---|---|---|---|---|
| Agent | API only | yes (one chain) | yes | executions | trace admin-only (over-restrictive for own runs) | only with real provider + tools env |
| Agent tools | `GET /v1/agent-tools` | deny-by-default | yes | env | firewall + tickets | 0 tools zero-config |
| Skills | `GET /v1/skills` (empty) | data-only (AD-4) | admin import | in-memory | reviewer/approval | none for tenants |
| Templates | picker + detail | StrategyExecutor | yes | built-in only (write half deferred) | tenant auth | one system template |
| App Factory | via `app_factory.plan@1` only | plan yes; `AppFactoryCapability` not composed; generation deferred (AD-7) | yes | — | — | plan whose stages user cannot see |
| Inspection | Runs raw; admin trace | — | — | — | — | weak |

No second agent path / App Factory / registry found.

## 10. LEARNING LOOP — **LEARNING INFRASTRUCTURE ONLY**

| transition | implemented | connected | note |
|---|---|---|---|
| execution → outcome | yes | yes | records + evaluations |
| outcome → feedback | **no** | — | R189 §6.8 deferred; gates structurally take no feedback |
| → evidence capture | manual only | admin `POST samples` / CSV | no execution produces a sample |
| qualification / provenance | yes | yes | scan → sanitize → admit; tenant-scoped; custody on durable |
| → evaluation | yes | yes | `evaluate` binds EvaluationRecord |
| → decision | yes, strict | partial | promotion needs artefact refs (`evaluation_id`, `security_evaluation_id`, scenario-replay `regression_execution_id`); asserted-true without refs **refused** (measured) — correct anti-poisoning |
| change generation / validation | GOLD memory item; source lane §14-gated | yes | never auto-applied |
| runtime activation | GOLD → memory (`source=learning.gold`, scope TENANT) → context composer | wired, **unobserved** | `gold_blocks 0` after attempt |
| monitoring / regression / rollback | dashboard placeholder; capability re-test; custody revoke/sweep | partial | no automatic regression detection |
| improved later execution | **NOT VERIFIED** | — | only measurable via `context_provenance.gold_blocks` |

Loop open at both ends by recorded operator deferrals (R189 §6.7–6.9). User feedback: not represented. Traceability sample → evaluation → GOLD item → provenance artefact exists.

## 11. SECURITY / TENANCY FINDINGS
Measured clean: anonymous 401 everywhere incl. session probe; tenant→admin 403; foreign resources 404 identical shape; agent routes admin-only; explicit unknown model 503 with no foreign data; no secrets in error bodies; UI keeps token in memory only; `&execution=` deep link resolved server-side. Credential custody by ref; Vault **NOT VERIFIED** live. Tools deny-by-default. **Open, operator-owned:** D-03 rotation/purge; N-9 legacy branches; public repo.

## 12. STATE / PERSISTENCE FINDINGS

| state | in-memory | durable | gaps |
|---|---|---|---|
| users/sessions/tokens | process | tables (digests) | no password reset; TTL **NOT VERIFIED** |
| executions + nodes | process | tables | no retention; no project/template ref |
| usage ledger | process | table | — |
| workspaces/projects | process | tables | delete cascades **NOT VERIFIED** |
| memory/conversations | process | tables | UI never reads |
| evaluations/learning samples/custody | process | tables | — |
| provider + model registries | process | **process** | by design (discovered at boot) |
| webhook subscriptions | process | **process dict** | lost on restart |
| engineering grants/tickets | process | **process** | documented |
| UI context | sessionStorage | same | token never stored |

## 13. OPERATIONAL FINDINGS
LOCAL DEMO works zero-config. DEV-USABLE with `ADMIN_EMAILS` + key (modulo quota). INTEGRATION-USABLE with Postgres + alembic (measured earlier, not re-run). PRODUCTION-CAPABLE **not claimed**: no Dockerfile/compose/CI in repo; single process; no email; D-03 open. `/healthz` liveness only.

## 14. COMPLEXITY / REDUNDANCY FINDINGS

| candidate | verdict |
|---|---|
| Three static trees, three login forms, three `api()` helpers | keep trees; shared session mechanism (D-2) removes the user pain |
| `RUN.md` vs `OPERATIONS.md` vs README historic prompt | README top → 10-line product entry; OPERATIONS stays authoritative |
| 24 per-round handoffs/pointers | history, not product; keep |
| `PlanLimits.modality_limits` unenforced; `TemplateOverride` without route | recorded deferrals |
| per-file `/v1/` literal ceilings | keep; declare per completion phase, not per literal |
| duplicate engines/routers/registries | **none found** |

## 15. REAL USER JOURNEY FAILURES
A: blocked at verify (console token); no orientation; raw JSON result; Runs link works. B: workspace/project work; project not recorded on the run; reload → login; toggle-off trap. C: template detail + run → single payload; agent/skills absent; Command honest for tenants. D: stale project → verbatim error without hint; async timeline honest; empty ask → contract text; live strategy failure opaque. E: admin console + Command correct; boundaries hold.

## 16. MASTER COMPLETION PLAN

### PHASE 1 — a real user can enter, run, read, continue (P0/P1)
| ID | P | problem | reuse | exact change | area | acceptance | risk |
|---|---|---|---|---|---|---|---|
| C-01 | P0 | `/` 404 | StaticFiles mount | redirect `/` → `/app/` | `apps/composition/runtime.py` | GET / lands on /app/ | nil |
| C-02 | P0 | onboarding blocked | register/verify routes | per **D-1** | `ui/app` (+`apps/api/auth.py` only under D-1 b/c) | new user completes signup on the stated path | posture differs per option |
| C-03 | P0 | raw JSON result | `result.type/content`, echo `note` | render message text; provider + hermetic badge from served fields; raw toggle | `ui/app` | answer readable | nil |
| C-04 | P1 | runs lack project/template | execution record (additive) | per **D-4**: `project_id`, `strategy`/`template_ref` on record + list; UI filter | contracts + `apps/api/app.py` + `ui/app` | Runs filter by project | freeze re-derive |
| C-05 | P1 | session lost | session tokens | per **D-2** | `ui/*` or `apps/api/auth.py` | reload keeps session | XSS vs CSRF trade-off |
| C-06 | P1 | opaque strategy failure | child reports | project failing stage's provider error into strategy error | `core/execution/strategy.py`, `apps/api/errors.py` | failure names stage + category | low |
| C-07 | P1 | no orientation | index.html | orientation block + first-run empty state from served facts | `ui/app` | `A_orientation` true | nil |
| C-08 | P2 | toggle trap | `selectWorkspace` | select, explicit deselect | `ui/app` | click keeps selection | nil |
| C-09 | P2 | no error hints | error codes | code → one-line next step | `ui/app` | D errors carry hint | nil |

### PHASE 2 — advanced capabilities genuinely usable (P1/P2)
| ID | P | problem | reuse | exact change | acceptance |
|---|---|---|---|---|---|
| C-10 | P1 | template stages invisible | `/v1/executions/{id}/events` replay (tenant) | read replay once after a sync template run; render stages with existing `stageLabel` (R188 C3 untouched) | 3 stage rows |
| C-11 | P1 | agent unreachable/uninspectable | `strategy=agent`, trace route | per **D-3**: composer toggle only when tools ≥1 or real provider bound; trace/diagnosis readable by OWNING tenant (foreign still 404) | tenant reads own trace |
| C-12 | P2 | refused models shown available | `resource_signals` | tenant-safe degraded/unavailable state in `/v1/models` | refused model not "available" |
| C-13 | P2 | skills/webhooks/memory invisible | served routes | read-only panels — only under **D-6** | panels read real routes |

### PHASE 3 — learning closed or explicitly deferred (P2/P3, D-5)
| ID | P | change | acceptance |
|---|---|---|---|
| C-14 | P2 | admin action "propose sample from execution X" (RAW, `source_execution_id`) | sample traceable to execution |
| C-15 | P2 | admin console runs security evaluation + scenario replay and passes ids as `evidence_refs` | a promotion succeeds with real refs |
| C-16 | P3 | surface `gold_blocks` on run detail; use existing capability re-test | `gold_blocks > 0` observed |
| C-17 | P3 | dashboard: real counts or DEFERRED label | no `placeholder:true` shown as data |

## 17. MINIMUM CHANGE SET (Phase 1 only)
C-01, C-02, C-03, C-06, C-07, C-08, C-09 → production files: `apps/composition/runtime.py` (redirect), `core/execution/strategy.py` + `apps/api/errors.py` (C-06), `apps/api/auth.py` only if D-1 = b/c; rest `ui/app`. No new endpoint, registry, or schema. C-04 is the first change needing a contract re-derive.

## 18. DEPENDENCIES
C-04 → freeze re-derive + literal ceilings re-declared. C-05 → D-2. C-10 → none. C-11 → D-3 + tenant-own read in `apps/api/agent.py`. C-12 → additive semantics. C-14–17 → D-5. Live proof of any path → working provider key (D-7).

## 19. VERIFICATION PLAN
Per phase: targeted pytest → `check_repo.sh` on fresh clone → freeze `--check` → 18-root regression → Chromium journeys (`evidence/audit_v2/probe_journeys*.py.txt`, extended per item) → API probes hermetic + live → evidence under `evidence/completion_v2/`. Tenancy trio + admin 403 sweep every phase. One disposable PostgreSQL run for phases touching records.

## 20. FINAL DEFINITION OF DONE (mission §23 mapped)
PRODUCT R1–R3 (C-01/02/07) · UNIFIED (C-05) · CORE EXECUTION (C-03 + one live 200) · NAVIGATION (C-01) · CONTEXT (C-04/05) · REAL INTEGRATION (C-10/11/13) · PROVIDER TRUTH (C-12 + hermetic badge) · MODEL TRUTH (no selector) · AGENT/TEMPLATES/APP FACTORY (C-10/11; generation stays AD-7 deferred) · LEARNING (C-14–17 or DEFERRED label) · SECURITY (trio + 403 sweep green) · PERSISTENCE (C-04 durable measured) · ERROR RECOVERY (C-06/09) · NO FALSE COMPLETENESS (F-1…F-9 closed or labelled) · NO DUPLICATE AUTHORITY (import-linter) · REQUIREMENT COVERAGE (§7 rows all FULLY USABLE / DEFERRED / BLOCKED / EXCLUDED with a record) · REAL USER PROOF (journeys A–E pass without operator steps except those D-1 keeps).

## 21. NOT VERIFIED / UNAVAILABLE EVIDENCE
Live inference success (key plan-refused); Groq/gateway; Vault round-trip; durable restart survival (not re-run); multi-provider failover; token TTL; workspace delete cascades; OTel export; webhook delivery to a receiver; engineering workspace tools; any usability test with a real person.

## 22. OPEN DECISIONS THAT TRULY REQUIRE USER AUTHORITY
- **D-1 Onboarding without email:** (a) keep console-token verification and say "operator-assisted onboarding" in-product; (b) dev-only token surfacing in the register response on the in-memory profile ONLY; (c) admin action "create verified user".
- **D-2 Session custody:** tab-scoped `sessionStorage` token (UI-only) vs HttpOnly cookie session (backend + CSRF).
- **D-3 Agent for tenants:** expose `strategy=agent` in the Workbench and open trace/diagnosis to the owning tenant, or keep admin-only for v1.
- **D-4 Additive execution-record fields** (`project_id`, `template_ref`/`strategy`) under the contract freeze.
- **D-5 Learning scope for v1:** close minimally (C-14–17) or label DEFERRED and stop.
- **D-6 Tenant panels for skills / webhooks / memory** in v1.
- **D-7 Live provider:** supply a working key, or accept hermetic-only proof this phase.
- **D-03 / N-9** remain operator-owned.

**STOP.** No production code modified. Awaiting explicit **APPROVE** with rulings D-1…D-7 and the approved phases.
