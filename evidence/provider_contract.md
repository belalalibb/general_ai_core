# QEVION R167-A — §4A Provider contract (as implemented at `b3bacf5`)

Sole baseline for judging routing/credential/error defects in this round. Every item is
either `[VERIFIED file::symbol Lnn]` (read at HEAD `b3bacf5`, line numbers current) or the
literal phrase **NOT PRESENT IN CODE**. Nothing here is aspirational; docs are not cited as
evidence of behaviour.

## 1. Provider identity model

- Entity: `core/contracts/domain.py::Provider` L226-234 — `id: UUID`, `provider_key`,
  `display_name`, `status: ProviderStatus`, `auth_types`, `supports_account_pool: bool` [VERIFIED].
- Registry key = `provider_key` string; `RegisteredProvider.is_routable` =
  `status is ACTIVE and manifest.is_functional and not is_template`
  (`core/providers/registry.py` L80-91) [VERIFIED].
- Composition creates exactly one `Provider` per configured env key with a fresh `uuid4()` at
  process start; `supports_account_pool=False` hard-coded
  (`apps/composition/runtime.py::_bind_real_providers` L498, loop L544-556) [VERIFIED].
- Identity is therefore **process-scoped**: `provider.id` changes every restart; only
  `provider_key` is stable. Consequence for audit: traces name `provider_key`
  (`apps/admin_agent/service.py::_trace_report` L604-612) [VERIFIED].

## 2. Credential model

- Contract entities exist: `Credential` (`domain.py` L254-263: `owner_type`, `owner_id`,
  `provider_id`, `credential_ref`, `status`) and `ProviderAccount` (L266-279:
  `credential_id`, `lifecycle_state`, `health_state`, `cooldown_until`) [VERIFIED].
- Pool machinery exists: `core/providers/accounts.py::AccountPool` L88,
  `AccountPoolManager.eligible_accounts` L201-256 (7 filters), `select_account` L258,
  `acquire_account` L281 (leased) [VERIFIED].
- **Wiring:** `AccountPoolManager` / `ResourceSelector` are re-exported
  (`core/providers/__init__.py` L11, `core/routing/__init__.py` L18) but **no call site exists
  in `apps/` or `core/execution`, `core/agent`, `core/routing/router.py`**
  (`grep -rn "AccountPoolManager\|ResourceSelector\|select_account\|acquire_account" apps core`
  → only the defining modules and `__init__` re-exports) [VERIFIED].
- Live credential path: env var → `InMemorySecretManager.store(platform_tenant, key)` →
  opaque `credential_ref` → `credential_refs[provider.id] = ref` (`runtime.py` L516-547, L571) → `ExecutionService(credential_refs=Mapping[UUID,str])`
  (`core/execution/service.py` L242, L265) → `_run_node` L509
  `credential_ref = self._credential_refs[candidate.provider_id]` [VERIFIED].
- Ownership: `platform_tenant = uuid4()` is the sole custody scope (`runtime.py` L516);
  `OwnerType`/`CredentialPolicy` (`domain.py` L91-116) are never consulted on the execution
  path [VERIFIED].
- **Per-tenant / per-application / per-request credential binding: NOT PRESENT IN CODE.**
  One credential per provider per process; `ProviderGenerateRequest.account_id` is always
  `None` because the Router emits `account_id=None` (`core/routing/router.py` L408) [VERIFIED].

## 3. Model resolution

- `Model` entity `domain.py` L202-223 (`model_key`, `tier`, `status`, scores);
  `ProviderModelBinding` L237-251 (`provider_model_name`, `availability`) [VERIFIED].
- Composition registers each configured model name at `ModelTier.MEDIUM` and binds it to the
  provider (`runtime.py` L558-562 `_model(name, tier=MEDIUM)`; bindings.register) [VERIFIED].
- Router candidate build: model active in tier + provider routable + binding not UNAVAILABLE;
  DEGRADED binding is admitted with a recorded risk (`router.py` L330-358) [VERIFIED].
- Execution resolves `provider_model_name` from `bindings.get(provider_id, model_id)`
  (`service.py` L508, L517) and pre-validates every routed candidate has adapter + credential
  + binding before work starts (`_validate_route` L631-643) [VERIFIED].

