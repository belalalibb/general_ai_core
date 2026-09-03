# QEVION R167-A — §4B Multi-account routing matrix

Mode OFFLINE-ENVELOPE ⇒ every row below is **[INJECTED]**: real `SimpleScoringRouter` + real
`ExecutionService` + real `InMemoryUsageAccounting`, with scripted adapters
(`tests/certification/test_r167a_routing_matrix.py`). Command and result:

```
env -u GSK_API_KEY -u GROQ_API_KEY python3 -m pytest -p no:cacheprovider -o addopts="" -q tests/certification -s
→ 17 passed
```

Rows are the `MATRIX|` lines printed by the harness, verbatim. Judged against
`evidence/provider_contract.md` (items 2, 4, 6, 7, 9, 10). Classes: (A) same provider+model,
multiple accounts; (B) different providers, same model; (C) different models; (D) different
tenant/app bindings.

| Case | Class | Credential logical id(s) used | Retries | Failover | Surfaced error | Contract trace | Binding preserved | Attribution | Duplicate billable? | Audit names credential? |
|------|-------|-------------------------------|---------|----------|----------------|----------------|-------------------|-------------|---------------------|--------------------------|
| A healthy | A | `secret-ref://A` | 0 | none | — | item 4, 9 | yes | tenant+execution; settled 1.0 | no | **no** (item 10: no field) |
| A restricted (Groq `organization_restricted` shape) → B | B | A, B | 0 (non-retryable) | A→B | none (B succeeded) | item 5 (ae295f6), 7 | yes | settled 1.0 | no | no |
| A retryable 429 / 5xx / timeout | B | A, B | 1 on A (`PROVIDER_MAX_RETRIES`) | A→B | none | item 6, 7 | yes | settled 1.0 | no | no |
| A credential fault, only A bound | A | A | 0 | **none available** | `invalid_credential` (run fails) | item 2, 7 | yes | failed 0.0 | no | no |
| A malformed request | — | A | 0 | **suppressed** (request-indicting) | `bad_request`; B never called | item 5 `_REQUEST_INDICTING` | yes | failed 0.0 | no | no |
| same model via B then C | B | A, B, C | 0 | A→B→C in Router order | none | item 4, 7 | yes | settled 1.0 | no | no |
| same model different provider, silent caller (AUTO) | B | A, B | 0 | A→B (default scope) | none | item 4 (cf37e69) | yes | settled 1.0 | no | no |
| model unavailable on bound account (`same_tier`) | C | A, B | 0 | A(model M)→B(other model) | none | item 3, 4 | model changed **by policy** (`same_tier` requested) | settled 1.0 | no | no |
| concurrent tenants while A degraded | D | A, B (shared) | 1 per tenant | A→B per tenant | none | item 9 | yes | each tenant exactly 1.0; distinct `tenant_id` | no | no |
| two credentials, same provider | A | — | — | — | — | item 2 | — | — | — | **NOT SUPPORTED BY CURRENT CONTRACT** — `credential_refs` is 1:1 per `provider_id`; second dict write overwrites; `ProviderRegistry.register` raises `DuplicateRegistration` for a repeated `provider_key` |
| credential missing for a routed provider | — | — | — | — | `CredentialNotConfigured` before any call | item 3 `_validate_route` | — | no reservation | no | — |
| model not bound anywhere | — | — | — | — | `NoEligibleCandidates` at routing | item 4 | — | no reservation | no | — |

## Findings (absence is a valid finding; nothing manufactured)

- **M-1 [INJECTED→VERIFIED by contract]** Class A (multi-account, same provider) has no
  executable strategy: contract items 2/7. Recorded as ABSENCE → `defect_ledger.md` D-03
  (S3, architecture limitation, HANDOFF).
- **M-2 [VERIFIED]** No row can satisfy "audit names the credential": `AttemptRecord` /
  `TraceAttempt` carry `provider_key`+`model_key` only; `PROVIDER_ACCOUNT_USED` has no
  emitter (item 10) → D-04 (S3).
- **M-3 [INJECTED]** Class D holds: two tenants sharing the same degraded provider are billed
  exactly one unit each; no cross-tenant retry state exists to leak because no health state
  exists at all (item 8) — the same absence that prevents cooldown also prevents leakage.
- **M-4 [INJECTED]** `bad_request` correctly suppresses failover; combined with D-02 (a
  proxy's model-not-allowed 400 has no `error.code` and lands as `bad_request`) this means a
  model-availability problem on a provider that omits `error.code` will *never* fail over.

## Live cross-check

The single live row available (`evidence/tasks/15_developer_transcript.log` §10: explicit
model + `max_escalation`, one provider bound → fast fail) matches injected row 4 exactly
[CAPTURED vs INJECTED agree].
