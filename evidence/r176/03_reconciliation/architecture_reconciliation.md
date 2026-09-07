# A3 — Architecture reconciliation (prompt §2.3)

HEAD at start 2330bd5. Authority used: `final_docs_v3/00_INDEX.md` (all 20 V3 docs COMPLETE_AUTHORITATIVE; V2 = archived)
→ `02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md` §2 (15 invariants) → `41_IMPLEMENTATION_PLAN_AND_MVP.md` Part III map →
12 ACCEPTED ADRs (`engineering/adr/`). Source-of-truth order per prompt §0.4.

## 1. Invariants — executed checks where possible

| # | invariant | check | result | status |
|---|---|---|---|---|
| 1,2 | Core provider-/model-agnostic | `grep -rliE 'groq|assemblyai|genspark|openai|anthropic' core/` → 4 .py files, **6 hits, all comments** citing live evidence (R165), zero identifiers/imports; `grep` for framework imports (`fastapi|sqlalchemy|redis|httpx|boto3|hvac`) in core/ → **0** | kept | VERIFIED · STATIC+MEASURED |
| 12 | contracts / registries / adapters | `lint-imports` → **13 kept, 0 broken** (`lint_imports.txt`), incl. "Core must not import the HTTP client (ADR-0008)", "Admin surfaces must not import engineering adapters (ADR-0012)" | kept | VERIFIED · TEST |
| 3,4 | Model ≠ Provider ≠ Account; platform ≠ user credentials | alembic 0018 `provider_model_bindings`; `evidence/credential_binding_boundary.md` (R-prior) | consistent with tree | INFERRED (A5/A9 will execute) |
| 7,8 | LLM never a security authority; unknown ⇒ DENY | `tests/security` (6 files), `tests/tools` tool-call gate, R168 D-07 tokenless 401 | consistent | INFERRED until A5 executes denied cases |
| 11 | Admin config cannot break security invariants | R168 D-10 admin gate order fix; `tests/admin*` (12 files) | consistent | INFERRED until A6 |
| 14 | significant change ⇒ ADR | 12 ADRs, all ACCEPTED with operator decision line and date | kept | VERIFIED · STATIC |
| 15 | commit + verification only trusted progress | R-series ledgers; check_repo gate | kept (F-R176-03 drift noted) | VERIFIED · RUNTIME (A1) |
| 5,6,9,10,13 | router decides / runtime owns state / memory ≠ training / verified intelligence / policies versioned | `core/routing`, `core/runtime`, `core/memory`, `core/learning`, `core/evaluation` exist with tests (3/4/2/3/3 files) | present | INFERRED until A8 |

## 2. Historical requirement vs current implementation (41 Part III map)

| capability area | FINAL requirement (Part I) | current tree (STATIC; RUNTIME where noted) | conflict | actual authority | decision |
|---|---|---|---|---|---|
| Auth / Tenant | full identity, device identity, entitlements | email/password + verification, personal tenant, Bearer auth, 401 tokenless (RUNTIME R168), `ADMIN_EMAILS`; no device identity | FINAL "device identity" absent | 41 Part III lists device identity under FINAL not MVP | **IMPLEMENTATION GAP (POST-RELEASE)** — no consumer requires it today |
| Providers | full migration, pools, credential policies | gateway-service (Groq, AssemblyAI, fixture_echo) + platform adapters (`providers/real`), bindings 0018; ADR-0008/0011 | ADR-0008 *changed* the shape (remote gateway) vs 41's in-process plugin | ADR > plan (§0.4 rank 2 > 3) | **REQUIREMENT CHANGE — accepted by ADR, NOT a gap** |
| Models | full registries | `/v1/models`, admin model routes (59 admin method-routes) | — | — | to verify A4 |
| Routing | full Router Engine + fallbacks | `core/routing/router.py` per-model caps, failover classes (R168 D-01, R175 F-02 parity) | — | — | to verify A9 |
| Execution | all strategies incl. debate/map-reduce/agent/hybrid | `/v1/execute`, `/v1/agent`, executions, SSE (R146) | debate / map-reduce strategy presence unknown | — | **UNVERIFIED → A4** |
| Async fabric | outbox/DLQ/backpressure | in-process outbox relay (hermetic) + durable outbox tables | horizontal-scale claims | — | to classify A7 |
| Memory | Personal Context Engine + hierarchy | `core/memory`, `core/context`, pgvector embeddings (durable tests) | — | — | A8 |
| Roles / Skills / Tools | custom roles, import lifecycle, Tool Fabric + Client Runtime + Device Trust | `core/roles`, `core/skills`, `core/tools` + `/v1/skills`, `/v1/agent-tools`, ADR-0012 engineering workspace | "Client Runtime / Device Trust" not seen | 41 marks client-runtime GA under FUTURE | **NOT A REAL GAP** (FUTURE) |
| Evaluation | all graders + counter-eval | `core/evaluation` (R088 specialty graders) | — | — | A8 |
| Learning | shadow/canary/promotion | `core/learning` (R090 gates, R161 phase 3) | — | — | A8 |
| Usage / Billing | plans + cost snapshots + failover cost rules | `core/usage` (R089 estimate→reserve), `/v1/usage` | payments integration = FUTURE | — | NOT A REAL GAP |
| API | full public surface + webhooks | `/v1/{execute,executions,models,usage,webhooks,workspaces,projects}` (RUNTIME: routes) | SDK absent | prompt §0.3 says "future SDK path" | **OPTIONAL IMPROVEMENT → A10** |
| Admin | all modules + config lifecycle | 59 admin method-routes, `/admin` UI, admin agent | — | — | A6 |
| Deployment | multi-AZ HA + DR | single process, single region | FINAL requirement unmet | 41 §26 Phase 23 | **POST-RELEASE** (outside a code-closure verdict; documented honestly in OPERATIONS §13) |
| UI | (not in 41 map) | `/app`, `/admin` mounted; browser live-suite NOT EVALUATED (gate line) | — | R175 §6: UI not authorised | **UNVERIFIED — out of this round's mandate** |

## 3. Contradictions worth recording

| historical | current | conflict | authority | decision |
|---|---|---|---|---|
| 41 §2 layout + 52 protocol: single mutable state file `PROJECT_EXECUTION_STATE.md` | per-round `evidence/rNNN_state_ledger.md` since R168 | state file frozen at R168 | OPERATIONS §12 (rank 6) vs 52 (rank 6) — tie; practice + reality decide | DOCUMENTATION DRIFT (F-R176-03) |
| 41 in-process provider plugins | ADR-0008 remote provider gateway + platform adapter | shape change | ADR (rank 2) | REQUIREMENT CHANGE, accepted |
| prompt §0.6 "placeholders only" | literal live values committed at 521d885 | security invariant breach | rank 1 | **REAL BLOCKER for the gate** (F-R176-01, FIX-01 proposed) |
| README/52 "agent must not push" | R168–R176 practice pushes with operator-supplied token | wording vs practice | operator's standing instruction | DOCUMENTATION DRIFT (F-R176-04) |

No historical requirement is being forced onto the newer architecture; no healthy architecture is being redesigned.

## 4. Carry-forward to later items
- A4 must answer: which execution strategies actually exist (debate / map-reduce / hybrid) — RUNTIME or TEST evidence.
- A5–A7 turn the INFERRED invariants (3,4,7,8,11) into executed probes (P0).
- A10 decides whether "no SDK" is a closure blocker (prompt §2.10 one-line app challenge) or documented path.
