# R182 HANDOFF — implementation contract for R182-IMPL (UI implementation)

Branch `genspark_ai_developer_r182`, base `main` 743e203f (post-R181 merge commit). Analysis lives in `R182_READINESS.md` (row numbers below refer to its §4 inventory); this file only says what the next round does. R182-IMPL is NOT a discovery round: it starts from the items below.

## 1. Architecture / ADR status
ADR-0013 `engineering/adr/ADR-0013-ui-front-end-stack-and-serving-posture.md` — **PROPOSED — AWAITING OPERATOR DECISION**. Operating default: **Alternative C** = vanilla ES modules + hand-written SVG/CSS + optional hand-written WebGL2 layer; no framework, no build step, no runtime dependency; served by the existing `StaticFiles(html=True)` posture. **No production UI file may be written until the operator accepts one alternative (D-1).** B/D require the extra declarations listed in ADR-0013 §Decision before code.

> **Superseded 2026-09-14 (R182-DEC-02, `60_DECISION_LOG.md`; ADR-0013 §Status).** The line above is the opening-time state. ADR-0013 is **ACCEPTED — Alternative C** (operator text pasted verbatim in the ADR); D-1 and D-3 (b) were answered, so the write-block in §1 was lifted and `ui/app/command/` was implemented in R182-IMPL (`evidence/r182_impl_state_ledger.md` rows 4, 8, 22). This paragraph is kept as history, not rewritten.

## 2. Command Center tree / path
Default (D-2 a + D-3 b): files at **`ui/app/command/`** (`index.html`, `command.js`, `command.css`) — a sub-directory of the already-mounted `/app` tree, served at `/app/command/` with **zero production change** (no mount line; `apps/` stays frozen). Declared and guarded as its own unit (§13/§14). If the operator picks D-3 (a): `ui/command/` + one `StaticFiles` mount in `apps/composition/runtime.py` under a consciously raised ceiling (0→1, declared with history BEFORE the commit).

## 3. UI files allowed to change
- NEW: `ui/app/command/index.html`, `ui/app/command/command.js`, `ui/app/command/command.css` (default path).
- EXISTING, branding only (§15): `ui/admin/index.html`, `ui/app/index.html`.
- FORBIDDEN: any file under `core/`, `apps/`, `infrastructure/` (ceiling 0); `ui/admin/app.js` literal count may not rise (73 = N0); `ui/admin/` file list may not change without the manifest equality edit.

## 4. Dependencies permitted
Runtime: **none** (default C). Dev-only, IMPL round, on D-4 = yes: `playwright` declared in `pyproject [dev]` (+ browser install command recorded in OPERATIONS) — it replaces NOT-EVALUATED #1. No `package.json`, no lockfile, no `node_modules`, no `three`/React/Next unless ADR-0013 B/D is accepted with its declarations.

## 5. APEX concepts to REUSE (conceptually, rebuilt by hand)
Central orb with breathing ring + orbit dots (rows 1, 30); constellation graph with circuit traces around the core (row 3); bottom status bar text cluster (row 31); visually-hidden keyboard list mirroring the graph (row 34); dark palette and keyframe vocabulary (`apex-orb.css` ideas, not text).

## 6. Components to REBUILD / DISCARD
REBUILD: orb ring (no waveform), particle/plasma layer as hand-written 2D-canvas/WebGL2 with SVG fallback (row 29), reasoning web as capability/stage graph, status bar (no equalizer), composer, detail dialog. DISCARD: tap-cycle state machine + 8 s timer, `ROSTER`, `INFO`, overview panel (clock/weather/social), `/api/weather`, social links, `lucide-react`, three/fiber/postprocessing. **Never vendor or import APEX source; never use the Apex name or branding** (F-R182-04).

