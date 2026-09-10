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

## Authorized protected-decision unit (2026-09-10)

Recovered clean `47962487` from PR #14; main still `369cf37c`. Operator explicitly
approved R178-DEC-01 option B implementation and rejection of legacy evidence
without valid support; R178-DEC-02 option B is DESIGN REVIEW FIRST only. Preserve
all integrity constraints; never invent successful executions. Previous completed
FIX-01 remains closed; full gate 3321/0/0/64 is retained baseline evidence.

DEC-01 bounded production scope (independent `round_r178_dec01`, cap 5 files):
`apps/api/scenarios.py`, `apps/api/regression_evidence.py` (pure evidence codec),
`apps/api/promotion_evidence.py`, `apps/api/app.py`, `apps/api/admin.py`.
Reuse existing append-only EvaluationStorePort and real replay executions; no new
store, schema, enum, provider or training system. Record required check results
and versioned provenance bound to tenant/execution/scenario/output. Missing,
legacy, ambiguous or failed evidence must deny, including non-strict legacy paths.
Do not derive a passing regression verdict from SUCCEEDED alone. Tests must cover
positive stored evidence, failed checks, missing/foreign/tampered/stale/duplicate
records and persistence failures. DEC-02 adds only a reviewed lifecycle/transaction
proposal and evidence, NOT storage rewiring or data migration. Rollback preserves
stored evidence; never recommend restoring permissive legacy promotion semantics.

## P01 implementation authorization and closure gate (2026-09-10)

Operator now authorizes the next tests-first P01 IMPLEMENTATION, not design-only:
close external-evidence gap end-to-end; full regression, gateway and adversarial
checks; reconcile state; do not declare R178 complete without Backend Closure.
Recovered clean published `aff12c0c`; main remains `369cf37c`; authenticated repo
identity/push verified. Existing approved DEC01 semantics and closed R177 remain.

No distinct machine-readable `Backend Closure` predicate was found in current
R178 artifacts; do not invent a weaker DONE condition. Conservative P01 acceptance:
real admitted per-row validator/ingestion subjects (no fake model executions),
shared tenant-scoped append-only evaluation evidence, durable sample/receipt and
subject binding with retry/restart/failure behavior, no cross-row/tenant trust,
no provenance/rights inference, unchanged integrity/security constraints, original
P01/P03 probes satisfied, full gate + gateway/integration PASS. Live local DB proof
is required before claiming database/restart closure; hermetic tests alone are
not that evidence. Broader live/provider/UI limitations must remain explicit.

Discovery: existing `learning_samples` table (migration-era metadata) has no
production repository callers; it carries FK-bound sample states but not knowledge
payload/provenance. Existing ExecutionStore and EvaluationStore use separate writes,
so do not call a sequence atomic. Investigate reuse before proposing schema changes.
Initial subunit: failing-first API/recovery tests plus workspace-local PostgreSQL
setup, production changes 0; implementation scope/accounting recorded before edits.
No ambient provider credentials, production DB, training or data migration used.

## First P01 production subunit: genuine subjects + shared evaluation

Recovery on 2026-09-10: clean published `2252939e` restored from the R178 remote;
main remains `369cf37c`. Authenticated repository identity/push and OPEN PR #14
verified. Interrupted edits, ingestion.py and targeted output are ABSENT, not
assumed successful. Published five-test RED remains the acceptance baseline.

Independent `round_r178_p01_subject` cap 5 production files:
`core/learning/lifecycle.py`, `apps/api/ingestion.py`, `apps/api/intake.py`,
`apps/api/admin.py`, `apps/api/app.py`. Record an actual bounded sanitizer scan
as a per-row VALIDATOR subject, propagate admitted actor, then use shared
append-only evaluations. Receipt writes precede sample mutation; scan completion
is NOT sanitization approval, eligibility, model inference or verified learning.
No existing FK, closed contract, historical budget or frozen surface changes.

This subunit DOES NOT establish durable sample lifecycle/restart closure. Follow
with real local PostgreSQL and restart tests, implement durable sample/receipt
recovery as required, and keep R178/Backend Closure OPEN until all recorded
acceptance conditions hold. Rollback must preserve evidence and fail-closed trust.

