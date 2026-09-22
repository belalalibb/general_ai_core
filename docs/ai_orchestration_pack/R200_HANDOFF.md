# R200 HANDOFF — Command capability → surface routing + non-admin Command posture (UI-only)

Status: **CLOSED** (R200-DEC-02). Base: `main f6991e16` → merged as `main ebe5e549` (PR #58, merge commit) + records-only closure PR. Branch `genspark_ai_developer_r200` (deleted after closure). Ceiling 0 used 0.

## 1. Authority (operator, verbatim anchors)
"APPROVE R200. Confirm: D1 = B, D2 = I, D3 = I including the /admin receiver, D4 = defer, D5 = accept as proposed. Execute R200 exactly as proposed. Preserve the unified shared multi-tenant QEVION direction: Command is the unified entry point, admin-only capabilities remain protected by the server, nothing implemented may become hidden, and no duplicate engine/router/agent or backend authority may be introduced. Do not pre-approve future rounds or broaden scope. Stop at the next decision gate."

## 2. Allowed / frozen
- MAY change: `ui/app/command/{command.js,index.html,command.css}`; `ui/app/app.js` (boot-once `#view=` receiver only); `ui/admin/app.js` (boot-once `#surface=` receiver only); `tests/ui/test_command_routing_r200.py` (new, RED first); pins whose wording says "byte-identical" for `command.js`/`ui/admin/app.js` (they become count pins: 12 / 73 hold); `evidence/r200/*`; records.
- FROZEN: `core/ apps/ infrastructure/` (0 files); contracts + freeze baseline (46); `CAPABILITY_IDS`; every `/v1/admin/*` and `/v1/agent/*` gate; register §C; `command.js` `/v1/` count 12 and one `fetch(`; `ui/app/app.js` 22 / 4; `ui/admin/app.js` 73.

## 3. Steps
1. Declaration (this file, R200-DEC-01, manifest `round_r200`, pointer, ledger row 1) — commit + push BEFORE code.
2. RED: `tests/ui/test_command_routing_r200.py` → `evidence/r200/red.txt`.
3. R200-A `command.js`: `surfaceForEvidence()` prefix table → `{tree, hash, admin}`; node detail gains a link / disabled labelled link / "no surface" line; `probeSession` admits any session; `loadCenter` → admin path unchanged, tenant path = tenant reads only + surfaces list + one locked admin node. R200-B hash receivers. R200-C markup + css.
4. GREEN → `evidence/r200/green.txt`; real-browser proof asserting the **request set** for tenant (no `/v1/admin/*`, no `/v1/agent/*`) and admin (== R185 set); guards 73 / 12 / 22 / 4; freeze; regression 18 roots.
5. Gate of record fresh clone → PR (merge commit) → post-merge gate → records-only closure PR → STOP.

## 4. Not in this round
Template picker in Command (D4 defer), `templates/{ref}` detail, `project_id` carry-through, shared agent panel, root `/` redirect, any register flip, any token sharing across trees. Each needs its own `APPROVE`.

## 5. Outcome
- **Delivered:** R200-A `command.js` — `surfaceForEvidence()` derives `{tree, hash, admin}` from the served evidence route prefix (escaped regex; no capability-id literals, no quoted `/v1/`); node detail renders a link / `aria-disabled` "— admin" labelled link / "not linked: node is <state>" / "no surface owns this route" line — nothing hidden; `probeSession` admits any authenticated session; `loadCenter` is two-tier: admin path == R185 request set (unchanged), tenant path = `/healthz` + `refreshExecutions()` only, surfaces list + one locked admin node labelled from `session.is_admin`. R200-B boot-once hash receivers: `ui/app/app.js` `#view=` (VIEWS-checked), `ui/admin/app.js` `#surface=` (clicks the rail item). R200-C `index.html` `#tenant-view`, `#detail-surface`; `command.css` affordance/tenant styles on shared tokens.
- **Guards:** `tests/ui/test_command_routing_r200.py` 21 items — RED 14 failed / 8 passed on the opening tree → GREEN 21/21 at 2744fde0. Real-browser request-set proof (`evidence/r200/browser_probe_2744fde0.json` + 3 screenshots): tenant issues zero `/v1/admin/*` / `/v1/agent/*` requests; admin set identical to R185.
- **Invariants held:** `core/ apps/ infrastructure/` diff EMPTY (`round_r200` 0/0); `command.js` `/v1/` 12 + one `fetch(`; `ui/app/app.js` 22 / 4; `ui/admin/app.js` 73; freeze `--check` MATCHES (46); every `/v1/admin/*` and `/v1/agent/*` gate untouched — the server 403 remains the only permission authority.
- **Gates:** gate of record fresh clone `c57d4c88` PASS 3972/0/0/64 + gateway 194; ratchet 3951 → 3972 (+21); head re-gates `e434f76d`, `02314a63`; PR #58 merged by merge commit → `main ebe5e549`; post-merge fresh clone `ebe5e549` PASS 3972/0/0/64 + gateway 194; regression 18 roots 3139 passed / 13 skipped / 0 failed (`evidence/r200/regression_ebe5e549.txt`).
- **Incidents:** ≥8 sandbox resets during the round erased unpushed work and gate outputs (redone from the pushed checkpoint each time); the first merge call for PR #58 was interrupted — API re-check showed the PR still open before the merge was re-issued. Recorded in the ledger (rows 2, 5–7).
- **NOT claimed:** Production Ready (D-03 / N-9 OPERATOR-OWNED-OPEN); template picker in Command (D4 deferred); `templates/{ref}` detail; `project_id` carry-through; shared agent panel; root `/` redirect; any register §C flip. Each needs its own `APPROVE`.
