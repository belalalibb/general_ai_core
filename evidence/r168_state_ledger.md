# R168 — State Ledger

One line per checkpoint. Format: `| UTC | item | intended change | HEAD at start | status |`.
Read this file first after any interruption (§0). An item is complete only when
`evidence/r168/<item-id>/` holds fail_first.txt, after_fix.txt, notes.md, gate_before_after.txt
and the commit hash resolves.

## §4 Baseline (captured at HEAD 2f1a0e9, before any edit) — MEASURED

| Metric | Measured | Previously recorded | Delta |
|---|---|---|---|
| `git rev-parse HEAD` | `2f1a0e9fb63cb014d7240299d686463d40b5208e` | — | — |
| `check_repo.sh` | RESULT: PASS, exit 0 (full output in `green_manifest.baseline.json`) | PASS | none |
| pytest `tests/ -o addopts="" -q -rs` | **2706 passed, 64 skipped, 0 failed, 0 errors**, exit 0 | 2706 / 64 | none |
| skipped by missing env | DATABASE_URL 41 · GSK_API_KEY 8 · GROQ_API_KEY 6 · VAULT_ADDR/VAULT_TOKEN 4 · OBJECT_STORAGE_* 4 · GW_GROQ_API_KEY 1 (= 64; every nodeid+reason in `green_manifest.baseline.json`) | — | all 64 reason-known |
| N0 = `grep -c '/v1/' ui/admin/app.js` | **73** (permanent ceiling) | — | — |
| `wc -c` app.js / index.html / styles.css | 79351 / 32385 / 16392 | 79351 / 32385 / 16392 | none |
| `final_docs_v3/*.md` count | 20 | 20 | none |
| `wc -c check_repo.sh` | 3343 | 3343 | none |
| mypy scope | `pyproject.toml [tool.mypy] packages=["core"]`, strict | — | — |
| secret scan (widened dry run) | 5 hits, all test sentinels (see manifest `secret_scan.exceptions`) | — | — |
| `.env` git-tracked | none | — | — |
| playwright / selenium | not installed → live suite NOT EVALUATED: missing dependency | — | — |

Baseline file: `engineering/verification/green_manifest.baseline.json`.

## Checkpoints

