# CAPABILITY MAP — what the core offers a builder today (R169 A1)

Reference for any application-building agent (IDE or otherwise). Accuracy over optimism.
Verified against HEAD `199b1cf` (2026-09-04). Every claim points at code in this repository.

## How a state is decided (the single rule)

`apps/api/capabilities.py` holds ONLY the closed id set (`CAPABILITY_IDS`, 16 ids) and the closed
state set `CapabilityState = {available, inert, unavailable}`. It declares NO states. States are
derived in `apps/api/app.py::create_app` (L1771–1858), from the same variables that mounted (or
did not mount) each route:

```python
def _cap(cap_id: str, available: bool, evidence: str) -> Capability:
    return Capability(id=cap_id,
        state=CapabilityState.AVAILABLE if available else CapabilityState.INERT, evidence=evidence)
```

- **available** — the seam is composed; a request can exercise it now in this process.
- **inert** — the code exists but the seam was not injected into `create_app`; wiring, not building, activates it.
- **unavailable** — requires code that does not exist (only `execute.token_streaming`).

The catalog is read at `GET /v1/admin/capabilities` (admin-gated, `apps/api/admin.py` L1019) and by
the admin agent's R0 tool. Scope is always `process` (this instance only).

The default composition root `apps/composition/runtime.py::build_runtime_profile` → `create_app(...)`
(L957–993) injects every seam listed below, so in the shipped profile all rows except
`execute.token_streaming` and the two env-gated rows are **available**.

## Capability table

| id | Deciding expression (`create_app`) | Composition key(s) → state in default profile | Missing-seam behaviour | Route(s) / admin control | What a builder can do today |
|---|---|---|---|---|---|
| `execute.sync` | `_cap("execute.sync", True, …)` | none — always mounted → **available** | n/a | `POST /v1/execute` (body `core/contracts/execute.py::ExecuteRequest`: `ask`, `mode`, `conversation_id`, `project_id`, `role`, `skills`, `model_policy`, `execution_policy`, `tools`, `context`, `output`, `webhook_url`; header `Idempotency-Key`). Bearer required (401 `unauthenticated`), tenant rate limit (429 `rate_limited`), budget (`entitlement_exceeded`). Admin: plans, routing weights, models. | Run one governed LLM execution with routing, budget, replay, audit and a typed report. |
| `execute.async` | `outbox is not None` | `outbox=` (InMemoryOutbox or BridgedOutbox when `DATABASE_URL`) → **available** | `execution_policy.async=true` ⇒ 400 `validation_error` "Async execution is not available on this deployment slice." (`details.field=execution_policy.async`) — never a silent sync fallback | `POST /v1/execute` with `execution_policy.async=true` ⇒ 202 `{status: queued, poll}`; `GET /v1/executions/{id}` to poll | Queue an execution and poll it. |
| `execute.token_streaming` | literal `CapabilityState.UNAVAILABLE` | none exists → **unavailable** | `execution_policy.stream=true` ⇒ 400 `validation_error` (`details.field=execution_policy.stream`) | none | Nothing — no streaming provider adapters exist (R115/V6-2 record). Placeholder. |
| `executions.progress_sse` | `sse` (bool) | `sse=True` → **available** | route absent (404) | `GET /v1/executions/{id}/events` (SSE) | Subscribe to progress events of an execution. |
| `conversations.persistence` | `conversations is not None` | `conversations=` (in-memory / Postgres under `DATABASE_URL`) → **available** | `conversation_id` is not persisted across calls; route set unchanged | `POST /v1/execute` `conversation_id` | Continue a conversation across executions. |
| `context.composition` | `composer is not None` | `composer=` → **available** | no context layering; the ask goes as-is | `POST /v1/execute` `context`; admin `GET /v1/admin/context-lab/checks`, `POST …/validate` | Have role/skills/memory/project context composed into the prompt with recorded budget checks. |
| `models.listing` | `models is not None and bindings is not None` | `models=`, `bindings=` → **available** | route absent (404) | `GET /v1/models` → `ModelsListResponse{models:[{id,name,tier,modalities,capabilities,availability}]}` (`core/contracts/model_listing.py`); admin `GET /v1/admin/models`, `/providers` | Enumerate active models with best-across-bindings availability — the pattern the A6 publish-mode list copies. |
| `skills.listing` | `_cap("skills.listing", True, …)` | always (SkillRegistry default) → **available** | n/a | `GET /v1/skills` → `SkillsListResponse` (selectable only) | Discover selectable skills and name them in `ExecuteRequest.skills`. |
| `usage.reporting` | `usage is not None` | `usage=` → **available** | route absent (404) | `GET /v1/usage` → tenant plan + budgets; unconfigured tenant ⇒ `entitlement_exceeded`; admin `GET /v1/admin/usage`, `/plans/{tenant}` | Read the caller tenant's plan and consumption. |
| `webhooks.registration` | `webhooks` (bool) | `webhooks=True` → **available** | routes absent (404) | `POST /v1/webhooks` (201), `GET /v1/webhooks`, `DELETE /v1/webhooks/{id}` | Register tenant webhook subscriptions for the six 10 §12 event types. |
| `webhooks.delivery_staging` | `webhooks and outbox is not None` | both → **available** | events not staged for delivery | staging via outbox (`execution.queued`) | Have execution events staged for delivery to registered webhooks. Delivery worker: `apps/api/worker.py`. |
| `admin.control_plane` | `admin is not None` | `admin=` (AdminSurface); admins are `ADMIN_EMAILS` (env, comma list) → **available**; with no admin emails every caller is 403 | `/v1/admin/*` absent (404) | `/v1/admin/*` (~60 ops; `apps/api/admin.py`): changes draft/validate/preview/publish/rollback, models, providers, plans, routing weights, evaluations, audit, usage, capabilities (+exercise), scenarios, context-lab, source-changes, system, engineering. Non-admin ⇒ 403 `unauthorized` + `permission_denied` audit row (R168 D-10/D-11). | Operate the platform: publish config changes (human act, INV-5), read audit, inspect catalog, propose/verify/approve source changes. |
| `learning.lifecycle` | `admin is not None and memory is not None` | `admin=`, `memory=` → **available** | `/v1/admin/learning/*` absent | `/v1/admin/learning/*` samples → evaluate/scan/sanitize/admit/promote; `learned`, `dashboard`, `ask` | Curate learning samples through a gated lifecycle; promotion is an admin act. |
| `rate_limits.execute` | `rate_limits is not None and execute_rate_limit > 0` | `rate_limits=InMemoryRateLimiter()` always; `EXECUTE_RATE_LIMIT` env (default `0`) → **inert** unless `EXECUTE_RATE_LIMIT>0` | no per-tenant execute limit enforced | `POST /v1/execute` ⇒ 429 `rate_limited` (retryable) when exceeded | Enforce a per-tenant execute rate once the operator sets `EXECUTE_RATE_LIMIT`. |
| `auth.sessions` | `auth is not None` | `auth=` → **available**; `DEV_DEMO_PRINCIPAL=1` (dev only, closed by default, R168 D-07) substitutes a demo principal | every tenant route ⇒ 401 `unauthenticated` (no fallback) | `/v1/auth/register` (201), `/verify`, `/login`, `/logout` (204), `GET /session`; `REGISTER_RATE_LIMIT` env | Register/verify/login; each user gets a personal tenant; bearer sessions for every other route. |
| `health.liveness` | `healthz` (bool) | `healthz=True` → **available** | route absent | `GET /healthz` → `{status: alive, scope: process, time}`; admin `GET /v1/admin/system` | Liveness probe for this process. |

