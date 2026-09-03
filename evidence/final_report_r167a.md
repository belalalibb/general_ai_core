# R167-A v2 — FINAL BACKEND CERTIFICATION ROUND — REPORT

Repo `belalalibb/general_ai_core`, branch `main`, prior close `b3bacf5` (R167-QEVION). Round commits `4d26a80 … 31dc819` + this report.
Tags per §14: [VERIFIED] [MEASURED] [CAPTURED] [INJECTED] [PARTIAL] [SOURCED] [OBSERVED] [INFERRED] [UNVERIFIED].

## 1. RESULT

**GATE NOT EVALUATED — OFFLINE ENVELOPE.** MODE = OFFLINE-ENVELOPE (`evidence/credentials_manifest.md`): GROQ_API_KEY unset; the only bound provider (genspark_llm) returns HTTP 200 with an in-band plan refusal on every call. Every live number below therefore measures the platform's coordination, isolation and accounting behaviour around a refusing provider, not model quality. Defects found: 11 (S1 0 / S2 4 / S3 5 / — 2 containment probes HELD). Fixes shipped: 1 of ≤5 (D-09). Full suite 2706 passed / 64 skipped; `check_repo.sh` RESULT: PASS [VERIFIED].

## 2. LIVE CLOSURE

`evidence/live_closure.md`. Stage 1 re-run of the 13 R167 tasks on genspark_llm (`evidence/tasks/r167a_stage1/`): 4 PASS (08 authz denial, 09 verification failure, 11 admin op, 13 capability registration — all PASS-by-invariant, no model output needed) / 9 FAIL (`invalid_proposal … got 'invalid_json'`) [MEASURED]. Immutable pre-round snapshot `evidence/degraded_before.md` (4/9 with `invalid_credential/organization_restricted` on Groq). Finding LC-1 = D-01: child reasoning execution booked SUCCEEDED and settled 1.0 unit for a refusal sentence; parent fails; `/diagnosis` reports "no provider error was recorded". Honesty ratio for prior-round claims 10/12 (1 withdrawn — benchmark ranking; 1 partial). §7.5 efficiency delta NOT MEASURABLE (fixtures only, `evidence/baseline.md` annotated).

## 3. PROVIDER CONTRACT

`evidence/provider_contract.md` — 10 items with source citations [SOURCED]. Present: opaque credential refs via `InMemorySecretManager`, `ProviderErrorCategory` (12 values), retry-on-`retryable` with `retry_after_ms` cap 60 000 ms, route = selected + fallbacks, `_REQUEST_INDICTING={BAD_REQUEST, CONTENT_REJECTED}` suppresses failover, settlement = units × SUCCEEDED stages. NOT PRESENT IN CODE: per-app/tenant credential binding, account-level selection (`AccountPoolManager`/`ResourceSelector` have no call sites), in-band 200 refusal detection, backoff policy, same-provider credential failover, runtime health mutation from execution outcomes, provider/credential cost attribution, per-call `PROVIDER_ACCOUNT_USED` emitter.

## 4. MULTI-ACCOUNT ROUTING MATRIX

`evidence/provider_routing_matrix.md`, 12 rows, all [INJECTED] via `tests/certification/test_r167a_routing_matrix.py` (ScriptedAdapter over the real `SimpleScoringRouter` + `ExecutionService`; 17 tests pass). Held: healthy path; restricted-then-fallback across providers (class B); retryable then success; model-unavailable failover; concurrent tenants with one degraded provider; credential-missing is a pre-check failure (`CredentialNotConfigured`); no-route is named. Defects: M-1 class A (same provider, other account) ABSENT — second credential for a provider key raises `DuplicateRegistration` (D-03); M-2 audit never names the credential (D-04); M-4 `bad_request` suppresses failover, and D-02 shows a real Groq shape that lands there wrongly. Live cross-check: matrix row 4 matches the R167 transcript §10 [SOURCED].

## 5. CREDENTIAL BINDING BOUNDARY

