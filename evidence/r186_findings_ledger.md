# R186 findings ledger (every measurement that FAILED or contradicted the brief; a finding gets an entry, never an off-books fix)

Scope of the round: F-R185-L01 and F-R185-L02 only (carried in from `evidence/r185_findings_ledger.md`). Anything else discovered is RECORDED here and NOT fixed under `round_r186`.

| id | finding | evidence | severity | disposition | owning round |
|---|---|---|---|---|---|
| F-R185-L01 (carried) | 390 px horizontal overflow after a FAILED execution (unwrapped `error` frame JSON) | `evidence/r185/live_preview_e2e/overflow_390_root_cause.txt` | medium | **FIXED** (`command.css`: `overflow-wrap: anywhere` on `.frame`/`.error`) — browser proof: recorded live frame 511 px → 0 px overflow at 390 px (`evidence/r186/browser_proof_r186.json`) | R186 |
| F-R185-L02 (carried) | literal `undefined` for `verification.*` when `verification` is null (`reasoning_failed` / `invalid_proposal`) | `evidence/r185/live_preview_e2e/converse_verification_undefined.txt` | low | **FIXED** (`command.js`: null `verification` rendered by name citing `stop_reason`; five served counters verbatim otherwise) — browser proof: 5× `undefined` → none (`evidence/r186/browser_proof_r186.json`) | R186 |

Nothing new raised during R186 (the ruff E501 gate failure on 96fa0dd6 was a lint slip in the new test, fixed in 44fc99b6 — ledger row 4).
