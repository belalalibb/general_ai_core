# ADR-0001 — Implementation Language / Stack Selection

```text
STATUS: ACCEPTED (explicit user decision, 2026-08-25: "use Python — اعتمد Python / FastAPI / Pydantic")
DATE: 2026-08-25 (proposed at T-IMPL-002; user decision + acceptance at T-IMPL-003)
TASK: T-IMPL-002 (proposal) / T-IMPL-003 (acceptance)
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

## Decision (ACCEPTED — user selected Alternative B)

**Python 3.12+ / FastAPI / Pydantic v2 monorepo** with:

```text
Runtime:        Python 3.12+ (CPython)
Language:       Python with strict typing (mypy --strict on core/, contracts especially)
Contracts:      Pydantic v2 models as single source → runtime validation +
                JSON Schema export (model_json_schema); language-neutral
                contract artifacts preserved
API:            FastAPI (Pydantic-native, schema-validated HTTP, OpenAPI built-in),
                POST /v1/execute per 10_API_CONTRACTS
DB:             PostgreSQL via SQLAlchemy 2.x (typed, async) + Alembic migrations;
                pgvector via the pgvector-sqlalchemy integration
Queues/locks:   Redis Streams (redis-py asyncio)
Workflows:      start with Postgres-backed outbox + workers (40 §4.2);
                adopt Temporal (Python SDK) when durable-workflow complexity
                justifies it (separate ADR then)
Observability:  OpenTelemetry Python + structlog structured logs
Tests:          pytest (+ pytest-asyncio) for unit/contract/integration;
                import-linter for architecture boundary tests (40 §6.2)
Lint/format:    ruff (lint + format), mypy (type gate)
Monorepo:       single Python package tree mirroring the 41 §2 layout
                (apps/, core/, providers/, infrastructure/, tests/) managed
                with uv/pip + pyproject.toml; admin UI / client runtime remain
                thin consumers of the JSON-Schema contracts (their stack is a
                future ADR when those apps start)
```

## Reason

Explicit user decision (2026-08-25): the user selected Python / FastAPI /
Pydantic over the proposed TypeScript stack. Grounds consistent with the
analysis above:

```text
- Pydantic v2 satisfies the contract-first principle (40 §2.1): one model is
  simultaneously the runtime validator, the type surface, and the JSON Schema
  exporter — equivalent in role to zod in the rejected alternative.
- FastAPI is Pydantic-native: request/response validation and OpenAPI are
  derived from the same contract models, no duplication.
- The AI/ML + LLM-provider ecosystem is strongest in Python (first-class SDKs
  for essentially every provider), which serves the Providers subsystem —
  the heart of this platform.
- asyncio covers the I/O-bound orchestration workload (provider fan-out);
  the GIL is irrelevant for I/O-bound work; CPU-bound futures get their own
  service + ADR as already planned.
- All fixed infrastructure has mature Python support: SQLAlchemy/Alembic
  (Postgres + pgvector), redis-py (Streams), Temporal Python SDK, OTel Python.
- Boundary enforcement (40 §6.2) is achievable with import-linter contracts
  (layer + forbidden-import rules), mirroring dependency-cruiser's role.
```

Accepted trade-offs (from the Alternatives analysis, acknowledged):

```text
- Admin UI / client-runtime apps will likely need a second language (JS/TS)
  later; mitigated because they consume the language-neutral JSON-Schema
  contracts. Their stack is deferred to a future ADR.
- Gradual typing is weaker than TS strict; mitigated by mypy --strict on
  core/ + contracts, ruff, and runtime Pydantic validation at every boundary.
```

## Consequences

```text
+ Pydantic models become the literal contract artifacts required by MVP Phase 1.
+ Best-in-class provider SDK access for the Providers subsystem.
+ FastAPI OpenAPI output gives the public API docs (10 §1) for free.
- mypy --strict + import-linter must run in CI from Phase 1 onward (same
  entry point as local, per the CI-mirrors-local rule).
- A future ADR is required for the admin/client-runtime app stack.
- If future CPU-bound subsystems appear (e.g. local inference), they get their
  own service + ADR; the provider-agnostic Core is unaffected (02 invariants).
Rollback: contracts are exported as JSON Schema (language-neutral), so a stack
change later loses implementation code but not the contract layer's content.
```

## Status

ACCEPTED (T-IMPL-003, 2026-08-25) by explicit user decision recorded in
PROJECT_EXECUTION_STATE.md. The user selected Alternative B (Python /
FastAPI / Pydantic); Decision and Reason were rewritten accordingly before
acceptance, per the flow defined at proposal time. From this point this file
is append-only per ADR rules (40 §8.1); changes require a superseding ADR.
MVP Phase 1 (Contracts) is now unblocked.
