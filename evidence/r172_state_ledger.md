# R172 — state ledger (observed state, checkpoints, resumption points)

Repository `belalalibb/general_ai_core`, branch `main`. Round-start `67824d0` (R170 closure); R171 verified NOT landed.

## Checkpoints

| When | Item | Note | HEAD | Status |
|---|---|---|---|---|
| 2026-09-04 | §0/§2 | `.gitignore` hygiene block (`/secrets/` anchored after unanchored form matched 8 tracked files); `round_r172` ceiling 8 + verifier loop + guard test; Groq no-leak tests (3, no production change); `evidence/r172/{discovery.md,secret_scan.txt}` | e8772f6 | done |
| 2026-09-04 | C1 | `core/tools/denied_paths.py` NEW + `apps/agent_dev/surface.py` wiring (budget 1/8); tests 61 passed 1 xfailed; `evidence/r172/C1/`; IMPL-018. Collateral: `*accounts*`/`*password*` deny `core/providers/accounts.py`, `infrastructure/security/password.py` (kept, documented). `session_dump.txt` decided ALLOWED. Sandbox reset wiped the first uncommitted test file — recreated | see commit | done |
| 2026-09-04 | C2 | `core/contracts/binding_store.py` NEW, `core/tools/binding_store.py` NEW, `apps/agent_dev/git_tools.py` optional `store` (budget 2/8); 14 tests; suites 300 passed 1 xfailed; `evidence/r172/C2/`; IMPL-019. Composition wiring left as owner decision | see commit | done |
| 2026-09-04 | C3 | `GitRefusalCode.REMOTE_NOT_TRUSTED`; `core/contracts/remote_trust.py` NEW; `core/tools/{atomic_json,remote_trust}.py` NEW; `binding_store.py` refactored onto atomic_json (14 C2 tests green, `d24a213`); `apps/agent_dev/git_tools.py` `trust` + `_require_trust` before `_token` in fetch/publish (budget 3/8); 19 tests; suites 319 passed 1 xfailed; `evidence/r172/C3/`; IMPL-020. Composition wiring left as owner decision. Reset mid-C3 wiped uncommitted contract/atomic_json/refactor once — recreated, WIP committed early | see commit | done |

## Resets this round
Reset after prep push (deps/identity/credential/helper gone; uncommitted C1 test lost). Recovered per protocol; nothing on origin redone. Two further resets before C2 (identity, deps, helper, uncommitted 73→64 fix lost once) — same recovery; policy is now commit after every small step (fail-first committed separately as 3728f0a).
