# R172 — state ledger (observed state, checkpoints, resumption points)

Repository `belalalibb/general_ai_core`, branch `main`. Round-start `67824d0` (R170 closure); R171 verified NOT landed.

## Checkpoints

| When | Item | Note | HEAD | Status |
|---|---|---|---|---|
| 2026-09-04 | §0/§2 | `.gitignore` hygiene block (`/secrets/` anchored after unanchored form matched 8 tracked files); `round_r172` ceiling 8 + verifier loop + guard test; Groq no-leak tests (3, no production change); `evidence/r172/{discovery.md,secret_scan.txt}` | e8772f6 | done |
| 2026-09-04 | C1 | `core/tools/denied_paths.py` NEW + `apps/agent_dev/surface.py` wiring (budget 1/8); tests 61 passed 1 xfailed; `evidence/r172/C1/`; IMPL-018. Collateral: `*accounts*`/`*password*` deny `core/providers/accounts.py`, `infrastructure/security/password.py` (kept, documented). `session_dump.txt` decided ALLOWED. Sandbox reset wiped the first uncommitted test file — recreated | see commit | done |

## Resets this round
Reset after prep push (deps/identity/credential/helper gone; uncommitted C1 test lost). Recovered per protocol; nothing on origin redone.
