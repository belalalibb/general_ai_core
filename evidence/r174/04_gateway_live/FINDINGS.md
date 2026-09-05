# R174 §4 — Live E2E through the gateway process (AssemblyAI, real key)

Date: 2026-09-05 · HEAD at start: 9c689e7 · Gateway: `python app.py` (uvicorn 127.0.0.1:8800)

## Setup (what was in the environment, and where)

| thing | where | ever in repo / evidence? |
|---|---|---|
| AssemblyAI key | `GW_ASSEMBLYAI_API_KEY` in the **gateway process env only** | no — grep for 32-hex in all evidence + gateway log = 0 |
| Gateway secret | `GW_SECRET_CURRENT=r174-local-gw-secret` (throwaway) | redacted in evidence; asserted absent |
| Route map | `GW_ROUTE_MAP=rt_aai_r174:assemblyai,rt_groq_r174:groq` | tokens are opaque; the slug never crosses the wire |
| Caller | `probe.py` — knows ONLY the gateway secret and the route token | identical position to the platform's RemoteGatewayAdapter |

Paid upstream calls: **2** (budget ≤3). Free control calls: 2.

## Results — 10/10 checks PASS (`checks.json`)

### A — success, `qwen3.5-4b-32k-fast` → `A_success.json`
```
200  succeeded=true  output.text="pong"  finish_reason="stop"
usage.input_tokens=19  output_tokens=2  units=1  latency_ms=410  error=null
```
The response is the **canonical ResponseEnvelope** — no `choices[]`, no AssemblyAI
field names, no upstream request id. Layer 2 did its job.

### B — unknown model → `B_unknown_model.json`
```
200  succeeded=false  error.category="model_unavailable"  retryable=false
error.message="model is not supported by the provider"  provider_code="unsupported_model"
```
Matches §2 live probe #3 (upstream `400 + "... is not supported"`) → Layer 1
`unsupported_model` → Layer 2 `model_unavailable`. The upstream's raw message (which
names the model and lists alternatives) does **not** cross; only the fixed safe
message does. `provider_code` is a sanitized short token per CONTRACT §error.

### C — wrong route token → `C_bad_route_token.json`
```
404  error.category="provider_unavailable"  message="unknown route"
```
No upstream call was made (gateway log shows the 404 with no provider activity).
Route addressing exists only via the header; there is no URL path to a provider.

### D — describe → `D_describe.json`
```
200  display_name="AssemblyAI LLM Gateway"  credential_mode="platform"
operations=["generate_text"]  models=[qwen3.5-4b-32k-fast/32768, gemini-2.5-flash-lite/1048576]
health_supported=false
```
The manifest projection never mentions the slug, the upstream URL, or the key env var.

## What this proves for the R174 question

1. **The second provider went through the SAME door as the first.** Zero changes to
   `gateway/` (contract, routes, auth, registry) were needed. The registration is one
   line in `app.py`. `git diff 3d1ede4..HEAD --stat -- gateway-service/gateway/` = empty.
2. **The key never leaves the gateway.** The caller cannot supply, see, or infer it
   (credential mode `platform`; a `user_key` envelope would be rejected as
   `bad_request` before any upstream call — covered hermetically in test_assemblyai.py).
3. **Errors are canonical end-to-end live**, not just in mocks: the live bad-model
   body shape from §2 produced exactly the category the hermetic tests predicted.

## What this does NOT yet prove (→ §5)

- The **platform → gateway** link (`providers/real/RemoteGatewayAdapter` → core port).
  §4 stood in the adapter's shoes with a hand-built envelope; §5 must drive it from
  the platform's own code path with the platform's own envelope builder, and check
  the F-2/F-3 findings from §1 (route-token config surface; two providers exposing
  the same model name without collision).

## Reproduce
```
cd gateway-service
export GW_ASSEMBLYAI_API_KEY=<key> GW_SECRET_CURRENT=<any> GW_SECRET_CURRENT_VERSION=1 \
       GW_ROUTE_MAP=rt_aai_r174:assemblyai
.venv/bin/python app.py &
GW_SECRET_CURRENT=<same> .venv/bin/python ../evidence/r174/04_gateway_live/probe.py
```
