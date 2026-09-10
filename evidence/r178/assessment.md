# R178 — engineering checkpoint and decision evidence

## Current post-authorization A–K checkpoint (supersedes historical status below)

**A — State:** DEC-01 implemented and verified; DEC-02 design review delivered,
not runtime ingestion implementation. R177 remains closed. PR #14 contains the
bounded work; no deployment or main-branch merge performed.

**B — Verified strengths:** `decisions_final_gate.txt` at `002f19af` records
3342 passed / 0 failed/errors / 64 skipped, all governance checks PASS, exit 0.
`decisions_gateway.txt`: 194 passed, exit 0. Both captured at `04bc9ea1`.
`dec01_codec_recheck.txt`: 21 focused tests including real persistence codecs
(pass and fail cases); these are hermetic, not live PostgreSQL tests.

**C — Gaps:** Original P03 is now VERIFIED (failed required scenario checks no
longer establish regression_pass). P01 remains FAILED: external-sample evaluation
still uses a private in-memory store. See `dec01_adversarial.txt`; its exit 1 is
honest because P01 remains, not a hidden regression-suite failure.

**D — Changes:** ScenarioService appends actual required-check results through
the same EvaluationStorePort read by promotion. Evidence is bound to the stored
tenant/execution/scenario/input/output and check-policy version. A deterministic
per-run record ID prevents choosing a later contradictory append. Missing, legacy,
mismatched or failed evidence denies. Compatibility flags no longer bypass
artifact-backed verification; pure model scores alone do not count as passing
checks. Positive promotion and downstream refusal tests still exercise their
original behavior with real supporting evidence. Re-review found and fixed
HTTP duplicate-check validation before final verification.

**E — Blockers:** No live DB/restart, browser or two-account provider verification
claimed. The unchanged two not_evaluated entries remain separate from PASS.
External ingestion's per-row subject, durable sample/receipt and recovery design
must precede any evaluation-store switch. No FK or schema was changed.

**F — AI/model readiness:** Normal model/provider routing remains intact; no
training runner, native trained candidate, live teacher quality or weight
promotion/rollback proof is claimed by this unit.

**G — Universal learning:** Verification integrity improved; durable external
learning and the complete experience-to-training chain remain incomplete. Memory
and a dataset UUID are not a versioned training dataset or model adaptation.

**H — Evolution:** `dec02_ingestion_design.md` reviews actual validator-operation
representation, per-row provenance, rights/retention, idempotency, transactions,
crash recovery, partial batches and rollback. `dec02_contract_review.txt` checks
existing contract/schema assumptions. No successful execution was invented.

**I — Decisions:** Both operator authorizations honored: DEC-01 option B delivered;
DEC-02 option B design review complete, without silently expanding to storage
implementation or production data migration. Earlier decision packets below are
historical rationale, NOT outstanding approval requests for these completed units.

**J — Safe continuation:** Prepare the next tests-first ingestion implementation
proposal using the reviewed prerequisites; preserve fail-closed legacy behavior,
FKs, tenant isolation and actual source rights. No training or live promotion.

**K — Exact next action:** Reconcile final ledger/PR, then specify per-row subject
and durable transaction/receipt acceptance tests before any external-ingestion
store rewiring. This completes the authorized bounded units, not the whole
continuous-evolution mission or every readiness gap. Unit histories remain on
`r178_verified_units` (initial work) and `r178_decisions_verified_units` (decisions)
when the PR is squashed; evidence snapshot hashes remain resolvable there.

---

## Historical initial assessment and decision packets (pre-authorization)

Scope: current post-R177 mission; R177 remains CLOSED. This is an initial
cross-system checkpoint, not certification of every platform subsystem.
Primary labels: VERIFIED / FAILED require executed evidence; INFERRED means
source inspection; UNVERIFIED means not exercised here. A green suite does not
cancel adversarial findings. No live provider, training or production data used.

## A. Current system state