## 4. Selection / routing

- Entry: `Router.route(RoutingRequest)`; scoring weights `core/contracts/routing.py::ScoringWeights`
  L58-72; result `RoutingDecision{selected, ranked, fallback_candidates, excluded,
  fallback_policy}` L121-143 [VERIFIED].
- Fallback scope resolution `router.py::_resolve_fallback_scope` L433-445: `allow_fallback=False`
  → NONE; explicit scope honoured; silent caller → `SAME_MODEL_DIFFERENT_PROVIDER` (cf37e69)
  [VERIFIED]. Candidate expansion `_fallback_candidates` L447+ handles NONE /
  ADMIN_DEFINED_CHAIN / SAME_MODEL_DIFFERENT_PROVIDER / SAME_TIER /
  LOWER_COST_SAME_CAPABILITY / MAX_ESCALATION [VERIFIED].
- Selection granularity is **(model, provider)**. Account-level selection (multiple credentials
  for one provider): **NOT PRESENT IN CODE** on the executed path (see item 2).

## 5. Error taxonomy

- `core/contracts/provider.py::ProviderErrorCategory` L310-324 — 12 closed values:
  auth_expired, invalid_credential, rate_limited, quota_exceeded, model_unavailable,
  provider_unavailable, unsupported_capability, bad_request, content_rejected, timeout,
  retryable_server_error, non_retryable_error [VERIFIED].
- `ProviderError` L327-338: `category`, `retryable`, `retry_after_ms`, `provider_code`,
  `safe_message` [VERIFIED].
- Groq mapping `providers/real/groq/adapter.py::_normalize_http_response` L390-460, with
  `_ACCOUNT_INDICTING_CODES = {"organization_restricted"}` (ae295f6) [VERIFIED].
- Request-indicting set (no retry, no failover): `core/execution/service.py::_REQUEST_INDICTING`
  L124-129 = {BAD_REQUEST, CONTENT_REJECTED} [VERIFIED].
- **Semantic-failure-inside-HTTP-200 detection (provider returns a refusal string as the
  assistant message): NOT PRESENT IN CODE.** `_run_node` treats `response.succeeded=True` as
  terminal success (L534-535); see `evidence/failure_shapes/genspark_llm_200_plan_refusal.json`.

## 6. Retry semantics

- Same-candidate bounded retry: `while attempt <= self._max_retries` (`service.py` L511);
  `max_retries_per_candidate` default 1 (L244), env `PROVIDER_MAX_RETRIES`
  (`runtime.py` L611, L701) [VERIFIED].
- Retry only if `error.retryable`; honours `retry_after_ms` by sleeping, **unless** it exceeds
  `max_retry_wait_ms` (default 60 000 ms, L138) in which case the candidate is abandoned and
  failover proceeds (L540-553) [VERIFIED].
- Retryability is decided solely by the adapter's `ProviderError.retryable`; no
  service-side backoff/jitter policy: **NOT PRESENT IN CODE** (sleep is exactly
  `retry_after_ms`, or none).

## 7. Failover scope

- Route order = `[decision.selected, *decision.fallback_candidates]`, never re-scored
  (`service.py` L502) [VERIFIED].
- Failover occurs on any non-request-indicting failure after the retry budget is spent, or
  immediately on non-retryable errors (L537-556 `break`) [VERIFIED].
- Failover unit is the next **(model, provider)** candidate. Failover to a second credential
  of the same provider: **NOT PRESENT IN CODE**.
- Live consequence: with one provider bound, `fallback_candidates=[]` and
  `max_escalation` cannot widen anything (`evidence/tasks/15_developer_transcript.log` §10) [CAPTURED].

## 8. Health / cooldown / circuit state

- Contracts exist: `ProviderHealth` L254-265, `CredentialHealth` L355-365,
  `RateLimitStatus{state, cooldown_until}` L280-294, `ProviderAccount.cooldown_until` [VERIFIED].
