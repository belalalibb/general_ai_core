# R169 — A5 GitHub connectivity (evidence notes)

## Verdict
PASS (fake transport). Live GitHub transport: **NOT EVALUATED** (no network transport implementation
exists in the repo; the mandate forbids logging/committing the temporary token and no live call was made).

## Fail-first artifact
`fail_first.txt` — with `apps/agent_dev/git_tools.py` removed and `surface.py` at pre-A5 (631970f),
`tests/agent_dev/test_git_tools.py` fails at collection (`ModuleNotFoundError`), EXIT=2.

## After fix
`after_fix.txt` — 38 passed, EXIT=0.

## Budget
- #3 `apps/agent_dev/git_tools.py` (+559/-0) — commit 796b0dd
- #4 `apps/agent_dev/surface.py` (+32/-13) — commit 833a6ce
- tests: `tests/agent_dev/test_git_tools.py` — commit 1dd565c (budget-free)
- contracts: `core/contracts/{repo_binding,publish_mode}.py` — commit d381489 (budget-free)

## Invariants
- INV-1: contracts first (`RepoBinding`, `Git*Request/Result`, `GitRefusal`, `GitRefusalCode`).
- INV-2: every refusal is `GitRefusal` with a `GitRefusalCode`; protected-branch rejection maps to
  `REMOTE_REJECTED_PROTECTED_BRANCH` with `suggested_mode=pull_request`.
- INV-3: binding carries only `credential_ref`; the token is resolved via `SecretManagerPort.resolve`
  inside the handler, passed to the transport, and never appears in `ToolCallRecord`, audit details or trace
  (asserted by tests).
- INV-7: admin agent untouched; git power lives only in the separately composed dev surface
  (`build_dev_surface(..., git=GitToolset)`); firewall policy needs `git.*` permissions (`dev_tenant_policy(git=True)`).
- Per-binding jail: `jail_path` refuses paths outside the binding root (`PATH_OUTSIDE_BINDING`), including
  a path that belongs to another binding of the same tenant.
- Audit: no new `AuditEventType`; the executor's single `TOOL_CALL` event is enriched with `details["mode"]`
  through `ModeRecordingAudit` (contextvar), so one event per attempt is preserved.

## Open
- Live transport implementation (subprocess git / GitHub REST) is an operator decision; would live under
  `infrastructure/` and be composed, not in `core/` or `apps/agent_dev`.
