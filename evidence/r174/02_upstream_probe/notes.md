# §2 Direct upstream probe — llm-gateway.assemblyai.com (2026-09-05)

4 calls, key only ever in an env var / header; bodies grep-verified key-free before commit.

| probe | auth header | model | HTTP | body facts |
|---|---|---|---|---|
| p1 | `authorization: <raw key>` (documented) | qwen3.5-4b-32k-fast | 200, 0.33 s | `choices[0].message.content="OK"`, `finish_reason="stop"`, usage `input_tokens=19 output_tokens=2` (ALSO `prompt_tokens/completion_tokens` duplicates), `http_status_code=200`, `llm_status_code` |
| p2 | `authorization: Bearer <key>` | same | 200 | identical shape — both forms accepted; facade uses the DOCUMENTED raw form |
| p3 | 32 zeros | same | **401** | `{"error": "Authentication error, API token missing/invalid", "status": "error", "request_id"}` — a shape NOT in the OpenAPI (`ErrorResponse` says `{code,message,request_id}`) |
| p4 | real key | `no-such-model-r174` | **400** | `{"code":400,"message":"invalid request body","metadata":{"errors":["model no-such-model-r174 is not supported"]},"request_id"}` |

Layer-1 consequences (all inside the provider package, none in the contract):
- error parsing must tolerate BOTH `{code,message}` and `{error,status}`; `provider_code` = `str(http_status)` (never message text).
- HTTP 400 whose `metadata.errors[]` contains "is not supported" ⇒ `model_unavailable` (upstream has no 404 for models); other 400 ⇒ `bad_request`.
- `fallback_config: {"retry": false}` accepted (echoed nowhere; request copy shows only model/max_tokens/temperature).
