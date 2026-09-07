# A2 — Repository state map (prompt §2.2)

HEAD at start 20efafa (A1). All facts below are EXECUTED (RUNTIME/STATIC) on this HEAD unless marked INFERRED.

## Identity
| item | value | evidence type |
|---|---|---|
| repository | github.com/belalalibb/general_ai_core (`origin`) | RUNTIME (ls-remote) |
| branch / HEAD | `main` / 20efafa (origin/main = 521d885; 2 local R176 ledger commits ahead, push blocked by invalid token) | RUNTIME |
| worktree | clean; no stash; no dangling objects of interest | RUNTIME |
| package | `ai-orchestration-platform` 0.1.0, Python ≥ 3.12 (sandbox 3.13.14) | STATIC (pyproject) |
| size | platform py ≈ 53 k lines (excl. tests, venv, gateway); gateway-service ≈ 3 k lines; 190 test files | MEASURED |

## Entrypoints (executed)
| purpose | command | result |
|---|---|---|
| runtime | `python3 -m apps.cli serve` (= `apps.main`, HOST/PORT env) | not started in A2 (Tier 2 comes in A5+) |
| CLI | `python3 -m apps.cli {serve,check,test,routes,describe}` | `--help` OK |
| test | `python3 -m apps.cli test …` / `pytest` | via gate |
| verification gate | `python3 -m apps.cli check` = `engineering/verification/check_repo.sh` reading `engineering/verification/green_manifest.json` (5 pytest slices, floor 3127, max_skipped 64, mypy strict scope, ruff, import-linter, secret scan w/ 5 exceptions, .env guard, change budgets, 2 NOT EVALUATED lines) | A0: **FAIL** only on secret scan (F-R176-01); all other checks PASS |
| profile facts | `apps.cli describe` (hermetic env) | `agent_runtime=true, agent_tools_offered=0, demo_principal=false, durable=false, provider_keys=[local_echo], route_count=79, ui_mounts=[/admin,/app]` |
| route surface | `apps.cli routes` (hermetic env) → `routes_hermetic.txt` | 79 paths / 88 method-routes: `/healthz` 1 · `/v1/admin/*` 59 · `/v1/auth` 5 · `/v1/agent` 4 · `/v1/agent-tools` 1 · `/v1/execute` 1 · `/v1/executions` 3 · `/v1/models` 1 · `/v1/projects` 4 · `/v1/skills` 1 · `/v1/usage` 1 · `/v1/webhooks` 3 · `/v1/workspaces` 4 |
| authoritative ops doc | `docs/OPERATIONS.md` ("the ONE authoritative run/operate document", §0–§14) | STATIC; §12 points execution state at the R-series ledger |

## Topology (STATIC from tree; wiring proven later by tests/runtime)
```text
core/            admin agent audit context contracts engineering evaluation events execution identity
                 learning memory providers roles routing runtime secrets security skills sourcechange
                 storage tools usage workspace                      (framework-free domain; import-linter 12 contracts)
apps/            api (FastAPI routers) · composition (env → profile; secrets/storage adapters) · main · cli
                 admin_agent · agent_dev · observability
providers/       common · real/ (platform-side adapters incl. remote-gateway) · registry · templates
gateway-service/ separate package (own pyproject): providers/{groq, assemblyai, fixture_echo, _template, _example}
                 → canonical contract → RemoteGatewayAdapter in platform      (R174: 0 provider-specific lines in core/)
infrastructure/  db (alembic, 18 migrations → 0018_provider_model_bindings) · redis · secrets (Vault) · storage (S3) · security · engineering
ui/              app (/app) · admin (/admin) static mounts
engineering/     adr (12 ADRs + template) · decisions · gates · githooks · proposals · verification
evidence/        R-series ledgers + per-round raw/tracked evidence
docs/            OPERATIONS.md · architecture · ai_orchestration_pack (final_docs_v3 specs, state file, this prompt) · r168–r175 reports
```

## Provider topology (hermetic profile, RUNTIME)
`local_echo` only (honestly labelled). With keys: Groq (platform adapter + gateway Layer-1), AssemblyAI (gateway), Genspark `genspark_llm`. Live evidence so far: R175 L-03 (Groq 7/0/0), R174 (AssemblyAI through the whole chain).

## Composition profiles (OPERATIONS §2, STATIC)
- no env → in-memory, in-process worker + outbox relay, auth-only (401 without Bearer), `local_echo`.
- `DATABASE_URL` → durable (Postgres 17 + pgvector, alembic head 0018). R175 D-01: 3197/0/17/1xfail.
- `DEV_DEMO_PRINCIPAL=1` → demo principal (never admin). `ADMIN_EMAILS` → admin. `AGENT_WORKSPACE_ROOT` → engineering tools.

## Deltas vs prompt assumptions
- Prompt §1.1 lists `RUN.md` (exists — pointer doc) and `tests_live/` — the latter does NOT exist ( live tests live in `tests/providers/test_*_live.py` and gateway tests). Not a defect; recorded as prompt/repo mismatch.
- Prompt env names (`GROQ_API_KEY`, `GW_ASSEMBLYAI_API_KEY`, `GITHUB_TOKEN`) match repo names for the two provider keys; the repo has no `GITHUB_TOKEN` consumer (engineering workspace uses the checkout's own git remote auth).
