# R175 — FINAL BACKEND CERTIFICATION / REAL-PROVIDER HARD GATE

Governed by R168 (REV 3). Additive only. Baseline 45e0eb7 (R174 close). Verdict computed from `evidence/r175_findings_ledger.md`; process history in `evidence/r175_state_ledger.md`.

## 1. Verdict

**BACKEND CERTIFIED — HERMETIC + DURABLE. REAL-PROVIDER GATE: NOT SATISFIED (external).**

| track | result |
|---|---|
| Hermetic governance gate (`apps.cli check`) | **PASS, EXIT 0** — was FAIL at baseline |
| pytest hermetic | 3156 passed / 0 failed / 0 errors / 58 skipped |
| pytest durable (real Postgres 17 + pgvector @0018) | 3197 passed / 0 failed / 17 skipped / 1 xfailed |
| mypy --strict · ruff · import-linter · secret scan · budgets | all green |
| gateway-service suite | 194 / 0 |
| Real-provider hard gate (7 Groq live tests) | **NOT PROMOTED** — 0 of 3 runs qualified |
| core/ lines changed in R175 | **0** |

## 2. What the real-provider gate showed

Rule (operator-set): the 7 Groq-gated tests are raw material until a real upstream call succeeds in the same run; promotion requires exactly 7 passed / 0 skipped / 0 failed and an OK probe for every key.

Three runs, all recorded, none promoted:

| run | keys | probe (`GET /openai/v1/models`) | pytest | disposition |
|---|---|---|---|---|
| run0 | none | skipped | 7 skipped | NOT_PROMOTED (proves the gate refuses skips) |
| run1 | `GROQ_API_KEY`, `GW_GROQ_API_KEY` (process env only) | HTTP 400 `organization_restricted` on both | 6 F / 1 P / 0 S | NOT_PROMOTED |
| run2 (after F-R175-02) | same | same | 6 F / 1 P / 0 S | NOT_PROMOTED |

Groq answers *"Organization has been restricted. Please reach out to support if you believe this was in error."* for both keys on the free model-listing endpoint, before any generation is attempted. This is an upstream account state; 0 paid calls were made. Nothing was reclassified, no test was relaxed, no skip became a pass.

Key custody held: keys entered only as process environment variables, were never written to disk, and every artifact was scrubbed (literal + `gsk_` shape) and asserted clean before being written. `grep gsk_` across all evidence = 0 hits.

## 3. Findings and repairs

| id | sev | summary | status |
|---|---|---|---|
| F-R175-01 | BLOCKER/S2 | 10× ruff E501 left by R174 turned the only green gate red | FIXED d89de3e (whitespace-only) |
| F-R175-02 | S2 | gateway Groq adapter classified `organization_restricted` as `bad_request` (failover forbidden) while the platform adapter says `invalid_credential` (failover allowed) — same upstream reply, two categories by path. **Found by the live run**, not by any hermetic test | FIXED 64776a8, gateway-service only, 2 pinning tests including AST parity with the platform's code set |
| F-R175-03 | S1 external | Groq organisation restricted for both supplied keys | OPEN — not a code defect; needs a working account |
| F-R175-04 | S3 ops | `check_repo.sh` uses bare `python3`; outside the venv it fails with 86 collection errors | OPEN — recorded |

Repair protocol followed for both fixes: fail-first (both new tests fail on the pre-fix adapter — stash check), minimal diff, pinned, full gates re-run after.

## 4. Change budget

`core/` 0 lines · `apps/` 0 · `infrastructure/` 0 · `providers/` 0. Changes: `gateway-service/providers/groq/adapter.py` +18, `gateway-service/providers/assemblyai/_upstream.py` +3/−3 (wrap), tests +57, two R174 probe scripts (wraps). Budget ceilings: within (`check_repo_after.txt` line 30).

## 5. Not evaluated (verbatim from the gate; never green, never FAIL)

- live-suite: browser automation against the real server and real UI — missing dependency
- real two-account provider round-trip (D-03 Class-A failover against live providers) — credential unavailable

Plus the 17 credential-only skips in the durable profile (Groq ×7, Vault ×4, S3 ×4, GSK plan-exhausted ×2).

## 6. Does this authorise UI work?

**No, not on its own.** The operator's condition was explicit: a Groq success alone is not a UI go-ahead, and here Groq did not even succeed. What is certified is that the backend is internally consistent, reproducible from a clean clone, green on every hermetic and durable gate, and that its error classification is now identical across both provider surfaces. What is not certified is any end-to-end path through a live provider in this round.

To close the real-provider gate: supply a Groq key whose organisation is not restricted (or another already-integrated provider with a live-test module) and run
`GROQ_API_KEY=… GW_GROQ_API_KEY=… python3 evidence/r175/03_real_provider_gate/run_gate.py`.
Promotion is automatic and only on 7/0/0 with OK probes; ≤4 paid calls.

## 7. Operational note

Sandbox resets #12, #13, #14 hit during R175 (venv, Postgres, credentials wiped each time). No committed work was lost: every commit was bundled off-sandbox before the next step (bundle ids in the state ledger). GitHub push was unavailable after reset #14; the final bundle for this round is recorded in the state ledger.
