# ADR-0001 — Implementation Language / Stack Selection

```text
STATUS: PROPOSED (requires explicit user approval before ACCEPTED)
DATE: 2026-08-25
TASK: T-IMPL-002
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: MVP Phase 1 (Contracts) code must not be written until this ADR is ACCEPTED
(recorded in `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md`).

---

## Context

The v3 documentation pack fixes the architecture shape but is deliberately
language-agnostic. Fixed constraints the stack must serve
(`final_docs_v3/02` §5, `40` §5):

```text
Modular monolith (Core / Infrastructure / Providers never mix)
PostgreSQL = source of truth (+ pgvector)
Redis Streams = runtime queues, locks, leases
Durable workflow runtime; at-least-once + idempotency
Unified HTTP API (POST /v1/execute), schema-validated contracts
OpenTelemetry observability
Contract-first: schemas and types drive everything (40 §2.1)
Strong architecture boundary tests (40 §6.2)
Single AI agent implements everything via micro-tasks
```

MVP scope (`41` §38): auth, tenants, execute API, 1–2 providers, model
registry, simple router, execution records, memory basics, admin basics,
usage accounting.

## Alternatives

### A. TypeScript / Node.js (single language, modular monolith)

Pros:
```text
- One language across API, core, workers, and future admin UI/client runtime
  (apps/admin, apps/client-runtime in the 41 §2 layout).
- Contract-first fits natively: zod/JSON Schema + generated types; the same
  schema validates at runtime and types at compile time (40 §2.1).
- First-class SDK coverage for LLM providers; excellent async I/O profile for
  an orchestration workload that is I/O-bound (provider calls), not CPU-bound.
- Mature ecosystem for the fixed infra: node-postgres/drizzle, ioredis
  (Streams), Temporal TS SDK (durable workflows), OpenTelemetry JS.
- Monorepo tooling (workspaces) maps 1:1 to the core/providers/infrastructure
  boundary layout; boundary lint rules (eslint import rules / dependency-cruiser)
  give cheap architecture boundary tests (40 §6.2).
```
Cons:
```text
- Weaker CPU-parallelism (worker_threads needed for heavy compute — not an
  MVP workload).
- Runtime type erasure: discipline needed to keep runtime validation at all
  boundaries (mitigated by contract-first zod validation).
```

### B. Python (FastAPI + Pydantic)

Pros:
```text
- Strong AI/ML ecosystem; Pydantic gives runtime-validated contracts.
- Fast to prototype; Temporal Python SDK exists.
```
Cons:
```text
- Two-language future is likely (admin UI/client runtime still need TS).
- Concurrency model (GIL/asyncio) is workable but weaker for a high-fanout
  I/O orchestrator; typing is gradual, boundary enforcement weaker.
- Packaging/monorepo boundary tooling weaker than TS workspaces.
```

### C. Go

Pros:
```text
- Best runtime performance/concurrency; single static binary; strong typing.
- Excellent for infrastructure-heavy services.
```
Cons:
```text
- Schema-first ergonomics weaker (no zod/Pydantic equivalent; more codegen).
- Slower iteration for a contract-heavy, rapidly evolving domain model
  (15+ entity types, 5 policy types, 5 router modes).
- Two-language future guaranteed (UI); LLM provider SDK coverage thinner.
```

## Decision (PROPOSED)

**TypeScript / Node.js (LTS) monorepo** with:

```text
Runtime:        Node.js LTS
Language:       TypeScript (strict)
Contracts:      zod schemas as single source → inferred types + JSON Schema export
API:            Fastify (schema-validated HTTP), POST /v1/execute per 10_API_CONTRACTS
DB:             PostgreSQL via a typed query layer + migrations (drizzle-kit or equivalent)
Queues/locks:   Redis Streams (ioredis)
Workflows:      start with Postgres-backed outbox + workers (40 §4.2);
                adopt Temporal when durable-workflow complexity justifies it (ADR then)
Observability:  OpenTelemetry JS + pino structured logs
Tests:          vitest (unit/contract/integration) + dependency-cruiser boundary tests
Monorepo:       npm/pnpm workspaces mirroring the 41 §2 layout
                (apps/, core/, providers/, infrastructure/)
```

## Reason

The workload is I/O-bound orchestration with heavy contract churn — exactly
where TS excels. It is the only option keeping one language across every
planned deliverable (API, workers, admin, client runtime), maximizing
throughput for a single-agent build. Contract-first (the pack's #1
engineering principle) has its best-in-class tooling in the TS ecosystem.
Cons are mitigated: no CPU-heavy MVP workload; runtime validation enforced by
the contract layer at every boundary.

## Consequences

```text
+ One toolchain: one CI matrix, one test runner, one lint/boundary system.
+ zod schemas become the literal contract artifacts required by MVP Phase 1.
- Node LTS upgrade cadence must be tracked.
- If future CPU-bound subsystems appear (e.g. local inference), they get their
  own service + ADR; the provider-agnostic Core is unaffected (02 invariants).
Rollback: contracts are exported as JSON Schema (language-neutral), so a stack
change later loses implementation code but not the contract layer's content.
```

## Status

PROPOSED — awaiting explicit user approval. On approval: flip to ACCEPTED,
record in PROJECT_EXECUTION_STATE.md, then MVP Phase 1 (Contracts) unblocks.
If the user selects a different alternative, rewrite Decision/Reason
accordingly before ACCEPTED (this file may be edited freely while PROPOSED).
