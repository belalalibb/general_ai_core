# R178 — engineering checkpoint and decision evidence

## Current revocation successor A–K checkpoint — tested slice VERIFIED, Backend Closure OPEN

- **A / Recovery — VERIFIED, CAPTURED:** restored confirmed 13a70e21 bundle
  (SHA256 6ab1fd68edda1002b1967efb8d92556de8e32814e7f23cdadf00f7271f71e01c).
  Product a5084dc3, schema ef86e88e, migration 7d009e54 retained. R177 CLOSED;
  prior receipt/custody/adapter/source/Core/API-runtime units not reimplemented.
- **B / Integrated verification — VERIFIED, TEST:** dec03_revocation_full_gate.txt
  at 13a70e21, committed snapshot 9ade59a3, isolated env-i: 3495 passed,
  0 failed/errors, 64 skipped; mypy/ruff/import-linter/secret scan/budgets PASS;
  not_evaluated=2 unchanged. This is the revocation product gate, not stale API proof.
- **C / Live acceptance — VERIFIED, LIVE + TEST:** dec03_revocation_live.txt,
  290ddfe7, snapshot 10d65159: 53 passed. Original four post-revocation 201-vs-404
  failures now pass unchanged, as do both original restart acceptance cases.
  Stale/fresh adapters and zero/nonzero existing custody are included.
- **D / Transactions — VERIFIED within LIVE + TEST envelope:** common tenant/policy
  advisory transaction lock orders capture and revoke before the existing retry
  lock. Persistent tombstones deny new admission; same-key retries return existing
  redacted evidence, not new rows. Real pg_locks wait observed in both orderings;
  late invalidation failure rolls back tombstone and redaction together.
- **E / Trust — VERIFIED within LIVE + TEST envelope:** policy/rights/idempotency,
  tenant boundaries and independent evaluation lineage preserved. No default
  consent, duplicate evaluation store, fabricated provenance or local shadow.
  Rights references remain attestations, not ownership/training authorization.
- **F / Models — UNVERIFIED outside prior envelope:** no real-provider call,
  training, weight modification or model promotion. Native routing unchanged.
- **G / Migration — VERIFIED within LIVE + TEST envelope:** real Alembic traversal
  from stamped 0019 over metadata-built prerequisites, not a complete 0001..0018
  rehearsal. Empty downgrade succeeds; populated downgrade refuses, preserving
  stamp/evidence. Published 0019 unchanged. Legacy tenants receive explicit
  tenant-wide legacy_unresolved holds, even without rows; no policy intent is
  inferred from flags that also encode expiry. Hold denies capture/read/list/save.
- **H / Limits — INFERRED, STATIC:** legacy hold is not erasure and has no automatic
  release. Operator reconciliation must be reviewed before enabling legacy
  learning. Stop all old writers before migration; old binaries do not enforce
  0020. No production migration or rolling-upgrade/crash proof claimed.
- **I / Scope:** explicit operator approval recorded in ledger: only 0020 plus
  DEC03 ceiling 12, now 12/12. Test 07060433 updates the obsolete exact-head pin
  to the authorized 0020 and adds revocation uniqueness; original evaluation/
  custody uniqueness unchanged. Before/after: dec03_revocation_head_pin.txt
  (1 failed/9 passed -> 10 passed). No scanner or acceptance threshold relaxed.
- **J / Companions — VERIFIED, TEST:** Gateway 194 (2 warnings), 105d7bdd;
  original unchanged adversarial harness exit 0, 02942030. Frozen surfaces and
  product equality to the verified snapshot checked after recovery.
- **K / Next and verdict:** runtime retention/derived-copy and legacy reconciliation
  review, tests-first partial-batch/concurrency boundaries and true process-crash
  recovery, then final integrated closure verification after any product changes.
  Durable GOLD remains fail-closed. P01 final closure, Backend Closure, R178/UI OPEN.
  Publication remains BLOCKED pending safe environment authentication; no chat
  credential used/persisted, PR #14 update, merge/deployment or PR #13 change.

## Historical revocation admission checkpoint — FAILED / LIVE + TEST

