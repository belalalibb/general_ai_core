# QEVION R167-A — §7 Stage 1: live closure of the 13 categories

Mode: OFFLINE-ENVELOPE (`evidence/credentials_manifest.md`). The only credential present
in this session is `GSK_API_KEY` → provider `genspark_llm`. `GROQ_API_KEY` is absent. The
platform was started for real (`python3 -m apps.main`, `/v1/admin/system` →
`provider_keys:["genspark_llm"]`) and all 13 categories were re-run with the unchanged
runner `evidence/tasks/run_live.py` into a new directory
`evidence/tasks/r167a_stage1/` [CAPTURED]. The R167-QEVION logs in `evidence/tasks/` were
not touched (the runner gained only an `OUT` env override, 2 lines, so that it never
overwrites a committed transcript).

## 7.1 Re-run result vs `degraded_before.md`

| # | Category | Before (Groq) | After (genspark_llm) | Cause before | Cause after | Reconciliation |
|---|----------|---------------|----------------------|--------------|-------------|----------------|
| 01 | simple | FAIL | FAIL | `propose_failed` — `invalid_credential/organization_restricted` | `invalid_proposal` — `action must be one of ['final','tool_call'], got 'invalid_json'` | **different cause, same outcome**; see finding LC-1 |
| 02 | multi_step | FAIL | FAIL | same | same as 01 | same |
| 03 | multi_tool | FAIL | FAIL | same | same | same |
| 04 | artifact | FAIL | FAIL | same | same | same |
| 05 | external_provider | FAIL | FAIL | same | same | same |
| 06 | provider_failure_fallback | FAIL | FAIL | one provider bound | one provider bound (different one) | unchanged: no failover candidate exists |
| 07 | tool_failure_recovery | FAIL | FAIL | same | same | same |
| 08 | authz_denial | PASS (invariant) | PASS (invariant) | stop `propose_failed` | stop `invalid_proposal` | file untouched in both; still PASS-by-invariant, not by completion |
| 09 | verification_failure | PASS (invariant) | PASS (invariant) | idem | idem | no fabricated line in both |
| 10 | partial_success | FAIL | FAIL | same | same | same |
| 11 | admin_op | PASS | PASS | n/a | n/a | identical |
| 12 | external_api_consumption | FAIL | FAIL | execute step | execute step | tools listing/record/trace/list still 200 |
| 13 | capability_registration | PASS | PASS | n/a | n/a | identical |

Totals unchanged: 4 PASS / 9 FAIL [CAPTURED]. Zero categories moved. The **cause** of the
9 failures changed from an account-indicting provider error to an in-band refusal, which
exposes a new defect:

### Finding LC-1 — HTTP 200 refusal is booked as a successful model call [CAPTURED]

Child reasoning execution `f1a345c5-…` (trace via `GET /v1/agent/executions/{id}/trace`):
`status:"succeeded"`, one attempt `provider_key:"genspark_llm", model_key:"claude-opus-4-5",
succeeded:true, latency_ms:360`, `ledger: {status:"settled", units_reserved:1, units_settled:1}`.
Its `result.content` is verbatim: *"Free-plan credits can't be used with the Genspark API /
LLM proxy. Please visit https://www.genspark.ai/pricing …"*. The parent agent run then fails
with `invalid_proposal … got 'invalid_json'` and `/diagnosis` reports
`"execution did not succeed but no provider error was recorded"`, `tier:"undetermined"`.
Tenant usage advanced 19.0 → 20.0 units for one `max_steps=1` run that produced nothing
[MEASURED `/v1/usage` before/after].

Classification against `evidence/provider_contract.md` item 5: the contract has **no
in-band semantic failure detection** ("NOT PRESENT IN CODE"). So this is *not* a
misclassification by the adapter (it received a well-formed 200) — it is an ABSENCE. Impact:
(a) the tenant is billed a task unit for a non-answer; (b) diagnosis cannot attribute the
cause; (c) `PROVIDER_MAX_RETRIES` and failover are never engaged because nothing "failed".
Ledger: `evidence/defect_ledger.md` **D-01**, severity S2 (billable duplicate / wrong
attribution, no data exposure). Fix is NOT shipped this round: it would require a new
concept (semantic response validation) which §16 forbids manufacturing inside a
certification round; handed to R168 with the captured shape
`evidence/failure_shapes/genspark_llm_200_plan_refusal.json`.