## Rows (append before each unit; completion needs Git + actual evidence)

| Task | State / evidence | Exact next action |
|---|---|---|
| RECOVERY | Current Git/remote/auth reality reconciled above; lost local-only artifacts explicitly not trusted. R177 closed. No product modifications. | Finish isolated dependency installation; capture a fresh full gate and gateway run. Recreate and run hermetic learning/evaluation/scenario probes, distinguish test failures from harness contamination, then rank findings and authority boundaries. |
| PROBES | VERIFIED reproduction / TEST at `73155a1c`: `evidence/r178/probe_learning_chain.py` and actual `learning_probe.txt`. P01: successful external-sample evaluation leaves admin execution-evaluation list empty. P03: actual ScenarioService replay reports failed required quality check, but PromotionEvidenceResolver returns regression_pass=true. These are current cross-system failures, NOT reopened historical tasks by assumption. C01/C02/C03 controls hold: evaluation alone leaves eligibility pending, two caller-metadata probes do not establish regression evidence, and foreign-tenant execution evidence is denied. Probe exits 1 intentionally while failures remain; no product fix yet. | Finish the current isolated full gate; inspect contracts/adjacent persistence before selecting a bounded correction or protected decision. |
| RECOVERY-3 | Fresh checkout again started at main `369cf37c`; fetched and recovered published R178 `73155a1c` from `origin/genspark_ai_developer_r178`. Worktree clean, PR #14 OPEN, repository identity/push permission reverified. Only the committed probe and ledger survived; uncommitted baseline/diagnostic files and venv were absent, so no lost baseline result is claimed. Prior visible diagnostics showed nested test workspaces triggering the correct ADR-0009 platform-checkout refusal. New run uses a byte-identical Git clone under `.venv/r178_verify` with temporary fixtures in sibling `.venv/r178_tmp`, both inside allowed sandbox writes. This changes test placement, NOT product code/security gates/test assertions. | Run full verifier in the isolated clone, capture real output and process exit, then immediately commit/push evidence to PR #14 before further work. Run gateway suite and finish ranked learning/model readiness assessment. |
| BASELINE | VERIFIED / TEST: saved `isolated_gate.txt` at snapshot `73155a1c`, evidence commit `b8e38c44`, 3318 passed / 0 failed/errors / 64 skipped; all governance checks PASS. Valid sibling fixture placement preserved the unchanged ADR-0009 guard. | Complete the bounded duplicate exception correction already reproduced at `91890137`. |
| FIX-01 | VERIFIED / TEST: `dd0f3c28` restores metadata-aligned primary-key error translation, unrelated integrity failures propagate; `duplicate_after.txt` 31 passed. Full `final_gate.txt` and `gateway_final.txt` committed at `91b5e017`: 3321 passed / 0 failed/errors / 64 skipped, all governance checks PASS, budget R178=1/1, not_evaluated=2; gateway 194 passed; both process exit 0. One production file changed, no schema or trust-boundary change. | Reassess unresolved learning evidence findings without calling the whole platform complete. |
| ASSESSMENT | Bounded A–K report and full decision packets: `evidence/r178/assessment.md`. P01/P03 remain FAILED / TEST; no fake green or hidden skipped tests. Training/dataset/candidate/shadow/canary chain is partial or unverified, not a functioning native training platform. Protected choices R178-DEC-01 (authoritative regression evidence/legacy refs) and R178-DEC-02 (external-ingestion evaluation subject) await operator decision; routine read-only analysis/test preparation may continue. Current mission PR: https://github.com/belalalibb/general_ai_core/pull/14, main and unrelated PR #13 unchanged. Unit commit IDs will be preserved on remote `r178_verified_units` before the required PR squash. | Operator: review DEC-01 option B and DEC-02 option B design-only packet. Safe autonomous next: prepare provenance/legacy-ref acceptance tests and map ingestion transaction/subject constraints; do not modify protected acceptance semantics, foreign keys or enable training before the decisions. |
| DEC01-IMPLEMENTATION | Operator approval is recorded in the authorized section above. Implemented `f1733051`: immutable per-replay check results in existing EvaluationStorePort, versioned provenance digest, deterministic tenant/execution evidence identity; legacy/status-only/missing evidence refuses, including compatibility mode. Failing-first `dec01_before.txt`: 15 failed / 1 passed; initial after: 16 passed. Positive-path fixture migration uses real replay + stored support, not weaker assertions (`dec01_compatibility.txt`, 77 passed, `e896b9bd`). | Re-review input validation and durable reconstruction, then final gate. |
| DEC01-REVIEW | Found and corrected duplicate-check API validation regression (`95df1392` RED 1/18, `3e83034b` GREEN 39). `72c3b04e` saved actual full gate 3340/0/0/64 and gateway 194, both exit 0. Added real durable report/evaluation codec rechecks (hermetic, no live DB claim), `002f19af`: 21 passed. Original adversarial P03 now VERIFIED; P01 remains FAILED by DEC02 design-only scope (`dec01_adversarial.txt`). | Run final full gate including the two new codec tests; do not infer its result from the prior gate. |
| DEC02-DESIGN | Design review complete at `82e11fc8`: `dec02_ingestion_design.md` and `dec02_contract_review.txt`. Existing validator orchestration can represent real ingestion, but per-row subject linkage, durable samples/receipts and transaction/recovery semantics must precede store unification. No fake successful execution, schema/FK change or learning-store rewiring. P01 not claimed fixed. | Preserve design recommendations and scope a tests-first implementation proposal; do not silently treat design review as runtime delivery. |
| RECOVERY-FINAL | Recovered clean published `002f19af` after another reset; final decision-unit output files were absent, while prior 3340-pass gate and 21-test codec recheck survived. Restoring tooling and rerunning only the missing final gate/gateway; no completed product work repeated. | Capture and publish `decisions_final_gate.txt` / `decisions_gateway.txt`, reconcile A–K report and final PR checkpoint, retain precise remaining limitations. |
| DECISIONS-VERIFIED | Authorized bounded units complete within the declared hermetic envelope. DEC01 implementation/re-review: `decisions_final_gate.txt` at `002f19af`, saved `04bc9ea1`, **3342 passed / 0 failed/errors / 64 skipped**, all governance checks PASS; gateway **194 passed**, both exit 0. Actual original probe recheck: P03 fixed, P01 remains FAILED (`dec01_adversarial.txt`). DEC02 **design review complete only**, no ingestion-store rewiring/schema change/fabricated successful executions. Current A–K status at the top of `assessment.md` supersedes historical pre-authorization statements. Five authorized production files changed; separate budget 5/5, earlier budgets/invariants preserved. No claim of live PostgreSQL, trained model or universal-learning closure. Verified unit histories preserved on `r178_verified_units` and `r178_decisions_verified_units` before final PR squash. | Next bounded work: specify per-row ingestion subject and durable sample/receipt transaction/recovery tests per `dec02_ingestion_design.md` before proposing any store switch. Existing approvals are honored, not pending again; remaining implementation is not silently included in the design-only unit. Preserve fail-closed promotion and all integrity constraints. |

