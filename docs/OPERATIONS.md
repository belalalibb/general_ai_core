# OPERATIONS — the ONE authoritative run/operate document

**START HERE.** Everything an engineer/operator needs to install, configure,
start, test, verify and troubleshoot the platform. Other files (`RUN.md`,
`README.md`, `docs/architecture/*`) defer to this document for operational
procedure; if any of them disagrees with this file, this file wins and the
other is stale.

Repository evidence, not claims: every command below is the same entrypoint
the test suite and the gate script exercise.

---

## 0. Start here (60 seconds)

```bash
git clone <repo> && cd general_ai_core
pip install -e ".[dev]"            # Python 3.12+
python3 -m apps.cli check          # full repo gate (pytest + mypy + ruff + import-linter + secret scan)
python3 -m apps.cli serve          # http://127.0.0.1:8000  (zero-config, in-memory, local-echo provider)
curl -s localhost:8000/healthz
```

No environment variables ⇒ hermetic in-memory profile: a `local_echo`
provider (honestly labelled — it never pretends a real model answered), a
demo principal (tenant id printed in the startup banner), in-process worker
and outbox relay. This is exactly the posture the 2,500+ hermetic tests prove.

---

## 1. Required services and startup order

| Profile | Services | Startup order |
|---|---|---|
| **Local / dev** (default) | none — one Python process | `apps.cli serve` |
| **Durable single-server** | PostgreSQL (`DATABASE_URL`) | 1. Postgres up → 2. `alembic upgrade head` → 3. `apps.cli serve` |
| **Real providers** (either profile) | outbound HTTPS to the provider(s) | set the key env var(s) BEFORE start; keys are read once at composition |

One process serves the API, drains the transactional outbox, and executes
queued work (`apps/main.py` lifespan: outbox-relay task + exec-worker task).
Shutdown order (automatic): cancel worker/relay → release pooled provider HTTP
clients (S2, `RuntimeProfile.release_adapters`) → dispose DB engine on the
bridge loop → close bridge.

---

## 2. Authoritative configuration = environment variables

The composition root `apps/composition/runtime.py::build_runtime_profile(environ)`
is the ONLY place configuration is read. There is no config file. Everything
below is read from the process environment at start.

| Variable | Effect | Default |
|---|---|---|
| `HOST`, `PORT` | bind address | `127.0.0.1`, `8000` |
| `LOG_LEVEL` | uvicorn/log level | `info` |
| `DATABASE_URL` | **durable profile** (Postgres, asyncpg URL). Absent ⇒ in-memory | absent |
| `ADMIN_EMAILS` | comma-separated emails granted admin on login (both profiles) | none ⇒ no admin |
| `GROQ_API_KEY` | binds the real Groq adapter (direct) | absent |
| `GSK_API_KEY` | binds the real Genspark LLM proxy adapter (direct) | absent |
| `GATEWAY_BASE_URL`, `GATEWAY_SECRET`, `GATEWAY_SECRET_VERSION` | binds the remote gateway adapter; enables provider onboarding routes (`/v1/admin/providers/onboard*`) | absent ⇒ onboarding routes NOT mounted (404) |
| `AGENT_SOURCE_ROOT` | directory jail; enables the read-only source tools for agent mode | absent ⇒ 0 source tools |
| `AGENT_WORKSPACE_ROOT` | **engineering workspace** (ADR-0012): a git checkout the shared agent may read, write, run allow-listed commands in and commit/push/merge — under Admin authorization. Refused if it is (or contains / is inside) the platform's own checkout (ADR-0009 §14) | absent ⇒ 0 engineering tools, `/v1/admin/engineering/*` NOT mounted (404) |
| `AGENT_WORKSPACE_REMOTE` | git remote name used by `git_push` / `git_compare` | `origin` |
| `AGENT_WORKSPACE_COMMANDS` | comma-separated executables `ws_run` may launch (allow-list; `bash`, `sh`, `curl` etc. are refused unless listed) | `python3,pytest,ruff` |
| `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_MOUNT` | Vault-backed `SecretManagerPort` (secret refs resolve there) | absent ⇒ env-backed refs |
| `EXECUTE_RATE_LIMIT`, `REGISTER_RATE_LIMIT` | per-tenant / per-IP limits | recorded defaults |

Verify what the environment actually composes (evidence, not a claim):

```bash
python3 -m apps.cli describe   # durable?, provider_keys, agent tools offered, route_count, ui mounts
python3 -m apps.cli routes     # every served path+method (from app.openapi())
```

