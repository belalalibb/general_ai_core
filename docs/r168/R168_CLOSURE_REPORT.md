# R168 CLOSURE REPORT — QEVION CORE (`belalalibb/general_ai_core`, `main`)

Date: 2026-09-04 · Mandate: R168 CLOSURE MANDATE REV 5 · Baseline: `2f1a0e9` (R167-A close) → R168 baseline commit `44052ef` · Report head: see `evidence/r168_state_ledger.md` final row.

Single verifier: `engineering/verification/check_repo.sh` (manifest-driven; `engineering/verification/green_manifest.json`). Canonical run is HERMETIC (`GSK_API_KEY`, `GENSPARK_TOKEN`, `GSK_TOKEN` unset — C-03). Every claim below cites a file under `evidence/r168/`.

## 1. Defect table (D-01 … D-11)

| Id | Area | Sev | R167-A status | R168 status | Fix location (LOC) | Evidence |
|---|---|---|---|---|---|---|
| D-01 | Execution settlement (200 plan-refusal booked SUCCEEDED) | S2 | OPEN | **FIXED** — adapter detects zero-usage + refusal marker ⇒ `quota_exceeded` / `plan_refusal_200`, run FAILED, 0 units, failover-permitting | `providers/real/genspark_llm/adapter.py` (budget-free); settlement path per INV-2 exception | `evidence/r168/D-01/` |
| D-02 | Groq normaliser (`detail`-only 400 model-not-allowed → `bad_request`) | S2 | OPEN | **FIXED** — `_is_model_not_allowed` ⇒ `model_unavailable` / `model_not_allowed` (candidate-indicting ⇒ failover); detail never crosses; other `detail`-only 400s stay `bad_request` (IMPL-012) | `providers/real/groq/adapter.py` +32/−0 (budget-free) | `evidence/r168/D-02/` |
| D-03 | Multi-account routing (2 credentials, same provider) | S3 | OPEN | **FIXED (contract level)** — `ResourceSelector.complete()` account-complete routes; hermetic 2-account failover proven. Composition wiring: OUT OF SCOPE (R168): budget — scheduled for R169 | `core/routing/resources.py` +60/−0; `core/execution/service.py` +66/−3 | `evidence/r168/D-03-04/` |
| D-04 | Audit / attribution (`PROVIDER_ACCOUNT_USED`) | S3 | OPEN | **FIXED (contract level)** — `RoutingRequest.credential_policy`; `PROVIDER_ACCOUNT_USED` per attempt for pooled candidates | `core/contracts/routing.py` +5/−1 (+ D-03 files) | `evidence/r168/D-03-04/` |
| D-05 | Credential containment (responses) | — | CLOSED — HELD | unchanged (HELD [MEASURED]) | — | R167-A |
| D-06 | Credential containment (logs) | — | CLOSED — HELD | unchanged (HELD [MEASURED]) | — | R167-A |
| D-07 | Auth lifecycle (anonymous → demo principal) | S2 | OPEN | **FIXED** — `DEV_DEMO_PRINCIPAL` opt-in (closed by default); `PUBLIC_PATHS`; admission middleware; 79 paths, 0 leaks | `apps/composition/runtime.py` +24/−1; `apps/api/app.py` (shared with D-10) | `evidence/r168/D-07/` |
| D-08 | Authz under composition (`project_id` ignored) | S3 | OPEN | **FIXED** — reference resolved in caller's tenant before any work; foreign == unknown == malformed ⇒ ONE 404 (byte-identical) | `apps/api/app.py` +22/−1; `apps/api/workspaces.py` +8/−1 | `evidence/r168/D-08/` |
| D-09 | Admin control-plane audit | S2 | FIXED (R167-A) | unchanged | — | `evidence/fixes/D-09.md` |
| D-10 | Admin gate ordering (422 before 403) | S3 | OPEN | **FIXED** — admission before body validation on all 59 admin operations | `apps/api/app.py` +50/−1 | `evidence/r168/D-10/` |
| D-11 | Audit coverage (denials unaudited) | S3 | OPEN | **FIXED (partial)** — `PERMISSION_DENIED` at `/v1/admin/*` non-admin 403; `CROSS_TENANT_ACCESS_DENIED` at unresolved `project_id` 404; actor's tenant; tenant admin reads via `GET /v1/admin/audit`. NOT FIXED: `CREDENTIAL_CREATED/REVOKED` (no route exists); `PROVIDER_ACCOUNT_USED` at composition (R169); platform-wide audit read: OUT OF SCOPE (R168): design — scheduled for R169 | `apps/api/app.py` +37/−0 | `evidence/r168/D-11/` |

