# R175 — FINAL BACKEND CERTIFICATION / REAL-PROVIDER HARD GATE

Governed by R168 (REV 3). Additive only. Baseline 45e0eb7 (R174 close). Verdict computed from `evidence/r175_findings_ledger.md`; process history in `evidence/r175_state_ledger.md`.

## 1. Verdict

**BACKEND CERTIFIED — HERMETIC + DURABLE + REAL-PROVIDER GATE SATISFIED.**

(Superseded verdict, kept for the record: at close of the first pass on 2026-09-05 the real-provider gate was NOT SATISFIED because both supplied Groq keys were organisation-restricted upstream. On 2026-09-06 a key from an unrestricted organisation was supplied; the same unchanged driver promoted run3. Code HEAD is unchanged since 733c188.)

| track | result |
|---|---|
| Hermetic governance gate (`apps.cli check`) | **PASS, EXIT 0** — was FAIL at baseline |
| pytest hermetic | 3156 passed / 0 failed / 0 errors / 58 skipped |
| pytest durable (real Postgres 17 + pgvector @0018) | 3197 passed / 0 failed / 17 skipped / 1 xfailed |
| mypy --strict · ruff · import-linter · secret scan · budgets | all green |
| gateway-service suite | 194 / 0 |
| Real-provider hard gate (7 Groq live tests) | **PROMOTED (run3)** — probes HTTP 200 ×2, 7 passed / 0 skipped / 0 failed; runs 0–2 remain RAW |
| core/ lines changed in R175 | **0** |

## 2. What the real-provider gate showed

Rule (operator-set): the 7 Groq-gated tests are raw material until a real upstream call succeeds in the same run; promotion requires exactly 7 passed / 0 skipped / 0 failed and an OK probe for every key.

Four runs, all recorded, one promoted:

| run | keys | probe (`GET /openai/v1/models`) | pytest | disposition |
|---|---|---|---|---|
| run0 | none | skipped | 7 skipped | NOT_PROMOTED (proves the gate refuses skips) |
| run1 | `GROQ_API_KEY`, `GW_GROQ_API_KEY` (process env only) | HTTP 400 `organization_restricted` on both | 6 F / 1 P / 0 S | NOT_PROMOTED |
| run2 (after F-R175-02) | same | same | 6 F / 1 P / 0 S | NOT_PROMOTED |
| **run3** (2026-09-06, code identical to 733c188) | one key from an unrestricted organisation, used for both env names (process env only); two further keys supplied were not used | **HTTP 200 ×2** — 14 models, `allam-2-7b` present | **7 P / 0 S / 0 F / 0 E** in 3.83 s | **PROMOTED → EVIDENCE** (`evidence/r175/03_real_provider_gate/verdict.json`) |

Runs 1–2: Groq answered *"Organization has been restricted…"* for both keys on the free model-listing endpoint, before any generation was attempted — an upstream account state; 0 paid calls. Run3: a key from a different organisation passed the same probe and the seven tests passed through the same driver, tests and adapters — proving the earlier failure was the account, not the code. Run3 paid calls: ≤4. Nothing was reclassified, no test was relaxed, no skip became a pass; the driver's promotion rule (OK probe for every key AND exactly 7/0/0/0) was applied mechanically.

What run3 actually proves, per module: `test_groq_live` — credential validates active, provider health healthy, discovery returns real models, one real generation, key absent from all artifacts; `test_groq_live_e2e` — `POST /v1/execute` returns `succeeded` with non-empty content through the real adapter and settles exactly 1.0 task unit; `test_gateway_groq_live_e2e` — both entry points (platform HTTP `/v1/execute` and the direct orchestrator path) succeed through the real gateway Layer-1 resolution to real Groq, usage ledger SETTLED at 1.0 each, and neither the live key, the route token, the upstream host nor the internal slug crosses into any response.

Key custody held: keys entered only as process environment variables, were never written to disk, and every artifact was scrubbed (literal + `gsk_` shape) and asserted clean before being written. `grep gsk_` across all evidence = 0 hits.

## 3. Findings and repairs