`evidence/credential_binding_boundary.md`. Outcome (§4C verbatim): **NOT SUPPORTED BY CURRENT CONTRACT** → **NOT EXECUTABLE — CONTRACT ABSENT**. Credentials are bound once at composition (`_bind_real_providers`, platform tenant = `uuid4()`), `CandidateScore.account_id` is always None, `ProviderGenerateRequest.credential_ref` is filled from `credential_refs[provider.id]` regardless of caller tenant. Containment probes D-05/D-06 HELD [MEASURED]: GSK_API_KEY value absent from admin views, failure bodies, trace, diagnosis, events and server stdout after ~45 requests. Severity S3 (no leak; capability absent).

## 6. DEVELOPER TRANSCRIPT

Split recorded in `evidence/live_closure.md` §7.4: generic execution/routing/agent core contains no IDE/workspace vocabulary (`grep -E '\bide\b|workspace' core/execution core/routing core/agent/runtime.py` → 0) [VERIFIED]; consumer-side engineering tools live under `core/engineering` + `apps/api/engineering_admin.py`. Model transcript for this round: NOT PROBED — every model call returned a refusal, so there is no developer conversation to archive beyond `r167a_stage1/*.log`.

## 7. DEFECT LEDGER

`evidence/defect_ledger.md` (columns per §12). Summary:

| ID | Sev | Class | One line | Status |
|---|---|---|---|---|
| D-01 | S2 | MISBOOK | 200 refusal booked SUCCEEDED + billed | OPEN → R168 |
| D-02 | S2 | MISCLASS | detail-only 400 → bad_request, no failover | OPEN → R168 |
| D-03 | S3 | ABSENT | no same-provider multi-account failover | OPEN → R168 |
| D-04 | S3 | AUDIT-GAP | credential never named in audit/cost | OPEN → R168 |
| D-05/06 | — | — | key containment (responses / logs) | HELD |
| D-07 | S2 | POSTURE | anonymous → demo principal, in-memory hybrid profile; anon `POST /v1/execute` → 200 billed | OPEN → R168 |
| D-08 | S3 | SILENT | `project_id` accepted and ignored (incl. foreign/non-UUID) | OPEN → R168 |
| D-09 | S2 | AUDIT-GAP | admin write-grant to another tenant left no audit row | **FIXED 2ce3aba** |
| D-10 | S3 | ORDER | body validation runs before admin gate on 16/64 POST routes (schema hints to non-admin; no admission) | OPEN → R168 |
| D-11 | S3 | AUDIT-GAP | PERMISSION_DENIED / CROSS_TENANT_ACCESS_DENIED never emitted; audit read is reader-tenant-scoped | OPEN → R168 |

## 8. FIXES SHIPPED

1/5 accepted changes. **D-09** (`evidence/fixes/D-09.md`): fail-first `pytest tests/certification/test_r167a_admin_grant_audit.py` → `1 failed, 1 passed`, exit 1 (`D-09_fail_first.txt`); fix +36/−5 LOC in `apps/api/engineering_admin.py` (optional `audit: AuditLogPort`, `grant(..., actor_id, actor_tenant_id)` appends `SECURITY_POLICY_CHANGED` under the **target** tenant with `surface/actor_tenant_id/permissions/granted_permissions/outcome`), `apps/api/admin.py` (passes admitted identity), `apps/composition/runtime.py` (binds the shared audit log), test helper; after: `103 passed`, exit 0 (`D-09_after_fix.txt`); live re-verification `evidence/stage2/s17_admin_ab_after_fix.log` shows the row and the derived SECURITY notification [MEASURED]. No timeouts widened, no tests skipped, no logs edited. D-01/D-02 not fixed: neither is S1, and both need an adapter-level classification contract that does not exist (a "fix" would be a new feature).

## 9. TENANT ISOLATION + AUTHORIZATION

`evidence/stage2/stage2_transcript.log` (82 requests, 50 verdicts, 45 HELD) [MEASURED]. P0 HELD: foreign execution by-id/events/trace/diagnosis → 404, list excludes foreign rows; workspace/project/webhook foreign read+delete → 404 with object intact; project into foreign workspace → 404; conversation reuse across tenants leaks nothing; unknown tools → 422 named. P0 DEFECT: D-08 (silent `project_id`), D-07 (anonymous fallback). Worker context inheritance: NOT PROBED (no async worker path exercised; `initiated_by` observed on list rows only). Credential containment: HELD (D-05/D-06).

