# Green manifest — human view (R168 §6.3)

Authority: `engineering/verification/check_repo.sh` reads `green_manifest.json`; every other
consumer (this page, tests, reports) reads and never writes. When this page and the JSON
disagree, the JSON is right and this page is a defect.

Baseline (read-only): `green_manifest.baseline.json` — captured at `2f1a0e9` (R167-A close),
pytest 2706 passed / 64 skipped, UI `/v1/` count N0 = 73, 20 docs in `final_docs_v3`,
`check_repo.sh` 3343 bytes.

## Definition of green

`check_repo.sh` exits 0 only when every row below is PASS. `NOT EVALUATED` rows are printed,
counted separately, and are neither green nor FAIL.

| # | Check (script section) | Rule | Source in manifest |
|---|---|---|---|
| 1 | Governance structure | required files exist, manifest is valid JSON | — |
| 2 | Single mutable state file | no legacy state files (D10/D11) | — |
| 3 | Docs integrity | `final_docs_v3` = 20 `.md`; 5 state fields present | — |
| 4a | pytest slices + floor gate | per slice: counters parsed from the summary line; totals: `failed == 0`, `errors == 0`, `skipped <= max_skipped`, `passed >= min_passed`; a slice with no summary line (timeout/crash) counts as an error | `pytest.slices`, `pytest.gate` |
| 4b | Static gates | `mypy --strict` (scope: `pyproject.toml [tool.mypy].packages`), `ruff check .`, `lint-imports` clean | `non_test_items` |
| 5 | Secret scan | widened globs; every hit must be a declared `file:line` exception; exception count `<= ceiling` (ceiling never rises); no `.env*` tracked (`.env.example` allowed) | `secret_scan` |
| 6 | Change budget | `changes_used <= ceiling` per round; `changes_used == len(log)`; logged files under `core/ apps/ infrastructure/`; logged items scheduled for that round | `change_budget` |
| 7 | NOT EVALUATED | one line per item; reason from the closed set; count `<= not_evaluated_count_ceiling` | `not_evaluated` |

## pytest slices (§6.1)

Each slice runs as
`timeout <ceiling> python3 -m pytest <selection> -o addopts="" -q -p no:cacheprovider -W ignore::DeprecationWarning`
(`-o addopts=""` because `pyproject.toml` already sets `-q`; a second `-q` hides the summary line — conflict ledger C-02).

| Slice | Selection | Ceiling |
|---|---|---|
| api | `tests/api` | 300 s |
| contract-providers | `tests/contract tests/providers` | 300 s |
| execution-composition-infra | `tests/execution tests/composition tests/infrastructure` | 300 s |
| admin-security-evaluation | `tests/admin tests/admin_agent tests/security tests/evaluation tests/certification` | 300 s |
| rest | every remaining `tests/<pkg>` (incl. `tests/ui`, `tests/verification`) | 300 s |

Guard (AH): `tests/verification/test_green_manifest_guards.py::test_slices_partition_tests_directory`
fails if a `tests/<pkg>` is uncovered or covered twice.

Gate: `failed 0 · errors 0 · skipped <= 64 · passed >= min_passed` (floor raised only after a
measured hermetic run, never lowered).

### Canonical measurement is hermetic (C-03)

15 tests are gated on provider credentials in the shell (`GSK_API_KEY` 8, `GROQ_API_KEY` 6,
`GW_GROQ_API_KEY` 1). `pytest.last_measured` is therefore taken from

```
env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY bash engineering/verification/check_repo.sh
```

A credentialed run may exceed the floor; it never defines it.

### Classification of the 64 baseline skips

| Reason (closed set) | Trigger | Count |
|---|---|---|
| environment unavailable | `DATABASE_URL` not set (live Postgres) | 41 |
| credential unavailable | `GSK_API_KEY` not set | 8 |
| credential unavailable | `GROQ_API_KEY` not set | 6 |
| environment unavailable | `VAULT_ADDR`/`VAULT_TOKEN` not set | 4 |
| environment unavailable | `OBJECT_STORAGE_*` not set (live S3) | 4 |
| credential unavailable | `GW_GROQ_API_KEY` not set | 1 |
| | **total** | **64** |

Full list with test ids: `green_manifest.baseline.json → pytest.skipped_tests`.

## Secret scan (§6.2)

Patterns: `AKIA[0-9A-Z]{16}` · PEM private-key headers (RSA/EC/OPENSSH) · `xox[bap]-…` · `ghp_…{36}` · `sk-…{40,}`.
Globs: `*.md *.sh *.yml *.yaml *.json *.txt *.py *.js *.html *.css *.env*`. The manifest itself
is in scope, so exception reasons are worded to not self-match.

| File:line | Reason |
|---|---|
| `tests/admin_agent/test_aa2_admin_agent.py:533` | AWS documented example access key used as a scrub sentinel |
| `tests/memory/test_memory_stores.py:346` | literal PEM header used to prove secret-like values are rejected |
| `tests/memory/test_memory_stores.py:347` | AWS documented example access key used to prove rejection |
| `tests/security/test_log_secret_leakage.py:38` | AWS documented example access key used to prove log scrubbing |
| `tests/security/test_log_secret_leakage.py:74` | literal PEM header used to prove log scrubbing |

Exceptions 5 / ceiling 5. Guards: planted `ghp_…` → FAIL; tracked `.env` → FAIL; 6 exceptions → FAIL;
each declared exception must still be a real hit (stale exceptions fail).

## UI static check (§6.5)

`tests/ui/test_admin_static_check.py` reads `ui/admin/{app.js,index.html,styles.css}` as text:
route literals `api('/v1/…')` must match a served OpenAPI path (`${x}` ↔ `{param}` wildcards);
raw `/v1/` count in `app.js` `<= v1_count_ceiling_N0` (73, may only move down); single `fetch(`
inside `async function api(`; no provider branching; no quoted `CAPABILITY_IDS`; no schemas/DDL;
`index.html`/`styles.css` wire no `/v1/` routes. Exception ceiling 0. Fail-first evidence:
`evidence/r168/V-01/ui_static_fail_first.txt`.

## NOT EVALUATED (§6.4) — closed reason set: missing dependency · credential unavailable · environment unavailable

| Item | Reason |
|---|---|
| live-suite: browser automation against the real server and real UI | missing dependency |
| real two-account provider round-trip (D-03 Class-A failover against live providers) | credential unavailable |

Count 2 / ceiling 2.

## Deferred out of gate

`mypy --strict apps/admin_agent` — OUT OF SCOPE (R168): deferred to R169 (mandate §6.7). Not a
gate line because "deferred" is outside the closed reason set (conflict ledger C-01).

## Change budget (§2)

Counts production code under `core/ apps/ infrastructure/` only.

| Round | Items | Ceiling | Used |
|---|---|---|---|
| A | D-01, D-07, D-08, D-10 | 5 | `change_budget.round_a.changes_used` |
| B | D-03, D-04, D-11, D-02 (if budget) | 5 | `change_budget.round_b.changes_used` |

Every logged entry carries `item`, `file`, `loc`; `changes_used` must equal `len(log)`.

## Last measured

`pytest.last_measured` in the JSON (`passed`, `failed`, `errors`, `skipped`, `at_head`, `hermetic`,
`command`, `evidence`). Evidence of the run: `evidence/r168/V-01/check_repo_hermetic.txt`.
