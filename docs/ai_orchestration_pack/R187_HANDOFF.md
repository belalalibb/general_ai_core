# R187 HANDOFF — CS1 findings F-CS1-01 / F-CS1-02 in the Command Center (authoritative)

Round: **R187**, declared by operator plan item 2 (2026-09-16): "UI round → fix F-CS1-01 + F-CS1-02". Opened from `main` **d6f45198** (post PR #31). Decision record: `60_DECISION_LOG.md` R187-DEC-01. Budget: `green_manifest.json` `change_budget.round_r187` ceiling 0.

## 1. Authority
`evidence/cs1_state_ledger.md` rows 5/7; `evidence/cs1/CS1_CURRENT_STATE_CERTIFICATION.md` §C; `evidence/cs1/browser/01_desktop_1440.png` (178 px left bias), `browser_e2e.json` (reload → login view).

## 2. Boundaries
Thawed: `ui/app/command/{index.html,command.js,command.css}`, new `tests/ui/test_command_center_fix_r187.py`. Frozen: `core/ apps/ infrastructure/`, `core/tools/gate.py`, `ui/admin/`, `ui/app/{app.js,index.html,styles.css}`, served contracts. Guard frame `ui_command_static_check` unchanged (`/v1/` ≤ 12; one `fetch(`; no timers; no fabricated states).

## 3. Fix design (before code)
- **F-CS1-01** — token in `sessionStorage` (one key; never `localStorage`); boot: stored token → `GET /v1/auth/session` → 200 & `is_admin` → Command Center, else discard → login view; logout clears. No new route/contract.
- **F-CS1-02** — `.center` single centred column; `.detail` does not reserve width when hidden, Core stays at viewport centre at every width and does not jump when the detail panel opens.

## 4. Proof
RED first: `tests/ui/test_command_center_fix_r187.py` (static + browser). Then GREEN; all `tests/ui` guards green; fresh-clone gate; D-6 ratchet at gate of record; gateway 194.

## 5. Stop conditions
Any need to touch a counted root, a served contract, or the guard-frame ceilings → STOP and report.

## 6. Operator-only after R187
Item 4 (credential rotation: AssemblyAI key F-CS1-04 + GitHub token) is operator-owned. Items 5–7 (Provider / Learning closure, Contract Freeze, App Factory) need their own declarations/contracts after R187 closes.