| id | sev | summary | status |
|---|---|---|---|
| F-R175-01 | BLOCKER/S2 | 10× ruff E501 left by R174 turned the only green gate red | FIXED d89de3e (whitespace-only) |
| F-R175-02 | S2 | gateway Groq adapter classified `organization_restricted` as `bad_request` (failover forbidden) while the platform adapter says `invalid_credential` (failover allowed) — same upstream reply, two categories by path. **Found by the live run**, not by any hermetic test | FIXED 64776a8, gateway-service only, 2 pinning tests including AST parity with the platform's code set |
| F-R175-03 | S1 external | Groq organisation restricted for both keys supplied on 2026-09-05 | **CLOSED 2026-09-06** — external cause removed (unrestricted key, run3 promoted); zero code change |
| F-R175-04 | S3 ops | `check_repo.sh` uses bare `python3`; outside the venv it fails with 86 collection errors | OPEN — recorded |

Repair protocol followed for both fixes: fail-first (both new tests fail on the pre-fix adapter — stash check), minimal diff, pinned, full gates re-run after.

## 4. Change budget

`core/` 0 lines · `apps/` 0 · `infrastructure/` 0 · `providers/` 0. Changes: `gateway-service/providers/groq/adapter.py` +18, `gateway-service/providers/assemblyai/_upstream.py` +5/−1 (wrap), tests +57, two R174 probe scripts (wraps). Budget ceilings: within (`check_repo_after.txt` line 30).

## 5. Not evaluated (verbatim from the gate; never green, never FAIL)

- live-suite: browser automation against the real server and real UI — missing dependency
- real two-account provider round-trip (D-03 Class-A failover against live providers) — credential unavailable

Plus the credential-only skips in the durable profile: Vault ×4, S3 ×4, GSK plan-exhausted ×2 remain skipped. The Groq ×7 are no longer skips — they are the promoted run3 (they ran in the dedicated gate run, not inside the durable profile run, which is why the durable numbers above are unchanged).

## 6. Does this authorise UI work?

**Backend prerequisite: proven. UI work: not started, not modified, not scheduled by this round.**

The operator asked whether the *primary backend capability the UI depends on* is demonstrated. Read from repository reality (not from any plan document — there is no `U-16`/`U-17` identifier anywhere in the tracked tree; the only UI-phase artefacts are `ui/app`, `ui/admin` and `docs/benchmarks/ui-phase-live`):

- The end-user surface `ui/app/app.js` binds to `/v1/auth/*`, `/v1/execute`, `/v1/executions`, `/v1/models`, `/v1/projects`, `/v1/workspaces`, `/v1/usage`. Its primary capability is **`POST /v1/execute` producing a real model answer with usage settled**. That exact path is what L-03 proves end-to-end against a real provider (`test_groq_live_e2e`, `test_gateway_groq_live_e2e`), with the key never in the response.
- The admin surface `ui/admin/app.js` binds only to `/v1/admin/*` and `/v1/agent-tools`; every one of those routes is covered by the hermetic + durable suites (3197 passed, 0 failed) and by the earlier committed live browser proof (`docs/benchmarks/ui-phase-live/evidence/results.json`, 32/32), which was not re-run here.

So: **the primary backend capability for the UI is proven** — hermetic, durable, and now through a real provider. What remains NOT evaluated is unchanged from §5: browser automation against the live UI (dependency absent in this sandbox) and the two-account Class-A failover round-trip (a second working key exists but no R175 contract item covers exercising it; running it would be new scope). Per the operator's standing instruction, this round does not open UI work; any UI phase is a separate contract.

To reproduce the gate: `GROQ_API_KEY=… GW_GROQ_API_KEY=… python3 evidence/r175/03_real_provider_gate/run_gate.py` (venv active). Promotion is automatic and only on 7/0/0 with OK probes; ≤4 paid calls.

## 7. Operational note

Sandbox resets #12, #13, #14 hit during R175 (venv, Postgres, credentials wiped each time). No committed work was lost: every commit was bundled off-sandbox before the next step (bundle ids in the state ledger). GitHub push was unavailable after reset #14; the bundle is recorded in the state ledger. Resets #15 and #16 followed; all commits are on `origin/main`. The run3 gate was executed after reset #16 on a rebuilt venv, code unchanged.