### Exercise surface (real probes)
`GET /v1/admin/capabilities/exercisable` lists ids with a REAL probe; `POST /v1/admin/capabilities/{id}/exercise`
runs it against the composed machinery, billed to the caller's tenant (`apps/api/exercise.py`). A capability
without a probe is honestly not exercisable.

## Not capabilities (yet) — surfaces R169 adds beside the catalog

The 16-id set is closed by test; R169 does NOT extend it (extending it is a deliberate edit to
`capabilities.py`, counted against budget, and would require a catalog row for a seam the default
runtime does not compose). R169 delivers these as a separately composed **development-agent surface**
(`apps/agent_dev/`, INV-7) with its own tool registry; nothing is added to the admin agent:

| Surface | Contract | Tool ids (dev registry) | Notes |
|---|---|---|---|
| Bounded source WRITE | `core/contracts/source_write.py` (`SourceWriteOp`, `SourceWriteRefusalCode`, `SourceWriteResult`) | `source.write` | root jail per binding, denylist = reader's, byte/op caps, precondition (sha256) on overwrite/delete |
| Bounded source READ | existing `core/tools/source_reader.py` | `source.read` | unchanged module |
| Repository binding + GitHub | `core/contracts/repo_binding.py` (`RepoBinding`, `GitOperation`, `GitRefusalCode`) | `git.fetch`, `git.status`, `git.commit`, `git.publish` | token only via `SecretManagerPort.resolve(credential_ref)`; transport is a port (fake in tests) |
| Publish mode | `core/contracts/publish_mode.py` (`PublishMode`, `PublishModeOption`, `PublishModesResponse`) | recorded in every `git.publish` audit event | see list below |

### Publish modes (A6) — the list a UI dropdown binds to (never hard-code it)

Read endpoint: `GET /v1/dev/bindings/{binding_id}/publish-modes` (bearer; tenant-scoped; absent dev seam ⇒ 404).
Response `PublishModesResponse{default: "pull_request", modes: [PublishModeOption…]}` where each option is
`{id, label, description, selectable: bool, reason: str|null}` — same posture as `GET /v1/models`.

| id | label | description | selectable when |
|---|---|---|---|
| `dry_run` | Dry run | Compute the diff; write nothing to the remote | in binding `allowed_modes` (default set includes it) |
| `local_commit_only` | Local commit only | Commit in the binding's local root; never touch the remote | in `allowed_modes` |
| `pull_request` | Pull request | Push a work branch and open a PR against the bound branch (**default**) | in `allowed_modes` |
| `direct_push` | Direct push | Push to the bound branch | ONLY if explicitly in `allowed_modes`; otherwise `reason="direct_push_not_enabled_for_binding"` and a request naming it is refused with `publish_mode_not_allowed` (no downgrade, no silent push) |

Per-request override: `PublishRequest.mode` validated against `RepoBinding.allowed_modes`. Protected-branch
rejection by the remote ⇒ typed refusal `remote_rejected_protected_branch` with `suggested_mode="pull_request"`.
UI implementation is OUT OF SCOPE for R169; this table plus the endpoint is the binding surface for the UI round.
