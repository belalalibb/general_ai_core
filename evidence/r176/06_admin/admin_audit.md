# A6 — Admin control-plane audit (prompt §2.6) — EXECUTED

HEAD at start 75cedd6 (sandbox reset #22 between turns wiped the untracked A6 draft; re-run from the committed
rerunnable probe `a6_probe.py` → `admin_probes.txt`). Real hermetic server, admin + fresh non-admin principal.

## 1. Mutation model (STATIC + RUNTIME)
- There is **no direct mutation route** for providers/models/routing/plans/skills/tools (M-07 `PUT /v1/admin/routing/weights`
  → 405). All configuration changes go through ONE lifecycle: `POST /v1/admin/changes` (draft) → `/validate` → `/preview` →
  `/publish` → `/rollback`; 13 actions in 7 areas (`core/contracts/admin.py` ACTION_AREA); area derived from action, tenant +
  actor from the principal (clients never claim identity). Every route: `_admit` (is_admin) BEFORE parsing.
- Other admin mutations (learning sample admit/evaluate/promote, skills import lifecycle, source-change proposals, scenarios,
  notifications ack) follow the same pattern; each is tenant-scoped via `admitted.tenant_id` (`apps/api/admin.py`).

## 2. Lifecycle probe results
| probe | result | status |
|---|---|---|
| L-01..03 draft → validate (`passed`) → preview (`impact_preview`: "model 'local-echo-1' leaves the routing pool") | 201/200/200 | VERIFIED |
| L-04 non-admin publish | 403 | VERIFIED |
| L-05 publish → `published_version: models-v1` | 200 | VERIFIED |
| **L-06 stale-config test**: user `GET /v1/models` on the very next request | `{"models":[]}` — propagation is immediate, read-through (no cache) | VERIFIED · consistency = **strong / process-local** |
| **L-07** user execute after disable | 503 `model_unavailable` — loud, no silent fallback to the disabled model | VERIFIED |
| L-08..10 rollback → models back → execute 200 | | VERIFIED |
| L-11 audit | `admin_config_published` event with tenant_id, actor_id, change_id, action, `admin_change{what, previous_version models-v0, new_version models-v1, validation_result, impact_preview}` — actor/scope/target/outcome all present | VERIFIED |
| L-12 publish after rollback | 409 `invalid lifecycle transition: expected validated, found rolled_back` | VERIFIED (state machine enforced) |
| L-13 `set_plan` with empty payload | draft accepted (201); refusal is deferred to validate (design: validation is a lifecycle step, honest 200 "rejected") | consistent with docstring |
| L-15 non-admin lists changes | 403 | VERIFIED |

Effect on running / queued executions: not probed with in-flight work (a disable during a queued async job) — **NOT PROBED
(P2)**; the hermetic worker drains within ms so the window is not reachable from the wire without a fault seam.

## 3. Finding

**F-R176-07 — credential material accepted into a config-change payload and echoed back (S3, credential hygiene).**
- EXPECTED (contract docstring `core/contracts/admin.py:150-153`: payloads "NEVER credential material (20 §5 — credentials stay in
  the secret-manager flow, referenced by opaque refs only)"): a `register_provider` draft whose payload contains `api_key` is refused
  at draft, or at least the value is never persisted/echoed.
- ACTUAL (L-14/14b/14c): draft **201 stored**; validate → `rejected` but only because `payload requires a 'provider' object` — the
  rejection is structural, not credential-aware; `GET /v1/admin/changes/{id}` **echoes the marker value in clear**. Audit: the value
  is NOT in audit events (L-14e audit=False) — good.
- IMPACT: admin-only surface, same tenant, in-memory here; in the durable profile a rejected draft with a real key would sit in
  `config_changes` rows in clear. Not a cross-tenant or unauthenticated leak; it is a footgun that contradicts the written contract.
- Classification: **SHOULD FIX BEFORE EXTERNAL CONSUMPTION**. Proposed **FIX-04** (not executed): deny-list of credential-shaped
  keys (`api_key`, `secret`, `token`, `password`, `*_key`) in `AdminDraftRequest.payload` at draft time → 422
  `validation_error` field `payload`, plus failing-first test in `tests/admin/`. Blast radius: `core/contracts/admin.py` (validator)
  or `apps/api/admin.py` draft route + 1 test; `ui/admin` provider-onboarding form must be checked for which fields it sends.

## 4. Admin-removal / authority separation
`AdminArea`/lifecycle live in `core/admin`; runtime enforcement (auth 401, tenant 404, tool gate, model ACTIVE filter) is in
`core/*` + middleware and does not consult the admin surface at request time — with `admin=None` composition the `/v1/admin/*`
routes are simply absent (docstrings "Absent seam = absent routes") while the enforcement stays. CONTROL-PLANE AUTHORITY
(admin) ≠ RUNTIME ENFORCEMENT (core): **VERIFIED · STATIC**, RUNTIME only for the composed-with-admin profile.

## 5. Coverage
P0 admin boundary probes: 4/4 executed (non-admin → 403 before validation; anonymous → 401; admin cannot read user data via user
routes (A5 S-17); tenant-scoped change records). P1: lifecycle 12/12. P2 NOT PROBED: config change during in-flight execution.
