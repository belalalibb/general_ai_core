# R191 state ledger — General Agent + Templates + App Factory slice

| # | Step | Fact | Status | Commit |
|---|---|---|---|---|
| 1 | Baseline | `HEAD = origin/main = dc1c62de`, clean, open PRs 0; records reconciled (R190 pointer / DEC-02 / HANDOFF §7 / ledger row 13 / freeze update). No disagreement. | VERIFIED | — |
| 2 | Discovery | Strategy layer + executor + `/v1/execute` template/skills seams exist (R188); Skill registry/resolver exist; router same-model fallback + per-binding signals exist (R188/R190); provider-native agent contracts exist; GitHub transport exists (no tree read). ABSENT: template abstraction/registry/overrides, agent-capability registry, General Agent, App Factory. | VERIFIED | — |
| 3 | Declaration | manifest `round_r191` (ceiling 6), R191-DEC-01, `R191_HANDOFF.md`, this ledger — BEFORE any production commit. | DONE | (this) |