- Confirmed recovery: 40227b18, including tests efc1da52 and actual PostgreSQL
  evidence dec03_revocation_admission_before.txt: 4 failed, 1 passed,
  39 deselected. New API captures return 201 after policy revocation instead of
  the existing safe policy-unavailable 404. Both stale/fresh configured adapters
  and revocation with/without existing samples expose the defect.
- Existing payload redaction and independent evaluation retention assertions
  pass before the admission failure. Cross-tenant/other-policy control passes.
  These are API/adapter/database tests, not process-kill proof.
- Product, hermetic tests and gate configuration are unchanged from faf00219.
  Retained integrated gate 3495/0/0/64, Gateway 194 and prior 39-case live suite
  remain historical proof of their declared scope, NOT full revocation closure.
  The interrupted expanded-live/report checkpoint was not uploaded and is not
  treated as retained evidence here.
- INFERRED / STATIC: revoke_policy only updates existing custody rows; no
  policy-level tombstone persists a zero-row revocation. Per-sample revoked also
  represents expiry, so historical policy intent must not be fabricated.
- BLOCKED / scope: 0019 already exists on mission remote 84563ab9, same blob
  247cb784f08e8474eefb258d2797c5585d694f73 as HEAD; rewriting its upgrade does
  not migrate an already-stamped DB. DEC03 production accounting is 11/11.
  Recommended fix needs one additive successor migration, not startup DDL,
  invented sample/execution rows or repurposed audit/evaluation evidence.
- NEXT: obtain narrow authorization for 0020_learning_policy_revocations.py
  and DEC03 ceiling 12; then implement tenant-policy tombstones and capture/
  revoke transaction ordering in the existing custody repository, with upgrade,
  rollback and race tests. DEC03 B remains approved; no reapproval requested.
  Retention/derived copies, runtime concurrency and true crash proof remain open.
  No budget, gate, assertion or production code changed in this checkpoint.

## Historical API/runtime custody A–K checkpoint — Backend Closure OPEN

- **A / State — VERIFIED, CAPTURED:** recovered confirmed 2591870c; product
  0e2d366f, main 369cf37c / mission remote prerequisite 84563ab9. Prior receipt,
  custody, adapter, source and Core lifecycle units retained; R177 stays CLOSED.
- **B / Regression — VERIFIED, TEST:** dec03_api_runtime_full_gate.txt (945309a8),
  committed snapshot 2591870c: 3495 passed, 0 failed/errors, 64 skipped; strict
  mypy, ruff, import boundaries, secret scan and budgets PASS; not_evaluated=2.
- **C / Original gap — VERIFIED, LIVE + TEST:** dec03_api_runtime_restart.txt
  (0dde9712): both original restart assertions now pass on PostgreSQL 17.11.
  Complete live suite 39 passed, 0 failed (cc1e4678). No acceptance relaxation.
- **D / Change — VERIFIED, TEST:** 18 actual failing-first binding cases
  (ca15625d), then 85 API/adapter passes and static checks (628b4bc7). Four
  approved surfaces inject the EXISTING Core custody seam and existing stores.
  Runtime parses explicit policy config and binds custody even with no grants;
  configured custody without a DB refuses, never silently becomes memory-only.
- **E / Trust — VERIFIED within TEST + LIVE scope:** explicit policy/rights/
  idempotency, admitted actor/tenant; source actor remains provenance only.
  Missing refs refuse before capture; storage failures map to constant safe
  refusals. Governed intake reports omit raw keys, columns and finding paths.
  Clean scans and rights references are not proof of consent/training rights.
- **F / Models — UNVERIFIED beyond prior envelope:** no real-provider inference,
  training, weights or model promotion claimed; native routing unchanged.
- **G / Learning — INFERRED, STATIC limits:** durable GOLD remains fail-closed
  pending derived-copy reconciliation. Batch rows are independent transactions
  with stable per-row retry keys, NOT atomic batch admission. Concurrent duplicate
  admission and all runtime failure interleavings are not yet proved.
- **H / Recovery — VERIFIED, LIVE + TEST within recomposition scope:** actual
  runtime recreates DB bindings, reuses the real durable session, restores sample,
  receipt and evaluation, and replays the same capture identity. 4a35eb8d added
  explicit test-operator policies/refs required by DEC03; original 200/identity/
  evidence assertions unchanged. Added no-policy negative control. No actual
  process-kill/crash recovery proof is claimed by these recomposition tests.
