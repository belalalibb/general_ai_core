# ADR-0014 — v1 production topology (AD-5)

- **Status:** ACCEPTED as the recorded v1 topology (R198, operator D2). This ADR records what the repository
  implements and how it is meant to be run; it is **not** a claim that the platform is production-ready —
  that claim is withheld while D-03 (credential rotation + history purge) is OPERATOR-OWNED-OPEN
  (see `docs/ai_orchestration_pack/V1_ACCEPTANCE_REGISTER.md`).
- **Ruling recorded verbatim (audit AD-5):** "v1 production topology = durable single-server, single API process, external Postgres; multi-replica future."
- **Sources of truth:** `docs/OPERATIONS.md` §1–§3, `apps/main.py` (lifespan), `apps/composition/runtime.py`
  (composition), `apps/composition/database.py` + `infrastructure/db/engine.py` (engine), `infrastructure/db/migrations/`
  (alembic 0001→0022), `evidence/r189/CONTRACT_FREEZE_RECORD.md` (P-R188-03/-04 exclusions).

## 1. Context
Before R198 the topology facts were spread across OPERATIONS §1 (profiles and startup order), OPERATIONS §13 (honest
limitations) and the R189 freeze record (why multi-replica is excluded). There was no single artefact an operator
could hand to a deployer. No container image, compose file, process manager unit or CI workflow exists in the
repository; this ADR does not add one.

## 2. Decision — the v1 topology

### 2.1 Durable single-server (the accepted profile)
Startup order (OPERATIONS §1): **1. Postgres up → 2. `alembic upgrade head` → 3. `apps.cli serve`.**

```
                     TLS terminates HERE (external ingress / reverse proxy — not part of this repository)
   clients ──HTTPS──▶ ingress ──HTTP──▶ ┌──────────────────────────────────────────────┐
                                        │  ONE Python process  (python -m apps.main,    │
                                        │  the CLI entrypoint of step 3 above)          │
                                        │  • FastAPI app: /v1/* + /healthz + static UIs │
                                        │  • outbox relay task (drains the outbox)      │
                                        │  • exec worker task (queued executions)       │
                                        │  • webhook worker task                        │
                                        └───────────────┬──────────────────────────────┘
                                                        │ postgresql+asyncpg (`DATABASE_URL`)
                                                        ▼
                                        ┌──────────────────────────────────────────────┐
                                        │  external PostgreSQL 17 (+ pgvector)          │
                                        │  schema applied by the alembic migration head │
                                        └──────────────────────────────────────────────┘
                                        outbound HTTPS to model providers only when a key is set
```

| Element | Fact (measured) |
|---|---|
| Processes | **One process** serves the API, drains the transactional outbox and executes queued work — `apps/main.py` lifespan spawns the relay loop, the worker loop and the webhook worker loop; shutdown cancels them, releases pooled provider HTTP clients, disposes the DB engine. |
| Database | External PostgreSQL reached through `DATABASE_URL` (`postgresql+asyncpg://…`, `infrastructure/db/engine.py`); pgvector required by migration 0007. Schema is applied **before** start (step 2 above; the alembic env reads `DATABASE_URL` from the environment only). |
| Identity | Durable identity mode (`ADMIN_EMAILS` names the admins); the demo principal exists only when `DEV_DEMO_PRINCIPAL` is set and is never used in this profile. |
| Secrets | Read once at composition from the environment; optional Vault custody through `VAULT_ADDR` / `VAULT_TOKEN` / `VAULT_MOUNT` (R195 AD-2); never from committed files. |
| TLS | Terminated at an **external ingress**; the process speaks plain HTTP on `HOST`:`PORT`. `HSTS` is set to `1` **only** when the process is reached over TLS (OPERATIONS §2, R194-A); the other hardening headers are unconditional. `OPENAPI_PUBLIC` stays unset (admin-gated OpenAPI). |
| Rate limits | `EXECUTE_RATE_LIMIT`, `REGISTER_RATE_LIMIT` (per tenant / per IP) inside the process. |
| Observability | `LOG_LEVEL`; audit events and executions persist in PostgreSQL. |
| Providers | Composed only when `GROQ_API_KEY` / `GSK_API_KEY` are present; otherwise the hermetic local adapter. |

### 2.2 What is deliberately **excluded** from v1 (with the recorded reason)
| Exclusion | Reason on record |
|---|---|
| **Multi-replica** API (N processes behind one ingress) | `ResourceSignalBoard` is process-local (P-R188-04 — operator NO to durable/shared signals; needed only when independent replicas serve); engineering tickets/grants live in-process (OPERATIONS §13). "Multi-replica future" is the ruling's own wording. |
| **No distributed worker** | The worker runs inside the API process (OPERATIONS §13); no external queue is composed by the runtime — the `infrastructure/redis` bindings exist as ADR-0003 port implementations, but no Redis environment key is read by `apps/composition/runtime.py`, so none is listed as a v1 knob. |
| **No token streaming** | OPERATIONS §13; async activity is the real per-execution SSE event stream only. |
| Async execution strategy | P-R188-03 NO — `execution_strategy` is sync-only. |
| Container image / process manager / CI deploy | None exists in the repository; deployers supply them. Not a v1 deliverable. |

## 3. Consequences
- Capacity is one machine; recovery is process restart + the durable stores. Durability across a real `SIGKILL`
  (memory items, conversations, audit, usage accounting) was measured in R181 (`evidence/r181/durability_measured_7a41caff.json`)
  and re-measured in R198 on current main (`evidence/r198/live_durability_measured_*.json`; register row AD-5).
- Anything that needs shared state across processes (signals, tickets/grants, distributed workers) is a **new decision**
  (P-R188-04 dependency), not an operational tweak.
- The ingress owns TLS, and therefore certificate handling and the decision to set `HSTS`.

## 4. Verification
`tests/verification/test_ad5_topology_artefact_r198.py` pins: the ruling verbatim; the OPERATIONS §1 order;
one process with relay + worker; every environment key named here is read by the code; the exclusions cite their
decisions; the TLS/`HSTS` posture; and that this document never claims "production-ready".