| UTC | item | intended change | HEAD at start | status |
|---|---|---|---|---|
| 2026-09-04 | R168 start (after sandbox reset wiped uncommitted §6 draft) | §0 VERIFY: HEAD 2f1a0e9 clean, no R168 artifacts; RESTORE env; re-measure §4 | 2f1a0e9 | done |
| 2026-09-04 | V-01 verification track | green_manifest.json/.md, baseline json, conflict ledger, check_repo.sh slices+counters+widened secret scan+NOT EVALUATED+budget guard, tests/verification guards (AH), tests/ui static check, decisions entry | 2f1a0e9 | in progress |
| 2026-09-04 | V-01 (restart #5) | sandbox reset again wiped local-only checkpoint commits (fresh clone at 44052ef) AND the /mnt/aidrive tar backup (mount empty after reset). GitHub credentials unavailable → push impossible. New persistence: `git bundle create` of main uploaded to blob storage after every commit; restore with `git fetch <bundle> main`. Re-implement V-01 | 44052ef | in progress |
| 2026-09-04 | V-01 (restart #6) | sandbox reset wiped local commits + deps again; restored main from the off-sandbox git bundle (d24284d) via `git fetch <bundle> main && git reset --hard FETCH_HEAD`; env reinstalled. Remaining V-01: tests/ui static check, C-03, green_manifest.md, hermetic run, last_measured/state | d24284d | in progress |
| 2026-09-04 | V-01 (restart #7) | reset wiped uncommitted green_manifest.md + hermetic evidence + manifest/state edits; restored main from bundle 8aae4c7; re-create and commit each artifact immediately | 8aae4c7 | in progress |
| 2026-09-04 | V-01 verification track | DONE: check_repo.sh manifest-driven (slices/counters/floor, secret scan 5/5 exceptions, NOT EVALUATED 2, budget guard), tests/verification 18 guards, tests/ui static check 14 (+fail-first), green_manifest.md. Hermetic run PASS: passed=2738 failed=0 errors=0 skipped=64 (evidence/r168/V-01/check_repo_hermetic.txt); floor raised 2706→2738; STATE_REVISION R168. Remaining V-01 sub-items tracked separately: §6.5 /v1/ degraded close, §6.6 test tenant, §6.7 mypy widen. | see commit | done |
| 2026-09-04 | §6.7 mypy widen (restart #8) | reset wiped un-bundled commit ead44028; restored 82e721ef; re-applying §6.7 and bundling immediately | 82e721ef | in progress |
| 2026-09-04 | §6.7 mypy apps/api + apps/composition | DONE: measured 0 errors (api 22 files, composition 15, admin_agent 7); packages widened to core+apps.api+apps.composition; gate mypy → 0 errors / 181 files; guard test_mypy_gate_scope_never_shrinks; IMPL-006; OPERATIONS §10 stubs naming (boto3-stubs[s3]). admin_agent → R169. Evidence evidence/r168/V-02/ | see commit | done |
| 2026-09-04 | §6.6 isolated test tenant | checkpoint (restart #8 re-entry): INV-6 conflict between mandate §6.6 rewire and frozen caller-scoped derivation in apps/api/exercise.py; resolving via conflict ledger C-04 + isolation proof tests | a8e0a126 | in progress |
| 2026-09-04 | §6.6 isolated test tenant | DONE (APPLIED-STRICTER, C-04): no production rewire; tests/api/test_exercise_tenant_isolation.py proves caller-only billing, bystander untouched, foreign lookup 404-equivalent, finite probe budget (4 passed; negative control fails as expected). Evidence evidence/r168/V-03/ | see commit | done |
| 2026-09-04 | D-07 (restart #9) | reset wiped uncommitted D-07 work; restored 39e89322; redoing D-07 with WIP commits + bundles | 39e89322 | in progress |
| 2026-09-04 | D-07 (restart #10) | reset wiped un-bundled middleware WIP; restored 7e1706e9; re-applying middleware + fixture opt-ins, bundling after every commit | 7e1706e9 | in progress |
| 2026-09-04 | D-07/D-10 (restart #11) | reset wiped un-uploaded eb101d0e; restored 56f6c9d8 (production intact); redoing D-10 test + evidence + docs + manifest | 56f6c9d8 | in progress |
| 2026-09-04 | D-07 + D-10 | DONE: DEV_DEMO_PRINCIPAL opt-in (closed default), PUBLIC_PATHS, admission middleware before body validation (runtime.py +24/-1, app.py +50/-1 = round A 2/5); D-07 79 paths 0 leaks; D-10 59 admin ops 403/401 before 422; OPERATIONS §0/§3; IMPL-007; defect ledger FIXED rows; hermetic gate run next | see commit | done (pending gate run) |
| 2026-09-04 | GATE after D-07/D-10 | hermetic check_repo.sh RESULT: PASS — pytest 2752/0/0/64 (floor 2738→2752), mypy clean, ruff clean, import-linter, secret scan 5/5, budget round_a=2/5, NOT EVALUATED 2 (evidence/r168/D-07/check_repo_after.txt) | see commit | done |
| 2026-09-04 | D-08 project_id (restart #12) | reset wiped un-uploaded d158aed3; restored b8fa4fed; checkpoint: FAIL FIRST — foreign/unknown/non-UUID project_id on /v1/execute must be the 404 byte-identical to GET /v1/projects/{unknown} | b8fa4fed | in progress |
| 2026-09-04 | D-08 project_id | DONE: /v1/execute resolves project_id in caller tenant before any work; foreign/unknown/malformed ⇒ byte-identical unknown-project 404 (app.py +22/-1, workspaces.py +8/-1 ⇒ round A 4/5); 4 tests; api+composition 602 passed; IMPL-008; defect ledger FIXED; hermetic gate run next | see commit | done (pending gate run) |
| 2026-09-04 | GATE after D-08 | hermetic check_repo.sh RESULT: PASS — pytest 2756/0/0/64 (floor 2752→2756), budget round_a=4/5, NOT EVALUATED 2 (evidence/r168/D-08/check_repo_after.txt) | see commit | done |
| 2026-09-04 | D-01 refusal (restart #13) | restored d32fba5e; checkpoint: FAIL FIRST — HTTP-200 plan refusal (LC-1 shape) must be a FAILED provider call, route-indicting (quota_exceeded), 0 units, failover-permitting; adapter-level (providers/, budget-free) | d32fba5e | in progress |
| 2026-09-04 | D-01 refusal | DONE: adapter-level refusal detection (zero usage AND marker ⇒ quota_exceeded/retryable=False/plan_refusal_200); 6 tests pass; certification row corrected; C-05; IMPL-009; defect ledger FIXED; budget round A 4/5 unchanged (providers/ only); hermetic gate run next | see commit | done (pending gate run) |
| 2026-09-04 | GATE after D-01 (restart #14) | reset wiped un-uploaded a52f6461; restored 0ef7820a; live GSK-gated tests skip (credential unavailable) on the D-01 refusal only; hermetic check_repo.sh RESULT: PASS — pytest 2762/0/0/64 (floor 2756→2762); credentialed run PASS 2768/0/0/58; budget round_a=4/5; NOT EVALUATED 2 (evidence/r168/D-01/check_repo_after.txt) | see commit | done |
| 2026-09-04 | V-04 §6.5 /v1/ drift | CLOSED DEGRADED: app.js 73 / N0 73 (ratio 1.00); no reduction (INV-2, no UI defect); guards in force; next step R169 route table; evidence/r168/V-04/ | see commit | done |
| 2026-09-04 | D-03/D-04 (restart #17) | restored e87c70b2 (restart #16 FAIL FIRST commit lost: bundle failed on `-q`, then reset); checkpoint: FAIL FIRST — hermetic two-account failover on ONE pooled provider: RoutingRequest.credential_policy carried; ResourceSelector.complete completes selected+fallback with account_id (one candidate per eligible account); ExecutionService resolves per-account credential_ref (SecretManagerPort refs) and emits PROVIDER_ACCOUNT_USED; plan ≤4 changes (contracts/routing.py, routing/resources.py, execution/service.py, composition/runtime.py) | e87c70b2 | in progress |