- **I / Decisions:** DEC03 B remains APPROVED, accounting 11/11. No frozen surface,
  threshold, scanner exception, constraint or assertion weakened. Durable
  revocation/new-admission denial across stale configured processes remains OPEN.
- **J / Other checks — VERIFIED, TEST:** Gateway 194 (two warnings), original
  adversarial harness exit 0, both retained at 5ad91e49. Publication BLOCKED,
  CAPTURED: dry-run mission push has no environment authentication. No supplied
  chat credential used, no PR update/merge/deployment or publication squash.
- **K / Next:** tests-first stale-process new-admission revocation and retention/
  derived-copy reconciliation; then runtime concurrency/partial-batch failures,
  tenant isolation and true process crash/restart. Repeat integrated verification
  after any product change. P01 final closure, Backend Closure and R178/UI OPEN.

## Historical Core lifecycle custody A–K checkpoint — Backend Closure OPEN

- **A / State — VERIFIED, CAPTURED:** restored confirmed 42fc734b. Product
  45e1f4b3 retained; main 369cf37c / mission remote 84563ab9. R177 remains CLOSED.
- **B / Regression — VERIFIED, TEST:** dec03_lifecycle_full_gate.txt, snapshot
  cef5a0fe: 3477 passed, 0 failed/errors, 64 skipped; all static/governance gates
  PASS, not_evaluated=2. No threshold, assertion or exception weakened.
- **C / Gap — FAILED, LIVE + TEST:** dec03_lifecycle_runtime_open.txt, 2e5eedad:
  37 passed / two original runtime restart failures at lines 193/307, 404 != 200.
- **D / Change — VERIFIED, TEST:** 19 failing-first missing-custody cases;
  182 learning/adapter cases pass, strict mypy/ruff clean (7afc02e0). Core-owned
  optional custody delegates both captures and detached reads/list/report/CAS,
  without durable raw _samples shadows. In-memory behavior remains tested.
- **E / Trust — VERIFIED within TEST + LIVE scope:** unavailable data remains
  metadata, not clean empty content. Review/level/eligibility use closed-state CAS;
  evaluation UUID binds tenant/source. Independent evaluation evidence survives
  CAS conflict without advanced sample trust. Clean scans/rights refs grant no rights.
- **F / Models — UNVERIFIED beyond existing tests:** no live inference, training,
  weights or model-promotion proof; existing native routing unchanged.
- **G / Learning — INFERRED, STATIC limits:** runtime/API/intake still unbound.
  Durable GOLD assignment/promotion/retrieval fail closed pending derived-copy
  reconciliation. Dedup is a snapshot, not cross-sample atomic admission proof.
- **H / Recovery — VERIFIED, LIVE + TEST (direct Core composition only):** five
  PostgreSQL 17.11 cases (1a6f733d / cef5a0fe): fresh review/evaluation/eligibility/
  retry, review/revocation races, sample-write rollback after custody CAS, and
  metadata-only quarantine. Direct recomposition is NOT process-crash proof.
- **I / Decisions:** DEC03 B APPROVED, accounting 7/11. Four approved files remain:
  API app/admin/intake and runtime. Policy snapshots are not durable revocation
  registries; stale-process new admission and derived-copy reconciliation are open.
- **J / Other checks — VERIFIED, TEST:** Gateway 194; original adversarial exit 0
  (2e5eedad). Publication BLOCKED / CAPTURED: environment GitHub authentication
  absent; dry-run push cannot authenticate. No chat credential used, PR update,
  merge, deployment or publication-time squashing claimed.
- **K / Next:** tests-first actual API/runtime custody composition with explicit
  policy, requesting actor, rights and idempotency admission and safe refusals;
  retention/revocation, derived copies, concurrent admission and true restart/crash
  remain required before final integrated Backend Closure. R178/UI remain OPEN.

## Historical execution-source custody A–K checkpoint — Backend Closure OPEN

- **A / State — VERIFIED, CAPTURED:** recovered 2e7385f3 with all verification;
  main 369cf37c / mission remote 84563ab9. R177 remains closed.