Every FIXED item has FAIL FIRST → FIX → PASS artifacts (`fail_first.txt`, `after_fix.txt`, `notes.md`, `gate_before_after.txt`, `check_repo_after.txt`).

## 2. Change budget (counted under `core/`, `apps/`, `infrastructure/` only)

**Round A: 4/5.** **Round B: 4/5.** `changes_used == len(log)` in `green_manifest.json` (guarded by `tests/verification`).

| Round | Item | File | LOC |
|---|---|---|---|
| A | D-07 | `apps/composition/runtime.py` | +24/−1 |
| A | D-10 | `apps/api/app.py` | +50/−1 |
| A | D-08 | `apps/api/app.py` | +22/−1 |
| A | D-08 | `apps/api/workspaces.py` | +8/−1 |
| B | D-04 | `core/contracts/routing.py` | +5/−1 |
| B | D-03 | `core/routing/resources.py` | +60/−0 |
| B | D-03 (+D-04) | `core/execution/service.py` | +66/−3 |
| B | D-11 | `apps/api/app.py` | +37/−0 |

Budget-free production edits (`providers/`): D-01 `providers/real/genspark_llm/adapter.py`; D-02 `providers/real/groq/adapter.py` +32/−0. Tests are budget-free.

## 3. pytest before / after

| | passed | failed | errors | skipped |
|---|---|---|---|---|
| Baseline (2f1a0e9 / 44052ef) | 2706 | 0 | 0 | 64 |
| Final hermetic gate (after D-02) | **2777** | 0 | 0 | **64** |

Floor raised monotonically 2706 → 2762 → 2769 → 2773 → 2777 (`pytest.gate.min_passed`); `max_skipped` 64 never raised.

**64 skips classified** (every nodeid + reason recorded in `green_manifest.baseline.json`; all environment-gated, none silent):

| Missing environment | count |
|---|---|
| `DATABASE_URL` (live Postgres, manual only — 41 §49) | 41 |
| `GSK_API_KEY` (live genspark_llm) | 8 |
| `GROQ_API_KEY` (live Groq) | 6 |
| `OBJECT_STORAGE_*` (live object store) | 4 |
| `VAULT_ADDR` / `VAULT_TOKEN` (live Vault) | 4 |
| `GW_GROQ_API_KEY` (live gateway) | 1 |
| **total** | **64** |

Credentialed runs (sandbox key present) are recorded separately and are NOT the gate: e.g. `evidence/r168/D-03-04/check_repo_after_credentialed.txt` PASS 2775/0/0/58 — the 6 un-skipped GSK tests pass or skip with the closed-set reason "credential unavailable" on the D-01 refusal only.

## 4. `/v1/` route-literal drift (§6.5)

`ui/admin/app.js`: **73 / N0 = 73 → ratio 1.00**. CLOSED DEGRADED (V-04): no drift up, no reduction — reduction would require rewriting a served asset with no defect against it (INV-2). Guards: raw count ≤ ceiling ≤ N0; ceiling may only move down. Next step recorded for R169 (single route table). `evidence/r168/V-04/`.

## 5. Full verifier output (final hermetic run, `evidence/r168/D-02/check_repo_after.txt`)

```
PASS: exists: engineering/adr/ADR-TEMPLATE.md
PASS: exists: engineering/adr/README.md
PASS: exists: engineering/gates/GATE-TEMPLATE.md
PASS: exists: engineering/decisions/README.md
PASS: exists: engineering/verification/README.md
PASS: exists: engineering/verification/green_manifest.json
PASS: exists: docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
PASS: no legacy state files (D10/D11)
PASS: v3 pack complete: 20 documents
PASS: state field present: STATE_REVISION
PASS: state field present: RESUME_TOKEN
PASS: state field present: CURRENT_TASK
PASS: state field present: NEXT_TASK
PASS: state field present: PHASE_2_STATUS
pytest slice api: passed=462 failed=0 errors=0 skipped=0
pytest slice contract-providers: passed=633 failed=0 errors=0 skipped=15
pytest slice execution-composition-infra: passed=380 failed=0 errors=0 skipped=49
pytest slice admin-security-evaluation: passed=417 failed=0 errors=0 skipped=0
pytest slice rest: passed=885 failed=0 errors=0 skipped=0
pytest coverage: slices ran = 5; passed=2777 failed=0 errors=0 skipped=64
PASS: pytest: passed=2777 (>= 2773) failed=0 errors=0 skipped=64 (<= 64)
PASS: mypy --strict (scope: pyproject.toml [tool.mypy].packages): clean
PASS: ruff: clean
PASS: import-linter: architecture boundaries kept (40 §6.2)
PASS: secret scan clean (declared exceptions: 5/5)
PASS: no .env tracked
PASS: change budget within ceilings: round_a=4/5; round_b=4/5
NOT EVALUATED: live-suite: browser automation against the real server and real UI — missing dependency
NOT EVALUATED: real two-account provider round-trip (D-03 Class-A failover against live providers) — credential unavailable
SUMMARY: not_evaluated=2 (counted separately; never green, never FAIL)
RESULT: PASS (all repo governance checks)
EXIT=0
```
(The floor printed is the pre-run value 2773; it was raised to 2777 in the same commit that recorded this output.)

