# A4 — Platform capability audit (prompt §2.4)

HEAD at start 0ce86ba. Tier 1 = `strategy_tests.txt` (65 passed); Tier 2 = `runtime_probe.txt` (24 probes P-01..P-24 against
a REAL local server: `apps.cli serve`, hermetic profile, `ADMIN_EMAILS=admin@r176.test`, port 8176; tokens redacted).

## 1. Capability matrix (Exists / Wired / Executable / Tested / Admin-controlled / Security-bounded / Documented)

| capability | exists | wired | executable (evidence) | tested | admin | sec-bounded | docs | status |
|---|---|---|---|---|---|---|---|---|
| Identity: register → verify(console) → login → Bearer | ✓ | ✓ | P-02..P-08 (201/200/200/200, `is_admin` true only for `ADMIN_EMAILS`) | tests/api, identity | ✓ | 401 tokenless (P-01), 403 non-admin (P-10) | OPS §3 | **VERIFIED · RUNTIME** |
| Core execution `POST /v1/execute` sync | ✓ | ✓ | P-12 200 `succeeded`, provider `local-echo`, honest note, usage reserved=settled=1 | tests/api (32 files) | — | tenant from session | OPS §4 | **VERIFIED · RUNTIME (platform)**; real provider = R175 L-03 (LIVE) |
| Async execution 202 → poll | ✓ | ✓ | P-13 202 `queued` + poll_url; P-14 200 `succeeded` progress 100 | ✓ | — | ✓ | OPS §4 | **VERIFIED · RUNTIME** |
| Execution strategies | contract enum 8 values (`single,parallel,pipeline,debate,review_judge,map_reduce,agent,hybrid`) | service implements SINGLE + PIPELINE (+ AGENT via seam); multi-model slice supports `fallback_chain`, `parallel_compare` only, refuses others loudly (UnsupportedStrategy, Tier 1 test) | **P-15 `debate`, P-16 `map_reduce`, P-17 `pipeline`, P-23 `nonsense_value` → all 200 single-stage echo, no refusal, no notice** | Tier 1 covers `model_policy.selection_strategy` refusal (test_execute_api.py:352) — NOT `execution_policy.strategy` | — | — | 10 §… example shows `"strategy":"auto"` | **FINDING F-R176-05** (below) |
| Agent strategy | ✓ (R160 shared `core.agent` runtime) | ✓ | P-18 unknown tool → 422 loud; P-24 no tools on `local_echo` → **502 `execution_failed` stop_reason `invalid_proposal`** — exactly the "honest 502" OPERATIONS §5 documents | tests/agent, agent_dev (13 files); R165 live | ✓ (`/v1/agent-tools` max_steps 8) | Capability Firewall in runtime | OPS §5 | **VERIFIED · RUNTIME (platform)**; behaviour with a real model = R165/R175 LIVE |
| Skills | ✓ `/v1/skills` | ✓ | P-20 200 `{"skills":[]}` (none installed hermetic) | tests/skills (2) + admin import | ✓ admin import | — | OPS §6 | **VERIFIED surface · RUNTIME**; lifecycle → A8 |
| Tools | ✓ `/v1/agent-tools` | ✓ | P-21 200 `tools:[]` (0 offered without `AGENT_WORKSPACE_ROOT`) — matches `describe` `agent_tools_offered=0` | tests/tools (6) | ✓ | allow-list resolved against catalog; unknown ⇒ 422 (P-18) | OPS §5.1 | **VERIFIED · RUNTIME** |
| Models | ✓ `/v1/models` | ✓ | P-09 200 one model `local-echo-1` tier medium | ✓ | ✓ (admin model routes) | ✓ | OPS §4 | **VERIFIED · RUNTIME** |
| Usage | ✓ `/v1/usage` | ✓ | P-22 200 plan `local-default`, used 5.0 after 5 executions — **accounting matches probe count** | tests/usage | ✓ | per-tenant | OPS | **VERIFIED · RUNTIME** |
| Admin control plane | ✓ 59 method-routes | ✓ | P-11 200 `/v1/admin/system` (profile, identity_mode, provider_keys) | tests/admin, admin_agent (12) | — | 403 for non-admin (P-10) | OPS §4, §8 | surface VERIFIED; mutations → A6 |
| Contract strictness | `extra=forbid` | ✓ | P-19 unknown field → 422 "Extra inputs are not permitted" | ✓ | — | ✓ | OPS §3 | **VERIFIED · RUNTIME** |
| Memory / context | ✓ core/memory, core/context; `context_provenance` artifact in every result (P-12: blocks_total 1, memory 0, gold 0) | ✓ | provenance observed | tests/memory, context; pgvector durable (R175) | — | — | 13 | surface VERIFIED; isolation → A5/A8 |
| Evaluation / Learning | ✓ core/evaluation, core/learning | wired to admin routes | not exercised in A4 | tests (3+3) | ✓ | — | OPS §8 | INFERRED → A8 |
| Observability / audit | ✓ core/audit, apps/observability; `/v1/admin/audit` | ✓ | structured JSON log observed (verification-token event); audit → A6 | ✓ | ✓ | — | OPS §9 | INFERRED → A6 |
| UI | `/app`, `/admin` mounted (describe) | ✓ | not exercised (browser live-suite NOT EVALUATED per gate) | tests/ui static (1) | — | — | OPS §4 | UNVERIFIED (out of mandate) |
| External consumption | HTTP API + `examples/minimal-platform-app/client.py` (R150) | — | → A10 | — | — | — | — | → A10 |
| Engineering workspace (ADR-0012) | ✓ | only with `AGENT_WORKSPACE_ROOT` | 404 unmounted hermetic (by design) | tests/engineering (4) | ✓ | refuses platform's own checkout | OPS §5.1 | INFERRED (not exercised; needs a workspace dir) |
| Recovery / resume | ledger protocol | — | A1: two real resume tests PASS | — | — | — | OPS §12 | **VERIFIED · RUNTIME** |