- **B / Regression — VERIFIED, TEST:** dec03_execution_adapter_full_gate.txt:
  3458 passed, 0 failed/errors, 64 skipped, all static/governance checks PASS.
- **C / Gap — FAILED, LIVE + TEST:** dec03_execution_adapter_runtime_open.txt:
  32 passed / 2 unchanged sample-restart failures (404 != 200), exit 1.
- **D / Change — VERIFIED, TEST:** 11 genuine missing-binding failures before
  implementation, all 49 adapter tests pass after, strict mypy/ruff pass.
- **E / Trust — VERIFIED within TEST + LIVE scope:** actual tenant-scoped source,
  no fabricated ingestion or node rewrite, RAW/PENDING only. Source actor is
  provenance, not caller authorization. Missing policy/source/references refuse.
- **F / Models — UNVERIFIED beyond existing tests:** test provider only;
  no new live inference, training/weights or model-promotion evidence.
- **G / Learning — INFERRED, STATIC:** lifecycle/runtime/API still unbound;
  memory is not training data; execution success is not verified learning.
- **H / Recovery — VERIFIED, LIVE + TEST (adapter scope):** four PostgreSQL cases
  pass, covering real API source executions, fresh retry, quarantine, tenant
  denial, source conflicts and late-write rollback. Duplicate fixture plan name
  was corrected, not database constraints. No process-crash closure claim.
- **I / Decisions:** DEC03 B APPROVED, 6/11, not_evaluated=2, gates unchanged.
  Source read and custody capture are separate transactions, not atomic together.
- **J / Other checks — VERIFIED, TEST:** Gateway 194 and original adversarial
  exit 0 in dec03_execution_adapter_* evidence. No PR update/merge/deployment.
- **K / Next:** tests-first Core lifecycle custody port/read/CAS binding; then
  runtime/API admission, expiry/revocation, derived-copy reconciliation and
  true crash/restart proof. Backend Closure, R178 and UI readiness remain OPEN.

## Historical external adapter A–K checkpoint — Backend Closure OPEN

This section supersedes the historical assessments below.

- **A / State — VERIFIED, CAPTURED:** restored confirmed 4edf9e87 checkpoint;
  full gate and six live adapter cases retained. Main 369cf37c / mission remote
  84563ab9; R177 closed. No product implementation repeated.
- **B / Regression — VERIFIED, TEST:** dec03_adapter_full_gate.txt at 0a369e69:
  **3447 passed, 0 failed/errors, 64 skipped**, static/governance checks PASS,
  process_exit=0. Later changes are live tests/evidence, not product changes.
- **C / Gap — FAILED, LIVE + TEST:** dec03_adapter_runtime_open.txt at d0ba8032,
  saved bce9cb79: **28 passed / 2 failed**, process_exit=1. Both original sample
  restart assertions still return 404 rather than 200; no assertion changed.
- **D / Change — VERIFIED, TEST:** dec03_adapter_before/after.txt record
  **38 failed -> 38 passed**, strict mypy/ruff success. Explicit closed policy
  parser, atomic external custody capture, decoded get/list and guarded CAS save.
- **E / Trust — VERIFIED within TEST + LIVE scope:** no default policy/rights/
  retention, metadata-only quarantine, tenant-safe reads, conflicting retry and
  stale-save refusal. Policy removal suppresses content and denies new capture;
  policy snapshots are NOT durable revocation registries or automatic erasure.
- **F / Models — UNVERIFIED beyond existing tests:** no new external-provider,
  training, weights or model-promotion proof. Core routing unchanged.
- **G / Learning — INFERRED, STATIC (partial):** lifecycle/runtime/API remain
  unbound. Memory is not training data; receipt success is not verified learning.
- **H / Recovery — VERIFIED within adapter LIVE + TEST scope:**
  dec03_adapter_live.txt: **6 passed, 24 deselected**, PostgreSQL 17.11, real
  session factory/AsyncBridge. Fresh clean/quarantined reads and retry identity,
  policy-removal denial, CAS/revocation, response loss AFTER actual commit and
  four concurrent callers/one identity. Not HTTP binding or process-crash proof.
- **I / Decisions:** DEC03 B APPROVED, accounting **6/11**, not_evaluated=2;
  remaining files: lifecycle, API app/admin/intake and runtime. Gates unchanged.
