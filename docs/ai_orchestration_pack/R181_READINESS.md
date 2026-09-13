# R181 READINESS — analysis (backend-closure pre-round, BEFORE the UI phase)

Round: R181 on `genspark_ai_developer_r181` (base `main` ed61f7e6 = MERGE COMMIT of PR #19). Everything below is derived
from committed evidence; nothing is claimed that a test or a measurement did not show. UI phase NOT started; `ui/` zero-diff.

## Part 1 — What R181 did and how it was proven

| Mandate | Outcome | Proof |
|---|---|---|
| R180 handoff item #1 — gate on the merge commit | canonical `check_repo.sh` on a fresh clone of ed61f7e6 (`env -i`): **3624 / 0 / 0 / 64**; gateway **194** | `evidence/r181/gate_merge_ed61f7e6.txt`, `gateway_merge_ed61f7e6.txt` |
| Carry-over inventory (read-only, before any edit) | DEFINED+ACTIONABLE: Q6/F-R179-06, F-R175-04, manifest `deferred_out_of_gate` (mypy `apps.admin_agent`). RECORD-ONLY: D-11 residue, in-process engineering tickets. UNDEFINED: Q7, Provider slice | `evidence/r181_state_ledger.md` row "Carry-over inventory" |
| **Q6 (F-R179-06) — durable usage** | option (b): migration **0022** drops ONLY `fk_usage_ledger_execution_id_executions`; `execution_id` stays NOT NULL + UNIQUE; metadata mirror; runtime binds the already-composed `DurableUsageAccounting` on the `DATABASE_URL` profile (one-name flip). In-memory profile byte-identical | tests-first `tests/infrastructure/test_usage_ledger_key_q6_r181.py` (6, RED at 04b29fcc → GREEN at 7a41caff); 5 conscious pin updates; live: **P4 `used` 6.0 → 8.0 across a real SIGKILL** (`evidence/r181/durability_measured_7a41caff.json`; R179 baseline reset 6.0 → 2.0), r179 live **5 passed** (deploy truth head **0022**, forward/backward via the real tool, two-step downgrade then populated-0020 refusal), r178 live **59 passed**, FK transcript `evidence/r181/q6_live_fk_verification_7a41caff.txt` (orphan insert OK · duplicate refused · NULL refused · downgrade fails closed on orphan rows · FK restored when empty) |
| **F-R175-04** — `check_repo.sh` bare `python3` footgun | step **1b interpreter guard**: fails closed with the venv install path when `python3` lacks pytest/mypy/ruff (no misleading 86 collection errors). Ops-only, outside the counted roots; `BUDGET=$(mf '` snippet intact | `tests/engineering/test_check_repo_interpreter_guard_r181.py` (2: static placement + shim-interpreter fail-closed run) |
| **mypy `apps.admin_agent` (`deferred_out_of_gate`)** | ADMITTED to the `--strict` gate: pyproject `packages += apps.admin_agent`; manifest `gate_scope_packages` + disposition CLOSED; guard-test exact-set pin consciously grown. Tree stays frozen (type-checking reads, never edits) | `mypy` → **Success: no issues found in 215 source files** (was 208) |
| Q7 / Provider slice | **UNDEFINED** — no repository definition anywhere (only the R180-DEC-02 echo). Recorded, not invented | `R181-DEC-01`, `evidence/r181_findings_ledger.md`, state ledger |
| Docs | OPERATIONS §13 now states usage durable on the `DATABASE_URL` profile (measured); R179_HANDOFF Q6 row + F-R179-06 / F-R179-04 rows closed; R180_HANDOFF item 3 status; `60_DECISION_LOG.md` += R181-DEC-01 (append-only, +9 lines) | this file, `R181_HANDOFF.md` |

### diff == log table (production files under core/ apps/ infrastructure/, base ed61f7e6)

| file | git diff (+/−) | manifest `round_r181_backend_closure.log` entry | item |
|---|---|---|---|
| infrastructure/db/migrations/versions/0022_usage_ledger_key.py | +45/−0 (new) | yes | Q6 |
| infrastructure/db/tables.py | +5/−1 | yes | Q6 |
| apps/composition/runtime.py | +6/−12 | yes | Q6 |
| **total** | **3 files** | **3 entries = changes_used 3 ≤ ceiling 3** (declared BEFORE the production commit, ae766602) | — |

Frozen this round (zero diff vs ed61f7e6): `ui/`, `apps/admin_agent/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`,
`final_docs_v3` except the append-only `60_DECISION_LOG.md` (+9). `pyproject.toml` (mypy scope) and `engineering/verification/check_repo.sh`
are outside the counted roots and outside the frozen list; both changes are pinned by tests.

## Part 2 — Findings

| id | severity | disposition |
|---|---|---|
| F-R181-01 parity regex missed the formatter-wrapped `op.drop_constraint(` in 0022 | S3 (test-only) | FIXED test-only (`tests/db/test_schema_contract_parity.py`); budget unaffected |
| F-R179-06 (carried) | S2 | **CLOSED** (Q6, 0022, R181-DEC-01) |
| F-R179-04 usage half (carried) | S2 | **CLOSED** with F-R179-06 |
| F-R175-04 (carried) | S3 ops | **CLOSED** (step 1b) |

## Part 3 — Vision audit deltas

| Vision element | was (R180 close) | now |
|---|---|---|
| Durable usage (billing/quota across restart) | INERT — decision-gated (F-R179-06 → Q6) | **WIRED on the durable profile, measured** (P4 6.0 → 8.0 across SIGKILL) |
| Gate typing scope | core + apps.api + apps.composition (208 files) | + apps.admin_agent (**215 files**, strict, 0 errors) |
| Gate honesty outside the venv | misleading collection-error FAIL | fail-closed with the install path |
| Q7 / Provider slice | DEFERRED (echo only) | **UNDEFINED, formally recorded** — an operator definition is the precondition for any work |

## Part 4 — Backend-ready status

**BACKEND-READY: YES** for the scope the repository defines. Every DEFINED and ACTIONABLE backend/core carry-over is closed with tests and
(where the item is durability) with a live measurement on real PostgreSQL 17.11. Nothing remains in the backend queue except items that have
no repository definition (Q7, Provider slice) or that are feature scope by inspection (D-11 residue, engineering tickets table). Final gate
numbers on the PR head are in `R181_HANDOFF.md` §C and `evidence/r181/`.
