# R183 findings ledger (every measurement that FAILED or contradicted the brief; a finding gets an entry, never an off-books fix)

Precedent: `evidence/r182_findings_ledger.md`, `evidence/r182_impl_findings_ledger.md`. Round budget: `round_r183` ceiling **1** (spent on F-R182-01) — no further finding may be fixed inside `core/ apps/ infrastructure/` under this round id.

| id | finding | evidence | severity | disposition | owning round |
|---|---|---|---|---|---|
| — | No new finding in R183 so far: the RED test failed exactly as predicted by F-R182-01 (3/3 assertions on the stale phrase), the fix was doc-only, every guard suite and the fresh-clone gate held. | `evidence/r183/red_test_f_r182_01.txt`; `evidence/r183/gate_head_*.txt` | — | — | — |

Carried forward, recorded, NOT worked (no repository definition — operator contract first; R181-DEC-01, R182_READINESS §4/§6, R182_HANDOFF §12):
- Q7 (evaluation "never evaluated" vs "evaluated: none" served distinction, row 15) — UNDEFINED.
- Provider slice / live account verification + selection enforcement (row 13) — UNDEFINED.
- App Factory persistence / VCS metadata / preview URL / build-deploy state (row 24) — UNDEFINED; "operator-defined contract needed first".
- API keys / scopes route (row 25) — UNDEFINED (routes 404).
- Webhook delivery / attempt status (row 26) — UNDEFINED (registration only).
- F-R182-03 baseline `ui.bytes` drift — RECORDED data; mutation of `green_manifest.baseline.json` requires operator authorization (R182 prompt §6).
- F-R182-02 / F-R182-04 / F-R182I-03 / F-R182I-04 / F-R182I-06 — standing rules, in force, nothing to fix.