Recovered from main `369cf37c`; work is in PR #14 on the isolated remote branch
`genspark_ai_developer_r178`. Existing R175 PR #13 is unchanged. The repository's
per-round ledger remains the only active checkpoint mechanism.

Baseline `isolated_gate.txt` at snapshot `73155a1c`: 3318 passed, 0 failed/errors,
64 skipped, all governance checks PASS. This is actual captured output, committed
at `b8e38c44`, not reconstructed output. All writes stayed in the permitted
workspace: clone under `.venv/r178_verify`, fixture TMPDIR in a sibling directory.
That placement preserves ADR-0009's prohibition on engineering workspaces inside
the platform checkout. The source tree/security tests were not patched to pass.

Correction `dd0f3c28`: one production file, two lines added/one removed.
`duplicate_after.txt`: 31 targeted/adjacent tests passed. VERIFIED / TEST:
`final_gate.txt` records 3321 passed, 0 failed/errors, 64 skipped; mypy, ruff,
architecture boundaries, secret scan and budgets PASS, process exit 0.
`gateway_final.txt`: 194 passed, process exit 0. Actual final evidence committed
at `91b5e017`. P01/P03 remain separate FAILED findings despite that green gate.

## B. Verified strengths (within the measured envelope)

- Baseline's declared five test slices passed; mypy, ruff, architecture boundary
  checks, credential scan and unchanged governance thresholds passed.
- Hermetic learning probe C01: successful evaluation alone leaves eligibility
  PENDING. C02: both tested caller metadata forms did not establish regression
  evidence. C03: foreign-tenant execution evidence was denied.
- Duplicate correction's controls preserve original FK/CHECK IntegrityError
  propagation; duplicate evidence is refused through the documented domain error.
- Provider/model-independent contracts and registries are exercised by the
  contract/provider and execution slices. This is not proof of a live provider.

## C. Ranked verified gaps and scope limitations

| Priority / ID | Classification | Observation and consequence |
|---|---|---|
| High F-R178-01 / P03 | FAILED / TEST; reproduced | A genuine ScenarioService replay reports `passed=false` for required `error_free_output`, yet PromotionEvidenceResolver returns `regression_pass=true`. Successful execution is being substituted for a passing regression check at this seam. |
| High F-R178-02 / P01 | FAILED / TEST; reproduced | External sample evaluation returns success, but the admin list for its source execution contains zero evaluations. Evidence consumers cannot discover the evaluation through their shared store. |
| Medium F-R178-03 | FAILED before, targeted VERIFIED after / TEST | Real repository error translation checked `evaluations_pkey`; migration 0010 and metadata name `pk_evaluations`. Injected SQLAlchemy error leaked instead of DuplicateEvaluation. Fixed in the bounded unit. |

P01/P03 execution and controls: `probe_learning_chain.py`, `learning_probe.txt`.
Run `.venv/bin/python -m evidence.r178.probe_learning_chain` from the root.
It intentionally exits 1 while those two invariants fail. This separate adversarial
harness is NOT a passing regression test or part of the old green claim.
No unauthenticated privilege escalation or actual model promotion was demonstrated.
P03 is a promotion-input integrity defect, not proof all other gates can be bypassed.

Adjacent source facts (INFERRED / STATIC, not live DB findings):
- `apps/api/app.py:2139-2148` builds the learning evaluator over a private
  InMemoryEvaluationStore, while admin/resolver reads use AdminSurface.evaluations.
- External capture generates a synthetic source execution UUID in
  `core/learning/lifecycle.py:234-251`. Migration 0010 requires evaluation execution
  IDs to reference actual executions. Blindly substituting the durable admin
  store risks breaking external evaluation; do not invent fake successful runs
  or remove the FK to hide the mismatch.
- Scenario replay returns check verdicts, but stores the execution before grading
  (`apps/api/scenarios.py:205-223`). Resolver regression logic checks the replay
  label and SUCCEEDED status, not those verdicts (`promotion_evidence.py:154-170`).