## 7.2 Reconcile by cause

| Cause | Categories | Before | After |
|-------|------------|--------|-------|
| Bound provider cannot perform inference (account-side) | 01–07, 10, 12 | Groq `organization_restricted` | genspark free-plan refusal in 200 |
| Only one provider bound → no fallback candidate | 06 | yes | yes |
| Model-independent, real | 08, 09, 11, 13 | PASS | PASS |

## 7.3 Benchmark claim downgrade

`evidence/benchmark.md` "Honest reading" sentence edited: the wording *"parity-or-better by
construction claim"* is withdrawn; every non-measured domain is labelled **UNRANKED —
competitor not executed**. No domain claims LEADING / HIGHLY COMPETITIVE. Executed
head-to-head domains this round: **0**.

## 7.4 Developer transcript split (generic platform vs consumer side)

Source: `evidence/tasks/15_developer_transcript.log` (17 calls, unchanged).

| Generic platform (SHARED NUCLEUS) | Consumer side (IDE-style first consumer) |
|-----------------------------------|------------------------------------------|
| `/v1/admin/system`, `/v1/admin/providers`, `/v1/admin/models` (§1-3) | `/v1/admin/engineering/status` — workspace root, allowed commands (§11) |
| `POST /v1/execute` + record + trace + list (§4-7) | `/v1/admin/engineering/grants`, `/authorizations` — fs.write / cmd.run / git.* acts (§12-14) |
| `GET /v1/agent-tools` (20 tools) (§8) | `AGENT_WORKSPACE_ROOT`, `AGENT_SOURCE_ROOT`, `AGENT_WORKSPACE_COMMANDS` env (composition) |
| direct provider probe + explicit-model/`max_escalation` re-issue (§9-10) | — |
| `/v1/admin/audit`, `/v1/admin/usage` (§15-17) | — |

Consumer-side surface is confined to `apps/api/engineering_admin.py` +
`core/engineering/*`; no IDE concept appears in `core/execution`, `core/routing`,
`core/agent/runtime.py` (`grep -rn -i "\bide\b\|workspace" core/execution core/routing core/agent/runtime.py` → 0
hits) [VERIFIED].

## 7.5 Reliability delta

`evidence/baseline.md` annotated: all baseline numbers are fixture/mock (scripted model,
`tests/agent/world.py`) and measure coordination logic only. Live reliability delta:
**NOT MEASURABLE** this round (0 usable credentials) — recorded as NOT PROBED.

## 7.6 Honesty ratio of prior (R167-QEVION `final_report.md`) claims

| # | Prior claim | Survives? | Why |
|---|-------------|-----------|-----|
| 1 | Baseline 8/11 → 11/11 [MEASURED] | yes, **re-tagged** | numbers hold; now explicitly fixture-only |
| 2 | 2683→2687 passed / 64 skipped [VERIFIED] | yes | re-run this round (see report §1) |
| 3 | Persistence/resume is the one seam where a competitor is clearly ahead | yes | still documented-vs-absent |
| 4 | "Everything else at parity-or-better by construction claim" | **no — withdrawn** | no head-to-head executed |
| 5 | Change 1 bounded recovery; Change 2 silent default; Change 3 org_restricted→invalid_credential | yes | pin tests present and green |
| 6 | Model-dependent categories NOT VERIFIED live | yes | still true, with a second provider |
| 7 | Model-independent 08/09/11/13 PASS live | yes, **qualified** | 08/09 are PASS-by-invariant only |
| 8 | "Failover cannot rescue a single restricted account; harness rows prove mechanism" | yes | mechanism fixture-proven only |
| 9 | Security: no secrets in repo; logs redact bearer | yes | re-checked this round |
| 10 | Per-run call ceiling formula [INFERRED] | yes | unchanged code |
| 11 | Gate NOT emitted, condition (f) | yes | correct |
| 12 | "Fast honest failure is RECOVER-boundary behaviour" | **partially** | true for Groq; for genspark the failure is neither fast-attributed nor honest to the ledger (LC-1) |

Honesty ratio: **10 / 12 survive intact**, 1 withdrawn, 1 partially (0.83 intact; 0.92
counting the partial). Two claims were re-tagged without changing their truth value.
