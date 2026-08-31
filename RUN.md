# Running the platform (P-B local-first runtime)

One process serves the API, drains the transactional outbox, and executes
queued work — the smallest deployable unit (Operator directive P-B, Option A).

## Local dev (zero configuration)

```bash
pip install -e ".[dev]"      # or the flat dependency list from pyproject
python3 -m apps.main         # http://127.0.0.1:8000
```

No environment variables ⇒ **everything is in-memory** (the exact hermetic
posture the test suite proves):

- a hermetic `local-echo` provider serves `/v1/execute` (honestly labeled —
  it never pretends a real model answered);
- a **demo principal** with a generous budget is auto-bound, so requests
  need no Authorization header; its tenant id is printed in the startup
  banner;
- async execute works end to end: `{"execution_policy": {"async": true}}`
  → 202 → the in-process worker drains it → poll `/v1/executions/{id}`.

```bash
curl -s localhost:8000/healthz
curl -s -X POST localhost:8000/v1/execute \
     -H 'Content-Type: application/json' -d '{"ask": "hello"}'
```

## Real providers (optional, independent of the database)

| Variable       | Effect                                                        |
|----------------|---------------------------------------------------------------|
| `GROQ_API_KEY` | binds the Groq adapter (verified text models, T-IMPL-036)     |
| `GSK_API_KEY`  | binds the Genspark LLM proxy adapter (T-IMPL-037)             |

Keys enter through the secret manager → opaque credential_ref → adapter-side
resolution (20 §5). With any real key present the echo provider is NOT bound.

## Durable single-server profile (VPS shape)

```bash
export DATABASE_URL='postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME'
python3 -m alembic -c infrastructure/db/alembic.ini upgrade head   # once
python3 -m apps.main
```

`DATABASE_URL` swaps in the P-A durable bindings — call sites unchanged:

- executions (P-A.1), identity/sessions (P-A.2), source-change
  proposals/snapshots (P-A.3), plus the durable outbox + worker
  idempotency for the async path;
- **no demo principal**: the durable profile always authenticates.
  Register → the verification token prints to the server console (MVP
  Phase 2 forbids real email delivery — honest local binding) → verify →
  login → call with `Authorization: Bearer <session token>`;
- a `local-default` plan row is seeded idempotently at startup
  (`tenants.plan_id` is a RESTRICT FK);
- sessions survive restarts (tokens at rest are SHA-256 digests only).

Optional: `ADMIN_EMAILS=a@x.com,b@y.com` grants the admin surface to those
accounts; `EXECUTE_RATE_LIMIT=N` enables the per-tenant execute gate;
`HOST`/`PORT`/`LOG_LEVEL` control the server; `DATABASE_ECHO=1` logs SQL.

## Operator notes

- **§14 gate**: `authoritative_applier=None` is hardcoded in the composition
  — R3 can never touch authoritative source regardless of profile or env.
- Alternative launch: `uvicorn --factory apps.main:create_runtime_app`.
- VPS: run under a `systemd` unit (Restart=always) or any process manager;
  the process shuts down cleanly (tasks cancelled, engine disposed on the
  bridge loop, bridge closed).
- Secrets (`DATABASE_URL`, API keys) are never logged (20 §5).