## D. Implemented correction

R178-FIX-01 is routine, reversible and contract-preserving: derive the expected
primary-key name from shared SQLAlchemy metadata, match its unique-constraint
failure, and raise DuplicateEvaluation with the original cause. Other integrity
errors still propagate. No schema, authorization or model-policy change.

Evidence: `duplicate_before.txt` (1 failed / 2 passed),
`duplicate_after.txt` (31 passed), new tests under
`tests/infrastructure/test_evaluation_error_translation_r178.py`.
These inject driver errors into the real repository; they do not prove a live
PostgreSQL insert/restart. Independent budget is 1/1 in `round_r178`; old rounds,
floors, skip ceiling, exclusions, and not_evaluated count are unchanged.

## E. Remaining blockers / confidence boundaries

P01 and P03 remain unfixed. Their durable evidence/acceptance choices are below.
No live PostgreSQL, browser UI, two-account provider, distributed load, or backup
restore was exercised. Historical evidence does not make these current VERIFIED.
No deployment or production migration was performed. Credential rotation is
operator-owned and remains unverified. Lost uncommitted diagnostics from earlier
interruptions are not presented as retained evidence.

## F–H. AI/model, universal learning, long-term evolution readiness

| Chain / adjacent concern | Current classification | Evidence and limitation |
|---|---|---|
| Experience capture | Implemented / partial; TEST + STATIC | HTTP external capture/evaluate exercised; execution and intake paths exist. Sample lifecycle remains an in-process map. |
| Trusted learning | Partial / FAILED at two seams | P01/P03 above; evaluation level != globally traceable evidence. No universal-learning readiness claim. |
| Sanitization / eligibility | Implemented / partial | Existing gates and tests; minimum level in app composition is RAW. Policy/rights assertions are not proof of lawful provenance. Source UUID alone is not a license or consent record. |
| Dataset version | Missing implementation in inspected path / INFERRED | admit_to_training assigns dataset_id or a random UUID; no versioned manifest or reproducible membership snapshot in that path. |
| Training / adaptation | Not found in inspected runtime / INFERRED | No training runner, trainer adapter or artifact lineage found by bounded source search. Memory writes do not update model weights. |
| Model candidate | Supported general model registry; improvement lineage UNVERIFIED | Normal Model/Provider/Binding objects remain the required routing path. No native candidate-to-training-run linkage demonstrated. |
| Evaluation | Implemented / partial | Grader policy, records, selective optional judge exist; no live teacher quality proof or provider-term assessment in this unit. |
| Shadow / canary | Representable signals / partial | Promotion booleans and optional judge selector exist, not evidence of real traffic experiments or automated rollout. |
| Promotion / rollback | Gates and admin controls exist; training chain UNVERIFIED | GOLD promotion writes a memory item and emits an audit event. It is not executable proof of a trained model release, measured canary or weight rollback. |
| Backend/API/auth/runtime | Covered by baseline slices, not exhaustive certification | Core/API/security/agent tests ran; P03 shows integration assertions still matter despite green totals. |
| DB / recovery / observability | Partial | Durable bindings exist; audit, usage and learning state include in-process stores. Restart/atomic provenance/live recovery need independent proof. |
| Scale / infrastructure / data rights | UNVERIFIED for this unit | No load envelope, distributed recovery, retention/revocation or licensed training provenance verified. Do not invent them from abstractions. |

Source searches: `training_surface_search.txt`, `composition_surface_search.txt`.
They are bounded code-search evidence, not an exhaustive proof of absence.
Inspect `core/learning/lifecycle.py:433-521` to distinguish dataset-id assignment,
GOLD retrieval writes and audit labels from an actual training platform.
No external industry research was material to these repository-local defects.
Before any real training, provenance, rights, retention, eligibility snapshots,
dataset reproducibility, candidate lineage and promotion/rollback evidence need
explicit acceptance criteria. No vendor/model hardcoding or hidden-reasoning
transfer is proposed.

