# QEVION R167-A — §5.0.4 Degraded state BEFORE (IMMUTABLE)

Snapshot taken 2026-09-03 from the committed, unedited transcripts
`evidence/tasks/01..13_*.log` (captured at `021124d`, R167-QEVION Phase 6, real HTTP
against `python3 -m apps.main` bound to the only configured provider, `groq`).
This file is written once and never edited; reconciliation lives in `evidence/live_closure.md`.

Source of each row: the `VERDICT:` line of the named log [CAPTURED]. The surfaced error is
the exact `error.details.agent.error.detail` string returned by `POST /v1/execute` (HTTP 502,
`error.code=execution_failed`, `stop_reason=propose_failed`, `node=plan-2`) [CAPTURED].

| # | Category | Log | Verdict | Model-dependent | Exact surfaced error |
|---|----------|-----|---------|-----------------|----------------------|
| 01 | simple | 01_simple.log | FAIL — http=502 status=failed content='' | yes | `ReasoningFailed: reasoning execution did not succeed (invalid_credential/organization_restricted)` |
| 02 | multi_step | 02_multi_step.log | FAIL — status=failed acts=[] stages=2 | yes | same |
| 03 | multi_tool | 03_multi_tool.log | FAIL — status=failed distinct_tools=[] | yes | same |
| 04 | artifact | 04_artifact.log | FAIL — status=failed artifact_on_disk=False acts=[] | yes | same |
| 05 | external_provider | 05_external_provider.log | FAIL — providers=None status=failed record=ok | yes | same |
| 06 | provider_failure_fallback | 06_provider_failure_fallback.log | FAIL — status=failed attempts_by_candidate={} | yes | same (only one provider bound → no failover candidate) |
| 07 | tool_failure_recovery | 07_tool_failure_recovery.log | FAIL — status=failed failed_stages=['plan-1','plan-2'] acts=[] | yes | same |
| 08 | authz_denial | 08_authz_denial.log | PASS — http=502 status=failed stop=propose_failed refusal_stages=[] file_unchanged=True | no (invariant: protected file untouched) | same (execution never reached the tool) |
| 09 | verification_failure | 09_verification_failure.log | PASS — http=502 status=failed stop=propose_failed fabricated_line=False stages=2 | no (invariant: no fabrication) | same |
| 10 | partial_success | 10_partial_success.log | FAIL — http=502 status=failed stop=propose_failed preserved_succeeded_stages=[] | yes | same |
| 11 | admin_op | 11_admin_op.log | PASS — capabilities=200 exercisable=200 exercise(execute.sync)=200 exercised=None system=200 audit=200 | no | n/a |
| 12 | external_api_consumption | 12_external_api_consumption.log | FAIL — agent_tools=200 (20 tools) execute=502 record=200 trace=200 list=200 | yes (execute step only) | same |
| 13 | capability_registration | 13_capability_registration.log | PASS — rows=16 states=['available','inert','unavailable'] all_rows_have_evidence=True exercisable=200 | no | n/a |

Totals: 4 PASS / 9 FAIL. All 9 failures share one cause — the bound Groq organisation is
restricted. Direct provider probe (bearer redacted, `15_developer_transcript.log` §9):
`GET https://api.groq.com/openai/v1/models` →
`{"error":{"message":"Organization has been restricted. Please reach out to support if you believe this was in error.","type":"invalid_request_error","code":"organization_restricted"}}` [CAPTURED].

Notes on the PASS rows 08 and 09: they pass on their invariant (no unauthorized write; no
fabricated output) but the model never produced a proposal. They are PASS-by-invariant, not
PASS-by-completion; this is recorded so that a later "still passes" is not over-read.
