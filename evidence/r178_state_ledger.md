# R178 state ledger — post-R177 engineering ownership

## Mission / authority / recovery

R177 is CLOSED. The operator's new post-R177 full engineering ownership mission
allows routine reversible investigation, tests, contract-preserving fixes and
verification autonomously. Protected architecture, authorization boundaries,
breaking contracts, major data governance, model promotion and irreversible
production/cost decisions require a decision packet and explicit approval.
Do not resume old Phase B or reopen its work without new executable evidence.
Successful execution != verified learning. Memory != training data. No live
provider calls, production data processing, training or model promotion here.

Existing protocol: `docs/ai_orchestration_pack/final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md`
§2 and the pointer in `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md`.
Highest tracked ledger at recovery was R177; this file is the next round in that
same mechanism, NOT a replacement progress system. Frozen project state and
closed ledgers remain untouched. Trust Git/filesystem/evidence, not chat claims.
Resume: status/log/diff, remote fetch, last row here, evidence, actual runtime,
then exact next action. Never delete/reset uncommitted recovery candidates blindly.

## Recovery on 2026-09-10 (second session)

- VERIFIED / CAPTURED: clean `main`, HEAD == fetched origin/main ==
  `369cf37c8ca60234c78f7da61f1781c5c62be846`; correct repository
  `belalalibb/general_ai_core`. Authenticated GitHub repository API returned
  this identity and push permission. No credential is stored in this record.
- Local-only R178 work from the previous interrupted session is absent:
  no ledger/directory/venv and `git cat-file -t 13d01d05` cannot resolve the
  prior local commit. Those prior probe results are NOT current durable evidence.
  Reconstruct this checkpoint, then rerun measurements; do not fabricate lost logs.
- Canonical prompt, README, RUN, OPERATIONS, current protocol, frozen state
  pointer, R177 ledger and committed final gate were read during recovery.
  Historical documentation-only / one-task-stop instructions are superseded by
  the current explicit mission; security/correctness invariants remain binding.
- R177 historical gate artifact: `evidence/r177/BG_final/gate_run2.txt`, 3318
  passed / 0 failures/errors / 64 skipped. Current baseline not yet rerun.
- Previous interrupted baseline used TMPDIR inside a scanned `.tmp/` tree;
  generated negative secret-scan fixtures contaminated that scan. Its lost
  results are not product-regression evidence. New TMPDIR is inside already
  excluded `.venv/r178_tmp`; no verification exclusion or threshold is changed.
- GitHub remote `genspark_ai_developer` belongs to unrelated OPEN PR #13 (R175),
  with four branch-only commits. Preserve it and its PR unchanged. Local work
  uses `genspark_ai_developer` based on current main; publish this isolated
  mission to `genspark_ai_developer_r178` and a separate PR rather than overwrite
  the existing branch or import stale edits to the frozen project state.

## Initial accounting and guardrails

Initial unit: recovery, baseline, focused cross-system assessment and probes.
Production-change allowance for this unit: **0**. R177's 9/12 budget is historical,
not available headroom. Before a later code correction, record its independent
scope/accounting under current mission authority. No changes to old budgets.
Keep canonical prompt, frozen state, `ui/`, `apps/admin_agent/`,
`core/tools/gate.py` unchanged. Preserve v3=20, not_evaluated=2 and all gate
thresholds (passed >=3127, failed/errors=0, skipped <=64). No legacy state files.
External credential rotation remains operator-owned/unverified.

## Bounded correction under current mission authority

R178-FIX-01 restores the existing DuplicateEvaluation exception contract for the
actual `pk_evaluations` constraint (migration 0010 and shared metadata). Current
failing-first evidence `duplicate_before.txt`, commit `91890137`: one failed,
two passed. The previous interrupted correction was NOT saved; recovered code
still matches `evaluations_pkey`. Only production file authorized for this unit:
`infrastructure/db/repositories/evaluations.py`. Independent budget: one file,
cap 1 in a new manifest round; no historical budget or threshold changes.
Routine reversible binding fix, no schema/security-policy change. FK and CHECK
errors must still propagate unchanged. Injected-error tests do not prove live DB
persistence. Rollback: revert this one-file fix; preserve tests/evidence.
The initial zero-production measurement unit is complete; this is the next unit.

## Rows (append before each unit; completion needs Git + actual evidence)

| Task | State / evidence | Exact next action |
|---|---|---|
| RECOVERY | Current Git/remote/auth reality reconciled above; lost local-only artifacts explicitly not trusted. R177 closed. No product modifications. | Finish isolated dependency installation; capture a fresh full gate and gateway run. Recreate and run hermetic learning/evaluation/scenario probes, distinguish test failures from harness contamination, then rank findings and authority boundaries. |
| PROBES | VERIFIED reproduction / TEST at `73155a1c`: `evidence/r178/probe_learning_chain.py` and actual `learning_probe.txt`. P01: successful external-sample evaluation leaves admin execution-evaluation list empty. P03: actual ScenarioService replay reports failed required quality check, but PromotionEvidenceResolver returns regression_pass=true. These are current cross-system failures, NOT reopened historical tasks by assumption. C01/C02/C03 controls hold: evaluation alone leaves eligibility pending, two caller-metadata probes do not establish regression evidence, and foreign-tenant execution evidence is denied. Probe exits 1 intentionally while failures remain; no product fix yet. | Finish the current isolated full gate; inspect contracts/adjacent persistence before selecting a bounded correction or protected decision. |
| RECOVERY-3 | Fresh checkout again started at main `369cf37c`; fetched and recovered published R178 `73155a1c` from `origin/genspark_ai_developer_r178`. Worktree clean, PR #14 OPEN, repository identity/push permission reverified. Only the committed probe and ledger survived; uncommitted baseline/diagnostic files and venv were absent, so no lost baseline result is claimed. Prior visible diagnostics showed nested test workspaces triggering the correct ADR-0009 platform-checkout refusal. New run uses a byte-identical Git clone under `.venv/r178_verify` with temporary fixtures in sibling `.venv/r178_tmp`, both inside allowed sandbox writes. This changes test placement, NOT product code/security gates/test assertions. | Run full verifier in the isolated clone, capture real output and process exit, then immediately commit/push evidence to PR #14 before further work. Run gateway suite and finish ranked learning/model readiness assessment. |
