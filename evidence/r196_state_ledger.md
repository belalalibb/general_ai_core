# R196 state ledger

| # | When | State | Evidence |
|---|------|-------|----------|
| 1 | 2026-09-20 | R196 proposal delivered read-only (findings F1–F10); operator "APPROVE R196 with confirmation" (D1–D5) | chat; R196-DEC-01 |
| 2 | 2026-09-20 | Declaration committed BEFORE code: R196-DEC-01, manifest `round_r196` (ceiling 4, used 0), handoff, this ledger; shape change (2 additive routes) DECLARED | this commit |
| 3 | 2026-09-20 | RED recorded at bd94ad04 (collection error: `TemplateListEntry` missing) | `evidence/r196/red_r196.txt` |
| 4 | 2026-09-20 | Production 4/4 at 95ad78fd (+ ruff 0564e85b); GREEN 16/16; mypy strict 4 files clean; ruff clean; baseline re-derived `--write` (44 → 46 routes, modules identical) → `--check` MATCHES; guards + catalog/shelf suites 58/58 (pins 23 → 24, `/v1/templates` → `templates.listing`) | `evidence/r196/green_r196.txt`, `CONTRACT_FREEZE_RECORD_R196_UPDATE.md` |
| 5 | 2026-09-20 | Records: CAPABILITY_MAP `templates.listing`; ADMIN_UI coverage note; STATE_OF_TRUTH T1 (8f084086). Regression 18 roots at 8f084086: 3123 passed / 14 skipped-xfail / 0 failed (EXIT=0) | `evidence/r196/regression_8f084086.txt` |
| 6 | 2026-09-20 | **Gate of record** fresh clone `63f7b876`: `RESULT: PASS` pytest 3888/0/0/64 (≥ 3872), gateway 194; freeze `--check` MATCHES inside the clone (re-derived baseline). D-6 ratchet `min_passed` 3872 → 3888; `ceiling_history` gate entry | `evidence/r196/{gate_head_63f7b876.txt, gateway_head_63f7b876.txt}` |
