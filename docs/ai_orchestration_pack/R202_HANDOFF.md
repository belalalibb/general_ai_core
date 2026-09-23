# R202 HANDOFF — Templates + App Factory UX (UI-only)

Status: **OPEN** (R202-DEC-01). Base: `main 22111694` (post-R201 closure). Branch `genspark_ai_developer_r202`. Production ceiling 0; `ui/app/app.js` `/v1/` ceiling 22 → 23 (declared).

## 1. Authority (operator, verbatim)
"APPROVE R202. Confirm the proposed rulings: D1 = a, D2 = i, D3 = i, D4 = i, D5 = i, D6 = i, D7 = yes, D8 = defer. Confirm the declared ui/app/app.js /v1/ ceiling adjustment: 22 → 23. Execute R202 exactly as proposed. Preserve the unified QEVION direction, existing shared multi-tenant architecture, security/authorization boundaries, one Router, one StrategyExecutor, one TemplateRegistry, and the existing execution path. Do not add TemplateOverride/model selection, project filtering, Command template reads, template persistence, user/workspace templates, or App Factory code generation. Stop at the next decision gate."

## 2. Allowed / frozen
- MAY change: `ui/app/{app.js,index.html,styles.css}`; `tests/ui/test_template_detail_r202.py` (new, RED first); R197 D4 pin flipped 1:1; R201 count pin `<= 23`; manifest ceiling fields; `evidence/r202/*`; records; register §C row for `GET /v1/templates/{ref}` at closure.
- FROZEN: `core/ apps/ infrastructure/` (0 files); contracts + freeze baseline (46); every `/v1/admin/*` and `/v1/agent/*` gate; `CAPABILITY_IDS`; `command.js` 12 + one `fetch(`; `ui/admin/app.js` 73; `POST /v1/execute` wire shape.

## 3. Steps
1. Declaration (this file, R202-DEC-01, manifest `round_r202` + ceiling 23, pointer, ledger row 1) — commit + push BEFORE code.
2. RED: `tests/ui/test_template_detail_r202.py` + R197 pin flip → `evidence/r202/red.txt`.
3. R202-A `loadTemplateDetail` / `renderTemplateDetail` / `#template-detail` panel / styles. R202-B timeline labels.
4. GREEN → `evidence/r202/green.txt`; real-browser proof; guards 23/4 · 12/1 · 73; freeze; production diff 0.
5. Gate of record fresh clone → ratchet → head re-gate → PR (merge commit) → post-merge gate + regression → closure PR (records + register flip) → STOP.

## 4. Not in this round (operator ruling)
`TemplateOverride` / model selection in template mode (D6); template ref on the execution record (D8); project filtering; Command template reads or a Command picker; template persistence; user/workspace templates; App Factory code generation; token custody across trees. Each needs its own `APPROVE`.
