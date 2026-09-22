# R201 HANDOFF — Context-carrying execution (UI-only)

Status: **OPEN** (R201-DEC-01). Base: `main daa88afd` (post-R200 closure). Branch `genspark_ai_developer_r201`. Ceiling 0.

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
