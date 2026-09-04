# C7 — mount the dev read router in `create_app` (IMPL-024, budget row 7/8)

## What changed
- `apps/api/capabilities.py` (+2): `"dev.publish_modes"` added to the closed `CAPABILITY_IDS`
  (16 → 17). Module header already says extending is "a deliberate edit HERE"; this is that edit.
- `apps/api/app.py` (+23): import `RepoBindingRegistry` type; `create_app(..., dev_bindings:
  RepoBindingRegistry | None = None)`; after the workspace router, `if dev_bindings is not None:`
  composition-time `from apps.agent_dev.http import create_dev_router` and
  `app.include_router(create_dev_router(dev_bindings, resolve=_principal))`; catalog row
  `_cap("dev.publish_modes", dev_bindings is not None, "dev_bindings seam -> GET /v1/dev/bindings/{id}/publish-modes (R169 A6 / R172 C7)")`.
- `tests/api/test_dev_router_mount_r172.py` NEW (11 tests). `docs/r169/CAPABILITY_MAP.md` updated
  (17 ids, new row, C7 paragraph, publish-modes section).

## Decision: flag, not always-on (owner decision)
- Seam-presence flag, identical posture to `models=`, `usage=`, `outbox=`: the catalog derives
  `available`/`inert` from the SAME variable that mounts the route (V7 honesty rule).
- Always-on was rejected: the router needs a `RepoBindingRegistry`, and `apps/composition/runtime.py`
  builds none today (C2 binding store and C3 trust registry are not wired there). Mounting an empty
  registry always-on would serve a route where every id is "unknown" — a hidden claim.
- Consequence: **production stays `inert`** for `dev.publish_modes` until a later round injects the
  registry. Pinned by `test_default_runtime_profile_does_not_compose_the_dev_seam` so flipping it is
  a deliberate, documented act. Recorded as an open item for §9.

## Behaviour pinned (11 tests)
closed id present; seam ON: 200 with all four modes (`default=pull_request`, `direct_push`
unselectable with reason, no credref/remote leak), route in `app.openapi()` and dispatches, capability
`available`, unknown id → one typed 404 (`validation_error`, `details={binding_id}`, retryable False),
malformed id same 404, foreign-tenant id byte-identical to unknown (after id/trace normalisation; no
label/remote/branch/credref in body), own binding resolves beside a foreign one; seam OFF: route absent
(generic 404, no `binding_id` echo), capability `inert`, `runtime.py` passes no `dev_bindings=`.

## UI route guard
`tests/ui` 14 passed — `test_ui_route_literals_exist_on_served_app` and
`test_no_hardcoded_capability_ids` did not trip (no UI file touched; `dev.publish_modes` is not
quoted in `ui/admin/app.js`). Stop condition not reached.

## Findings
- Import cycle `apps.agent_dev.http → apps.api.errors → apps.api.__init__ → apps.api.app` when
  `app.py` imports `create_dev_router` at module level; fixed with a composition-time import at the
  seam (precedent: `TYPE_CHECKING`/local imports of `Principal` across `apps/api/*`). Both import
  orders pinned in `after_fix.txt`.
- FastAPI 0.141 `_IncludedRouter` lazy routes (already recorded in `test_aa1_api_seams.py`) — the
  route-table assertion goes through `openapi()` plus a dispatch check.

## Not done / open
- Production composition does not inject `dev_bindings` (needs C2 store + C3 trust registry wiring).
- No write routes under `/v1/dev` — read surface only, as R169 A6 scoped it.

## Verification
- fail-first: `evidence/r172/C7/fail_first.txt` (9 failed / 2 passed at bde7276 — TypeError
  `unexpected keyword argument 'dev_bindings'`, KeyError `dev.publish_modes`).
- after-fix: `evidence/r172/C7/after_fix.txt`.
