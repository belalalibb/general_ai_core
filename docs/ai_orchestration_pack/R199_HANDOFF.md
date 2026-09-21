# R199 HANDOFF — Unified Shell Foundation (UI-only, layer A)

Status: **CLOSED** (R199-DEC-02). Base: `main f1a9752a` → PR #56 merge commit **`main 8110179e`**; records-only closure PR follows. Gate of record `d8f39043` PASS 3951/0/0/64 + gateway 194; head re-gate `bdb3bb6e` PASS; post-merge `8110179e` PASS 3951/0/0/64 + gateway 194. Ceiling 0, used 0. Ratchet `min_passed` 3929 → 3951.

## 1. Authority (operator, verbatim anchors)
"APPROVE R199. Accept D1–D5 as proposed: D1 = A, D2 = A, D3 = QEVION · Command / QEVION · Workbench / QEVION · Admin, D4 = use only real catalog/API provider-state values, D5 = standard gate ratchet. Execute R199 exactly as proposed. Do not pre-approve R200 or R204. Preserve the unified shared multi-tenant product direction and all existing security, authorization, Core, contract, and provider boundaries. Stop at the next decision gate."

## 2. Allowed / frozen
- MAY change: `ui/app/command/{index.html,command.css}`, `ui/app/{index.html,app.js,styles.css}`, `ui/admin/{index.html,styles.css}`; `tests/ui/test_unified_shell_r199.py` (new, RED first); the three title pins (`tests/ui/test_command_center_topology_r182.py`, `tests/ui/test_command_center_browser_r182.py`, `tests/ui/test_command_center_browser_r185.py`) and `tests/composition/test_admin_console_runtime.py` only if its substring pin fails; `evidence/r199/*`; records.
- FROZEN: `core/ apps/ infrastructure/` (0 files); `ui/app/command/command.js` (12 by identity); `ui/admin/app.js` (73 = N0 by identity); contracts + freeze baseline (46; `--check` MATCHES); `ui_workbench_static_check` 22 / 4.

## 3. Steps
1. Declaration (this file, R199-DEC-01, manifest `round_r199`, pointer) — commit + push BEFORE code.
2. RED: `tests/ui/test_unified_shell_r199.py` fails on the opening tree → `evidence/r199/red.txt`.
3. R199-A brand strings (D3) · R199-B `command.css` shared tokens · R199-C cross-links (`href` without `/v1/`) · R199-D `/app` providers chips + truth strip from `GET /v1/models` only (D4) · R199-E Command sign-in copy names the admin requirement and links to the Workbench (D1 = A).
4. GREEN → `evidence/r199/green.txt`; UI guards (73 / 12 / 22 / fetch 4); freeze `--check`; regression 18 roots; browser proofs (`tests/ui/test_command_center_browser_*`) with the moved title pins.
5. Gate of record on a fresh clone → PR (merge commit) → post-merge gate → records-only closure PR → STOP.

## 4. Not in this round
R200 (Command capability→surface routing; non-admin Command posture), R201 (`project_id` carried into execute), R202 (`templates/{ref}` + App Factory UX), R203 (shared agent panel), R204 (root `/` redirect — composition, ceiling 1). Each needs its own `APPROVE`.

## 5. Outcome (CLOSED)
All five items delivered as declared; 22 new guards; real-browser probe evidence; ceilings 73 / 12 / 22 / fetch 4 unchanged; production tree untouched. Full record: R199-DEC-02, `evidence/r199_state_ledger.md` rows 1–9, `evidence/r199/*`. **Next round requires a fresh `APPROVE <ROUND_ID>`** (R200 Command routing/discovery is the proposed next step; not pre-approved).