## 6. NOT EVALUATED (verbatim; never green, never FAIL)

- `live-suite: browser automation against the real server and real UI — missing dependency`
- `real two-account provider round-trip (D-03 Class-A failover against live providers) — credential unavailable`
- Per item, also NOT EVALUATED: D-01 live success on a non-exhausted key (sandbox key plan-exhausted); D-02 live proxy round-trip of a disallowed model (credential unavailable).

## 7. OUT OF SCOPE (verbatim)

- D-03/D-04 composition wiring (`apps/composition/runtime.py` account pool + `account_credentials`): **OUT OF SCOPE (R168): budget — scheduled for R169**.
- D-11 platform-wide audit read across tenants (port forbids cross-tenant reads by design; no platform-admin identity): **OUT OF SCOPE (R168): design — scheduled for R169**.
- D-11 `CREDENTIAL_CREATED/REVOKED` emitters: no credential lifecycle route exists to emit from — not fixable without a new surface (R169).
- §6.5 `/v1/` literal reduction: CLOSED DEGRADED (see §4).

## 8. mypy

Scope (gate): `pyproject.toml [tool.mypy].packages` = `core`, `apps.api`, `apps.composition` → **0 errors / 181 files** (V-02, widened this round from `core` only). Measured but out of gate until R169 (§6.7): `apps.admin_agent` 0 errors / 7 files. Per-fix spot checks: `mypy --strict apps/api/app.py`, `providers/real/groq/adapter.py` clean.

## 9. Secret scan

Widened patterns (AWS key, PEM header, Slack, GitHub PAT, `sk-…`), all text globs; **5/5 declared per-line exceptions**, all in tests proving rejection/scrubbing: `tests/admin_agent/test_aa2_admin_agent.py:533`, `tests/memory/test_memory_stores.py:346`, `:347`, `tests/security/test_log_secret_leakage.py:38`, `:74`. No `.env` tracked. Secrets only via `SecretManagerPort`; no credential value appears in any evidence file.

## 10. Severity totals

R167-A close (mandate baseline): `S1: 0/0 · S2: 4 found (D-01, D-02, D-07, D-09) / 1 fixed (D-09) · S3: 5 found (D-03, D-04, D-08, D-10, D-11) / 0 fixed · S4: 0`.

R168 close: **S1: 0 found / 0 fixed · S2: 4 found / 4 fixed (D-09 in R167-A; D-01, D-02, D-07 in R168) · S3: 5 found / 5 fixed in R168 (D-03, D-04 contract level; D-08; D-10; D-11 partial) · S4: 0.**

## 11. Verification track (§6)

V-01 manifest-driven verifier + guards (`tests/verification` 19, `tests/ui` static check); V-02 mypy scope widened (0 errors); V-03 §6.6 isolated test tenant (APPLIED-STRICTER, C-04); V-04 §6.5 CLOSED DEGRADED. Conflict ledger: `evidence/r168_conflict_ledger.md` (C-01…C-04). Decision log: IMPL-010 (D-03/D-04), IMPL-011 (D-11), IMPL-012 (D-02).

## 12. Operational note

23 sandbox resets during R168 wiped local-only commits repeatedly; `git push` was unavailable. Continuity was kept by off-sandbox git bundles after every commit (restore chain recorded in `evidence/r168_state_ledger.md`). No history was rewritten; every commit in the chain is present on `main`.

---

This is a PARTIAL CLOSURE within the verified envelope. Items marked NOT EVALUATED or OUT OF SCOPE are open. The backend is not closed to further repair.