### Secrets by reference
Provider credentials are never stored by value in platform data. Provider
registrations, onboarding bodies and account records carry an opaque
`credential_ref`; the adapter resolves it at the last moment through
`SecretManagerPort` (env-backed locally, Vault when `VAULT_*` is set).
`GROQ_API_KEY`/`GSK_API_KEY` are turned into refs by the composition root —
the key value never enters registries, logs, audit or HTTP responses
(pinned by `tests/security/test_log_secret_leakage.py` and the adapter
secret-containment suites).

---

## 3. Identity modes

| Profile | Mode | Behaviour |
|---|---|---|
| in-memory | **hybrid** | no token ⇒ demo principal (never admin); Bearer ⇒ real session; bad token ⇒ 401 |
| durable | **auth only** | Bearer required on protected routes |

Flow (both profiles): `POST /v1/auth/register {email,password,preferred_language}`
→ verification token is **printed to the server console** (no email delivery
exists — honest scope) → `POST /v1/auth/verify {token}` →
`POST /v1/auth/login {email,password}` → `Authorization: Bearer <token>`.
Admin iff the email is in `ADMIN_EMAILS`. Probe: `GET /v1/auth/session`.
Request bodies are closed shapes (`extra=forbid`): unknown fields ⇒ 422.

---

## 4. Surfaces

- **API** — `/v1/*` (see `apps.cli routes`). Core entry: `POST /v1/execute`
  (sync or `{"execution_policy":{"async":true}}` ⇒ 202 → `GET /v1/executions/{id}`),
  `GET /v1/agent/executions/{id}/trace` (agent runs), `GET /v1/agent-tools`, `GET /v1/models`.
- **End-user web UI** — `/app/` (static, talks to the same API).
- **Admin console** — `/admin/` (static; every panel reads REAL routes;
  `GET /v1/admin/system`, `/v1/admin/usage`, learning, skills import,
  provider onboarding, self-review, source-change workflow).
- **Health** — `GET /healthz` (liveness). Provider health is per provider
  through the admin surfaces; "cannot verify" is reported as UNAVAILABLE,
  never as healthy.
- **Unified CLI** — `python3 -m apps.cli {serve,check,test,routes,describe}`.

---

## 5. Agent mode

```bash
curl -s -X POST localhost:8000/v1/execute -H 'content-type: application/json' \
  -d '{"ask":"list the files under the agent directory",
       "execution_policy":{"strategy":"agent"},
       "tools":{"allowed":["source_list","source_read","source_search"]}}'
```

The strategy lives under `execution_policy`; tools are granted through the
`tools.allowed` allow-list (closed shape; unknown names ⇒ 422). With the
zero-config `local_echo` provider an agent turn ends in an **honest 502**
`execution_failed` (echo cannot drive reasoning; pinned) — the failed
reasoning execution is still traceable. With a real provider key (verified
live: `plan-1 → act-1-source_list → plan-2 → verify-2 → finalize-2 → final`)
the answer carries `evidence` indices into the ledger.

`strategy=agent` runs `core/agent/runtime.py::AgentRuntime` over the shared
`core/execution/loop.py::AgentLoop`: understand → plan → select → act →
observe → reassess → recover → verify → finalize/stop. Bounded by
`DEFAULT_AGENT_MAX_STEPS=8` (hard cap 32), `DEFAULT_AGENT_DEADLINE_MS=120000`,
repeated-identical-failure refusal, invented-evidence rejection. Tools flow
ToolRegistry → CapabilityFirewall → DeviceRegistry (one chain, shared with the
admin agent). **Deny by default:** with no allow-list and no skills the agent
is offered NO tools; set `AGENT_SOURCE_ROOT` to offer the read-only source tools.
Inspect: `GET /v1/agent-tools`, `GET /v1/agent/executions/{id}/trace` (stages + evidence ledger).

### 5.1 Engineering workspace (files · commands · Git) — ADR-0012

With `AGENT_WORKSPACE_ROOT` set, the SAME agent runtime offers 17 additional
tools (visible in `GET /v1/agent-tools`): reads `ws_read ws_list ws_search
git_status git_diff git_log git_branches git_compare`; privileged `ws_write
ws_move ws_delete ws_apply_changes ws_run git_checkout git_commit git_push
git_merge`. Capability ≠ authority — a privileged act needs **all three**:

1. **Tenant permission** (`workspace.write`, `workspace.exec`, `git.write`) —
   tenants are admitted with the READ permissions only; an admin grants writes:
   `POST /v1/admin/engineering/grants {"tenant_id","permissions":[...]}`.