## 7. QEVION contract feeding each major surface (exact)
| surface | route → fields |
|---|---|
| Core state (row 1) | `GET /v1/executions` → `executions[].status`; `GET /healthz`; `GET /v1/auth/session`; `GET /v1/admin/system` → `profile`, `scope` |
| Capability nodes (rows 3-6) | `GET /v1/admin/capabilities` → `capabilities[]{id,state,evidence}`; `GET /v1/admin/capabilities/exercisable` → `exercisable[]`; `POST /v1/admin/capabilities/{id}/exercise` |
| Execution graph (row 8) | `GET /v1/agent/executions/{id}/trace` → `stages[]{node_key,status,attempts[]}`, `ledger`, `as_recorded` |
| Live progress (rows 9-10) | `GET /v1/executions/{id}` → `status`, `progress{current_stage,percent}`; `GET /v1/executions/{id}/events` SSE (fetch-read) → `execution_started|node_started|node_completed|final|error` |
| Conversation (row 11) | `POST /v1/execute {ask}`; `POST /v1/agent/converse {message}` → `verification{…}`, `reasoning_trace[]` |
| Models / providers / routing (rows 12-14) | `GET /v1/models`, `GET /v1/admin/models`, `GET /v1/admin/providers`, `GET /v1/admin/routing/weights` |
| Evaluation (row 15) | `GET /v1/admin/executions/{id}/evaluations` → `evaluations[]` (`[]` = not evaluated); `GET /v1/admin/evaluations/{id}` → `level`, `score|null`, `confidence|null` |
| Learning (row 16) | `GET /v1/admin/learning/dashboard` → `placeholder` |
| Memory / usage (rows 17-18) | `GET /v1/memory/preferences`; `GET /v1/usage`; `GET /v1/admin/usage` → `usage[]{execution_id, ledger}` |
| Admin actions / notifications / audit (rows 20-22) | `GET /v1/admin/capabilities/actions`; `GET /v1/admin/notifications`; `GET /v1/admin/audit` |
| Projects (row 23) | `GET/POST /v1/projects` → `{project_id, workspace_id, name, metadata}` |

## 8. Allowed runtime states (closed)
Core: `idle | running | waiting_approval | failed | unreachable` (derived from `ExecutionStatus` + reachability). Node: `available | inert | unavailable | UNKNOWN` (`CapabilityState` + loud fallback). Execution: `queued | running | waiting_approval | succeeded | failed | cancelled`. Model availability: `available | unavailable | degraded | UNKNOWN`. Evaluation: `not evaluated | RAW | EVALUATED | VALIDATED | VERIFIED | GOLD`. Stream: the 5 emitted SSE types.

## 9. Forbidden / fabricated states
`thinking`, `speaking`, `listening`, `energized`, `processing`, `reasoning` as Core/node states; token typing or partial text (`delta` is never emitted); voice/audio waveform or equalizer; learning charts/trends while `placeholder: true`; any evaluation score when `evaluations` is `[]`; "verified" provider badges; webhook delivery status; App Factory generation/preview/deploy state; repository/branch/commit/preview fields on projects; fleet scope; clock/weather/social widgets; any usage→execution link when the execution record is absent.

## 10. BACKED surfaces (implement): rows 1, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13-read, 14, 17, 18, 19, 20, 21, 22, 23, 26-registration, 28, 31, 33, 34.
## 11. INERT surfaces (honest placeholder only): rows 5-inert nodes, 16 learning dashboard, 27 engineering workspace (404 ⇒ "route absent").
## 12. MISSING surfaces (do NOT represent): 13-provider verification (R183), 15-evaluation distinction Q7 (R183), 24 App Factory (undefined; operator contract first), 25 API keys, 26-delivery status, 35 branding (M1 fixes it).

## 13. Budget impact
`round_r182` ceiling **0**, changes_used 0 — stays 0 under D-3 (b). Under D-3 (a): ceiling 0→1 declared with `ceiling_history` BEFORE the mount commit; log entry for `apps/composition/runtime.py` only. `ui/` never counts. Any other frozen-tree need = STOP + name contract + R183.

## 14. Guard impact
BEFORE the first Command Center file: add a manifest block (name: `ui_command_static_check`) declaring exact file list, `/v1/` literal ceiling for `command.js` = its measured count at first GREEN of M1 (only moves down), exception ceiling 0, single `fetch(` inside one `api()`, banned `EventSource(`/`WebSocket(`/`XMLHttpRequest`/`axios`, no quoted `CAPABILITY_IDS`, no provider branching; plus a test module under `tests/ui/` enforcing it (the first red test §16 is part of it). `ui/admin` block unchanged; N0 73 unchanged; NE ceiling 2 unchanged; secret-scan exceptions 5 unchanged; guard test `test_manifest_lists_exactly_the_ui_files` stays scoped to `ui/admin`.

