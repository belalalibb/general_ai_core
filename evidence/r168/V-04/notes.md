# V-04 — §6.5 `/v1/` route-literal drift in `ui/admin/app.js` (verification track, outside the change budget)

## Status: CLOSED DEGRADED (count held at ceiling; not reduced)

- Count at close: **73 / N0 = 73** → ratio **1.00** (no drift up, no reduction).
- Distinct `api('/v1/...')` literals: 54 (64 call sites; 73 raw `/v1/` occurrences incl. template strings and comments).
- `index.html`: 15 textual occurrences, **0 wired** (`href/src/action/data-*`) — guarded by `test_html_and_css_carry_no_v1_routes`. `styles.css`: 0.
- Guards in force (`tests/ui/test_admin_static_check.py`):
  - `test_v1_occurrence_count_never_exceeds_N0` — raw count ≤ manifest ceiling ≤ baseline N0 (ceiling may only move down).
  - every `api('/v1/...')` literal must resolve to a route served by the FastAPI app (static route match).

## Why not reduced in R168
1. Reduction requires editing `ui/admin/app.js`, a served asset with no R168 defect against it (D-01..D-11 are backend items). INV-2 (additive-only) forbids a count-driven rewrite of call sites.
2. A prefix-constant refactor (`const V1 = "/v1"`) would drop the raw count to ~1 without changing behaviour — but it would also blind the served-route guard (literals become non-static) unless the guard is rewritten in the same commit; that is a UI/verifier rewrite, not an R168 repair.
3. INV-5: the ceiling is **not** lowered artificially; the manifest stays at 73 = measured.

## Next step (R169)
- Introduce a single route table in `app.js` (`ROUTES = { login: "/v1/auth/login", ... }`) and extend the static check to read literals from that table; then lower `ui_static_check.v1_count_ceiling_N0` to the table size (~54) in the same commit (INV-3: guard + decision-log entry).

- Budget: 0 production changes (ui/ not in budget scope; nothing edited).