| P01-SUBJECT | VERIFIED / TEST at `a546bc53`: original five P01 tests PASS. Adjacent first pass `p01_subject_adjacent.txt`: 4 failed / 823 passed / 4 skipped; failures are trusted direct fixtures lacking explicit actor. At `8348d86b`, fixtures explicitly supply actors and production-reach pin counts one genuine validator without model context (14 focused passed); no actor borrowing across tenants. First subunit is not final closure. | Review receipts, then live DB/restart. |
| P01-REVIEW-RED | Recovered published `8348d86b` after reset; interrupted review tests were absent. Recreated and saved at `938e2b37`: 3 failed / 8 passed. Two product defects: mutable caller payload changes content under receipt; durable reconstruction invents provider response for validator. Third failure is a test fixture typo (`RuntimeProfile.store` absent), corrected to existing ScenarioService execution store; no assertion weakened. | Freeze payload at capture and correct real codec, then rerun focused and full suites. |

### P01 codec correction scope

New executable evidence above authorizes one additional routine correction under
current mission: `apps/composition/durability.py`, independent
`round_r178_p01_codec` cap 1. Only MODEL_CALL nodes can reconstruct a provider
response; validator output remains stored node evidence, not model inference.
Existing P01 subject cap remains 5; freezing caller-owned JSON is inside its
already-declared lifecycle.py scope. No schema, trust threshold or frozen edits.
Backend Closure remains OPEN, sample restart/idempotency not yet implemented.


