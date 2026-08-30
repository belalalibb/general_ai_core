# PLATFORM CAPABILITY SUMMARY (Operator-Facing)

**Date:** 2026-08-30 · **State assessed:** `main` @ `5c1410b`
**Full analysis:** `docs/architecture/PLATFORM_CAPABILITY_ASSESSMENT.md`

---

## What do we have now?

A **multi-tenant AI orchestration kernel** — proven by 1605 platform +
122 gateway tests and 12 machine-enforced architecture contracts:

- One execute API (`POST /v1/execute`) → routing (named exclusions) →
  execution with retry/failover → exact-once usage settlement →
  evaluation → audit-able trail (`GET /v1/executions/{id}`).
- Pluggable providers behind one port: Groq, Genspark LLM, and a hardened
  **Remote Provider Gateway** (separate data plane, secret rotation,
  failure containment — G1–G4).
- Deny-by-default security: capability firewall, tool-call admission gate
  with device trust, per-tenant physical isolation, opaque secret refs
  end-to-end (Vault-bound), per-tenant rate limits, budgets denied
  before any provider work.
- Governance: admin change lifecycle (draft→validate→preview→publish→
  rollback), plans/entitlements, closed-set audit log.
- Runtime machinery ready but not yet carrying executions: queue/worker
  with dedup+DLQ (Redis-bound), leases, transactional outbox, admission/
  fair scheduling; 12 Postgres migrations with schema↔contract parity.

**It is NOT an agent platform yet:** agent contracts exist (AGENT
strategy, 11-node execution graph, approval states, provider-agent port),
but there is no tool *executor*, no plan→act→observe loop, no async
execution (API rejects it explicitly), no durable workflow binding, no
streaming.

## What can we build now?

- **Multi-provider AI applications** — governed prompt→answer over many
  models: READY NOW.
- **Chat/assistant products (sync)** and **internal enterprise AI tools**
  — READY WITH CONFIGURATION (real auth binding + Postgres repositories;
  both are bindings at existing seams).
- **Text content-generation products** — READY WITH CONFIGURATION
  (more adapters; contracts for image/audio exist, adapters don't).

## What can we build with small additions?

- **Analysis/decision-support** (parallel/debate graphs) — needs graph
  execution beyond the linear pipeline.
- **Chat with live UX** — needs streaming (contracts exist).
- **Notification-driven products** — needs webhook *delivery*
  (registration exists).

## What is genuinely missing?

1. Tool execution runtime (admission gate exists; executor doesn't).
2. Agent loop (model proposes → code disposes → observe → repeat).
3. Async/durable execution (queue machinery exists; nothing rides it;
   workflow-engine port has no binding).
4. Scheduler/triggers; webhook delivery.
5. Postgres repository layer (schema done; repositories not).
6. HTTP auth endpoints (identity service exists; Principal is
   composition-injected).
7. Streaming.

## Top 3 highest-leverage additions (X²)

1. **Async durable execution** — compose the already-proven queue/worker/
   outbox under `/v1/execute async=true`. Unblocks every long-running
   product class. Purely additive.
2. **Tool execution runtime** — complete the already-built admission gate
   with a dispatching executor (handlers live in apps, never core).
   Turns "AI answers" into "AI acts", safely.
3. **Agent execution loop** — bounded plan→act→observe inside the
   existing budget/firewall/lifecycle cage (with the R095 same-commit
   output-validator duty). This is what makes it a true agent platform.

Enabling prerequisite: Postgres repositories (durability honesty).
All four attach at existing tested seams — **no core rewrite, no port
breakage, no isolation weakening** (verified in assessment §11/§16).

## Should we proceed to UI/UX now?

**Yes.** The API surface (execute, executions, models, usage, skills,
webhooks registration, and a 14-route admin control plane including the
full change-governance lifecycle) supports a serious management UI today.
Three thin companion endpoints should ride the UI phase (all surface
existing core machinery, no new platform capability): auth endpoints at
the Principal seam, an executions *list* endpoint, and an audit read
endpoint. Nothing blocks starting.