- `validate_credential` and `health_check` are invoked **only** in the admin onboarding flow
  (`core/providers/onboarding.py` L203, L218) — never on the execution path; the composition's
  health callable returns `CredentialStatus.ACTIVE` unconditionally for the local-echo adapter
  (`runtime.py` L346) [VERIFIED].
- The Router consults `binding.availability` (static registry state, admin-settable via
  `replay_admin_status_overrides`, `apps/composition/provider_onboarding.py` L274) but no
  runtime-derived health signal [VERIFIED].
- **Failure-driven cooldown / circuit breaker / health-state mutation from execution
  outcomes: NOT PRESENT IN CODE.** A `rate_limited` or `invalid_credential` result does not
  change any future routing decision; each execution re-tries the same route.

## 9. Cost / quota attribution identity

- Reservation/settlement keyed by `(tenant_id, execution_id)`:
  `UsageLedger{tenant_id, execution_id, units_reserved, units_settled, modality_costs}`
  (`core/contracts/usage.py` L47-56); `InMemoryUsageAccounting.reserve/settle/fail`
  (`core/usage/memory.py` L104-160) [VERIFIED].
- Settled units = `units_per_stage × SUCCEEDED stages`; raw provider usage stored as
  `modality_costs.provider_usage = [{node_key, usage}]` (`service.py` L441-455) [VERIFIED].
- Crash mid-execution resolves the reservation as failed with 0 units before re-raising
  (L429-435) [VERIFIED].
- Attribution to **provider, model, credential or account: NOT PRESENT IN CODE** in the
  ledger. `provider_usage` entries carry `node_key` only; the (provider, model) is recoverable
  by joining the trace, the credential/account is not recorded anywhere.

## 10. Audit record per external call

- `AuditEventType` (`core/contracts/audit.py` L49-70) includes `PROVIDER_ACCOUNT_USED`
  [VERIFIED], but `grep -rn PROVIDER_ACCOUNT_USED core apps` finds **no emitter** outside the
  contract module → **per-external-call audit event: NOT PRESENT IN CODE**.
- What does exist per attempt: `AttemptRecord{node_key, candidate(model_id, provider_id,
  account_id=None), attempt, succeeded, error, latency_ms}` (`service.py` L161-169), kept in
  the stored `ExecutionReport` and rendered by `GET /v1/agent/executions/{id}/trace` as
  `TraceAttempt{model_key, provider_key, error_category, safe_message, latency_ms}`
  (`apps/admin_agent/service.py` L607-618) [VERIFIED]. It does **not** name the credential
  (no field exists) — audit-names-credential requirement of §4B is structurally unmeetable.
- Operator log: Groq adapter emits `groq_http_error status= type= code= param=`
  (`providers/real/groq/adapter.py::_safe_error_code` L581) through the structlog scrubber
  (`apps/observability/logs.py::scrub_secrets` L25) [VERIFIED].

## Summary table

| # | Item | Status |
|---|------|--------|
| 1 | Provider identity | VERIFIED — process-scoped UUID, stable `provider_key` |
| 2 | Credential model | VERIFIED env→secret_ref, one per provider; per-app/tenant binding NOT PRESENT IN CODE |
| 3 | Model resolution | VERIFIED |
| 4 | Selection/routing | VERIFIED at (model, provider); account-level NOT PRESENT IN CODE |
| 5 | Error taxonomy | VERIFIED 12 categories; in-band 200 refusal detection NOT PRESENT IN CODE |
| 6 | Retry semantics | VERIFIED bounded, adapter-decided; backoff policy NOT PRESENT IN CODE |
| 7 | Failover scope | VERIFIED (model, provider); same-provider credential failover NOT PRESENT IN CODE |
| 8 | Health/cooldown/circuit | contracts VERIFIED; runtime mutation from failures NOT PRESENT IN CODE |
| 9 | Cost/quota attribution | VERIFIED (tenant, execution); provider/credential attribution NOT PRESENT IN CODE |
| 10 | Audit per external call | attempt trace VERIFIED; audit event emitter NOT PRESENT IN CODE; credential never named |

## §5.0.7b consequence

Credential injection is env-var-only (item 2). Ledger entry: **no per-application credential
binding exists** → §4C outcome 3, **NOT EXECUTABLE — CONTRACT ABSENT**.
