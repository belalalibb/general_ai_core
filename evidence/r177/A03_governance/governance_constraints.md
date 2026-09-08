# R177-A03 — Governance-constraint confirmation (read directly from the gate and its manifest)

| § | Constraint | Evidence (path:line / command → output) | Status |
|---|---|---|---|
| 3.1 | forbidden filenames | `check_repo.sh:41` `for legacy in STATE.md PROGRESS.md HANDOFF.md NEXT_PLAN.md FUTURE_IMPROVEMENTS.md ARCHITECTURE_GAPS.md` → `fail "legacy state file present"` | CONFIRMED — R177 writes none of them |
| 3.2 | v3 pack == 20 | `check_repo.sh:50-54`; `ls docs/ai_orchestration_pack/final_docs_v3/*.md \| wc -l` → 20 | CONFIRMED |
| 3.3 | state header fields | `check_repo.sh:56` `for field in STATE_REVISION RESUME_TOKEN CURRENT_TASK NEXT_TASK PHASE_2_STATUS` → all 5 present | CONFIRMED — file not touched in R177 |
| 3.4 | secret-scan patterns | manifest `secret_scan.patterns` = `AKIA[0-9A-Z]{16}\|-----BEGIN (RSA\|EC\|OPENSSH) PRIVATE KEY-----\|xox[bap]-[0-9A-Za-z-]{10,}\|ghp_[0-9A-Za-z]{36}\|sk-[A-Za-z0-9]{40,}`; exceptions **5 / ceiling 5 (full)** | CONFIRMED |
| 3.4 | which prompt lines are detected | `re.search(patterns, line)` on lines 132/133/134 (values never printed): **132 DETECTED (key GITHUB_TOKEN)**, **133 NOT detected (GROQ_API_KEY)**, **134 NOT detected (GW_ASSEMBLYAI_API_KEY)** | CONFIRMED — a green scan does NOT prove the file is credential-free |
| 3.5 | hardcoded budget tuple | `check_repo.sh:143` `for r in ("round_a", "round_b", "round_r169", "round_r172", "round_r173"):` + `:144 if r not in cb: continue`; manifest rounds = exactly those 5 | CONFIRMED → **F-R177-01** |
| 3.6 | not_evaluated 2/2 | manifest `not_evaluated` len 2, ceiling 2; `check_repo.sh:163-174` fails when count > ceiling | CONFIRMED — no new NOT EVALUATED items |
| 3.7 | VerificationLevel closed | `core/contracts/evaluation.py:64-68` RAW, EVALUATED, VALIDATED, VERIFIED, GOLD (no CANDIDATE) | CONFIRMED |
| 3.7 | ErrorCode closed 11 | `core/contracts/errors.py:31-44` incl. VALIDATION_ERROR, CAPABILITY_DENIED, TOOL_APPROVAL_REQUIRED | CONFIRMED |
| 3.7 | CAPABILITY_IDS closed | `apps/api/capabilities.py:58-78` frozenset of **17** ids (16 roadmap + `dev.publish_modes`, R172 C7); CapabilityState available/inert/unavailable | CONFIRMED — directive said 16; **repository says 17** (repository wins) |
| 3.7 | FirewallDecision closed | `core/contracts/security.py:69-72` ALLOW, DENY, ALLOW_WITH_LIMIT, REQUIRE_APPROVAL | CONFIRMED |
| 3.8 | import-linter 13 contracts | `grep -c "^\[importlinter:contract" pyproject.toml` → 13; gate `check_repo.sh:101-105` | CONFIRMED |
| 3.9 | frozen trees | manifest `change_budget.round_r173.frozen_trees_zero_diff` = `ui/`, `apps/admin_agent/`, `core/tools/gate.py` | CONFIRMED |
| 3.10 | pytest floor | manifest `pytest.gate` = failed 0, errors 0, max_skipped 64, min_passed 3127 | CONFIRMED |

## F-R177-01 — change-budget enforcement hole (S3, governance)
- **Evidence**: `engineering/verification/check_repo.sh:143` iterates a HARDCODED tuple `("round_a","round_b","round_r169","round_r172","round_r173")`; `:144` `if r not in cb: continue`. Any other `change_budget` key is silently ignored.
- **Consequence (KNOWN)**: R176 Phase B changed production files (core/events/webhooks.py, core/contracts/admin.py, core/learning/sanitizer.py, core/memory/memory.py, apps/api/app.py, core/agent/runtime.py) with **no** `round_r176` manifest entry and therefore **no** ceiling check; the gate line `PASS: change budget within ceilings: round_a=4/5; …; round_r173=1/1` was true and irrelevant.
- **Minimum fix (R177-FIX-01, needs DEC-05)**: (a) add `round_r177` to the manifest with an explicit ceiling + log; (b) iterate every `change_budget` key starting with `round_` (or extend the tuple); (c) failing-first test proving a round outside the old tuple is now accounted (fixture manifest with `round_zz.changes_used > ceiling` ⇒ budget step FAIL). Files: `engineering/verification/check_repo.sh`, `green_manifest.json`, one new test. Rollback: revert.
- **Not executed in R177 Phase A** — `engineering/verification/*` edits are outside this round's git authorization (§20).
