# A9 — Provider / model / routing audit (prompt §2.9) — EXECUTED

HEAD at start 2a6567e (reset #24 between turns; Tier-1 runs redone and committed before anything else).

## 1. Tier 1 (hermetic, keys unset)
- Platform: `tests/providers tests/routing tests/contract tests/usage` → **752 passed, 15 skipped** (`tier1_provider_routing.txt`);
  the 15 skips are the credential-gated live modules (Groq ×6, GW-Groq ×1, Genspark ×8).
- Gateway-service (own package, run from its dir): **194 passed** (`gateway_suite_hermetic.txt`). This also resolves
  **F-R176-02**: the editable install fails in a fresh venv only because `gateway-service/pyproject.toml` has no `[build-system]`
  table; the suite itself runs fine with the platform venv from the package dir — reclassified **S4 / DOCUMENTATION** (OPERATIONS
  could say "run from `gateway-service/`").
- Failure taxonomy: `ProviderErrorCategory` 12 classes (`core/contracts/provider.py:310`); router failover classes tested
  (`test_d03_d04_two_account_failover` 7, `test_router_engine_components` 18, `test_router_scoring` 41 — inside the 752).

## 2. Tier 3 (real external provider) — spend budget set at 3 calls, used 1 paid + 3 free
Free liveness (`free_liveness_probes.txt`, status codes only):
| key (from prompt §0.6, env-only in the probe) | endpoint | result |
|---|---|---|
| AssemblyAI | `GET /v2/transcript?limit=1`; `GET llm-gateway/v1/models` | **200 / 200 — live** |
| Groq (prompt line 133) | `GET /openai/v1/models` | 400 `organization_restricted` — same class as F-R175-03; the working Groq key from R175 L-03 was NOT re-supplied this round |

Gateway live E2E (`gateway_live/`, rerun of the R174 §4 rerunnable probe, unchanged): gateway process on :8800 with
`GW_ASSEMBLYAI_API_KEY` in **its env only**, route map `rt_aai_r174 → assemblyai`, throwaway gateway secret:
| check | result |
|---|---|
| A real completion `qwen3.5-4b-32k-fast` via canonical envelope | http 200, `succeeded`, non-empty text, usage tokens present (**1 paid call**) |
| B unknown model | 200 envelope, `succeeded:false`, category `model_unavailable`, `retryable:false` (0 paid) |
| C bad route token | 4xx route rejected (0 paid) |
| D describe | 200 |
| secret hygiene | key string: 0 hits across `evidence/r176/**` and gateway log; gateway secret redacted in artefacts |
**10/10 checks PASS.** Platform → gateway → AssemblyAI chain was proven in R174 §5/§7 (two processes, 0 core lines); the
platform → Groq chain in R175 L-03 (7/0/0). Not re-spent this round (§2.1: never spend to prove the proven).

## 3. Routing / credential binding (RUNTIME from earlier items)
- Router decides, execution executes: disabling the only ACTIVE model → 503 `model_unavailable` with `excluded` reasons (A6 L-07), no
  silent fallback; explicit unknown model → 503 with only the caller's key echoed (A5 S-22).
- Model ≠ provider ≠ account: bindings table (alembic 0018), `credential: {mode: platform}` in the envelope; per-tenant credential
  mode exists in contract; user-owned credentials not exercised (no user key) → **NOT PROBED (P1, credential unavailable)**.
- Provider health honesty: OPERATIONS §7 — "cannot verify ≠ healthy"; `/v1/admin/providers` lists only `local_echo` hermetic.

## 4. Provider failure classes (evidence map, prompt §2.9 "Degradation preservation")
| class | evidence | tier |
|---|---|---|
| invalid credential / org restricted | R175 run1/run2 (Groq 400 → `invalid_credential`, failover-permitting; F-R175-02 parity fix) + this round's free probe | LIVE (prior) + LIVE (probe) |
| rate limit 429 / Retry-After | R165 live comments in `core/execution/service.py:567`; hermetic tests | LIVE (prior) + TEST |
| model unavailable | A6 L-07, A5 S-22 (platform); gateway B (live envelope) | RUNTIME + LIVE |
| timeout / 5xx / malformed | `tests/runtime/test_chaos_transport_t071.py` (A7) | TEST |
| unsupported operation | gateway suite `test_dispatch`/`test_contracts` | TEST |
| quota exhausted (HTTP 200 plan refusal) | R168 D-01 (Genspark) | LIVE (prior) |

## 5. Findings
- No new S1/S2. F-R176-02 reclassified S4 (see §1).
- The prompt's Groq key is unusable (org restricted) — **BLOCKED (external)**, not a platform defect; recorded, does not stop
  Tier 0–2 or the AssemblyAI Tier-3 evidence.

## 6. Coverage
P0 credential containment: executed (0 key leaks in evidence/logs; envelope carries `mode`, never the key). P1 executed: 6/7
(user-owned credential path BLOCKED). P2 NOT PROBED: Groq live this round (key restricted), streaming over the gateway.
