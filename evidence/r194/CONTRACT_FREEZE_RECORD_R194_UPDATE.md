# Contract Freeze Record — R194 update

Round: R194 — Hardening + Composition Closure (non-architectural). Baseline: `main = b5c46561`. Branch: `genspark_ai_developer_r194`.

## 1. Shape impact on the frozen contract set

**NONE.** `contract_freeze_derive.py --check` → `contract freeze baseline: MATCHES current tree` at 7ee14495 (after all three production edits).

| Touched file | Change | Frozen set touched? |
|---|---|---|
| `apps/api/app.py` | `create_app(hsts=False, openapi_public=True)`; outermost hardening-header middleware; admin-gated `/openapi.json` + `/redoc` when `openapi_public=False` | No — `served_routes_v1` unchanged (44); the two document paths are not in the frozen set; response **headers** are additive metadata on every existing response, bodies unchanged |
| `apps/composition/runtime.py` | shared subscription map; `build_webhook_sender`; `webhook_worker`; `openapi_public_from_env`; `HSTS` posture | No — composition only |
| `apps/main.py` | lifespan drives the webhook worker | No — process lifecycle only |

Reachability delta: none on the in-memory profile. On the durable profile (or `OPENAPI_PUBLIC=0`) `/openapi.json` and `/redoc` now answer 401/403 to non-admins — a stricter refusal, unified envelope, no new shape.

## 2. Authorities reused (none duplicated)

`bearer_token` / `unauthenticated` / `error_response` / the per-request `_principal` resolver (AA-1) · `AuditEventType.PERMISSION_DENIED` denial audit (R168 D-11) · `Worker` (41 §13) · `OutboxRelay` · `WEBHOOK_STREAM` / `WebhookDeliveryHandler` / `stage_execution_event` / `validate_webhook_url` (V6, R176 FIX-07) · `ExecutionMessageHandler(outbox=, subscriptions=)` (V6 chunk 3 seam) · `create_app(webhook_subscriptions=)` (T-IMPL-072 seam) · `httpx` at the composition root (ADR-0008 precedent: `dev_bindings.py`, `gateway.py`).

## 3. Tenancy statement (verified by test)

The subscription map is keyed by `tenant_id`; the API writes the caller's rows, the execution worker reads the owning tenant's rows only; `stage_execution_event` never widens scope. Test: two tenants register; tenant A executes; only A's URL receives `execution.queued` + the terminal event; B receives nothing; the payload `tenant_id` is A; no `Authorization` header leaves the process. No admin-only execution path; the OpenAPI gate reuses the existing admin admission (shared control plane, not per-tenant).

## 4. NOT claimed

- Durable/shared subscription storage (process-local map, same posture as the queue and the pre-R194 `create_app` default).
- Signed webhook payloads / receiver verification (no contract exists; would be a SHAPE proposal).
- N-5 checkpoints (withdrawn: finding R194-F1).
- A CSP without `style-src 'unsafe-inline'` (needs a UI thaw to remove `style=` attributes).

## 5. Operator decisions still required (unchanged, re-checked)

P-R191-01 · P-R192-02 · P-R192-03 · G-TRUST / G-BIND (AD-1) · AD-2 · AD-5 · DEC-03/AD-6 · AD-7 · D-03 credential rotation · **new: N-5 checkpoint composition path (R194-F1)**.

## 6. Backward compatibility

All existing suites unchanged (regression recorded in `evidence/r194_state_ledger.md`). `create_app` callers that pass neither new kwarg get the pre-R194 documents posture plus the headers. `build_runtime_profile(environ)` positional use unchanged; `webhook_transport` is keyword-only.
