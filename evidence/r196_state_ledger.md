# R196 state ledger

| # | When | State | Evidence |
|---|------|-------|----------|
| 1 | 2026-09-20 | R196 proposal delivered read-only (findings F1–F10); operator "APPROVE R196 with confirmation" (D1–D5) | chat; R196-DEC-01 |
| 2 | 2026-09-20 | Declaration committed BEFORE code: R196-DEC-01, manifest `round_r196` (ceiling 4, used 0), handoff, this ledger; shape change (2 additive routes) DECLARED | this commit |
| 3 | 2026-09-20 | RED recorded at bd94ad04 (collection error: `TemplateListEntry` missing) | `evidence/r196/red_r196.txt` |
| 4 | 2026-09-20 | Production 4/4 at 95ad78fd (+ ruff 0564e85b); GREEN 16/16; mypy strict 4 files clean; ruff clean; baseline re-derived `--write` (44 → 46 routes, modules identical) → `--check` MATCHES; guards + catalog/shelf suites 58/58 (pins 23 → 24, `/v1/templates` → `templates.listing`) | `evidence/r196/green_r196.txt`, `CONTRACT_FREEZE_RECORD_R196_UPDATE.md` |
