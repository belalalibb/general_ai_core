# R174 §1 — Read & reconcile: AssemblyAI LLM Gateway vs. the repo's external-provider reference

Sources read in full (repo): `gateway-service/docs/CONTRACT.md`, `gateway-service/docs/ONBOARDING.md`,
`gateway-service/gateway/{contracts,provider_registry,route_registry,discovery,config,credentials,context,routes}.py`,
`gateway-service/app.py`, `providers/_template/*`, `providers/_example/*`, `providers/groq/*` (all 4 files),
`providers/real/gateway/adapter.py` (RemoteGatewayAdapter), `apps/composition/{gateway,provider_onboarding,runtime}.py`,
`apps/api/provider_onboarding.py`, `core/providers/registry.py`, `core/routing/router.py` (binding selection),
`tests/providers/test_gateway_groq_live_e2e.py`, `docs/OPERATIONS.md §7`, `RUN.md`.
Sources read (AssemblyAI, fetched 2026-09-05, copies in this folder): create-chat-completion OpenAPI 3.1,
available-models, quickstart.

## A. What AssemblyAI actually supports (their reference, not assumed)

| Fact | Value |
|---|---|
| Base URL | `https://llm-gateway.assemblyai.com/v1` (EU: `llm-gateway.eu.assemblyai.com`) |
| Endpoint | `POST /chat/completions` — the ONLY documented LLM endpoint; no `/models` listing endpoint |
| Auth | `securitySchemes.ApiKey: {type: apiKey, in: header, name: Authorization}` — quickstart sends the RAW key as `Authorization: <key>` (no `Bearer`). OpenAI-SDK tab implies `Bearer <key>` is also accepted — VERIFY LIVE (§2) |
| Request | `model` (required); `messages[{role,content}]` or `prompt`; `max_tokens` (int ≥1, default 1000); `temperature` (0..2); `stream` (OpenAI models only); `tools/tool_choice/response_format`; `fallbacks`, `fallback_config{retry: default TRUE, depth}`; `post_processing_steps`; `transcript_id`; `model_region` |
| Success body | `{request_id, choices[{message{role,content,tool_calls}, finish_reason}], request{...}, usage{input_tokens,output_tokens,total_tokens}, http_status_code, response_time(ns), llm_status_code}` |
| Error body | `{code:int, message:str, request_id, metadata?{errors[]}}` — **NOT** the OpenAI `{error:{code,type,message}}` shape |
| Models (subset) | `qwen3.5-4b-32k-fast` (AssemblyAI-hosted, 32768 ctx, $0.1/$0.5 per M — cheapest), `gemini-2.5-flash-lite` (1,048,576 ctx), `gpt-oss-20b`, `gpt-oss-120b`, `qwen3-32B`, Claude/GPT families |

Shape deltas vs. Groq (OpenAI-compatible) that a facade must translate — none of them is a contract problem:
1. Auth header form (raw key vs `Bearer`) — Layer 1.
2. Usage keys `input_tokens/output_tokens` (Groq: `prompt_tokens/completion_tokens`) — Layer 1 → canonical `Usage` unchanged.
3. Error body is flat `{code,message}`; safe `provider_code` = `str(code)` — Layer 1.
4. `max_tokens` (Groq: `max_completion_tokens`) — Layer 1.
5. **`fallback_config.retry` defaults to TRUE upstream** (auto-retry once after 500 ms on failure). CONTRACT: "any provider-internal retry is subject to the gateway's rules — v1 = ZERO gateway-level retries (billing integrity)". Decision (standing authority): the facade sends `fallback_config: {retry: false}` explicitly so one canonical request ⇒ at most one billed upstream attempt. Logged here; reversible by one literal.
6. `finish_reason` free string (examples: `stop`) → mapped conservatively like Groq (`stop|length|content_filter→filter`, else `stop`).

Everything AssemblyAI offers beyond `generate_text` (tools, structured output, transcript injection, fallbacks)
is OUTSIDE the canonical `generate_text` payload (`messages/temperature/max_tokens` only) — declared honestly as
not supported (deny-by-default). AssemblyAI STT is a separate API and is NOT this provider.

## B. Repo reference as it stands — and where it contradicts itself