## 10. PRESSURE / CONCURRENCY / IDEMPOTENCY

Idempotency: same tenant + same `Idempotency-Key` → identical execution id, 1.0 unit across two calls; same key from another tenant → distinct execution (key tenant-scoped) [MEASURED]. Attribution: ops units unchanged while dev executes. Atomicity: failed explicit-model run (503) charged 0.0. Pressure: 12 concurrent `POST /v1/execute` → 12×200, 12 distinct ids, ledger delta 12.0 = successes (each "success" is a refusal sentence — D-01 applies). Quota exhaustion, rate-limit ceiling and duplicate-billable-under-retry: NOT PROBED (limits 1 000 000 units; EXECUTE_RATE_LIMIT not enabled in this profile).

## 11. SAAS-NUCLEUS ASSESSMENT

Two independent apps = two tenants (ops/admin, dev). Capability visibility is server-side: dev on `/v1/admin/capabilities` → 403; admin tooling via agent path → 422 "unknown agent tools" (not a client hide) [MEASURED]. Policy denial not bypassable via the other app's routes within the probed surface. Quota/cost attribution per tenant HELD. Audit identity: every row carries `actor_id` + `tenant_id`, but coverage is `login` (+ `approval_decision`, and now `security_policy_changed`) only — denials leave no trace (D-11). Genericity (≤300 words): the execution/routing/agent core is app-agnostic; the engineering (IDE) consumer sits in its own package and admin seam; provider binding is platform-global, so a second app cannot bring its own credentials — the nucleus is multi-tenant for data and quota, single-tenant for provider identity (D-03/§5).

## 12. ADMIN CONTROL-PLANE

`evidence/stage2/s17_admin_ab_after_fix.log` [MEASURED]. Admin is platform-global by contract (`is_admin = email in ADMIN_EMAILS`), so "App A admin cannot touch App B" is **NOT SUPPORTED BY CURRENT CONTRACT** as a scoping rule; within the contract: admin B cannot list, revoke (`{"revoked":false,"reason":"authorization unknown"}`) or read audit for admin A's tenant; A's ticket survives; B cannot read A's execution (404); `/evaluations` returns `[]` 200 for foreign and unknown ids alike. Non-admin on all 64 `/v1/admin/*` routes: never admitted (0 × 2xx/404/500); 16 POST routes answer 422 before the gate (D-10). Denials are honest (403 "Admin access required."). Mutation audit: engineering authorization issue → `approval_decision` (pre-existing); write-grant → `security_policy_changed` (this round, D-09).

## 13. FAILURE-SHAPE ARCHIVE + MAP

`evidence/failure_shapes/` (4 redacted real shapes [CAPTURED]): genspark 200 plan refusal, genspark 400 `detail: "Model … is not allowed"`, genspark 401 `detail: "Invalid or expired token"`, Groq 400 `organization_restricted`. `evidence/error_classification_map.md`: Groq org_restricted → INVALID_CREDENTIAL CORRECT; 401 CORRECT; detail-only 400 → bad_request MISCLASSIFIED (D-02); 200 refusal UNCLASSIFIABLE (D-01). Injected category table (12 categories) and status-only normaliser table included; 4 `test_shape_*` tests replay the shapes through the real `GroqAdapter` via `httpx.MockTransport` [INJECTED].

## 14. EFFICIENCY DELTA

NOT PROBED — OFFLINE ENVELOPE. `evidence/baseline.md` re-annotated (§7.5): fixture-only coordination numbers, no live reliability data; `evidence/benchmark.md` ranking withdrawn to "UNRANKED — competitor not executed".

## 15. BOUNDED COMPLETENESS (§11)

