# R190 state ledger — P-R189-01 logical Model identity

| # | Step | Fact | Status | Commit |
|---|---|---|---|---|
| 1 | Baseline | `origin/main = c9730d9d` (R189 closed; open PRs 0; clean). Records reconciled: PROJECT_EXECUTION_STATE R189 pointer, R189-DEC-02, CONTRACT_FREEZE_RECORD §4/§6.10 — all say P-R189-01 RECOMMENDED / not implemented. No disagreement found. | VERIFIED | — |
| 2 | Discovery | Refusal site `core/providers/onboarding.py:270-312`; registry/router/fallback/signals already operate over shared Models (`bindings_for_model`, `model_id` filters); hydration `apps/composition/provider_onboarding.py:255-264` re-registers Models per binding (would break on restart with a shared Model); onboarding admin-only; Models platform-global (no tenant field). | VERIFIED | — |
| 3 | Declaration | manifest `round_r190` (ceiling 2, justified), R190-DEC-01, `R190_HANDOFF.md`, this ledger — BEFORE any production commit. | DONE | (this) |
