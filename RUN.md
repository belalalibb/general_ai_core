> **Superseded for operations:** the ONE authoritative run/operate document is [`docs/OPERATIONS.md`](docs/OPERATIONS.md) (start there). This file is kept as a short local-first companion; where they differ, OPERATIONS.md wins.

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

## End-user web UI (P-D)

Open **`http://127.0.0.1:8000/app/`** — a static shell (no build step)
served by the same process:

- the shell PROBES the profile (`GET /v1/auth/session`): in-memory ⇒ an
  honest **demo banner** and straight in; durable ⇒ sign-in / create-account;
- **Ask** runs sync (labeled echo/real content rendered verbatim) or async
  (202 + the real `/events` SSE progress frames);
- **Executions / Models / Usage** are explicit-refresh read surfaces; the
  health badge reads `/healthz`.

On the durable profile the UI's *Create account* tab drives
`POST /v1/auth/register` → the verification token prints on the **server
console** → paste it in the *Verify email* field (`POST /v1/auth/verify`)
→ sign in. Registration rate limiting: `REGISTER_RATE_LIMIT=N` (global
fixed window, default off).

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
accounts (**both profiles** — see "Admin console" below); `EXECUTE_RATE_LIMIT=N`
enables the per-tenant execute gate; `REGISTER_RATE_LIMIT=N` enables the global
registration gate (P-D.1); `HOST`/`PORT`/`LOG_LEVEL` control the server;
`DATABASE_ECHO=1` logs SQL.

## Admin console (`/admin/`) and identity modes (R160)

Open **`http://127.0.0.1:8000/admin/`** (same process, no build step). The
console always authenticates — even on the in-memory profile — because
`ADMIN_EMAILS` needs a REAL session to name an admin:

| Profile | `create_app` identity mode | No `Authorization` header | Valid Bearer | Bad Bearer |
|---|---|---|---|---|
| in-memory (no `DATABASE_URL`) | **hybrid** (demo principal + auth) | demo principal (never admin) | real user; admin iff listed | 401 |
| durable (`DATABASE_URL`) | auth only | 401 | real user; admin iff listed | 401 |

`GET /v1/auth/session` without a token answers `200 {mode:"demo", is_admin:false}`
on the in-memory profile — both UIs probe this, they never assume.

Zero-config admin walkthrough:

```bash
ADMIN_EMAILS=admin@x.test AGENT_SOURCE_ROOT="$PWD" python3 -m apps.main
curl -s -X POST localhost:8000/v1/auth/register -H 'Content-Type: application/json' \
     -d '{"email":"admin@x.test","password":"correct horse battery staple"}'
# the verification token prints on the SERVER console → POST /v1/auth/verify {"token": …}
# then sign in on /admin/ (or POST /v1/auth/login → Bearer token)
```

Surfaces: Overview, Notifications, Executions, Tenants & Usage, Models &
Providers, **Provider onboarding**, Capabilities & Scenarios, **Learning**,
**Skills acquisition**, Changes & Audit, Source Changes, System. Every surface
reads a real route; an un-composed seam renders "route absent" (never a
placeholder). `AGENT_SOURCE_ROOT=<dir>` adds the read-only
`source_list/source_read/source_search` tools to `GET /v1/agent-tools`
(jailed to that directory). Provider onboarding needs `GATEWAY_BASE_URL`
(+ `GATEWAY_SECRET`) — absent gateway ⇒ absent route.

Details: `docs/architecture/R160_PLATFORM_EVOLUTION_IMPLEMENTATION.md`.

## Unified CLI

```bash
python3 -m apps.cli serve      # == python3 -m apps.main
python3 -m apps.cli routes     # HTTP surface of the env-composed profile (no server)
python3 -m apps.cli describe   # profile facts (durable? providers? identity mode?)
python3 -m apps.cli test       # hermetic pytest (args forwarded)
python3 -m apps.cli check      # repo gate (engineering/verification/check_repo.sh)
```

## Operator notes

- **§14 gate**: `authoritative_applier=None` is hardcoded in the composition
  — R3 can never touch authoritative source regardless of profile or env.
- Alternative launch: `uvicorn --factory apps.main:create_runtime_app`.
- VPS: run under a `systemd` unit (Restart=always) or any process manager;
  the process shuts down cleanly (tasks cancelled, engine disposed on the
  bridge loop, bridge closed).
- Secrets (`DATABASE_URL`, API keys) are never logged (20 §5).