| # | Claim (docs) | Code (wins) | Consequence for "same door" |
|---|---|---|---|
| F-1 | `provider_registry.py` docstring + ONBOARDING.md: "Auto-discovery of packages under `providers/`… `_`-prefixed skipped"; template README: "Touch nothing outside your folder" | There is NO discovery code anywhere in `gateway/`. `app.py::register_live_providers` hard-codes `registry.register("groq", …)`. | Every new provider needs ONE line in `gateway-service/app.py`. Not core/, not AssemblyAI-specific (Groq has the identical line) — but the runbook's promise is false. Report; do not smooth over. |
| F-2 | CONTRACT/ONBOARDING: two credential modes, `user_key` (BYOK) fully specified; `GatewayOnboardRequest.credential_mode` accepts `"user_key"` | `apps/composition/provider_onboarding.py::adapter_from_definition` never passes `user_key_resolver`; `RemoteGatewayAdapter.__init__` raises `ValueError("user_key credential mode requires a user_key_resolver")`. | A `user_key` provider onboarded through the real admin route/hydration cannot be constructed. **To test on purpose (§4).** For the proof, AssemblyAI goes in as `platform` mode (`GW_ASSEMBLYAI_API_KEY` at the gateway) — the same mode Groq used, so the comparison is apples-to-apples. |
| F-3 | OPERATIONS §7 / ONBOARDING platform steps: admin onboards with `route_token_ref`; "the platform generates the route_token (sole issuer); operator provisions it out-of-band into the gateway route map" | `runtime.py:747` `onboarding_secrets = InMemorySecretManager()` — a FRESH empty manager; **no code path anywhere stores a route token into it** (only `runtime.py:564` stores env provider keys, into a DIFFERENT manager). No env seam, no admin route. So in the real `apps.main` process, `route_token_ref` can never resolve ⇒ `SecretNotFound` at the first gateway call. | **Predicted break of the last link** (platform process → gateway process). Hermetic tests pass because they build their own manager and `.store()` into it. **Must be confirmed live (§4) before it is called a break.** |
| F-4 | check_repo.sh is "the verifier" | Its pytest slices cover `tests/**` only; `gateway-service/tests/` (57 tests incl. groq facade) is NOT gated. | Pre-existing; any gateway provider I add is outside the floor unless a slice is added — noted for closure, not fixed silently. |
| F-5 | `providers/README.md`: "No real providers exist yet" | `_pending_real_providers.md` lists two verified real providers + the gateway route. | Stale doc; cosmetic. |

## C. Model-name collision surface (deliberate check design)

- Gateway: `RequestEnvelope.model` is an opaque string passed upstream verbatim; the provider is selected ONLY by
  `X-Route-Token → slug` (`route_registry`). The gateway never inspects `model` to route. Two slugs may declare the
  same model name (`DeclaredModel.name` is per-DEFINITION, no global index).
- Platform: `ModelRegistry` keys by `model_key` (globally unique), `BindingRegistry` by `(provider_id, model_id)`;
  `provider_model_name` is a per-binding fact. The router iterates bindings of a model and narrows by explicit
  `provider_id` (11 §14 rule 4). The wire `model` = `binding.provider_model_name`, so two providers may carry the
  same upstream name for one platform Model, or for two Models — no lookup is keyed by the upstream model name.
- Onboarding auto-discovery mints `model_key = f"{prefix}/{provider_model_name}"` (`core/providers/onboarding.py:265`)
  — need to confirm `prefix` is the provider_key (else two providers discovering `gpt-oss-20b` would collide on
  `model_key`). **Test on purpose (§5):** two gateway slugs, same declared model name; two platform providers, one
  Model, same `provider_model_name`; explicit provider selection must land at the intended slug both ways.

## D. What "the whole chain" means for this round (and what does NOT count)

```
apps.main (platform process, port 8000)
  POST /v1/execute → Router → ExecutionService → ProviderAdapterPort (core/providers/ports.py)
    → RemoteGatewayAdapter (providers/real/gateway) → TCP → gateway-service (uvicorn, port 8800)
      → routes.execute → route_registry (token→slug) → providers/assemblyai facade (Layer 2)
        → _upstream (Layer 1) → HTTPS llm-gateway.assemblyai.com/v1/chat/completions
```
- Counts as proof: a real `POST /v1/execute` on the platform process that returns model text produced by
  AssemblyAI, with usage settled, key/route-token/slug absent from every response body.
- Does NOT count: `curl` against the gateway on 8800 (proves the gateway only); a pytest that builds the world
  in-process with its own secret manager (proves the adapter, not the composition).
- The in-process pytest variant is still recorded (as `tests_live/r174/…`, env-gated) because it is the
  reproducible artifact; the verdict rests on the two-process run.

## E. Decisions taken under standing authority (logged)
1. Credential mode `platform` for the proof (parity with Groq; F-2 makes `user_key` untestable through the real
   door until fixed — which is itself a finding, tested separately).
2. `fallback_config.retry=false` sent by Layer 1 (billing integrity, CONTRACT one-request-one-response).
3. Declared models: `qwen3.5-4b-32k-fast` (cheapest, AssemblyAI-hosted) and `gemini-2.5-flash-lite` only — the two
   the live proof actually exercises (Groq precedent: declare what you exercise).
4. Env var name at the gateway: `GW_ASSEMBLYAI_API_KEY` (mirrors `GW_GROQ_API_KEY`). Name public, value never printed.