## 2. Finding

**F-R176-05 — `execution_policy.strategy` is not validated for non-agent values (S3, correctness/contract).**
- EXPECTED (spec 02 §2 inv. 8 "unknown ⇒ DENY"; 10 API contracts: closed shapes; the codebase's own stated rule in `apps/api/app.py:807` "Absent seam ⇒ loud rejection (never a silent single-shot)"; the multi-model slice refuses unsupported `selection_strategy` with 422): a request naming a strategy the deployment cannot run (`debate`, `map_reduce`, `review_judge`, `hybrid`, `parallel`) — or a value outside the enum entirely (`nonsense_value`) — is refused with 422 `validation_error` field `execution_policy.strategy`.
- ACTUAL (P-15, P-16, P-17, P-23): HTTP 200, `status: succeeded`, single-stage `local-echo` result, `progress.current_stage` would read `single`; no error, no notice in the result, usage settled. The caller believes a debate/map-reduce ran.
- ROOT CAUSE (STATIC): `ExecutionPolicy.strategy` is typed `BoundedStr | None` (core/contracts/execute.py:63), not `ExecutionStrategy`; `apps/api/app.py` only branches on `== "agent"`; everything else falls to the single path. `pipeline` is implemented in `core/execution/service.py:336` but is not reachable from `/v1/execute` via this field.
- IMPACT: silent degradation (contract lie), not a security bypass — the strategy field grants no extra capability; tenant/auth/tools gates are untouched (P-18/P-24 show the agent branch is strict). Classification: **SHOULD FIX BEFORE EXTERNAL CONSUMPTION** (an SDK consumer would build on a field that does nothing).
- REPRODUCTION: `runtime_probe.txt` P-15/P-16/P-17/P-23 (hermetic server, any Bearer).
- PROPOSED **FIX-03** (not executed): (a) type `ExecutionPolicy.strategy` as `ExecutionStrategy | None` so out-of-enum values → 422 at parse; (b) in `/v1/execute`, accept exactly the strategies the composed slice can run (`single`, `agent`; `pipeline` only if the service path is wired) and return 422 `validation_error` field `execution_policy.strategy` for the rest, mirroring the multi-model refusal; (c) failing-first regression test `tests/api/test_execute_api.py::test_unsupported_execution_strategy_is_validation_error` (fails on parent, passes after). Blast radius: `core/contracts/execute.py`, `apps/api/app.py`, one test file; UI `/app` must be checked for any hard-coded strategy string before approval.

## 3. Probe coverage for A4
P1 executed: 24/24 (all in `runtime_probe.txt`). P0 items (isolation, credential containment, async context) deliberately deferred to A5 where they are run as two-tenant probes. Nothing under `core/` or `apps/` was modified. Server stopped after the run.
