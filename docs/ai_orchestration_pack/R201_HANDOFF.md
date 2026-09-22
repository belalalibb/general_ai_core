# R201 HANDOFF — Context-carrying execution (UI-only)

Status: **CLOSED** (R201-DEC-02). Base: `main daa88afd` → merged as `main 2140e541` (PR #60, merge commit) + records-only closure PR. Branch `genspark_ai_developer_r201` (deleted after closure). Ceiling 0 used 0.

## 1. Authority (operator, verbatim)
"APPROVE R201 with D1–D7 confirmed (recommended: D1=a, D2=i, D3=i, D4=defer, D5=defer, D6=defer, D7=defer)"

## 2. Allowed / frozen
- MAY change: `ui/app/command/{command.js,index.html,command.css}`; `ui/app/app.js` (receiver `&execution=` + self-restore of non-secret selection); `ui/admin/app.js` (receiver `&execution=` only); `tests/ui/test_context_carry_r201.py` (new, RED first); `evidence/r201/*`; records.
- FROZEN: `core/ apps/ infrastructure/` (0 files); contracts + freeze baseline (46); every `/v1/admin/*` and `/v1/agent/*` gate; register §C; `CAPABILITY_IDS`; `command.js` `/v1/` 12 + one `fetch(`; `ui/app/app.js` ≤ 22 / 4; `ui/admin/app.js` 73.

## 3. Steps
1. Declaration (this file, R201-DEC-01, manifest `round_r201`, pointer, ledger row 1) — commit + push BEFORE code.
2. RED: `tests/ui/test_context_carry_r201.py` → `evidence/r201/red.txt`.
3. R201-A `command.js`: `executionHref(owner, id)`; admin-tier record affordances (Workbench · runs / Admin · executions) under the R200 permission rule; tenant tier lists served `state.executions` rows as execution-carrying links (no new request). Markup + css.
4. R201-B receivers: `#view=<v>&execution=<uuid>` → `showView` + `openRun` (runs only); `#surface=<s>&execution=<uuid>` → rail click + `openExecution` (executions only). Boot-once; anchored regex; no new reads.
5. R201-C Workbench self-restore (`sessionStorage` `qevion.app.context`; served-list membership; hash wins; cleared on logout; never the token).
6. GREEN → `evidence/r201/green.txt`; real-browser proof (request sets, malformed id, foreign id → verbatim server 404, round trip, `localStorage` empty); guards 12/1 · ≤22/4 · 73; freeze; production diff 0.
7. Gate of record fresh clone → PR (merge commit) → post-merge gate + regression → records-only closure PR → STOP.

## 4. Not in this round (operator D4–D7 = defer)
Token custody across trees (re-login stays); project filter on `GET /v1/executions` / project on the execution record (architectural); model/provider selection; Command attaching `project_id`; `templates/{ref}` detail; root `/` redirect; any register flip. Each needs its own `APPROVE`.

## 5. Outcome
- **Delivered:** R201-A `command.js` — `ADMIN_EXECUTIONS_OWNER` + `executionHref(owner, id)` (`<owner.href>&execution=<uuid>`, built from the routing table, no `/v1/` literal); `renderExecutionSurfaces()` on the selected execution (Workbench · runs / Admin · executions) under the R200 permission rule; tenant tier lists the already-fetched `state.executions` rows as execution-carrying links (`#tenant-execution-list`, no new request). R201-B `applyDeepLink` in `ui/app/app.js` and `ui/admin/app.js` accept an optional `&execution=<uuid>` and hand it to the EXISTING `openRun` / `openExecution` (runs / executions only); anchored regex, boot-once, no listeners, no timers, no new reads. R201-C `ui/app/app.js` `saveContext` / `restoreContext` / `clearContext` on `sessionStorage` `qevion.app.context` (view, selectedWorkspace, project, template); served-list membership required; explicit hash wins; cleared on logout; never the token; `localStorage` absent from the file.
- **Guards:** `tests/ui/test_context_carry_r201.py` 12 items — RED 8 failed / 4 passed on the opening tree 109fe293 → GREEN 12/12. Real-browser proof `evidence/r201/browser_probe_b67c0a09.json` + 7 screenshots: tenant hop = exactly one `GET /v1/executions/<id>`, no `/v1/admin/*`/`/v1/agent/*`; admin record links + admin deep link open the record; malformed id → no by-id request; tenant B with tenant A's id → the server's verbatim `validation_error: Unknown execution id.`; round trip restores workspace + project + template + view; `#view=models` overrides the stored view; `localStorage` keys `[]`; context `null` after logout.
- **Invariants held:** `core/ apps/ infrastructure/` diff EMPTY (`round_r201` 0/0); `command.js` 12 + one `fetch(`; `ui/app/app.js` 22 / 4; `ui/admin/app.js` 73; freeze `--check` MATCHES (46); every `/v1/admin/*` and `/v1/agent/*` gate untouched — the server remains the only tenancy/permission authority.
- **Gates:** gate of record fresh clone `798903ca` PASS 3984/0/0/64 + gateway 194 + regression 18 roots 3139/13/0; ratchet 3972 → 3984 (+12); head re-gate `318d7930` PASS with the ratchet in force; PR #60 merged by merge commit → `main 2140e541`; post-merge fresh clone `2140e541`: first run FAIL 3980/4 (environment: Chromium binary erased by a sandbox reset — recorded, row 10), re-run on the same clone after `playwright install chromium` PASS **3984/0/0/64** (row 11); gateway 194; regression 3139 passed / 13 skipped / 0 failed.
- **Incidents (honest record):** three sandbox resets during the round (guard run, merge call, post-merge gate); each time work resumed from the pushed checkpoint; one incomplete ratchet commit (fc6275c4) corrected by the next commit; the post-merge FAIL is kept in the evidence and explained rather than overwritten.
- **NOT claimed:** Production Ready (D-03 / N-9 OPERATOR-OWNED-OPEN); D4 token custody across trees; D5 project filter / project on the execution record (architectural); D6 model/provider selection; D7 Command attaching `project_id`; `templates/{ref}` detail; root `/` redirect; any register §C flip. Each needs its own `APPROVE`.
