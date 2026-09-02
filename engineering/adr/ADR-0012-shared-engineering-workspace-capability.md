# ADR-0012 — Shared Engineering Workspace Capability (files · commands · Git) under Admin authorization

```text
STATUS: ACCEPTED
DATE: 2026-09-02
TASK: R164 — CORE SELF-SUFFICIENCY DIRECTIVE (operator instruction: "execute the FINAL PROMPT fully, on main")
SUPERSEDES: NONE (ADR-0009 §14 remains in force, unchanged — see "Relationship to ADR-0009")
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
No significant architecture change is allowed without an ADR.

---

## Context

The P1 reconciliation ledger (`docs/benchmarks/r164-self-sufficiency/01_reconciliation_ledger.md`)
established, from filesystem evidence, that the SHARED agent runtime can **understand** a
repository (read-only `source_*` tools over a jail) but cannot **engineer** one:

- no file mutation reaches a real workspace (only hermetic snapshot patches; no move/rename;
  no atomic multi-file change set);
- no command / toolchain / test execution exists anywhere in `core`, `apps` or
  `infrastructure` (the only `subprocess` use is the operator CLI);
- no Git capability exists at all;
- the firewall's approval gate is a per-call boolean with no Admin-issued, bounded,
  consumable authorization for privileged acts.

Invariants that must hold:

1. Nothing generic under `apps/admin_agent`, `apps/api/admin.py`, `ui/admin` — the Admin
   **consumes** shared capability.
2. Exactly ONE tool registry / runtime / policy / source-change system.
3. `core` stays pure — ports in core, adapters in `infrastructure`.
4. Deny-by-default: capability ≠ authority; every privileged act needs a grant, an entitlement
   and an explicit authorization; every act is audited.
5. **ADR-0009 §14**: the running platform's own authoritative source is never written by the
   platform; `AuthoritativeApplierPort` stays unimplemented until a separate operator decision.

## Alternatives

**A. Extend `SourceChangeWorkflow` (R3) to write real files and drive Git.** R3 is the
§14-gated path for the platform's OWN source; widening it conflates workspace engineering with
self-modification and its `PatchOpKind` does not model move/rename, commands or Git. Rejected.

**B. Put file/command/Git handlers directly in `apps/composition/agent.py` (or the Admin
agent).** Generic capability outside core; untestable without composition; Admin would own it.
Rejected.

**C. A new shared `core.engineering` package (ports + pure engine) with `infrastructure`
adapters, registered into the ONE `ToolRegistry` by composition, guarded by the ONE firewall,
with Admin-issued authorizations for privileged acts, operating on a platform-managed
WORKSPACE structurally distinct from the platform's own source.** **Chosen.**

## Decision

1. **Contracts** — `core/contracts/engineering.py`: `ChangeSet`/`FileChange` (`write|move|delete`),
   `CommandRequest`/`CommandResult`, `GitStatus`/`GitCommitResult`/`GitPushResult`/`GitMergeResult`,
   `EngineeringAct` (closed: `fs.write`, `cmd.run`, `git.commit`, `git.push`, `git.merge`),
   `EngineeringAuthorization` (tenant, workspace label, acts, uses, expiry, issued_by).
2. **Core** — `core/engineering/`: `WorkspaceFs` (root-jailed like `SourceReader`, reuses its
   reader; byte-capped writes; move; delete; atomic `apply_change_set` with rollback);
   `CommandPolicy` + `CommandRunnerPort` (allowlisted argv[0], cwd inside jail, timeout ≤120 s,
   env allowlist); `GitPort` + `validate_ref` (push only to the configured remote name);
   `AuthorizationLedger` (issue/revoke/consume; every act appends `APPROVAL_DECISION` through
   the existing `AuditLogPort`); `engineering_tool_specs` (AgentToolSpecs: `ws_read/list/search`,
   `ws_write/move/delete/apply_changes`, `ws_run`, `git_status/diff/log/branches/compare`,
   `git_checkout/commit/push/merge`). Privileged handlers consume a ticket BEFORE acting;
   `ws_run` carries `verify_result` so a non-zero exit is a FAILED tool result.
3. **Adapters** — `infrastructure/engineering/`: `SubprocessCommandRunner` (asyncio exec, no
   shell, kill on timeout, capped output, scrubbed env) and `GitCli` (git binary through the
   same runner; `credential.helper=` disabled per command; conflicts abort + reported as data).
4. **Permissions (DATA on the existing `TenantPolicy`)**: `workspace.read`, `workspace.write`,
   `workspace.exec`, `git.read`, `git.write`; entitlement `agent.tools`; resource `workspace:root`.
   Default tenant policy grants READ permissions only; write/exec/git.write grants are Admin
   acts (`POST /v1/admin/engineering/grants`) and privileged calls additionally need a ticket.
5. **Composition** — `apps/composition/engineering.py` builds the bundle from
   `AGENT_WORKSPACE_ROOT` (+ `AGENT_WORKSPACE_REMOTE` default `origin`,
   `AGENT_WORKSPACE_COMMANDS` default `python3,pytest,ruff`) and REFUSES a root that equals or
   contains the process's own source root (structural §14 guard). `build_agent` takes it optionally.
6. **Admin consumption** — `/v1/admin/engineering/status`, `POST …/authorizations`,
   `GET …/authorizations`, `POST …/grants`; a minimal `ui/admin` Governance panel.
7. **Architecture contract** — import-linter: `apps.admin_agent` and `apps.api.admin` must not
   import `infrastructure.engineering`.

## Reason

Only C keeps the authority chain single, core pure, Admin a consumer, and §14 intact by
construction (workspace ≠ platform source; R3 / `AuthoritativeApplierPort` untouched).

## Consequences

- Any consumer gets the full engineering lifecycle through the same deny-by-default seam.
- Operators must provision a workspace clone + remote; a wrong root is refused loudly.
- Rollback: unset `AGENT_WORKSPACE_ROOT` ⇒ tools absent from the catalog (pre-ADR behaviour).
- Not changed: `AuditEventType`, R3/R4 never-registrable classes, `SourceChangeWorkflow`, §14.

## Relationship to ADR-0009

§14 gates writes to the platform's authoritative source. This ADR does not activate that path.
Engineering the platform's own repository through this capability would require a separate
explicit operator decision and a new ADR.

## Status

ACCEPTED — took effect in R164 (commits on `main` following `ea43046`).