2. **An Admin-issued ticket** — bounded by acts (`fs.write cmd.run git.commit
   git.push git.merge`), uses (1–1000) and TTL (≤ 24 h):
   `POST /v1/admin/engineering/authorizations {"acts":[...],"uses":3,"ttl_minutes":30,"note":"…"}`
   → the agent passes `authorization_id` in the tool call; each admitted act
   burns ONE use; `POST …/authorizations/{id}/revoke` kills it.
3. **Policy admission** — jail (no `..`, no symlink escape), denylist
   (`.env`, `.git/`, keys…), write cap, command allow-list, cwd inside the
   workspace, timeout cap. Policy is checked BEFORE the ticket is touched: a
   refused act never costs a use.

Refusals are data in the trace: firewall `capability_denied/firewall_deny`
(no permission — handler never runs); handler `execution_failed` with
`engineering refused: authorization_id missing | authorization exhausted |
authorization expired | invalid path … | path is denied by policy | executable
not allowlisted`. Every issue/consume/refuse/revoke is an audit event
(`surface=engineering_authorization`). `GET /v1/admin/engineering/status`
shows workspace, remote, commands, tenant grants and live tickets; the admin
console has the same panel under Governance → Engineering Authorizations.

Reproducible end-to-end proof against a real checkout with a bare remote:
`python3 docs/benchmarks/r164-self-sufficiency/live_e2e_proof.py /path/to/ws`
(scripted model output on the composed runtime; real fs / subprocess / git).

---

## 6. Skills / tools

External skills never auto-trust. Pipeline (admin only):
`POST /v1/admin/skills/import` → scan → validate → review (reviewer recorded)
→ approve → activate. Sources are an enumerated allow-list; content checksum
and provenance are recorded; a blocked skill cannot progress; unfinished
skills are unselectable. Pins: `tests/skills/test_skill_import_resolver.py`.

---

## 7. Provider discovery / onboarding