- **J / Other checks — VERIFIED, TEST:** dec03_adapter_gateway.txt **194 passed**;
  original dec03_adapter_adversarial.txt exit 0. Publication BLOCKED by absent
  environment GitHub authentication; no chat credential copied or tested, no
  PR #14 update, merge or deployment. Confirmed bundles preserve local progress.
- **K / Next:** retain complete-live output; tests-first execution-born custody
  using actual source records, Core-facing lifecycle port and durable CAS state;
  runtime/API/intake policy/rights/idempotency admission, expiry/revocation and
  derived-copy reconciliation. Prove actual restart/crash before Backend Closure.

**Backend Closure, R178 completion and UI readiness remain OPEN. Do not repeat
completed receipt/codec/adapter units or request DEC03 approval again.**

## Historical receipt seam A–K checkpoint — Backend Closure OPEN

This section superseded the codec/foundation assessments at that checkpoint.

- **A / State — VERIFIED, CAPTURED:** recovered bundle `fd4afd5c`, unchanged
  tested product at that snapshot; retained verification through `a38ed08a`.
  Main remains `369cf37c`, mission remote `84563ab9`; R177 remains closed.
- **B / Regression — VERIFIED, TEST:** `dec03_receipt_full_gate.txt`: **3409 passed,
  0 failed/errors, 64 skipped**, all static/governance checks PASS, exit 0.
  Identical committed clone, hermetic environment, sibling TMPDIR under .venv.
- **C / Gap — FAILED, LIVE + TEST:** `dec03_receipt_runtime_open.txt`: **22 passed,
  2 failed**. Original sample recomposition/runtime-restart assertions still
  return 404, not 200. No assertion relaxation, skip or invented recovery.
- **D / Change — VERIFIED, TEST:** `dec03_receipt_before.txt`: **7 failed,
  11 passed** before builder; `dec03_receipt_after.txt`: **18 passed** after.
  Genuine metadata-only scan report construction is now independent of storage.
  Legacy recorder delegates and retains its single write and actor fallback.
- **E / Trust — VERIFIED within TEST envelope:** builder tests cover secret-bearing
  keys/field names/values, content detachment, missing actor refusal before scan,
  scan failure propagation and no fabricated provider response. No storage-policy,
  rights, sanitization or learning authorization is granted by building a receipt.
- **F / Models — UNVERIFIED beyond existing tests:** no new external provider,
  training, weights or model-promotion evidence. Core routing remains unchanged.
- **G / Learning — INFERRED, STATIC (partial):** lifecycle/runtime remains unbound;
  memory is not training data and successful execution is not verified learning.
- **H / Recovery — VERIFIED within LIVE + TEST repository envelope:**
  `dec03_receipt_live.txt`: **20 passed, 4 deselected**, PostgreSQL 17.11. Live
  candidates use the builder directly, not an intermediate recorder. New test
  checks zero rows before custody, one atomic capture and fresh-row recovery;
  existing concurrency, late-write rollback, quarantine and codec checks pass.
  This is not runtime/process-crash closure; C remains failed.
- **I / Decisions:** DEC03 B APPROVED; usage **5/11** with apps/api/ingestion.py
  added to the four existing files. Historical budgets, frozen surfaces and
  thresholds unchanged; not_evaluated=2. No new approval needed.
- **J / Additional verification — VERIFIED, TEST:** `dec03_receipt_gateway.txt`
  **194 passed**; `dec03_receipt_adversarial.txt` original P01/P03 harness exit 0.
  These files are retained now. Secure Git publication remains BLOCKED: no token
  injected into Git environment; push dry-run refuses. Supplied chat credential
  was not tested or copied to files/logged commands. No PR update/merge/deploy.
- **K / Next:** tests-first explicit policy configuration and atomic adapter in
  apps/composition/learning.py, then durable lifecycle reads/CAS mutations,
  unavailable-payload guards, runtime/API/intake policy/rights/idempotency admission,
  expiry/revocation and derived-copy reconciliation. Prove real runtime retry,
  restart/crash/concurrency and all final checks before Backend Closure.

**Receipt construction unit is verified; Backend Closure, R178 completion and UI
readiness remain OPEN. Do not repeat the codec or receipt implementation.**

