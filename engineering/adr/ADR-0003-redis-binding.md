# ADR-0003 — Redis Client and Binding Approach (Streams, Locks, Cache)

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-25: "ADR-0003 = ACCEPTED")
DATE: 2026-08-25
TASK: T-IMPL-016
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: MVP Phase 3 "Redis setup" (41 §42) must not land — and no Redis
dependency may be added to `pyproject.toml` — until this ADR is ACCEPTED
with explicit operator sign-off (PHASE_2_GOVERNANCE).

---

## Context

Fixed constraints Redis must serve (40 §4, §5.1, §5.4; 02 invariants):

```text
- Redis = cache, runtime, locks, leases, rate limits, streams, short-lived
  state — NEVER a source of truth (40 §5.1). Durable truth is PostgreSQL.
- Fast/background jobs = Redis Streams (40 §4.1); outbox publisher targets
  the bus (40 §4.2); leases + fencing ONLY for exclusive resources such as
  provider accounts/credentials (40 §4.4).
- Backpressure primitives (queue limits, tenant/provider concurrency,
  priority) sit on top of the queue layer (40 §4.5).
- asyncio stack fixed by ADR-0001; core purity fixed by import-linter —
  ALL Redis code lives under infrastructure/, core sees only Protocol
  ports (queue port, lock/lease port, cache port, rate-limit port).
- mypy --strict on typed code; hermetic gates (no live Redis in the
  sandbox verification path).
```

## Alternatives

### A. redis-py (official `redis` package, asyncio API) — direct client

Pros:
```text
- Official, maintained client; asyncio API is first-class since 4.2+.
- Full command surface: XADD/XREADGROUP/XACK/XAUTOCLAIM for Streams
  consumer groups; SET NX PX + Lua for locks with fencing tokens;
  INCR/EXPIRE or Lua for rate limits — everything 40 §4 needs, no
  abstraction gaps.
- Type stubs shipped; workable under mypy --strict.
- Zero framework lock-in: our ports define semantics (at-least-once,
  ack/claim, lease fencing); the client is a thin transport underneath.
- Matches ADR-0001's ACCEPTED stack sketch ("Redis Streams (redis-py
  asyncio)").
```
Cons:
```text
- Consumer-group orchestration (pending-entry claims, dead-letter
  hand-off per 40 §4.7) is written by us against the port — deliberate,
  because those semantics are architecture, not client features.
```

### B. Task-framework layer (arq / taskiq / celery[redis])

Pros:
```text
- Ready-made worker loops, retries, scheduling.
```
Cons:
```text
- Celery is not asyncio-native; arq/taskiq impose their own job model,
  serialization, and retry semantics — colliding with 40 §4's explicit
  design (outbox-first, error-aware retry taxonomy, DLQ flow, leases with
  fencing). We would fight the framework to implement our own invariants.
- Frameworks own the queue topology; tenant/provider concurrency and fair
  scheduling (40 §4.5) become plugin work instead of port implementations.
- Extra dependency families for less control.
```

### C. glide / alternative clients (valkey-glide, aioredis legacy)

Pros:
```text
- valkey-glide: multi-language core, active development.
```
Cons:
```text
- aioredis is deprecated (merged into redis-py) — dead end.
- valkey-glide is newer, heavier (native core), and its Python typing +
  Streams ergonomics trail redis-py; no requirement pushes us there.
```

## Decision

**Alternative A — redis-py asyncio, confined to infrastructure/:**

```text
Client:      redis (redis-py) >= 5, asyncio API only
Location:    infrastructure/redis/ implements core ports:
             - queue port: Streams w/ consumer groups (XADD/XREADGROUP/
               XACK/XAUTOCLAIM), at-least-once + idempotency keys (40 §4.3)
             - lock/lease port: SET NX PX + fencing token counter, Lua for
               atomic release; leases only for exclusive resources (40 §4.4)
             - cache + rate-limit ports: TTL'd keys / Lua counters
Boundary:    core/ NEVER imports redis — a new import-linter forbidden
             contract lands WITH the dependency
DLQ:         terminal failures moved to a dead-letter stream + durable
             record in PostgreSQL (40 §4.7); Redis holds no truth
Testing:     port contract tests run against in-memory fakes (existing
             pattern); real-Redis integration tests use an ephemeral
             instance outside the hermetic gate path
```

## Reason

```text
- 40 §4's semantics (outbox, retry taxonomy, DLQ, leases+fencing,
  backpressure) are OUR architecture; a thin official client under our
  ports implements them exactly, while task frameworks (B) would impose
  competing semantics.
- redis-py is the maintained, typed, asyncio-native official client;
  alternatives (C) are deprecated or immature for this stack.
- Consistent with ADR-0001's ACCEPTED sketch — confirmation-with-analysis.
```

## Consequences

```text
+ Queue/lock/cache ports keep core testable with fakes (pattern already
  proven in Phases 2–3 abstractions).
- We own the consumer-group/claim/DLQ loop code — accepted: it encodes
  40 §4 invariants that no framework matches.
- New runtime dep: redis>=5 — pinned ONLY after this ADR is ACCEPTED.
- 6th import-linter contract (core must not import redis) lands with it.
Rollback: ports isolate the client; swapping transport (e.g. Valkey,
managed streams) replaces infrastructure/redis/ only.
```

## Status

ACCEPTED (T-IMPL-016, 2026-08-25) by explicit operator decision recorded in
PROJECT_EXECUTION_STATE.md: "Continue from the current checkpoint with the
operator authorization already granted: ADR-0003 = ACCEPTED". Alternative A
is confirmed as proposed, with no amendments. The redis>=5 dependency, the
6th import-linter contract, and the infrastructure/redis/ port bindings are
now unblocked. From this point this file is append-only per ADR rules
(40 §8.1); changes require a superseding ADR.