Requires the gateway binding (`GATEWAY_*`). `POST /v1/admin/providers/onboard`
with URL/config/**credential_ref** → connect → `/v1/describe` discovery →
validate (unknown operation 422, unreachable ⇒ loud 409 refusal, never a guess)
→ register **disabled** → admin enables. Explicit declarations win over
discovery. Direct adapters (`groq`, `genspark_llm`) discover models via
`GET /models` and return `[]` honestly without a health credential.

---

## 8. Learning lifecycle and capability re-test (admin)

```
POST /v1/admin/learning/samples            {knowledge_key, knowledge_value:<object>, source_execution_id?} → PENDING
POST .../samples/{id}/evaluate             {output:<object>} grade via EvaluationPolicyService
POST .../samples/{id}/scan                 deterministic secret scan (paths+labels+fingerprints, never text)
POST .../samples/{id}/sanitize             {passed} — passed=true over findings ⇒ 200 {sanitized:false}
POST .../samples/{id}/admit                {privacy_policy_allows, tenant_user_policy_allows, sensitive_data_handled, not_poisoned}
                                           22 §9 gate; deduplicated/scan-clean are DERIVED ⇒ {admitted:bool}
POST .../samples/{id}/promote              {offline_eval_pass, regression_pass, security_eval_pass, shadow_performance_acceptable,
                                            canary_performance_acceptable, rollback_plan_exists, approval_required, admin_approved}
                                           knowledge write FIRST, then GOLD ⇒ {promoted:bool, stage}
GET  /v1/admin/learning/learned            ask_learned
POST /v1/admin/learning/capability-retest  {probes:[...], baseline?} ⇒ score, delta, production reach
```

"Stored memory" is NOT treated as improvement: GOLD reaching production is
**measured** by the `context_provenance` artifact on real executions
(`gold_blocks` count) and by the re-test's `production` block (rows without
stored context are reported separately, never counted as zero reach).
Self-evolution: `GET /v1/admin/self-review` → `evolution.knowledge_lane` +
`evolution.source_lane`; authoritative source apply is **gated off**
(`authoritative_applier=None`, §14 operator gate) — proposals are sandboxed,
tested, reviewed, never auto-applied.

---

## 9. Observability / audit

- Per-execution: `GET /v1/executions/{id}` (result, artifacts incl.
  `context_provenance`), `GET /v1/agent/executions/{id}/trace` (per-round model/provider/attempts/latency +
  evidence ledger).
- Audit log: closed event set (`core/audit`), tenant-scoped; learning
  promotions, skill activations, admin changes are audited.
- Usage: `GET /v1/admin/usage`. System facts: `GET /v1/admin/system`.
- Startup banner (stdout JSON): profile, provider keys (names only), section-14 gate.

---

## 10. Tests and verification

| Purpose | Command | Safe in dev? |
|---|---|---|
| Full repo gate (what CI would run) | `python3 -m apps.cli check` (= `engineering/verification/check_repo.sh`) | yes |
| Full hermetic suite | `env -u GSK_API_KEY -u GROQ_API_KEY python3 -m pytest` | yes |
| Targeted | `python3 -m apps.cli test tests/agent tests/learning -q` | yes |
| Types (recorded scopes) | `mypy --strict core apps/api apps/admin_agent` | yes |
| Lint / imports | `ruff check .` · `lint-imports` (12 contracts) | yes |
| Live provider smoke (**spends real credits**) | run with `GROQ_API_KEY`/`GSK_API_KEY` set: `pytest tests/providers/test_*_live.py` | no — production-readiness only |
| End-to-end over the wire | start `apps.cli serve` with `ADMIN_EMAILS`, then register → verify (console token) → login → exercise §5–§8 with curl | yes (local) |
| Durable profile | `DATABASE_URL=... alembic upgrade head && pytest tests/api/test_composition_database_v1.py` | needs Postgres |

Read the pytest summary without the `-q` addopt: `python3 -m pytest -o addopts="" -q | tail -3`.

Note: `mypy --strict apps` (broader than the recorded scope) reports missing
third-party stubs for `hvac`/`boto3` in `apps/composition/{secrets,storage}.py`
and `infrastructure/` — a stubs gap, not a defect; install `types-boto3`/
`mypy-boto3-s3` to clear it.

---

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `403` on `/v1/admin/*` | not an admin: email absent from `ADMIN_EMAILS`, or no Bearer token (hybrid mode demo principal is never admin) |
| `404` on `/v1/admin/providers/onboard` | `GATEWAY_BASE_URL` not set — the route is not mounted by design (P2) |
| `404` on learning routes | memory seam absent — the whole lifecycle is absent, not half-available |
| `422` on auth bodies | closed shapes: use `preferred_language`, no extra fields |
| Agent offered 0 tools | deny-by-default; set `AGENT_SOURCE_ROOT` or grant tools via skills |
| `404` on `/v1/admin/engineering/*` | `AGENT_WORKSPACE_ROOT` unset or not a directory — engineering is absent by design (P2) |
| Startup `WorkspaceRootRefused` | `AGENT_WORKSPACE_ROOT` is the platform's own checkout (or contains / is inside it) — ADR-0009 §14; point it at a separate clone |
| `ws_write` refused `firewall_deny` | tenant lacks `workspace.write` — grant via `POST /v1/admin/engineering/grants` |
| `engineering refused: authorization_id missing / exhausted / expired` | no live ticket — issue one via `POST /v1/admin/engineering/authorizations` and pass its id in the tool call |
| `executable not allowlisted` | add it to `AGENT_WORKSPACE_COMMANDS` (shells are deliberately not in the default) |
| `{promoted:false, stage:"knowledge_write"}` | knowledge store refused the write (secret screen / backend) — sample stays VERIFIED, nothing claimed |
| Provider health `UNAVAILABLE: no health credential` | honest: cannot verify ≠ healthy; set the key |
| `attached to a different loop` at shutdown | only if bypassing `apps.main` — the lifespan disposes on the bridge loop |
| Verification email never arrives | there is no email delivery; read the token from the server console |

---

## 12. Where things live

| Concern | Location |
|---|---|
| Composition root (all config read) | `apps/composition/runtime.py` |
| Process entry / lifespan | `apps/main.py`, `apps/cli.py` |
| HTTP routes | `apps/api/*.py` (`create_app` seams) |
| Agent | `core/agent/`, `core/execution/loop.py`, `apps/composition/agent.py` |
| Providers | `core/providers/`, `providers/real/{gateway,groq,genspark_llm}` |
| Learning | `core/learning/`, `apps/api/provenance.py` |
| Skills | `core/skills/`, `apps/api/skills_import.py` |
| Gate script | `engineering/verification/check_repo.sh` |
| Product objective | `docs/architecture/MASTER_VISION_V2_FINAL_DOCUMENTATION.md` |
| Roadmap (dependency order V1–V9) | `docs/architecture/MASTER_VISION_V2_ROADMAP.md` |
| Execution state (R-series ledger) | `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md` |

## 13. Known limitations (honest)
No email delivery; durable stores exist for executions/identity/workspaces/
source-change but usage/audit/learning samples remain in-process; no
distributed worker; no token streaming; gateway onboarding is untestable
end-to-end without a gateway; authoritative self-modification is gated off
by design (the engineering workspace refuses the platform's own checkout —
ADR-0009 §14 unchanged); engineering tickets/grants live in-process (lost on
restart, re-issued by an admin); `ws_run` is a subprocess with a scrubbed
environment and timeout, not a container sandbox.
