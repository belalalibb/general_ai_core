# D-01 — in-band HTTP-200 plan refusal booked as SUCCESS (S2, MISBOOK)

## Defect
`genspark_llm` answers a plan-exhausted account with HTTP 200 whose body is the
gateway's refusal sentence ("Free-plan credits can't be used … genspark.ai/pricing …")
and `usage = {0,0,0}` (captured: `evidence/failure_shapes/genspark_llm_200_plan_refusal.json`).
The adapter booked it `succeeded=True`; the run SUCCEEDED; 1.0 unit settled; the
refusal text became the "answer"; `/diagnosis` said "no provider error was recorded".

## Fix (adapter-level, `providers/` — budget-free)
`providers/real/genspark_llm/adapter.py`:
- `_PLAN_REFUSAL_MARKERS` + `_is_plan_refusal(content, usage)`: refusal iff BOTH
  (a) usage block present and `total_tokens == 0 and completion_tokens == 0`
  (no inference happened) AND (b) content contains a refusal marker
  (case-insensitive). Either signal alone is NOT a refusal (guards: genuine
  completion quoting the wording with tokens>0 stays success; zero-usage plain
  text stays success).
- `generate()` chat path: on refusal → `_failed(...)` with
  `ProviderError(category=QUOTA_EXCEEDED, retryable=False,
  provider_code="plan_refusal_200", safe_message=<generic>)`. Output/usage empty;
  refusal text never crosses the boundary.

## Downstream contract (already frozen in core — no core change)
- `core/execution/service.py`: `quota_exceeded` + `retryable=False` is
  route-indicting ⇒ immediate failover to the next candidate; node FAILED if none;
  usage `fail` ⇒ 0 units settled, hold released.
- `core/evaluation/policy.py` L179: `not response.succeeded` ⇒ `JudgeFailure`
  ⇒ learning/gold path treats the call as unverified.
- API surface (observed live): `403 entitlement_exceeded`,
  `provider_error_category=quota_exceeded`, safe message only.

## Category decision (see conflict ledger C-05, IMPL-009)
Mandate text: "CONTENT_REJECTED / credential-indicting". In the frozen core,
`CONTENT_REJECTED` is REQUEST-indicting (`_REQUEST_INDICTING`) and FORBIDS
failover ("would launder a refusal"), which contradicts the mandate's own
"failover-permitting" requirement. The refusal indicts the account/plan, not the
request, so `QUOTA_EXCEEDED` (account-indicting, non-retryable, failover-permitting)
is the consistent classification.

## Tests
- `tests/providers/test_d01_refusal_contract.py` (6): fail-first 4F/2P → 6P.
- `tests/certification/test_r167a_routing_matrix.py`:
  `test_shape_200_plan_refusal_is_booked_as_success` (asserted the defect) →
  `test_shape_200_plan_refusal_is_quota_exceeded_r168` replaying the shape
  through the genspark_llm adapter (its origin). MAP row:
  `MAP|200_plan_refusal|quota_exceeded|retryable=False|D-01 FIXED R168`.
- Suites: tests/providers tests/certification tests/execution tests/evaluation →
  569 passed / 7 skipped / 2 failed; the 2 failures are
  `tests/providers/test_genspark_llm_live_e2e.py` (GSK_API_KEY-gated, network):
  the sandbox key IS plan-exhausted, so the live call now returns
  `403 entitlement_exceeded / quota_exceeded` instead of a fake 200 — i.e. the
  live test now observes the real failure D-01 was hiding. Hermetic (key unset):
  skipped. Not a regression of the tree; the hermetic gate is canonical (C-03).
- ruff / ruff format / mypy strict on adapter: clean.

## Budget
Production diff is in `providers/` only (counts: core/ apps/ infrastructure/) ⇒
round A stays 4/5.
