# R175 findings ledger (machine-readable; the verdict is COMPUTED from this file)

Contract: R175 REV 4 — FINAL BACKEND CERTIFICATION / REAL-PROVIDER HARD GATE, governed by R168 (REV 3).
Baseline HEAD: 45e0eb7 (R174 close). Final HEAD: see `docs/r175/R175_FINAL_BACKEND_CERTIFICATION.md`.

## Rules applied

- `EVIDENCE` rows count toward certification. `RAW` rows never do.
- A test that SKIPPED, was BLOCKED, or failed for an upstream reason is never promoted to PASS.
- Only a real, successful upstream call recorded in this round promotes a live test to `EVIDENCE`.
- Findings carry R168 severities (S1 release-blocking … S4 cosmetic). `BLOCKER` marks a gate that is red.

## A. Gates (hermetic, reproducible from a clean clone)

| id | gate | before (45e0eb7) | after (HEAD) | weight | evidence |
|---|---|---|---|---|---|
| G-01 | `python3 -m apps.cli check` overall | **FAIL** (EXIT 1) | **PASS** (EXIT 0) | EVIDENCE | `evidence/r175/00_baseline/check_repo_baseline.txt`, `evidence/r175/05_final_check/check_repo_after.txt` |
| G-02 | pytest hermetic (5 slices) | 3150 / 0 F / 0 E / 64 S | 3156 / 0 F / 0 E / 58 S (floor 3127, ceiling 64) | EVIDENCE | same |
| G-03 | mypy --strict (declared scope) | clean | clean | EVIDENCE | same |
| G-04 | ruff check . | **FAIL** — 10× E501 | clean | EVIDENCE | `evidence/r175/01_ruff_repair/` |
| G-05 | import-linter (40 §6.2 boundaries) | kept | kept | EVIDENCE | same |
| G-06 | secret scan (declared exceptions 5/5) | clean | clean | EVIDENCE | same |
| G-07 | change budget ceilings | within | within | EVIDENCE | same |
| G-08 | gateway-service suite | 192 / 0 | 194 / 0 | EVIDENCE | `evidence/r175/04_f02_repair/gateway_suite_after.txt` |

## B. Durable profile (real Postgres 17 + pgvector, alembic 0018, `DATABASE_URL` set)

| id | item | result | weight | evidence |
|---|---|---|---|---|
| D-01 | full suite with real DB | 3197 passed / 0 failed / 17 skipped / 1 xfailed (before and after repairs) | EVIDENCE | `evidence/r175/02_durable_profile/`, `evidence/r175/05_final_check/pytest_durable_after.txt` |
| D-02 | 41 DB-gated tests (repositories, memory embeddings, pgvector) | all execute and pass; skips 64 → 17 | EVIDENCE | same |
| D-03 | remaining 17 skips | credential-only: Groq ×6, GW Groq ×1, Vault ×4, S3 ×4, GSK plan-exhausted ×2 | RAW (not certified, not failed) | same |

## C. Real-provider hard gate (§3) — the 7 Groq-gated live tests

| id | run | keys | upstream probe | pytest | promoted | weight | evidence |
|---|---|---|---|---|---|---|---|
| L-00 | run0 | none | SKIPPED | 7 skipped | **NO** | RAW | `evidence/r175/03_real_provider_gate/not_promoted/run0_nokey/` |
| L-01 | run1 | 2 keys (env only) | HTTP 400 `organization_restricted` ×2 | 6 failed / 1 passed / 0 skipped | **NO** | RAW | `…/not_promoted/run1_org_restricted/` |
| L-02 | run2 (post F-R175-02) | 2 keys (env only) | HTTP 400 `organization_restricted` ×2 | 6 failed / 1 passed / 0 skipped | **NO** | RAW | `…/not_promoted/run2_post_f02/` |

Attribution: both keys are rejected by Groq with `organization_restricted` ("Organization has been restricted") on the free `/models` probe — an upstream ACCOUNT state, independent of this codebase. Paid calls: 0. The single pass (`test_live_key_never_in_response_artifacts`) is key-hygiene and is real, but the module as a whole is NOT promoted.

**Consequence:** the real-provider hard gate is **NOT SATISFIED** in R175. No live Groq evidence exists for this round. The gate was not lowered, and nothing was reclassified.

## D. Findings

| id | sev | area | status | fix (LOC, files) | core/ lines | evidence |
|---|---|---|---|---|---|---|
| F-R175-01 | BLOCKER (S2) | ruff E501 ×10 left by R174 (b131345, 59077a0, 76e7b87); the only green gate was red | **FIXED** d89de3e — whitespace-only wraps | 0 | `evidence/r175/01_ruff_repair/` |
| F-R175-02 | S2 | gateway `providers/groq/adapter.py` mapped upstream 400 `organization_restricted` → `bad_request` (failover forbidden) while the platform adapter maps the same code → `invalid_credential` (failover allowed): identical upstream reply, two categories depending on path. Surfaced LIVE by run1 (`provider_error_category` = `invalid_credential` via platform, `bad_request` via gateway) | **FIXED** 64776a8 — `_ACCOUNT_INDICTING_CODES` checked before the status table; 2 pinning tests (category + AST parity with the platform set); both fail on the pre-fix adapter | 0 (gateway-service +18, tests +47) | `evidence/r175/04_f02_repair/`, run1 vs run2 reports |
| F-R175-03 | S1 (external) | Groq organisation behind BOTH supplied keys is restricted upstream → the real-provider hard gate cannot be satisfied with these credentials | **OPEN — external**; not fixable in code | — | `…/not_promoted/run1_org_restricted/verdict.json` |
| F-R175-04 | S3 (ops) | `check_repo.sh` invokes bare `python3`; run outside the venv it reports 86 collection errors and FAIL. Not a code defect (documented install path is the venv) but a footgun for certification runs | OPEN — recorded, not changed (out of R175 budget; no core/ impact) | — | first §5 run, superseded by `check_repo_after.txt` |

Severity totals: S1 1 found / 0 fixed (external) · S2 2 found / 2 fixed · S3 1 found / 0 fixed · S4 0.

## E. Computed verdict

```
hermetic_gates_green      = G-01..G-08 all PASS                     -> TRUE
durable_profile_green     = D-01 0 failed                           -> TRUE
real_provider_gate        = any L-* promoted                        -> FALSE
open_blockers_in_code     = findings with status OPEN and sev<=S2 and fixable in code -> 0
```

**VERDICT: BACKEND CERTIFIED — HERMETIC + DURABLE. REAL-PROVIDER GATE: NOT SATISFIED (external, F-R175-03).**

Certification is therefore **PARTIAL**: everything that can be proven without a working provider account is proven and green; the one thing that requires a working account was attempted honestly twice and failed for an upstream reason. This verdict does not authorise UI work on its own — see the human report §6.
