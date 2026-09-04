# R169 A3/A4 — dev-agent composition root + tests

## Budget
- Change #2 of 6: `apps/agent_dev/surface.py` (+236/-0), committed as 631970f
  BEFORE its tests existed, deliberately, so the module survives sandbox resets
  (resets #7, #8, #9 each wiped uncommitted work). Tests followed in 080c534.
- `apps/agent_dev/__init__.py` re-exports only (same commit, same change).

## Fail-first / after-fix
- `fail_first.txt`: with `apps/agent_dev` moved aside, `tests/agent_dev`
  fails at collection (ImportError ×2), EXIT=2.
- `after_fix.txt`: module restored, 37 passed, EXIT=0.

## What the 37 tests pin
- `test_dev_surface.py` (28): composition over the core fabric; registry holds
  exactly `source.read`/`source.write`; approval policy NONE / BEFORE_ACTION;
  read jail + denylist refusals as `read_refused` data (no content leak);
  invalid arguments → `validation_error` data; write without approval →
  gate `tool_approval_required:before_action`; write not granted → `firewall_deny`;
  unknown tenant → `firewall_deny`; undeclared permission →
  `permission_undeclared:source.write`; missing usage entitlement →
  refused `entitlement_exceeded` with `gate_decision.admitted is True`; one
  TOOL_CALL audit event per attempt, never carrying content.
- `test_admin_boundary.py` (9, INV-7): snapshot of the admin registry's 11 base
  names and 3 source-read names; classes ⊆ {R0,R1,R2} and disjoint from
  NEVER_REGISTRABLE_CLASSES; no admin tool name contains write/git/github/
  publish/commit/push; dev names disjoint from admin names; AA2/AA3/NEVER sets
  and `len(ToolClass)==5` unchanged; `AgentToolSurface.repo_reader` stays a
  `SourceReader | None` with no writer/git field; admin `ToolRegistry` has no
  `register`; building the dev surface leaves the admin registry unchanged.

## Technique notes
- Async handlers driven through a sync `run[T]` wrapper (PEP 695).
- `ToolExecutor` reserves usage BEFORE the handler; tests configure a tenant
  plan or assert the typed refusal when none exists.
- `ToolCallGate.admit(*, tool_id, request, device_id=None)`; permission comes
  from `request.permission`.
- Admin constants are `AA2_REGISTRABLE_CLASSES` / `AA3_REGISTRABLE_CLASSES` /
  `NEVER_REGISTRABLE_CLASSES` (first draft after reset #9 guessed `*_ALLOWED`
  and failed at import; corrected).

## Lint / types
- `ruff format` + `ruff check tests/agent_dev` → clean.
- `mypy --strict apps/agent_dev` → clean (A3 commit).
- `lint-imports` → 13 kept, 0 broken (A3 commit).

## Manifest
- `pytest.slices[rest].selection` += `tests/agent_dev` (partition guard).
- `change_budget.round_r169`: `changes_used` 2, log += A3.