## Historical codec A–K checkpoint — Backend Closure OPEN

This section superseded the foundation-only assessment at the codec checkpoint.

- **A / State — VERIFIED, CAPTURED:** recovered committed `96d0e5d6` from the
  validated recovery bundle. Product codec is `414d7389`. Remote mission remains
  `84563ab9`; main remains `369cf37c`; R177 closed. No push/PR update/merge claimed.
- **B / Regression — VERIFIED, TEST:** `dec03_codec_full_gate.txt`: **3402 passed,
  0 failed/errors, 64 skipped**, all governance/static checks PASS, exit 0.
- **C / Gap — FAILED, LIVE + TEST:** `dec03_codec_runtime_open.txt`: **21 passed,
  2 failed**, exit 1. Original recomposition/runtime-restart samples still return
  404. No assertion or skip changes hide this gap.
- **D / Change — VERIFIED, TEST:** recovery codec tests-first **36 failed + 13
  passed → 49 passed**. Tenant/UUID identity, clocks, retention, revision, enums,
  closed metadata version/verdicts and content/descriptor digests are validated.
  Repository writes share the same descriptor/state codec. Mutable data detached.
- **E / Trust — VERIFIED, TEST:** rescanning rejects secret-bearing payloads;
  absent/changed/foreign policy, expiry, quarantine and revocation cannot restore
  content as clean data. None is not an empty payload. No rights or trust grant.
- **F / Models — UNVERIFIED beyond existing tests:** no new live inference,
  trained-model promotion or weights claimed; ordinary Core routing preserved.
- **G / Learning — partial:** memory is not training data; successful execution
  is not verified learning. Safe decoding is not durable lifecycle composition.
- **H / Recovery — VERIFIED within repository scope, LIVE + TEST:**
  `dec03_codec_live.txt`: **19 passed, 4 deselected**, PostgreSQL 17.11; includes
  fresh-repository decoding, unavailable-content handling and stored JSON
  corruption refusal. Runtime closure still FAILED as in C; no crash proof.
- **I / Decisions:** DEC03 B APPROVED; budget **4/11** unchanged, no frozen surface
  or threshold changes. not_evaluated remains **2**. Do not request approval again.
- **J / Verification boundary:** later Gateway/adversarial output was not in the
  saved bundle and is not claimed as retained current proof. Existing published
  Gateway/adversarial results remain historical pending final integrated checks.
- **K / Next:** explicit policy configuration and side-effect-free genuine receipt
  construction, atomic custody/lifecycle/runtime/API binding, admission fields,
  durable reads/CAS mutations, expiry/revocation and derived-copy reconciliation.
  Then prove actual restart/crash/idempotency/concurrency and all final checks.
  Preserve committed bundles while secure Git publication remains unavailable.

**Backend Closure, P01 runtime closure, R178 completion and UI readiness remain
OPEN. Do not reimplement the verified codec or repeat its gate without cause.**

## Historical foundation-only P01 A–K checkpoint

The following assessment predates the recovered codec implementation and tests.

**A — State (VERIFIED / CAPTURED):** Published `84563ab9` recovered after another
reset. Main remains `369cf37c`; R177 closed. Existing mission PR is #14; this
session has not merged, deployed or updated it. The attempted codec commits from
the preceding sandbox are absent locally and remotely, not recovered progress.
Remote reads succeed; authenticated publication is BLOCKED: push dry-run fails
for missing Git credentials, and GH_TOKEN/GITHUB_TOKEN are not injected. A token
in conversation must not be copied into logged commands or repository files.

**B — Strengths (VERIFIED / TEST):** `p01_subject_full_gate.txt`, snapshot `b9d9f55b`:
**3353 passed / 0 failed/errors / 64 skipped**, all governance/static gates PASS.
Gateway **194 passed** (`p01_subject_gateway.txt`). Focused review **114 passed /
1 existing skip** (`p01_subject_review_green.txt`). No test threshold, security
exception, frozen surface or old budget weakened. Those results predate DEC-03
production changes; they are not full-gate proof of the custody foundation.

