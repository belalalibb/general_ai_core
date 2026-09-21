# R197 HANDOFF — UI closure: Workbench template picker + R195 admin actions by discovery

Status: OPEN (declaration committed; RED next). Base: `main b8f2f706`. Branch: `genspark_ai_developer_r197`.

## 1. Authority
Operator: "APPROVE R197 (optionally with rulings on D1–D5)" — recommended rulings stand (R197-DEC-01): D1 thaw `ui/app/` only; D2 guard declared first (`ui_workbench_static_check`, `/v1/` ceiling null → measured at first GREEN); D3 no bespoke admin forms (discovery form is the closure); D4 ref-based picker, `execution_strategy {mode:"template", template_id: ref}`; D5 `round_r197` ceiling 0.

## 2. Allowed / frozen
- MAY change: `ui/app/app.js`, `ui/app/index.html`, `ui/app/styles.css`; new `tests/ui/test_workbench_template_picker_r197.py`, `tests/ui/test_r197_admin_actions_discovered.py`; manifest + records.
- FROZEN: `core/ apps/ infrastructure/` (0); `ui/admin/*` (73 = N0); `ui/app/command/*` (12); contracts; freeze baseline (46 routes).

## 3. Measured before code (b8f2f706)
`ui/app/app.js` `/v1/` = 21, `fetch(` = 4 (api, 2× DELETE, 1× SSE reader). `ui/admin/app.js` = 73. `command.js` = 12. TOOLS area active ⇒ the three R195 actions are already offered by the console.

## 4. Steps
1. Declaration (this commit). 2. RED. 3. Implement picker. 4. Verify (tests/ui, pd2, 18 roots, DOM probe, freeze --check, ruff/mypy on touched tests). 5. Set `v1_count_ceiling_app_js` to the measured GREEN count (expected 22). 6. Gate (fresh clone). 7. PR (merge commit). 8. Post-merge gate. 9. Records-only closure PR. 10. STOP.

## 5. Resume
After a reset: `git fetch`; `git checkout -B genspark_ai_developer_r197 origin/genspark_ai_developer_r197`; read the last row of `evidence/r197_state_ledger.md`; redo only the missing step.