## I. Operator decisions — protected evidence semantics, not routine maintenance

### R178-DEC-01: what establishes regression evidence for promotion?

Evidence/problem: F-R178-01. Current rule accepts execution success even when a
required scenario check failed. Changing the authoritative promotion-evidence
producer and treatment of historical refs affects a protected trust boundary.
The one-file error correction above does not settle that policy.

| Option | Before → after | Tradeoff / reversibility |
|---|---|---|
| A: recompute checks from current scenario definitions | Status+label → rerun known checks against stored output | Small, no schema; missing scenarios must deny. Definitions/version drift and restart loss can prevent reproducible historic decisions. Revert code, but do not undo decisions already made. |
| B: immutable replay evaluation via existing EvaluationStorePort (recommended) | Status+label → recorded per-run check verdicts, tenant/execution/scenario provenance; missing evidence denies | Reuses append-only evaluation seam, not a parallel store; requires defining source/check-version binding and legacy-ref behavior. Existing ungraded refs need replay, not fabricated backfill. No production migration unless separately approved. |
| C: explicitly hold promotions depending on these refs | Current permissive interpretation → named unavailable/unverified refusal until evidence design approved | Safest containment, but reduces availability. Reversible via a later reviewed implementation; no evidence rewrite. |

Recommendation: B, with fail-closed missing/failed/mismatched evidence and a replay
path for historical refs. API identifier shapes and tenant admission stay unchanged.
Before/after acceptance tests: actual failed check denies; actual passing recorded
run can satisfy only regression condition; absent/foreign/stale/ungraded refs deny;
ordinary successful executions never substitute for a regression verdict.
Exact decision requested: approve **R178-DEC-01 option B**, including rejection of
legacy ungraded refs and a bounded implementation proposal over existing ports.
No live promotion, retroactive rewriting or automated training is authorized.

### R178-DEC-02: durable evaluation subject for external intake

Evidence/problem: F-R178-02 plus the execution FK. Store unification without
subject reconciliation risks replacing missing evidence with failed persistence.

| Option | Before → after | Tradeoff / reversibility |
|---|---|---|
| A: unify execution-backed evidence only | Private evaluator → shared store for real executions; external evidence explicitly remains unverified | Small interim step; external capability remains partial. No FK removal or fake execution rows. Reversible wiring. |
| B: explicitly model ingestion provenance within approved execution semantics | Synthetic UUID without row → real bounded ingestion event/record with honest status and tenant ownership | Preserves FK if contract permits; requires reviewing what an Execution represents, costs/audits and failure atomicity. Never masquerade ingestion as successful model inference. |
| C: extend evaluation subject contract/schema | Execution-only FK → explicit execution/sample/ingestion subject | Broadest capability; breaking-contract/migration/retention implications. Needs ADR, migration/rollback plan and live DB tests. Not routine wiring. |

Recommendation: investigate B's compatibility first; do not silently implement C.
Exact decision requested: approve **R178-DEC-02 option B design review only**;
implementation approval follows a concrete subject/atomicity proposal. Meanwhile
A can be scoped as a separately verified interim correction, without claiming
external evidence durable. No new parallel evaluation store is proposed.

## J. Safe autonomous continuation

Read-only dependency analysis, stronger passing/failing/provenance test fixtures,
live-DB test preparation with seeded FK parents, and budget-scoped ordinary
binding corrections remain permitted. Do not equate awaiting protected decisions
with a blanket execution block. Do not weaken gates, relax foreign keys, invent
training data rights, enable model promotion or declare the whole mission complete.

## K. Exact next action

Confirm final gate and gateway outputs, reconcile and publish ledger/PR #14.
Then resolve R178-DEC-01's authority and artifact semantics before changing
promotion acceptance. In parallel, map external-ingestion subject/transaction
requirements for R178-DEC-02; no external training/provider activity is required.
