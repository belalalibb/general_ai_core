# R173 §1.6 — Groq ladder (keys 5→8) through the agent path

Harness: `evidence/r173/tools/groq_ladder_agent.py` — one in-process composition per key
(`build_runtime_profile(environ={GROQ_API_KEY:<value>, DEV_DEMO_PRINCIPAL:"1", PROVIDER_MAX_RETRIES:"0"})`),
one agent turn (`execution_policy.strategy=agent, max_steps=2`, no tools) posted to `/v1/execute`
over ASGI. Stop at first HTTP 200. Key NAMES only in evidence; every line secret-scanned before write.
Keys were exported in-shell from a 0600 file under `/tmp` (not tracked, purged at close).

## Result: ladder EXHAUSTED — no key produced a 200 (`ladder.jsonl`)
| order | key name | agent-path HTTP | error code | adapter category / provider_code (both plan attempts) | latency |
|---|---|---|---|---|---|
| 1 | `GROQ_API_KEY_5` | 502 | `execution_failed` "agent stopped (propose_failed)" | `invalid_credential` / `organization_restricted` ×2 (`allam-2-7b`) | 252 ms |
| 2 | `GROQ_API_KEY_6` | 502 | same | same | 142 ms |
| 3 | `GROQ_API_KEY_7` | 502 | same | same | 166 ms |
| 4 | `GROQ_API_KEY_8` | 502 | same | same | 128 ms |

Winner: **none**. Nothing was composed as `GROQ_API_KEY` for a server.

Cross-check on the bare `/v1/execute` path with the §1.2b recorder (`bare_execute_recheck.jsonl`,
6 passed): all four ⇒ 502 `invalid_credential` / `organization_restricted` (87–130 ms). Upstream
returns HTTP 400 `invalid_request_error code=organization_restricted` for every call.

## Observation (not a platform defect)
Keys 5 and 6 returned **200 `succeeded`** on this same bare path at 03:11 UTC today
(`evidence/r173/live_transport.txt`). At 12:15 UTC they are `organization_restricted`, identical
to keys 1 and 4 (§1.3). This is an upstream organisation-state change between the two runs, not
a platform regression: the same adapter, router and model (`allam-2-7b`) are in play and the
error is typed, non-retryable, and reaches the caller as a 502 with no `internal_error`.

The agent path made TWO adapter attempts per turn under `PROVIDER_MAX_RETRIES=0` — those are the
agent's own `plan-1`/`plan-2` stages (same shape as §1.5 hermetic/live), not provider retries.

## E1 / E2 verdict for §1.6
**NOT EVALUATED** — no proposal-capable provider available. The four typed errors are above.
R148's live E1/E2 PASS is NOT carried forward (owner decision 4); §1.5 INERT structural claim
(0 act stages without a proposal; record + trace agree) stands as the only E1/E2 evidence in R173.

Per owner instruction: recorded and moved straight to F-15.2 without blocking.
