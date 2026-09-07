# A10 — External consumption audit + one-line app challenge (prompt §2.10) — EXECUTED

HEAD at start 043bf7a (reset #25; probe committed before run). `a10_consumers.py` → `consumer_probes.txt`, real hermetic server.

## 1. Two materially different independent consumers (public HTTP contract only, no platform imports)

| | consumer #1 "support-ticket summariser" | consumer #2 "batch document pipeline" |
|---|---|---|
| goal | sync, one ask per ticket, project-scoped, wants usage + webhook | async fan-out, poll, continuity, asks for a tool it may not have |
| bootstrap | register → verify (token from server console) → login → Bearer | same |
| discovery | `/v1/models` 200 (1 model), `/v1/agent-tools` 200 (0 tools), `/v1/skills` 200 (0) | same surface |
| scoping | workspace 201 → project 201 → execute with `project_id` 200 | — |
| execution | X-16 200 `succeeded`, usage 1/1 (X-17) | X-21 5 async → **5/5 succeeded** |
| policy | webhook subscription 201 (X-18) | X-23 `git_push` → **422 loud** `unknown agent tools` |
| isolation | X-24 reads #2's execution → 404 | X-25 admin → 403 |
| contract | `/openapi.json` 200 (OpenAPI 3.1, title/version 0.1.0) | X-22 non-UUID `conversation_id` → 422 with field |
Consumer #0 = the repo's own `examples/minimal-platform-app/client.py` (stdlib urllib): **exit 0** end-to-end (healthz → session →
workspace → project → execute → fetch).

What QEVION provides vs what the app must implement (from execution, not description):
- **Provides**: identity + sessions, tenant isolation, model discovery, sync/async execution, executions read model, usage counters,
  webhook subscription (delivery relay NOT claimed — OPERATIONS/app.py:536), workspaces/projects, closed-shape validation with field
  errors, OpenAPI document, admin control plane (separate role).
- **App must implement**: email delivery for verification (platform prints the token to console — honest MVP scope), its own UI,
  its own domain model, webhook receiver, and any retry policy above the platform's idempotency key.

## 2. One-line application challenge
"Build a Slack bot that summarises a pasted incident report and files it under the team's project."
Walk-through against the actual surface:
| need | present? | evidence |
|---|---|---|
| authentication bootstrap | yes, but verification token is console-only → **hidden manual step** for a headless deployment (or the operator pre-creates the account) | X-00/X-1x bootstrap |
| capability discovery | `/v1/models`, `/v1/agent-tools`, `/v1/skills`, `/openapi.json` | X-11..13, X-26 |
| permissions / policy | tenant-scoped by session; tool allow-list refused when unknown; no per-app scoped API key (only user sessions) | X-23, X-25 |
| runtime invocation | `POST /v1/execute` sync/async + poll | X-16, X-21 |
| result handling | `result.type/content`, `artifacts.context_provenance`, unified error envelope `{code,message,retryable,details}` | X-16, X-22 |
Blockers found: **none hard**. Frictions: (a) no first-class **application credential** (API key / client credentials) — every consumer
is a *user* session with a password; (b) no SDK (stdlib client exists as example); (c) `/docs` 404 (Swagger UI disabled — fine, OpenAPI
JSON is served); (d) no `/v1/version` or capability-version discovery beyond `info.version` in OpenAPI and `X-*` none observed;
(e) verification-token-by-console. Classification: (a) **SHOULD FIX BEFORE EXTERNAL CONSUMPTION** (recorded as **F-R176-10**, S3,
product gap not defect — 41 Part III lists "entitlements / full identity" under FINAL); (b)(c)(d)(e) **OPTIONAL / DOCUMENTATION**.
Nothing here requires building a second platform.

## 3. Contract evolution
- Path versioning `/v1/*` present; OpenAPI `info.version 0.1.0`; request bodies `extra=forbid` (additive server fields are safe,
  additive client fields break — by design, loud). No deprecation headers, no capability versioning surface. **DOCUMENTATION /
  CONTRACT ONLY** — acceptable for a 0.1 API; note for external GA.

## 4. Single source of truth (from A2/A6/A7 reading + this run)
models/providers/bindings → registries + Postgres catalogs with replay on boot (one truth per process; multi-instance drift risk
already classified A7); skills → import lifecycle store; policies/routing weights → config lifecycle (`published_version`);
tenants/credentials → identity + secret manager refs; execution state → execution store. Drift risk: process-local caches only.

## 5. Observability integrity (from A5 S-27, A6 L-11)
Audit events carry `tenant_id, actor_id, event_type, occurred_at, details{change_id, action}, admin_change{previous/new version}`;
error envelope carries `trace_id` (null in hermetic — no OTel exporter bound). Success + failure paths both observed.

## 6. Coverage
P1 executed 15/15 (X-00..X-28). P2 NOT PROBED: webhook delivery (relay not composed — honest), streaming (`stream` flag),
SDK ergonomics beyond stdlib example.
