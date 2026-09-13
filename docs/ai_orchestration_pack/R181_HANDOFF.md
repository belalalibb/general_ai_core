# R181 HANDOFF — instructions

Branch `genspark_ai_developer_r181`; base `main` ed61f7e6. Read `R181_READINESS.md` for analysis; this file only says what to do next.
R181 is the BACKEND-CLOSURE pre-round. The UI phase has NOT started and must not start from this file's items without an operator instruction.

## A. Ordered items

| # | item | where | do |
|---|---|---|---|
| 1 | Merge R181 PR (#20) | GitHub | merge COMMIT (no squash) once the exit conditions in §C hold; re-run the canonical gate on the merge commit and record it under `evidence/r182/` (or the next round's evidence dir) |
| 2 | Rotate the in-session GitHub token | GitHub settings | operator action after merge (no credential lands in the workspace) |
| 3 | Deploy note for operators of the durable profile | `docs/OPERATIONS.md` §13 | run `alembic upgrade head` (0021 → 0022) BEFORE starting the new binary; the new runtime binds the durable usage ledger and on a 0021 database every `/v1/execute` would fail 500 exactly as F-R179-06 measured. Downgrade 0022 → 0021 fails closed while ledger rows without an executions row exist (by design) |
| 4 | Q7, Provider slice | operator | UNDEFINED in the repository. Provide a concrete definition (contract, acceptance, files) before any round picks them up; nothing speculative was created |
| 5 | UI phase | operator | begins only on explicit instruction, on a new branch, with its own declared budget and thaw list |

## B. Resume mechanism (unchanged)
Remote branch head is the checkpoint; rebuild `.venv` (`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`) and, for live suites,
`.venv/pg_root` per the header of `tests_live/r179/run_local_postgres.sh`. Several sandbox resets during R181 lost only uncommitted work —
publish the branch FIRST, commit after every landed item. Live recipes: `bash tests_live/r179/run_local_postgres.sh`,
`bash tests_live/r178/run_local_postgres.sh`, and the FK transcript header in `evidence/r181/q6_live_fk_verification_7a41caff.txt`.

## C. Exit conditions (verified on the PR head; numbers in `evidence/r181/`)
- canonical gate (fresh clone, `env -i`): PASS; pytest 5 slices with 0 failed / 0 errors; mypy `--strict` 215 files; ruff; import-linter; secret scan ≤ 5/5 exceptions; budgets incl. `round_r181_backend_closure` 3/3; not_evaluated = 2
- gateway suite: 194
- live (PostgreSQL 17.11 + pgvector): r179 5 passed (P4 usage survives SIGKILL; deploy truth head 0022), r178 59 passed, FK transcript
- diff == log (3 production files = 3 log entries); frozen trees zero-diff except append-only `60_DECISION_LOG.md`
- findings dispositioned (`evidence/r181_findings_ledger.md`); decision `R181-DEC-01` appended