## 15. Branding / pin changes (M1, one commit)
`ui/admin/index.html:6,44` and `ui/app/index.html:6,46` → `QEVION Control Plane` (brand `QEVION`); update pins `tests/composition/test_admin_console_runtime.py:80,146` and `tests/composition/test_ui_app_pd2.py:83` in the same commit. New Command Center `<title>` = `QEVION Control Plane — Command Center`.

## 16. First red test (exact)
Path: `tests/ui/test_command_center_topology_r182.py`
Test: `test_capability_nodes_derive_from_served_contract_not_a_roster`
Invariant: node ids rendered by `ui/app/command/command.js` == `{c["id"] for c in GET /v1/admin/capabilities}` on the served in-memory profile (admin session, pattern of `tests/composition/test_ui_app_pd2.py`); source has no quoted `CAPABILITY_IDS`, no `ROSTER`/roster array, no `thinking|speaking|listening`; state classes ⊆ `CapabilityState` ∪ {UNKNOWN}; Core vocabulary ⊆ §8.
Expected first run: RED — `FileNotFoundError` (file absent). Create it as the FIRST act of R182-IMPL, commit RED, then implement.

## 17. First implementation milestone — M1 "Honest topology"
Shell + Core (row 1) + capability nodes with `evidence` tooltips and inert/unavailable rendering (rows 3, 5, 6) + scope badge (row 7) + status bar (row 31) + keyboard list, aria, reduced-motion (row 34) + branding (§15) + guard block (§14). No execution graph, conversation, or stream yet (M2).

## 18. Proof commands
- `.venv/bin/python -m pytest tests/ui tests/composition/test_ui_app_pd2.py tests/composition/test_admin_console_runtime.py -o addopts="" -q -p no:cacheprovider`
- canonical gate in a fresh clone: `env -i PATH=$PWD/.venv/bin:/usr/bin:/bin HOME=/tmp bash engineering/verification/check_repo.sh` → `RESULT: PASS`, `not_evaluated=2` (→1 once browser proof lands), budgets `round_r182=0/0`
- gateway: `cd gateway-service && pytest -o addopts="" -q -p no:cacheprovider` → 194
- literal count: `grep -o '/v1/' ui/admin/app.js | wc -l` → 73; `grep -o '/v1/' ui/app/command/command.js | wc -l` ≤ declared ceiling
- browser proof (D-4 yes): Playwright script against `python3 -m apps.main` with `ADMIN_EMAILS`, asserting rendered node count == served capability count; evidence under `evidence/r182_impl/` (tracked, not `raw_*`).

## 19. Stop conditions
Any need to edit `core/ apps/ infrastructure/` (other than the D-3 (a) mount) → STOP, name the missing contract, assign R183. `ui/admin/app.js` literal count > 73 → STOP. A third NOT-EVALUATED item, a secret-scan exception, or an N0 change without the manifest+baseline pair and operator text → STOP. Any APEX source copied → STOP (F-R182-04). Any state from §9 rendered → STOP.

## 20. Unresolved operator-only decisions
D-1 stack (ADR-0013) · D-2 tree · D-3 serving under ceiling 0 · D-4 Playwright in IMPL · D-5 branding timing · D-6 min_passed ratchet. **D-1 and D-3 block M1**; the rest have operating defaults (`R182_READINESS.md` §9).

> **Resolved 2026-09-14 (R182-DEC-02).** All six were answered by the operator: D-1 ACCEPTED (C); D-2 per §2/§14; D-3 (b) on the existing `/app` mount, ceiling stays 0; D-4 yes (Playwright dev-only, replaced NOT-EVALUATED #1); D-5 branding in one commit (`a3e6ad0e`); D-6 ratchet only at the gate of record by the measured number (3504 → 3658 → 3666). The round closed at M2 (R182-DEC-03). No operator-only decision from this section remains open; the heading is kept as history.

## Resume mechanism
Remote branch head is the checkpoint; rebuild `.venv` (`pip install -e '.[dev]'`). Merge posture: merge COMMIT, no squash; gate on the merge commit; evidence under `evidence/r182/` (tracked names, never `raw_*`).
