# QEVION R167-A — §4C Credential binding boundary (S1 class)

## §4C.2 decision — by citation only

Question: does the current contract let application/tenant X be bound to credential K_x of
provider P such that a request from X can never be served with K_y (another application's
credential for the same P), including under retry, failover and concurrency?

Citations (all `[VERIFIED]`, HEAD `b3bacf5`, see `evidence/provider_contract.md`):

1. `apps/composition/runtime.py::_bind_real_providers` L498-571 — credentials are read from
   process environment (`GROQ_API_KEY`, `GSK_API_KEY`), stored once under a single
   `platform_tenant = uuid4()` custody scope, and written to `credential_refs[provider.id]`.
2. `core/execution/service.py` L242, L509 — `credential_refs: Mapping[UUID, str]` keyed by
   `provider_id` only; `_run_node` selects `self._credential_refs[candidate.provider_id]`
   with no reference to `tenant_id`, `user_id`, application, or request.
3. `core/routing/router.py` L408 — `CandidateScore.account_id=None` always; the Router never
   selects among accounts.
4. `core/providers/accounts.py::AccountPoolManager` — the only code that models
   owner-scoped credentials — has **no call site** in `apps/` or the execution path.
5. `core/contracts/execute.py` `ExecuteRequest` (L54-135) — no credential / account / binding
   field; `ModelPolicy` variants carry `model_id`, optional `provider_id`, fallback fields only.
6. No admin route creates, lists, or binds credentials: `/v1/admin/providers` onboarding
   (present only with `GATEWAY_BASE_URL`) validates one credential per provider
   (`core/providers/onboarding.py` L203) and still lands it in the same per-provider map.

Conclusion: the concept "credential bound to an application/tenant" does not exist on any
executed path. There is exactly one credential per provider per process, shared by every
tenant and application.

## Outcome (verbatim §4C.1 vocabulary)

**NOT SUPPORTED BY CURRENT CONTRACT** → ARCHITECTURE LIMITATION, severity **S3** (not S1:
an S1 would require a binding that *exists* and is *violated*; here no binding can be
expressed, so no request can be mis-served relative to a stated binding, and cross-tenant
leakage of the shared credential's *value* is separately prevented — see
`defect_ledger.md` D-05/D-06 containment probes).

Execution status: **NOT EXECUTABLE — CONTRACT ABSENT** (§5.0.7b). The two-placeholder
probe that §5.0.7c asks for in OFFLINE mode was still run as far as the contract allows
(`case_two_credentials_same_provider`): a second credential for the same provider either
overwrites the first (`dict` write) or is refused (`DuplicateRegistration`). No fallback,
pooling, or binding was manufactured to make it pass (§16).

## What IS held today [INJECTED + VERIFIED]

- Tenant isolation of *usage/attribution*: each tenant's reservation and settlement are keyed
  by its own `tenant_id` (matrix row "concurrent tenants").
- Containment of the shared credential value: only the opaque `credential_ref` travels in
  `ProviderGenerateRequest`; the value is resolved inside the adapter via `secret_resolver`
  and never appears in `AttemptRecord`, trace, error, or ledger (see D-05 probe results).

## HANDOFF to R168 (design, not implemented here)

The contract entities already exist (`Credential`, `ProviderAccount`, `OwnerType`,
`CredentialPolicy`, `AccountPoolManager` with 7 eligibility filters and LRU + lease). What is
missing is (i) a composition path that populates pools from something other than a single env
var, (ii) a per-request `CredentialPolicy`/owner scope carried from `ExecuteRequest` through
`RoutingRequest` into `ExecutionService`, and (iii) `account_id` populated on
`CandidateScore` so `AttemptRecord`/`TraceAttempt` can name the account. Until then §4C
must be re-evaluated, not re-asserted.