Current foundation verification at `84563ab9`: `dec03_foundation_gate.txt` records
**3366 passed / 0 failed/errors / 64 skipped**, all governance/static gates PASS,
process exit 0. Explicit strict mypy on the repository/policy modules and full
ruff are clean (`dec03_foundation_static.txt`). This is foundation regression
proof, not durable runtime closure. Gateway and adversarial results above remain
historical; no fresh post-integration result is claimed.

**C — Gap (FAILED / LIVE + TEST):** Original P01 shared-evaluation visibility and
original P03 now pass (`p01_subject_adversarial.txt`, exit 0). Durable P01 does NOT:
`p01_runtime_restart_red.txt` has **2 passed / 2 failed**, exit 1. Both recomposition
and actual durable runtime lose the sample (404); source/evaluation GETs survive.
No xfail/skip masks these acceptance failures.

**D — Changes (VERIFIED / TEST):** Genuine per-row validator scan receipts (no
provider inference), admitted actor forwarding, shared append-only evaluations,
write-failure containment. Review fixed caller payload aliasing and durable codec
fabrication of provider responses for validator nodes. Positive learning/reach
fixtures retain their assertions with explicit actors and honest receipt counts.

**E — Protected boundary (INFERRED / STATIC; foundation VERIFIED / TEST + LIVE):**
**R178-DEC-03 option B is APPROVED.** Explicit policy preparation, metadata-only
quarantine, additive custody schema/migration, atomic repository capture,
idempotency, CAS metadata saves, expiration and revocation are implemented at
`84563ab9`. Published `dec03_custody_migration.txt` records 12 passing focused live
tests. These repository operations are not yet bound to lifecycle/runtime/API.
Blind snapshots remain forbidden; there is no implicit retention or rights grant.
No production migration or purge was performed.

**F — AI/model readiness (UNVERIFIED / STATIC beyond existing tests):** Routing
remains hermetically covered, not new live inference or model training proof.
Native models remain ordinary Core-governed routable resources, not authorities.
No trained weights, candidate quality, live teacher or weight-promotion claim.

**G — Learning chain (INFERRED / STATIC with measured links):** Capture/shared
verification linkage VERIFIED here; durable sample/eligibility recovery FAILED.
Privacy/rights/sanitization remain independent. Dataset UUID != versioned dataset.
Training → candidate → trained-model evaluation → shadow/canary → promotion/rollback
is UNVERIFIED, not implied by software tests. Memory != training data; successful
execution != verified learning.

**H — Recovery (VERIFIED / LIVE + TEST within limits):** Local PostgreSQL 17.11
proves actual subject/evaluation persistence, fresh-store reads, real FK/duplicate
refusal, tenant isolation, durable identity and actual-runtime sample-loss failure.
ASGI transport and dependency-closed metadata tables were used. The focused
custody tests also rehearse migration 0019 empty downgrade/upgrade and populated
rollback refusal. No full historical migration-chain deployment, HTTP-network/
process-kill, pgvector, production concurrency or provider-live proof is claimed.
The two unchanged not_evaluated entries remain separate from PASS.

**I — Decisions:** DEC-01 implemented; DEC-02 design and subsequent P01 implementation
authority honored. The operator explicitly approved DEC-03 option B, including
policy-gated persistence, metadata-only quarantine and operator-defined retention.
No further DEC-03 approval is pending. The approved packet and rollback boundaries
remain in `dec02_ingestion_design.md` §8; implementation budget remains 4/11.

**J — Safe continuation:** Keep the real restart acceptance assertions intact;
turn them green only through production runtime binding. Re-run via
`bash tests_live/r178/run_local_postgres.sh`; binary bootstrap instructions are in
that runner. No ambient DB/provider credentials, raw secrets in receipts, fake
historical executions, FK removal, default rights grant, training or promotion.

**K — Exact next action:** The interrupted foundation full gate is now complete
and its actual output retained locally. Restore secure publication via an injected
Git credential, then implement tests-first policy configuration, safe recovery codec and atomic
capture composition in the already-approved scope. Bind lifecycle reads/mutations,
API/intake admission, expiry/revocation and derived-copy reconciliation. Finally
prove runtime/process restart, recovery/idempotency and full regression + Gateway
+ original adversarial + live checks. **P01 durable closure, Backend Closure,
R178 completion and UI readiness remain OPEN until all conditions are evidenced.**

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