TESTED ENVELOPE: in-memory profile, `identity_mode=hybrid`, two registered tenants + one demo principal, single bound provider (genspark_llm) answering HTTP 200 with an in-band refusal; Groq/OpenAI unbound; injected adapters for routing/classification; 82 live HTTP requests + 12 concurrent; 2706 unit/integration tests.
DEFECT LEDGER SUMMARY: S1 0/0, S2 4/1, S3 5/0, S4 0 (found/fixed).
NOT PROBED: live provider success path, real model transcripts, quota exhaustion, rate limiting, async worker context inheritance, durable (DATABASE_URL) profile, webhook delivery, source-change/learning/skills admin workflows beyond gate checks, benchmarks/efficiency delta.
CLAIM: "Zero known defects within the tested envelope." does **not** apply — 10 open defects are listed above. The tested envelope excludes all live external provider behavior.

## 16. SPEND REPORT

Ceiling USD 0 (manifest). Spend USD 0.00 [VERIFIED]: every genspark_llm call was refused before model execution; no Groq/OpenAI calls were possible. Abort counter 0/3.

## 17. LIMITS + NOT PROBED

See §15 NOT PROBED. Additional limits: pre-fix §17 transcript file was lost to sandbox reset #8 (its observation is reproduced in `evidence/fixes/D-09.md` and by the fail-first test); the D-09 audit row for a *foreign* target is written but not readable over HTTP by the acting admin because the audit read is reader-tenant-scoped (D-11) — observed via a self-tenant grant instead. Bash tooling was unreliable (resets #5–#8, self-matching `pkill`); no result above was replayed as live.

## 18. HANDOFF TO R168

Ordered by severity, each with the ledger entry: (1) D-01 in-band refusal detection at the adapter boundary → FAILED + 0 units; (2) D-07 make the anonymous→demo fallback opt-in (`DEMO_PRINCIPAL=1`) or strict in hybrid mode; (3) D-09 companion — platform-admin audit read across tenants + D-11 emitters for `PERMISSION_DENIED`/`CROSS_TENANT_ACCESS_DENIED`; (4) D-02 unknown-400 → non-indicting category; (5) D-08 validate `project_id` (UUID, caller-owned, else 404); (6) D-10 admit before body parsing on admin POST routes; (7) D-03/D-04 per-tenant credential binding + account pools + `PROVIDER_ACCOUNT_USED` (design in `credential_binding_boundary.md`). Re-run this round's §12/§17 probes (`evidence/stage2/probe_stage2.py`) with a real key to convert every [INJECTED]/[PARTIAL] into [MEASURED].

## 19. GATE EVALUATION

**GATE NOT EVALUATED — OFFLINE ENVELOPE.** Letters: (a) live closure — FAILED (9/13 provider refusal, cause named); (b) provider contract — documented, 8 absences; (c) routing matrix — [INJECTED] only; (d) credential boundary — NOT EXECUTABLE — CONTRACT ABSENT; (e) developer transcript — NOT PROBED; (f) defect ledger — done, S1 0; (g) fixes fail-first — done (1); (h) tenant/authz — 45/50 HELD, 5 defects recorded; (i) admin plane — held within contract, D-09 fixed, D-10/D-11 open; (j) honesty — no fabricated results, ledger bumped. Conditions to evaluate: a working GROQ_API_KEY **or** a GSK_API_KEY with credits; spend ceiling > 0 agreed. Closing command sequence:

```
git pull --ff-only origin main
export GROQ_API_KEY=<real>   # never commit; fingerprint only
pkill -f "python3 -m apps[.]main"; bash /tmp/ui/start.sh &   # recipe in evidence/credentials_manifest.md
OUT=evidence/tasks/r168_stage1 BASE=http://127.0.0.1:8000 TOKEN_FILE=/tmp/ui/ops.tok python3 evidence/tasks/run_live.py
OUT=evidence/stage2_live BASE=http://127.0.0.1:8000 OPS_TOKEN_FILE=/tmp/ui/ops.tok DEV_TOKEN_FILE=/tmp/ui/dev.tok python3 evidence/stage2/probe_stage2.py
env -u GSK_API_KEY -u GROQ_API_KEY python3 -m pytest -p no:cacheprovider -o addopts="" -q -W ignore && bash engineering/verification/check_repo.sh
```
