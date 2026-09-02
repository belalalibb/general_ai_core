# R164 — P1 Reconciliation Ledger (CORE SELF-SUFFICIENCY DIRECTIVE)

Run-id: `r164-self-sufficiency` · Baseline: `main@ea43046` · Gate at baseline: PASS
(pytest 2586 passed / 64 skipped; mypy --strict clean; ruff clean; import-linter 12/12; secret scan clean).

States: **PROVEN** (exists, wired, reachable, tested) · **INCOMPLETE** (exists, partial) ·
**DISCONNECTED** (exists, not reachable through the shared runtime) · **GATED** (exists,
blocked by a recorded decision) · **MISSING** (does not exist).

## §1 Engineering lifecycle — step by step

| # | Lifecycle step | Location (evidence) | State | Reachable via shared runtime? | Decision |
|---|---|---|---|---|---|
| 1 | Understand repo (read/list/search) | `core/tools/source_reader.py` → `apps/composition/agent.py::source_tool_specs`, env `AGENT_SOURCE_ROOT` | PROVEN | yes (`/v1/execute` strategy=agent, `/v1/agent-tools`) | keep; REUSE the reader engine for the workspace root |
| 2 | Plan / decompose | `core/agent/prompt.py` protocol, `core/execution/loop.py` bounds | INCOMPLETE (W3: no plan artifact) | yes | out of scope for this run (recorded W3 stays open) |
| 3 | Create / modify / move / delete files | `core/sourcechange/patch.py` (`add/modify/delete` in SNAPSHOT space only; no move) | DISCONNECTED + MISSING (move/rename, real workspace writes) | no | **implement**: `core/engineering/workspace.py` jailed `WorkspaceFs` |
| 4 | Multi-file atomic change set | `SourcePatch` (snapshot) | DISCONNECTED | no | **implement**: `ChangeSet` contract + `WorkspaceFs.apply_change_set` (all-or-nothing, restores on failure) |
| 5 | Run commands / toolchain / tests | none in core/apps (only `apps/cli.py`; `HermeticSandbox` compiles, never executes) | MISSING | no | **implement**: `CommandRunnerPort` (core) + `SubprocessCommandRunner` (infrastructure): allowlisted argv[0], cwd = jail, timeout ≤120s, output cap, scrubbed env |
| 6 | Diagnose & recover from failure | `AgentLoop` repeated-failure refusal, `verify_result` → `ToolResultRejected` (W1 closed) | INCOMPLETE (W2 open) | yes | keep; `verify_result` on `ws_run` so a failing test run is a FAILED tool result |
| 7 | Git status/diff/log/branch/compare | none (grep `subprocess`/`git` in core, apps, infrastructure ⇒ only apps/cli.py) | MISSING | no | **implement**: `GitPort` (core) + `GitCli` (infrastructure) |
| 8 | Git commit / push / merge / conflicts | none | MISSING | no | **implement**: `GitPort` write ops; push only to the composition-configured remote; conflicts abort cleanly, reported as data |
| 9 | Authorization of privileged acts | firewall `TenantPolicy` + `ToolCallGate`; ADR-0009 §14 for THIS platform's authoritative source | GATED (§14) for platform source; MISSING for a managed workspace | partial | **implement**: `AuthorizationLedger` — Admin-issued, audited (`APPROVAL_DECISION`), bounded (acts × uses × ttl × workspace) tickets consumed before the act; §14 UNCHANGED |
| 10 | Audit of file/command/git acts | closed `AuditEventType` (13); executor emits one `TOOL_CALL` per attempt | PROVEN (mechanism) | yes | keep closed set — act detail rides `details` |
| 11 | Admin consumption | `apps/api/admin.py::create_admin_router` seams; `ui/admin` Governance rail | MISSING for engineering | n/a | **implement**: `/v1/admin/engineering/*` + minimal UI panel; Admin CONSUMES `core.engineering` |
| 12 | Public seam exposure | `/v1/agent-tools`; deny-by-default allow-list | PROVEN | yes | automatic once specs enter the catalog |
| 13 | Benchmark harness (hermetic) | `tests/agent/test_coding_benchmark.py`, `tests/agent/world.py` | PROVEN (fakes only) | n/a | add REAL benchmark under this directory (P3) |

## §5.2 Authority-boundary classification

**(a)** intentional boundary · **(b)** missing connection · **(c)** missing capability · **(d)** Admin authorization requirement.

| Boundary found | Evidence | Class | Action |
|---|---|---|---|
| ADR-0009 §14: no writes to THIS platform's authoritative source; `AuthoritativeApplierPort` unimplemented | `core/sourcechange/workflow.py` | **(a)** | UNCHANGED. ADR-0012 scopes the capability to a **platform-managed workspace** (`AGENT_WORKSPACE_ROOT`) — composition refuses a root that equals/contains the process source root |
| R3/R4 never registrable as Admin companion classes | `apps/admin_agent/contracts.py` | **(a)** | UNCHANGED |
| `source_*` tools read-only, jailed | `core/tools/source_reader.py` | **(a)** | UNCHANGED; reader engine REUSED |
| `.git/**` + credential files denied to reads/writes | `DEFAULT_DENIED_PATTERNS` | **(a)** | UNCHANGED; Git only via `GitPort` |
| Admin config publish human-only | `apps/api/admin.py` | **(a)** | UNCHANGED |
| Closed `AuditEventType` | `core/contracts/audit.py` | **(a)** | UNCHANGED |
| No shared file-mutation / command / Git capability | rows 3–8 | **(c)** | ADR-0012 → `core/engineering` + `infrastructure/engineering` |
| No Admin-issued consumable authorization (firewall approval is a per-call boolean) | `FirewallDecisionInput.approval_state` | **(d)** | ADR-0012 → `AuthorizationLedger` |
| Workspace tools absent from catalog until wired | `build_agent` | **(b)** | wire `engineering_tool_specs` under `AGENT_WORKSPACE_ROOT` |
| Model policy provider-agnostic (`model_id` only) | `core/contracts/model_policy.py` | **(a)** | benchmark selects models via `explicit_model`; no hard-coded keys |

## Duplicates check
ONE `ToolRegistry` (composed in `build_agent`), ONE `AgentRuntime`, ONE firewall/policy, `SourceChangeWorkflow` untouched (workspace ≠ platform source), learning/skills untouched.
