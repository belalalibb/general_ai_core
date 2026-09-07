# A7 — Reliability audit (prompt §2.7) — EXECUTED

HEAD at start f58ddb4. Wire probes: `a7_probe.py` → `wire_probes.txt` (hermetic server). Tier 1: `tier1_chaos_infra.txt`
(chaos transport T071 + hardening T035 + infrastructure + composition: **254 passed, 49 skipped** — skips are the DB/Redis/Vault/S3
credential-gated tests; R175 D-01 ran the DB ones on real Postgres: 3197/0). Async fabric 96/96 in A5.

## 1. Horizontal-scale honesty (composition root `apps/composition/runtime.py`, STATIC — read, then confirmed by `describe`)

| mechanism | hermetic profile | durable profile (`DATABASE_URL`) | class | note |
|---|---|---|---|---|
| execution store | `InMemoryExecutionStore` | `PostgresExecutionRepository` (bridged) | SHARED (durable) | |
| outbox | `InMemoryOutbox` | `PostgresOutbox` (bridged) | SHARED (durable) | relay is caller-driven, one per process |
| idempotency | `InMemoryIdempotencyStore` | `PostgresIdempotencyStore` (bridged) | SHARED (durable) | |
| identity / sessions | `InMemoryIdentityService` | `PostgresIdentityRepository` | SHARED (durable) | |
| workspaces / projects / conversations / memory / audit / sourcechange | in-memory | Postgres repositories | SHARED (durable) | |
| **queue** | `InMemoryQueue` (line 1083) | **still `InMemoryQueue`** — `RedisQueue` exists (`infrastructure/redis`) but is not composed here | **PROCESS LOCAL — UNSAFE FOR HORIZONTAL SCALE** | outbox is durable, so a crash loses only the in-flight dispatch, which the relay re-publishes (dedup covers duplicates: test `relay_crash_window_duplicate_is_absorbed_by_worker_dedup`) |
| **rate limiter** | `InMemoryRateLimiter` (auth + execute) | same | PROCESS LOCAL | per-instance limits; `RedisRateLimiter` exists, not composed |
| **usage accounting** | `InMemoryUsageAccounting` | **same** — docstring line 291/712: "durable usage remains a later binding — honest scope" | PROCESS LOCAL — **quota resets on restart** | `PostgresUsageRepository` exists (usage *records*) but the reserve/settle ledger is in-memory |
| leases / cache | in-memory | in-memory unless bound | PROCESS LOCAL | `RedisLeaseManager`, `RedisCache` exist |
| provider clients | per adapter instance | same | INSTANCE LOCAL | |
| config lifecycle state | in-memory registries | write-through + replay on boot (`replay_admin_status_overrides`) | SHARED via replay at startup only | a second instance sees an admin publish **only after restart** (see A6 L-06: immediate within one process) |
| `/healthz` | `scope: process` | same | honest | |

Verdict: **single-instance durable** is the honestly supported deployment (OPERATIONS §13 says so). Multi-instance would need:
queue → Redis, usage → durable ledger, rate limits → Redis, config propagation → bus. None of that is claimed by the repo; the
prompt's FINAL "multi-AZ HA" is POST-RELEASE (A3). Classification: **NOT A CLOSURE BLOCKER; DOCUMENTATION honest**.

## 2. Idempotency / partial-success (wire)
| probe | result | class |
|---|---|---|
| R-01/02 async same `Idempotency-Key` twice | same execution_id, 202 both; usage 1 unit not 2 | RECOVER (dedup) ✓ |
| R-05/06 sync same key twice | same execution_id, 200 replay | ✓ |
| **R-03 same key, DIFFERENT body** | **202, replays the first execution** (no 409/422) | **F-R176-08** |
| R-04 usage after 3 keyed submits | 1.0 | correct |
| R-07 burst 40 async | 40×202, all `succeeded` (R-08: 42 listed) | no admission refusal at this depth (limit is composition data, 0 = off) |

**F-R176-08 — idempotency key reuse with a different payload is silently honoured as a replay (S3, correctness).**
Expected (industry contract, and the fabric's own `test_duplicate_request_is_settled_without_rerunning_handler` only covers
*identical* duplicates): key+different body ⇒ 409/422. Actual: client receives the *old* execution's id and never learns its new
ask was dropped. Impact: client bug surfaces as lost work; not a security issue. Classification: **SHOULD FIX BEFORE EXTERNAL
CONSUMPTION**. Proposed **FIX-05** (not executed): store a body hash with the idempotency record; mismatch ⇒ 409
`idempotency_conflict`; failing-first test on `/v1/execute`. Blast radius: `core/runtime/worker.py` IdempotencyPort record shape (+
Postgres column via migration 0019 for durable), `apps/api/app.py` execute path, tests.

## 3. Crash / recovery matrix (Tier 1 evidence, `tests/runtime/test_async_fabric_t059.py`, `test_chaos_transport_t071.py`)
| boundary | evidence | class |
|---|---|---|
| relay crash after publish before mark-dispatched | duplicate absorbed by worker dedup | RECOVER |
| worker crash mid-job | pending stays, peer reclaims stale delivery | RECOVER |
| transient handler failure | retry via stale claim then success | RECOVER |
| permanent failure / retry exhaustion | dead-letter immediately / after N | SAFE FAIL |
| queue depth flood / tenant window flood | refused at admission | SAFE FAIL |
| fair scheduler under a flooding tenant | others not starved | ✓ |
| transport faults (T071 chaos: timeouts, resets, malformed) | classified, no corruption | SAFE FAIL |
| reservation before settlement, process dies | usage ledger is in-memory ⇒ reservation LOST with the process (no leak, no double-charge) | LOSE (bounded, honest) |
| admin publish mid-execution | NOT PROBED (P2) | — |

## 4. Coverage
P0 crash/partial-atomicity: covered at Tier 1 (fabric + chaos suites executed this round), Tier 2 only for idempotency + burst.
P1 executed: 9/9 wire. P2 NOT PROBED: multi-instance run (no second process composed), config change during in-flight job.
