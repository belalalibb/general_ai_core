# QEVION R167-A — §4D Error classification map

Source of truth: the shipped normaliser `providers/real/groq/adapter.py::_normalize_http_response`
L394-470 (also the family used by the OpenAI-compatible `genspark_llm` adapter) and
`core/execution/service.py::_REQUEST_INDICTING` L124-129. Real shapes live in
`evidence/failure_shapes/` (one redacted response per shape). Each real shape was **replayed
through the shipped adapter over `httpx.MockTransport`** by
`tests/certification/test_r167a_routing_matrix.py::test_shape_*`; the resulting category is
the `MAP|` line, not a reading of the code. Misclassification threshold per contract: ≥ S2.

## Real captured shapes → category → downstream behaviour

| Shape file | Provider | HTTP | Body discriminator | Category (replayed) | retryable | Retry? | Failover? | Judgement |
|------------|----------|------|--------------------|---------------------|-----------|--------|-----------|-----------|
| `groq_400_organization_restricted.json` | groq | 400 | `error.code=organization_restricted` | `invalid_credential` | False | no | **yes** | CORRECT (fixed in ae295f6; before that: `bad_request`, no failover) [CAPTURED+INJECTED] |
| `genspark_llm_invalid_credential.json` | genspark proxy | 401 | `{"detail":"Invalid or expired token"}` (no `error` object) | `invalid_credential` | False | no | yes | CORRECT — status-driven; body shape irrelevant [CAPTURED+INJECTED] |
| `genspark_llm_unknown_model.json` | genspark proxy | 400 | `{"detail":"Model '…' is not allowed. See GET /v1/models…"}` (no `error.code`) | `bad_request` | False | no | **no** (request-indicting) | **MISCLASSIFIED — D-02, S2.** Semantically `model_unavailable` (should fail over to a provider that has the model). The normaliser only reads `error.code`/`error.param`; the proxy uses FastAPI's `detail`. [CAPTURED+INJECTED] |
| `genspark_llm_200_plan_refusal.json` | genspark proxy | 200 | `choices[0].message.content` = "Free-plan credits can't be used…" | **none — success** | — | no | no | **UNCLASSIFIABLE — D-01, S2.** No seam exists for an in-band refusal; booked as a successful, billable completion; agent then fails `invalid_proposal`; diagnosis says "no provider error was recorded". [CAPTURED live + INJECTED] |

## Injected categories (§9 fault classes) → contract behaviour

Reproduced by the matrix harness with scripted `ProviderError`s (no real provider involved):

| Injected category | retryable | ExecutionService behaviour | Matrix row |
|-------------------|-----------|----------------------------|------------|
| `invalid_credential` | False | no retry, failover | A_restricted_B_healthy, A_credential_fault_only_A |
| `rate_limited` (+`retry_after_ms`) | True | sleep `retry_after_ms` (≤ 60 s cap) then retry ≤ `PROVIDER_MAX_RETRIES`, then failover | A_retryable_429_5xx, concurrent_tenants |
| `retryable_server_error` | True | retry then failover | A_retryable_429_5xx |
| `provider_unavailable` | False | failover | same_model_via_B_then_C |
| `model_unavailable` | False | failover | model_unavailable_on_bound_account |
| `bad_request` | False | **stop**: no retry, no failover | A_malformed_request |
| `content_rejected` | False | stop (existing test `test_content_rejected_is_never_shopped_to_another_provider`) | — |
| `timeout` | adapter-decided | same path as retryable_server_error when `retryable=True` | (covered by category, not separately scripted) |
| raised exception from adapter | — | normalised via `adapter.normalize_error`, never re-raised (existing test) | — |

## Status-only table of the shipped normaliser (read, [VERIFIED] L394-470)

| Condition | Category |
|-----------|----------|
| 400 + `error.param=response_format` | `unsupported_capability` |
| 401 / 403, or `error.code ∈ {organization_restricted}` | `invalid_credential` |
| 429 | `rate_limited` (retry-after honoured) |
| 404 | `model_unavailable` |
| 400 + `error.code ∈ {json_validate_failed, tool_use_failed}` | `retryable_server_error` |
| 400 / 413 / 422 with "content" in `error.code` | `content_rejected` |
| 400 / 413 / 422 otherwise (incl. **no `error` object at all**) | `bad_request` |
| 500 / 502 / 503 / 504 | `retryable_server_error` |
| other | `non_retryable_error` (L463+) |

## Gaps (ledger entries)

- **D-01** in-band 200 refusal → success (S2). Absence of a concept; not fixed this round (§16: no
  new abstraction inside a certification round). HANDOFF with the captured shape.
- **D-02** `detail`-only 400 model-not-allowed → `bad_request` (S2 misclassification). A fix
  would be a normaliser edit, which §6 permits only for a §4A contract defect; item 5 lists
  the taxonomy as VERIFIED and this is a *provider-shape coverage* gap, so it is recorded
  with a fail-first test candidate for R168 rather than patched under certification.
