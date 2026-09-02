# ADR Index

Architecture Decision Records for the AI Orchestration Platform.

Rules (authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8):

```text
- Every significant architectural decision gets an ADR (Context / Alternatives /
  Decision / Reason / Consequences / Status).
- ADRs are append-only: never edit an ACCEPTED ADR's decision; write a new ADR
  with "Supersedes ADR-XXXX".
- File naming: ADR-NNNN-short-kebab-title.md (NNNN zero-padded, sequential).
- Product/scope decisions (non-architecture) go to
  docs/ai_orchestration_pack/final_docs_v3/60_DECISION_LOG.md instead.
```

## Index

| ADR | Title | Status | Task |
|-----|-------|--------|------|
| [ADR-0001](ADR-0001-implementation-stack.md) | Implementation language / stack selection — Python / FastAPI / Pydantic | ACCEPTED (explicit user decision, 2026-08-25) | T-IMPL-002 / T-IMPL-003 |
| [ADR-0002](ADR-0002-persistence-toolchain.md) | Persistence toolchain — SQLAlchemy 2.x async + asyncpg + Alembic + pgvector | ACCEPTED (explicit operator decision, 2026-08-25) | T-IMPL-015 |
| [ADR-0003](ADR-0003-redis-binding.md) | Redis client/binding — redis-py asyncio under core ports (streams, locks, cache) | ACCEPTED (explicit operator decision, 2026-08-25) | T-IMPL-016 |
| [ADR-0004](ADR-0004-observability-setup.md) | Observability — OpenTelemetry API/SDK at composition root + structlog + adaptive sampler | ACCEPTED (explicit operator decision, 2026-08-25) | T-IMPL-017 |
| [ADR-0008](ADR-0008-remote-provider-gateway.md) | Remote Provider Gateway — control-plane / data-plane split (OPEN-1..7 resolutions) | ACCEPTED (explicit operator decision, 2026-08-29) | R103 review / implementation NOT YET AUTHORIZED |
| [ADR-0009](ADR-0009-r3-source-change-sandbox.md) | R3 Source-Change Workflow — ephemeral pre-production sandbox + differential verification (hermetic build; real activation §14-gated) | ACCEPTED (explicit operator authorization, 2026-08-31) | V8 / R124 — REAL R3 ACTIVATION NOT AUTHORIZED |
| [ADR-0012](ADR-0012-shared-engineering-workspace-capability.md) | Shared Engineering Workspace Capability — files · commands · Git under Admin authorization (workspace ≠ platform source; §14 unchanged) | ACCEPTED (operator instruction, 2026-09-02) | R164 |
