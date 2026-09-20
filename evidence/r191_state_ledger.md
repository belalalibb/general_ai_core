# R191 state ledger — General Agent + Templates + App Factory slice

| # | Step | Fact | Status | Commit |
|---|---|---|---|---|
| 1 | Baseline | `HEAD = origin/main = dc1c62de`, clean, open PRs 0; records reconciled (R190 pointer / DEC-02 / HANDOFF §7 / ledger row 13 / freeze update). No disagreement. | VERIFIED | — |
| 2 | Discovery | Strategy layer + executor + `/v1/execute` template/skills seams exist (R188); Skill registry/resolver exist; router same-model fallback + per-binding signals exist (R188/R190); provider-native agent contracts exist; GitHub transport exists (no tree read). ABSENT: template abstraction/registry/overrides, agent-capability registry, General Agent, App Factory. | VERIFIED | — |
| 3 | Declaration | manifest `round_r191` (ceiling 6), R191-DEC-01, `R191_HANDOFF.md`, this ledger — BEFORE any production commit. | DONE | (this) |
| 4 | R191-A production | `core/contracts/agent_template.py` (7fb66017), `core/execution/templates.py` (330273bf), `core/agent/general.py` (145d90b2) — 3/6 of ceiling used. New modules only; no frozen contract touched. | DONE | 145d90b2 |
| 5 | R191-A RED→GREEN | RED at 23133338 (`ModuleNotFoundError` ×2, `evidence/r191/red_templates_agent.txt`); GREEN at bb408f77 19/19 (`evidence/r191/green_templates_agent.txt`). Two TEST defects fixed at bb408f77 (`SkillStatus.DRAFT` never existed → `IMPORTED`; test_n requirement made satisfiable by the R188 World model). No production change was needed. | VERIFIED | fbd5c42e |
| 6 | Budget | manifest `round_r191.changes_used = 3` (log rows R191-A ×3, loc from `git diff --numstat dc1c62de HEAD -- core apps`). | DONE | (this) |
| 7 | R191-B RED | `tests/agent/test_r191_app_factory_slice.py` at 9f8e2c4c: `ModuleNotFoundError: apps.agent_dev.project_inspector` (`evidence/r191/red_app_factory.txt`). | VERIFIED | 9f8e2c4c |
| 8 | R191-B production | `core/agent/app_factory.py` (5910ef31), `apps/agent_dev/project_inspector.py` (b41877e2) — 5/6 of ceiling used. App Factory = capability + DATA template; generation deferred. | DONE | b41877e2 |
| 9 | R191-B GREEN | 11/11 (`evidence/r191/green_app_factory.txt`); one TEST fix (model policy expressed as an explicit `TemplateOverride`, asserted via `overrides_applied`). | VERIFIED | 98268974 |
| 10 | Static | mypy strict clean on all 5 new modules; ruff check/format clean on touched files; `contract_freeze_derive.py --check` → MATCHES (new modules only; no served route added — P-R191-01 stays a PROPOSAL). | VERIFIED | e0306dd9 |
| 11 | Budget | manifest `round_r191.changes_used = 5` (rows R191-A ×3, R191-B ×2). R191-C headroom: NOT used (see row 12). | DONE | (this) |
| 12 | Regression | 2721 passed / 13 skipped / 0 failed across the standing suite set (incl. R188/R189/R190 suites) at 56d1fc61 (`evidence/r191/regression_56d1fc61.txt`). Freeze `--check` MATCHES. R191-C headroom deliberately unused (freeze record §3.4). | VERIFIED | (this) |
