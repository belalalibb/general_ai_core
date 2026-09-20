# R193 state ledger — production composition of the governed REST-Git path (P-R192-04)

| # | Step | Fact | Status | Commit |
|---|---|---|---|---|
| 1 | Baseline | `HEAD = origin/main = 7983590a`, clean, open PRs 0; R192 pointer / HANDOFF §7 / ledger row 9 / freeze update read; no newer record. | VERIFIED | — |
| 2 | Verification | C2 `JsonBindingStore`, C3 `RemoteTrustRegistry`, C7 `create_app(dev_bindings=)`, C8 `GitHubRestTransport`/`GitToolset`, R192 `BoundProjectInspector` all exist and are uncomposed; `build_engineering` and `repo_map` (run-context tenant) are the composition precedents. | VERIFIED | — |
| 3 | Declaration | manifest `round_r193` (ceiling 3), R193-DEC-01, `R193_HANDOFF.md`, this ledger — BEFORE any production commit. | DONE | (this) |
| 4 | RED | `tests/composition/test_r193_dev_bindings_composition.py` (11 tests) fails with `ModuleNotFoundError: apps.composition.dev_bindings` — `evidence/r193/red_dev_bindings.txt`. | VERIFIED | d7fa658f, 984c626c |
| 5 | Production 3/3 | `apps/composition/dev_bindings.py` (NEW), `apps/composition/agent.py`, `apps/composition/runtime.py`; Core untouched; `changes_used = 3 = ceiling`. Fix within file 1: `project.inspect` runs the sync R192 inspector via `asyncio.to_thread`. | DONE | b148f517, 3ba48552, c3eddc22, bb646e6d |
| 6 | Deliberate pin flip | IMPL-024 pin `test_default_runtime_profile_does_not_compose_the_dev_seam` now asserts the env-gated wiring (default profile inert); `docs/r169/CAPABILITY_MAP.md` `dev.publish_modes` row and `docs/r172/BACKEND_STATE_OF_TRUTH.md` §E C2/C3/C7/C8 updated. | DONE | 821cbbe6 |
| 7 | GREEN | 22 passed (11 R193 + 11 R172 pins) — `evidence/r193/green_dev_bindings.txt`; ruff format/check clean on touched files; mypy strict: `Success: no issues found in 3 source files`. | VERIFIED | 5e2bf448 |
| 8 | Budget | manifest `round_r193.log` 3 rows (R193-A), `changes_used: 3`; guards `tests/verification tests/engineering/test_budget_rounds_r177.py`. | DONE | (this) |
| 9 | Gate of record | fresh clone of 9ae8b6b6 (`/home/user/gates/g_9ae8b6b6`, `env -i`): `RESULT: PASS`, pytest passed=3837 failed=0 errors=0 skipped=64; gateway 194 passed; regression 16 roots 2962 passed / 14 skipped / 0 failed; freeze `--check` MATCHES; D-6 ratchet `min_passed` 3826 → 3837 (+11 = the R193 test file). | VERIFIED | (this) |
| 10 | Merge + post-merge gate | PR #44 (mergeable clean, protection 404, 0 statuses/check-runs/workflows) merged by merge commit → `main 04952844`; fresh clone of 04952844 `RESULT: PASS` 3837/0/0/64, gateway 194 (`evidence/r193/gate_merge_04952844.txt`, `gateway_merge_04952844.txt`). R193-DEC-02, HANDOFF §7, R193_POINTER, manifest `last_measured` written in the records-only closure branch. | VERIFIED | (this) |