## Current checkpoint — P01 durable closure OPEN (2026-09-10)

- VERIFIED / TEST: `1ddc3f9b` fixed receipt/payload review defects. Corrected focused
  run at `b9d9f55b`: `p01_subject_review_green.txt` 114 passed / 1 existing skip.
  `p01_subject_review_after.txt` is a preserved COMMAND ERROR (wrong test path,
  no tests ran), NOT passing evidence; the corrected artifact is authoritative.
- VERIFIED / TEST: `p01_subject_full_gate.txt` at `b9d9f55b` = 3353/0/0/64,
  governance PASS; gateway 194; original P01/P03 both pass. Saved at `43cf813a`.
  Subject budget 5/5 and codec 1/1; historical budgets/frozen surfaces unchanged.
- VERIFIED / LIVE + TEST: actual PostgreSQL subject/evaluation/tenant/FK/duplicate
  checks pass; sample recovery fails. Further actual build_runtime_profile and
  durable identity restart at `bffa5124`, saved `89e01dd3`, gives 2 passed/2 failed:
  receipt/evaluation GETs succeed but sample GET is 404. No process-kill/network/
  Alembic proof implied. `tests_live/r178/run_local_postgres.sh` is rerunnable.
- Recovery: clean main `369cf37c` again, no venv or interrupted reconciliation;
  recovered published `89e01dd3`, authenticated repo/push and OPEN PR #14 verified.
  Only missing reconciliation recreated. No production code changed after the
  saved 3353-pass gate; existing completed units are not reopened.
- BLOCKED for protected data-governance writes: complete R178-DEC-03 option B
  packet is `evidence/r178/dec02_ingestion_design.md` §8. P01 implementation is
  already authorized; raw custody/quarantine/retention decisions are narrower and
  were expressly left separate in the design. Do not serialize _SampleRecord
  blindly, infer consent from scan success or invent a production retention TTL.
- Exact next action: operator DEC-03 B decision → independent file scope →
  policy/quarantine/idempotency/concurrency/failure tests → transactional durable
  sample/payload/recovery binding → actual runtime restart + full validation.
  Current A–K assessment reconciled. **Backend Closure NOT satisfied; R178 OPEN.**


## R178-DEC-03 B APPROVED — implementation active

Operator explicitly approved option B: explicit storage/retention policy, governed
durable persistence, secret isolation without raw storage, operator-defined expiry,
and fail-closed absent policy. Treat this as the final prerequisite, not another
approval loop. Preserve trust/tenant/FK/rollback boundaries. Then live PostgreSQL,
restart/recovery/idempotency, full regression, gateway and adversarial verification;
no R178 completion or UI-ready claim without actual Backend Closure evidence.
Recovered clean published `c59f0718`; authenticated repo identity/push verified;
main remains `369cf37c`. Prior DEC-03 pending statements above are historical.

Independent implementation budget `round_r178_dec03`, cap 11 production files:
`core/learning/lifecycle.py`, `core/learning/storage.py`,
`apps/composition/learning.py`, `infrastructure/db/learning.py`,
`infrastructure/db/migrations/versions/0019_learning_custody.py`,
`apps/api/ingestion.py`, `apps/api/app.py`, `apps/api/admin.py`,
`apps/api/intake.py`, `apps/composition/runtime.py`,
`infrastructure/db/migrations/env.py` (only if metadata discovery needs it).
No earlier budget reused. Tests first; record actual results per bounded unit.
Policy has no implicit tenant, rights grant or retention duration. Scan is not
privacy/rights verification. Keep immutable redacted evidence on expiry/rollback.
