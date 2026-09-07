# A5 — Security audit (prompt §2.5) — P0 probes EXECUTED

HEAD at start 44b975c. Real local server (hermetic, port 8177, `ADMIN_EMAILS=admin@r176.test`), three principals in three
tenants: A, B (non-admin), admin. Raw transcript `two_tenant_probes.txt` (28 probes, tokens never written). Tier 1:
`tier1_security_suites.txt` (tests/security identity tools roles certification: **385 passed, 1 xfailed**),
`tier1_async_fabric.txt` (tests/runtime + execution service + bounded fan-out: **96 passed**).

## 1. Trust-boundary results (Compromised External Application = tenant B holding a valid token)

| probe | attack | result | status |
|---|---|---|---|
| S-01/02/03 | B reads A's execution by id | 404 `Unknown execution id.` — **byte-identical** to a random uuid 404 (no existence oracle) | VERIFIED · RUNTIME |
| S-05/06 | tokenless / forged Bearer read A's execution | 401 `unauthenticated`, one constant body | VERIFIED |
| S-07/S-21 | A lists executions | only own (11 rows, one `initiated_by`) | VERIFIED |
| S-08/09 | B reads A's workspace; B creates project inside A's workspace | 404 / 404 (workspace resolved in caller tenant — R168 D-08 holds) | VERIFIED |
| S-10/19/20 | usage counters | A 11.0 / B 11.0 after 11 executions each — separate, exact | VERIFIED · MEASURED |
| S-11/12/13 | B → `/v1/admin/{audit,capabilities POST,usage}` | 403 `Admin access required.` **before body validation** (empty `{}` body never reached 422) | VERIFIED |
| S-14 | tokenless → `/v1/admin/system` | 401 (not 403) — admin-ness not disclosed to anonymous | VERIFIED |
| S-17 | admin reads A's execution via user route | **404** — admin does NOT bypass tenant scoping on `/v1/executions` (control-plane authority ≠ data access) | VERIFIED |
| S-18 | **cross-tenant interleaving**: 10 A + 10 B async jobs submitted concurrently to the same in-process worker | 20/20 results carry the owner's own ask; 0 readable by the other tenant | VERIFIED · RUNTIME (P0) |
| S-22 | explicit unknown model | 503 `model_unavailable`, reason lists only the caller's own model key; no provider/credential detail | VERIFIED (no leak) |
| S-23 | role escalation via `role` selector | 422 closed shape | VERIFIED |
| S-24 | unknown skill | 422 `skill is not selectable` | VERIFIED |
| S-25 | foreign/unknown `project_id` | 404 | VERIFIED |
| S-26c/d | webhook subscription to loopback vs public | 422 `non-public address refused: 127.0.0.1` / 201 | VERIFIED (SSRF admission) |
| S-28 | 100 001-char ask | 422, not 500 | VERIFIED |

## 2. Async / worker context isolation (P0)
- STATIC: the async path builds `message_payload = {"tenant_id": str(caller.tenant_id), …}` (`apps/api/app.py:1179-1194`) —
  tenant is **serialized into the queue message**, not taken from ambient state; `QueueMessage.payload` is a str map
  (`core/runtime/ports.py:33`); `ContextVar` appears only in observability/log code and git tooling, never in execution.
- TEST: async fabric suite covers relay crash-window duplicate absorbed by dedup, worker crash → peer recovery, stale claim
  reclaim, retry-then-succeed, dead-letter, tenant-window flood refusal, fair scheduler round-robin + starvation guard (96 pass).
- RUNTIME: S-18 interleave above.
- Retry test with a *different* ambient tenant, and failure/cancellation residue, were not driven from the wire (no fault seam on
  the hermetic profile without code change) → **PARTIALLY VERIFIED**: serialization + interleave proven; retry-preserves-original-
  tenant proven only at unit level (`test_transient_failure_retries_via_stale_claim_then_succeeds`).

## 3. Observations requiring classification

**O-01 — `GET /v1/agent/executions/{id}/trace` is admin-only; the execution's owner gets 403 (S-15), admin gets 404 for another
tenant's id (S-16).** STATIC: route lives in `apps/admin_agent/http.py:106` behind `_admit` (admin). OPERATIONS §4 lists the
trace route under "API" without saying admin-only. Not a bypass (stricter than documented). Classification: **DOCUMENTATION
DRIFT** (S4) — fold into FIX-02's doc pointer or leave; not a blocker.

**O-02 — `ExecuteRequest.webhook_url` accepted (S-26 → 202) but no consumer found** (`grep webhook_url` → only the contract
field; delivery relay explicitly "never claimed" per `apps/api/app.py:536`). The SSRF gate is applied on `/v1/webhooks` (S-26c),
not on this dead field. Not exploitable (nothing dereferences it) but a **contract field that does nothing** — same family as
F-R176-05. Recorded as **F-R176-06 (S4, DOCUMENTATION / CONTRACT ONLY)**; proposed handling: either validate with
`validate_webhook_url` at admission or drop the field — decide with FIX-03.

## 4. Admin-compromise separation (partial, deeper in A6)
Admin token: full read of `/v1/admin/*`; **cannot** read tenant data through user routes (S-17); audit event rows carry
`tenant_id`, `actor_id`, `event_type`, `occurred_at` (S-27). Credential values: none appear in any response or in the server log
(grep for key shapes = 0). Confused-deputy via async, tools, skills: each gate (S-18, P-18, S-24) refuses at admission.

## 5. Verdict for §2.5
- Tenant isolation: **VERIFIED (RUNTIME, two tenants, concurrent)**.
- Authorization composition (direct, async, tool, skill, role): **VERIFIED at the entry gates**; agent-mediated laundering with a
  real model = LIVE evidence only from R165/R175 (not re-spent here).
- Credential containment: **VERIFIED (no values in responses/logs)**; provider-side graph → A9.
- Async context isolation: **PARTIALLY VERIFIED** (see §2).
- ZERO KNOWN DEFECTS WITHIN THE DECLARED TESTED ENVELOPE for isolation/authz; two contract-hygiene findings (O-01, F-R176-06).
