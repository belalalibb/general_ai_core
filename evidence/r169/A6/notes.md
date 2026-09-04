# R169 — A6: PublishMode + read endpoint

**Verdict:** PASS (backend read surface). UI OUT OF SCOPE.

## What was built
- Contracts (budget-free, commit d381489): `core/contracts/publish_mode.py`
  (`PublishMode`, `DEFAULT_PUBLISH_MODE`, `DEFAULT_ALLOWED_MODES`,
  `PublishModeOption`, `PublishModesResponse`, `publish_mode_options`).
- Production change #5 (commit 4ae4e09): `apps/agent_dev/http.py` (+99/-0) —
  `create_dev_router(bindings, *, resolve)` exposing
  `GET /v1/dev/bindings/{binding_id}/publish-modes`.
  - Reuses the admin-router `resolve` seam (401 before any lookup).
  - Tenant-scoped lookup via `RepoBindingRegistry.get(..., tenant_id=...)`;
    unknown, foreign-tenant and malformed ids collapse to one identical
    404 `validation_error` body (anti-enumeration).
  - Body is `PublishModesResponse` from contracts; `direct_push` reported
    non-selectable with `direct_push_not_enabled_for_binding` unless the
    binding opts in.
  - Response never carries `credential_ref`, remote URL or `local_root`.
- Mode recorded in audit/trace: covered by `ModeRecordingAudit` +
  `GitTraceEntry` (A5, `tests/agent_dev/test_git_tools.py`).

## Fail-first
- `fail_first.txt`: module moved aside → collection error
  `ModuleNotFoundError: No module named 'apps.agent_dev.http'`, EXIT=2.
- `after_fix.txt`: 10 passed, EXIT=0
  (`tests/agent_dev/test_publish_modes_http.py`, commit 7831b69).

## Not done (open operator decision)
- The dev router is NOT mounted in `apps/api/app.py`. Mounting it would be
  production change #6 and touches the composition root; left for the
  operator (see closure report).
- INV-7: admin-agent registry/permission classes untouched; the router is a
  new, separately composed surface.
