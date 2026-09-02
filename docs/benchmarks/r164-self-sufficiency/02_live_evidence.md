# R164 — Live evidence (ADR-0012 shared engineering workspace)

Companion to `01_reconciliation_ledger.md` (the P1 gap inventory). Everything
below was observed on 2026-09-02 against `main`; nothing is asserted that was
not printed by a real process. Where the sandbox could not prove something,
that is written down as a limitation, not smoothed over.

## 1. What was built (filesystem facts)

| Layer | Location | Content |
|---|---|---|
| Contracts | `core/contracts/engineering.py` | `EngineeringAct` (5 acts), `FileChange`/`ChangeSet`, `CommandRequest/Result`, `EngineeringAuthorization` |
| Core | `core/engineering/` | `WorkspaceFs` (jail, denylist, write cap, atomic change-set with rollback), `CommandPolicy`, `validate_ref`, `AuthorizationLedger`, `EngineeringBundle`, `engineering_tool_specs` (17 tools into the ONE `ToolRegistry`) |
| Adapters | `infrastructure/engineering/` | `SubprocessCommandRunner` (scrubbed env, timeout kill), `GitCli` |
| Composition | `apps/composition/engineering.py`, `agent.py`, `runtime.py` | env → bundle; §14 guard (`WorkspaceRootRefused`); tenants admitted with READ permissions only; `EngineeringAdminSurface` handed to `create_app` |
| Admin seam | `apps/api/engineering_admin.py`, `apps/api/admin.py` | `GET /v1/admin/engineering/status`, `GET/POST …/authorizations`, `POST …/authorizations/{id}/revoke`, `POST …/grants` |
| Admin UI | `ui/admin` | Governance → Engineering Authorizations (status, issue/revoke, grant); 3 sanctioned POSTs; 404 rendered as "route absent" |
| Guard rail | `pyproject.toml` import-linter | Admin surfaces must not import `infrastructure.engineering` (13/13 contracts kept) |

Tests: `tests/engineering/` — 62 (workspace/policy/ledger 36, runtime
authorization 8, real subprocess+git adapters 7, admin seam + composition 8,
plus pins added in this round); existing UI/composition pins extended.

## 2. Live HTTP smoke (real server, `python3 -m apps.main`)

Env: `ADMIN_EMAILS=ops@example.com AGENT_WORKSPACE_ROOT=/tmp/r164/ws
AGENT_WORKSPACE_COMMANDS=python3,pytest`. Identity: register → console token →
verify → login (Bearer).

| Call | Observed |
|---|---|
| `GET /v1/admin/engineering/status` (admin) | `configured:true`, `commands:[python3,pytest]`, `read_permissions:[git.read,workspace.read]`, `write_permissions:[git.write,workspace.exec,workspace.write]`, `tenant_granted:[git.read,source.read,workspace.read]` (READS ONLY on admission), `authorizations:[]` |
| `GET /v1/agent-tools` | 17 engineering tools offered (`git_* ×9`, `ws_* ×8`) |
| `POST …/grants {workspace.write, git.write}` | 200 → `granted_permissions` now includes both |
| `POST …/authorizations {acts:[fs.write,git.commit,git.push], uses:3, ttl_minutes:30}` | 201, ticket with `uses_remaining:3`, `expires_at` +30 min, `issued_by` = admin user id |
| `POST …/grants {root.everything}` | 422 (unknown permission) |
| `GET …/status` anonymous | 403 |
| same server WITHOUT `AGENT_WORKSPACE_ROOT` | 404 on every `/v1/admin/engineering/*` route; 0 engineering tools |
| `POST /v1/execute strategy=agent` with `ws_write` | **502 `execution_failed`** at `plan-1` — the model proxy answered `Free-plan credits can't be used with the Genspark API / LLM proxy` (raw text, `invalid_proposal`). Recorded limitation, see §4 |

## 3. Live end-to-end proof (composed runtime, real fs / subprocess / git)

`python3 docs/benchmarks/r164-self-sufficiency/live_e2e_proof.py /tmp/r164/ws`
— `/tmp/r164/ws` is a real git checkout with a bare `origin`. The script builds
the production profile (`build_runtime_profile`) and substitutes ONLY the
model's words (scripted adapter on the same `ExecutionService`); registry,
firewall, ledger, workspace, runner and git are the real composed instances.

```
== 1. tenant holds READ permissions only -> ws_write REFUSED by firewall
   step 1 ws_write refused {"reason":"capability_denied","detail":"firewall_deny"}   NOTE.md exists: False
== 2. Admin grants workspace.write + git.write, still NO ticket -> handler FAILS as data
   step 1 ws_write failed {"detail":"ValueError: engineering refused: authorization_id missing"}
== 3. Admin issues ticket [fs.write, git.commit, git.push] uses=3
== 4. write -> status -> commit -> push -> log
   step 1 ws_write   succeeded {"path":"NOTE.md","bytes":17,"created":true}
   step 2 git_status succeeded {"branch":"main","clean":false,"entries":["?? NOTE.md"]}
   step 3 git_commit succeeded {"committed":true,"sha":"81b0f4f…"}
   step 4 git_push   succeeded {"pushed":true,"remote":"origin","branch":"main"}
   step 5 git_log    succeeded {"commits":[{"sha":"81b0f4f…","subject":"feat: NOTE.md written by the shared agent runtime"},…]}
   stop: final | ok/failed: 5 0
== 5. ticket exhausted -> "engineering refused: authorization exhausted"; AGAIN.md exists: False
== 6. jail + policy bind WITH a valid ticket and exec permission
   ../escape.txt -> "invalid path … segment '..'"      (.env) -> "path is denied by policy"
   bash -lc id  -> "executable not allowlisted: bash"  python3 calc.py -> exit_code 0
   escape.txt outside jail: False | .env: False | ticket uses left: 4  (only the admitted run burned a use)
== 7. audit  {'issue': 2, 'consume': 4, 'refuse': 1}  refusal reasons: ['authorization exhausted']
PROOF OK
```

Real state afterwards: `git log` in the workspace AND in the bare remote both
show `feat: NOTE.md written by the shared agent runtime`; `NOTE.md` contains
`hello from agent`.

**Bug found by this proof and fixed** (`core/engineering/tools.py`): the file
handlers consumed the ticket BEFORE the jail/denylist check, so a refused
`../escape.txt` still cost a use (t2 showed 2 left instead of 4). Now
`ws_write/ws_move/ws_delete/ws_apply_changes` call `WorkspaceFs.admit()` first
— same order `ws_run` already had — pinned by
`test_ws_write_admits_jail_and_denylist_before_burning_ticket`.

## 4. Limitations (honest)

- A real-LLM agent turn over HTTP was NOT proven: the only reachable provider
  (Genspark proxy via `GSK_API_KEY`/`OPENAI_*`) refuses free-plan credits; no
  Groq key present. The runtime path that fails there (`plan-1`,
  `invalid_proposal`) is the same one that succeeded with a real key in R160.
- Tickets, grants and audit are in-process (in-memory profile); a restart
  requires the admin to re-issue.
- `ws_run` is a scrubbed-env subprocess with a timeout — not a container.
- ADR-0009 §14 is unchanged: `AuthoritativeApplierPort` remains unimplemented;
  the workspace guard refuses the platform's own checkout at composition time.
