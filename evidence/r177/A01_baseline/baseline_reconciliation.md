# R177-A01 — Baseline reconciliation (§2 verified row by row against the repository)

Method: every row checked with a command against the checked-out tree at session start. KNOWN = command output; nothing inferred.

| §2 row | Command | Result | Status |
|---|---|---|---|
| HEAD 13be858d, main, clean | `git log --oneline -1; git status --porcelain \| wc -l; git rev-parse origin/main` | `13be858d ledger(r176): B-G final gate DONE …`; 0 dirty paths; origin/main == HEAD | CONFIRMED |
| Phase A A0–A13 DONE, evidence dirs 00..12 | `ls evidence/r176/` | 00_session_start … 12_falsification + B_fixes | CONFIRMED |
| Report has 31 sections | `grep -c "^## " docs/r176/R176_FINAL_CLOSURE_EXAMINATION.md` | 31 | CONFIRMED |
| Ledger rows A13 and B-G present | `grep -n "^\| A13\|^\| B-G" evidence/r176_state_ledger.md` | checklist rows 36/44 and body rows 64/72 | CONFIRMED |
| FIX-07 bf5d0f9 | `git log --format='%h %s' --all` | `bf5d0f9d fix(core/events): FIX-07 refuse ambiguous numeric webhook hosts` | CONFIRMED |
| FIX-04 ff38b07 | idem | `ff38b072 fix(core/contracts/admin): FIX-04 …` | CONFIRMED |
| FIX-06 bd4bdd9 + eb44553 | idem | both present | CONFIRMED |
| FIX-03 005aa45 | idem | `005aa453 fix(apps/api): FIX-03 part 2 …` | CONFIRMED |
| FIX-05 (no migration) | idem | `4839b7b0 fix(apps/api): FIX-05 — … 409 idempotency_conflict`; no `0019_*` migration exists | CONFIRMED |
| FIX-02 f44cc703 | idem | `f44cc703 docs(r176 FIX-02): …` | CONFIRMED |
| Gate numbers | `evidence/r176/B_fixes/final_gate/02_apps_cli_check_rerun.txt` | `PASS: pytest: passed=3196 failed=0 errors=0 skipped=64`; mypy/ruff/import-linter PASS; `FAIL: possible secret detected …:132`; `RESULT: FAIL`, `EXIT 1` | CONFIRMED |
| Gateway 194 passed | `evidence/r176/B_fixes/final_gate/03_gateway_suite.txt` | `194 passed, 2 warnings` | CONFIRMED |
| FIX-01 untouched | `git log --oneline -- docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md` | only the operator's 521d885 | CONFIRMED (PENDING APPROVAL / OPERATOR-OWNED) |

Divergences from §2: **none**. The R177 baseline gate is run once in A03b to pin the R177 starting point
(`evidence/r177/A03_governance/baseline_gate.txt`).

Session facts: first R177 session had no git credential (`git push --dry-run` → "could not read Username") ⇒ PUBLICATION_BLOCKED; a
sandbox reset then erased the two local-only commits. This file is the verbatim rewrite from the same evidence, pushed in the next
credentialed session. No credential is read from repository or conversation text; the token lives only in `~/.git-credentials`.
