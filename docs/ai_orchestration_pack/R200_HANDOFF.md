# R200 HANDOFF — Command capability → surface routing + non-admin Command posture (UI-only)

Status: **OPEN** (R200-DEC-01). Base: `main f6991e16` (post-R199 closure). Branch `genspark_ai_developer_r200`. Ceiling 0.

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
