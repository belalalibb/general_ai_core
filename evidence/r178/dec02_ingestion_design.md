# R178-DEC-02 — external ingestion lifecycle design review

Sections 1–7 describe the HISTORICAL design unit. P01 implementation is now
authorized; genuine-subject/shared-evaluation code is published in PR #14.
Section 8 is a new, narrower protected payload-custody decision.

Historical status: DESIGN REVIEW COMPLETE; implementation NOT performed. Authority: operator
approved option B, design review first. No evaluation-store switch, schema change,
fake execution, constraint removal, data migration or training is part of this unit.

## 1. Evidence and problem

- FAILED / TEST: P01 in the unchanged `probe_learning_chain.py` successfully
  evaluates an external sample, but admin evaluation listing is empty. The final
  recheck is `dec01_adversarial.txt`; P03 is fixed independently, P01 remains.
- INFERRED / STATIC: `core/learning/lifecycle.py:234-251` assigns a new UUID to
  `source_execution_id` without creating an Execution. Sample state and source
  kind live in `_samples`, an in-process map. A UUID is not a provenance record.
- INFERRED / STATIC: `apps/api/app.py` still constructs the sample evaluator over
  its private InMemoryEvaluationStore. This design review deliberately leaves
  that behavior unchanged; DEC-01 only shared replay verification evidence.
- INFERRED / STATIC: migration 0010 and current metadata require
  `evaluations.execution_id -> executions.id` with RESTRICT. Existing Execution
  requires tenant, user, request hash, real status/strategy and timestamps.
  Existing node types include VALIDATOR and TOOL_CALL; a MODEL_CALL is not
  required by the entity contract (`core/contracts/execution.py`).
- INFERRED / STATIC: `ExecutionStorePort.put` and EvaluationStorePort.record are
  separate operations. Neither contract supplies a shared unit of work with
  durable learning samples. Do not claim their sequence is one DB transaction.

Therefore a one-line shared-store substitution is unsafe for external samples.
A valid durable subject must first exist, and sample/receipt recovery semantics
must be established. The missing subject is not repaired by weakening the FK.

## 2. Recommended representation (proposal, not new code)

Represent ingestion as an ACTUAL bounded orchestration operation, not model
inference: a real Execution with validator/tool nodes using existing strategy
and lifecycle vocabulary, driven by an ingestion coordinator outside Core's
provider path. Input descriptors may carry a versioned `external_ingestion`
operation discriminator in existing JsonObject fields; do not add a closed enum
or repurpose the billing/quality fields as a metadata store.

The coordinator must really perform the described intake work and persist its
outcomes. Do not call an echo/fake provider or create already-SUCCEEDED model
records merely to satisfy the FK. A proposal over existing entities is feasible
at the contract level; compatibility with every runtime/billing/trace consumer
requires tests before implementation can be approved as sound.

Required provenance descriptor (schema to be reviewed before coding):
- server-assigned operation identity, authenticated tenant and actor;
- tenant-scoped idempotency key and canonical descriptor/content digest;
- source kind, opaque source/object reference, source/content revision;
- bounded format and validator/sanitizer policy versions;
- explicit rights/policy receipt references and retention classification;
- per-row stable source position/content revision and admission/refusal outcome;
- timestamps and attempt/retry lineage without copying raw secrets into audit.

The fingerprint is integrity metadata, not proof of ownership, legal rights,
consent or authenticity. No cross-tenant hash-based deduplication. No secret
values, hidden reasoning or unrestricted raw source content in the receipt.

A batch receipt may summarize multiple rows, but evaluation MUST remain linked
to the exact sample/content revision. Since EvaluationRecord currently targets
execution-level subjects, a shared batch execution UUID alone is insufficient
for per-row promotion. Recommended follow-up design: distinct real row-validation
operations (each with its own execution identity) linked to the batch receipt, or
an explicitly approved sample/subject contract extension. Never silently label a
batch evaluation as verification of every row.

## 3. Lifecycle and honest status semantics

1. Admit actor/tenant, payload bounds, source policy and idempotency before effects.
2. Persist a QUEUED operation/receipt, then RUNNING while validation really occurs.
3. Parse/check/quarantine with bounded resource usage; create only RAW/PENDING
   sample candidates for admitted rows. Failed/refused rows get explicit outcomes.
4. Persist the row outcome, sample linkage and operation evidence using a reviewed
   durable transaction/recovery protocol. Only then acknowledge admission.
5. Finish the ingestion operation with honest status and counts. SUCCEEDED means
   the specified ingestion procedure completed and its outcome was durably recorded;
   it NEVER means all rows were eligible, sanitized, verified, training-ready or GOLD.
   Quarantined/unrecoverable batches are FAILED with a named reason; no synthetic
   success. For partial batches, define explicitly whether per-row admission is
   allowed and expose accepted/refused counts; no new undocumented PARTIAL enum.
6. Evaluation, verification and training eligibility are later independent acts,
   each referencing the exact admitted row/content revision and persisted subject.
7. Cancellation/deletion/retention acts must reconcile descendants and eligibility;
   they cannot erase append-only verification or create orphan references.

No evaluation is written before its genuine subject exists. No sample may enter
trusted learning because its ingestion Execution has status SUCCEEDED.

## 4. Transactions, retries and recovery

A future implementation must choose and prove ONE existing repository-compatible
unit-of-work/outbox pattern, not add an ad hoc second store or recovery journal.
Learning samples are currently in-process, so changing only evaluation durability
would leave broken sample/evidence lineage after restart. A durable sample/receipt
binding and recovery path are prerequisites to claiming a durable intake chain.

Failure matrix / required behavior:

| Failure | Required behavior |
|---|---|
| Actor/policy/payload admission fails | No operation effects, no sample/evaluation; tenant-safe refusal. |
| Subject/receipt write fails | Do not capture or acknowledge a sample; no evaluation attempt. |
| Sample write fails after operation starts | Mark/recover unfinished operation; no admitted success receipt. |
| Evaluation write fails | Keep actual execution/sample truth; no verified/training/promotion success. Retry only with stable subject/version and idempotent semantics. |
| Response lost after commit | Same tenant/idempotency key returns same receipt, no duplicate sample or fictional second execution. |
| Same key, different content/version | Explicit conflict; no silent overwrite of provenance. |
| Restart between phases | Recover from committed state/outbox; unknown/incomplete never upgraded to success. |
| Foreign tenant ID/reference | Same absence/refusal shape, no read or write under another tenant. |

DEC-01's execution-then-evaluation sequence already fails closed if the evidence
append fails, but is not a cross-store transaction. Do not generalize it into a
claim that ingestion/sample persistence is atomic.

## 5. Verification plan before any store switch

Existing failing-first anchor: P01 remains red by design-review scope. Do not
skip it or alter its expected one-record outcome. Additional implementation tests
must be written before future production changes:

- contract/source-type tests: actual validator operations, no provider invocation,
  no model cost/quality success inferred; honest trace/UI/API representation;
- per-row binding: evaluating row A cannot verify row B from the same batch;
- policy/rights missing or revoked -> no training eligibility; sanitizer, dedup,
  poisoning and tenant policy gates remain independent and deny by default;
- idempotent retries, changed-content conflict, cancellation, partial/quarantined
  batches and every failure point in the table above;
- restart/crash tests over real PostgreSQL with valid tenant/plan/actor/execution
  parents seeded, before/after evidence identity and actual FK/CHECK enforcement;
- migration rehearsal only if later deemed necessary, rollback and retention
  integrity, no provenance fabrication for existing synthetic UUIDs;
- full existing gate, gateway/integration suites and original P01/P03 probes.

No live PostgreSQL/crash proof was obtained in this design review. Static schema
inspection and hermetic tests must not be relabeled as live durability evidence.

## 6. Rollout and rollback constraints

Keep old synthetic-UUID samples explicitly unverified for durable-evidence use;
require controlled re-ingestion with real source provenance. Do not fabricate
historical Execution rows or auto-grant rights to old data. Prefer an opt-in,
contract-tested ingestion path before default adoption. Reverting a deployment
must not delete persisted evidence or restore permissive promotion. Retain a
fail-closed reader for unsupported versions. Operational rollout, migrations,
retention policy and any irreversible processing remain separate protected acts.

## 7. Design conclusion / exact next action

Option B is feasible as an actual ingestion orchestration, not a FK workaround.
It is NOT yet a justified one-line evidence-store switch. The review identifies
three implementation prerequisites: exact per-row subject binding, durable sample
and receipt persistence, and proven transaction/recovery semantics. Existing
entities can express validator work, but repository consumers and data-rights
policy need explicit acceptance tests before adopting this representation.

Next bounded engineering proposal: tests-first ingestion coordinator plus shared
transaction/receipt design over existing ports, with per-row subject semantics
and rights/retention inputs specified. No production ingestion rewiring in this
review. P01 remains a known gap; universal learning/model-training readiness is
not claimed. DEC-01 implementation and its green gate do not close DEC-02 runtime.


## 8. R178-DEC-03 — durable payload custody, quarantine and retention

**Historical pre-approval status: BLOCKED / STATIC + LIVE + TEST.**
**Current decision: option B APPROVED; implementation is partial.**
P01 IMPLEMENTATION is already authorized. This is NOT another request to approve
DEC-02 implementation or reopen DEC-01. The choice now required is what raw data
may become durable and its retention/revocation policy. Section 6 explicitly
reserved retention policy and irreversible processing; the continuing mission
also reserves major data-governance decisions to the operator.

### New evidence and why a simple snapshot is unsafe

- VERIFIED / LIVE + TEST: `p01_runtime_restart_red.txt`, code `bffa5124`, saved
  `89e01dd3`: PostgreSQL 17.11, actual build_runtime_profile, real durable identity,
  capture/evaluate, disposal of engine/bridge, then a newly composed runtime using
  the SAME durable session. Execution and evaluation GETs succeed; sample GET is
  404. Two restart tests fail, two FK/tenant/append-integrity tests pass. This is
  real DB + ASGI, NOT a network/process-kill test or Alembic rehearsal.
- VERIFIED / TEST: flagged-batch acceptance in the 3353-pass full gate proves raw
  flagged candidates stay tracked in process, RAW/PENDING, with clean-review
  refusal. Their execution receipts contain hashes/counts, not payloads.
- INFERRED / STATIC: learning_samples lacks raw key/value, provenance and verdict
  snapshots. Serializing _SampleRecord wholesale would newly persist unresolved
  secret material; even scan paths may contain caller-controlled key text.
- A regex-clean scan does not establish privacy, ownership, consent or a retention
  period. Putting payload into execution JSON would expand receipt exposure;
  using memory as a raw training-source store would violate memory != training data.

### Options

| Option | Result | Benefit | Limitation / risk |
|---|---|---|---|
| A | Persist existing sample metadata only; missing payload remains unavailable | No new raw-data custody | Full lifecycle/re-evaluation recovery remains incomplete; cannot claim Backend Closure. |
| B — recommended | Explicit policy-governed durable payload companion, metadata-only quarantine, finite retention/revocation | Can support safe recovery and exact lineage | Additive schema, policy admission and coordinated lifecycle writes; missing policy must refuse durable payload admission. |
| C — rejected | Unconditionally serialize raw sample/scan state to JSONB or execution metadata | Smallest patch | Unbounded flagged/secret-data persistence and missing rights/retention authority; not safe. |

### Exact option B envelope — APPROVED by the operator (R178-DEC-03)

1. Preserve learning_samples, all existing FKs/CHECKs, append-only evaluations and
   frozen LearningSample fields. Add ONE infrastructure-owned payload/provenance/
   lifecycle-revision companion, not another evaluation store. No historical
   synthetic executions or fabricated provenance backfills.
2. Persist payload only under an explicit tenant-admitted storage-policy reference,
   source/rights attestation reference and finite expiry. **No default rights grant
   or assistant-selected production TTL.** Missing/foreign/expired/revoked policy
   refuses durable payload admission. Policy values are deployment input, not
   inferred from scan success; attestations are not proof of legal ownership or
   authorization to train.
3. Unresolved secret findings yield metadata-only durable quarantine: opaque IDs,
   digest/counts/closed reason codes; never raw flagged content, raw finding paths
   or secret-shaped keys in receipts/audit/DB. Corrected content is re-ingested as
   a new revision, still RAW/PENDING. Missing content must never restore as empty,
   clean, eligible or verified data.
4. Expiry/revocation disables further source eligibility and reconciles derived
   retrieval copies while preserving redacted immutable evidence. Payload deletion
   is not evidence deletion. No production purge/migration/processing is authorized
   merely by implementing the code; rollout still needs deployment policy inputs.
5. Tenant + idempotency key + exact descriptor/content revision returns the SAME
   result after response loss/restart; changed content/policy conflicts. Database
   uniqueness/transaction owns the decision; execution upsert is not create-once
   authority. No cross-tenant deduplication or actor borrowing.
6. Commit subject/sample/payload linkage atomically when all live in PostgreSQL.
   Cross-store effects use the EXISTING outbox/recovery pattern. Lifecycle revision
   checks prevent stale writers; failures never publish advanced trust. Sequential
   independent writes must not be described as one transaction.
7. Unconfigured durable custody is fail-closed and explicitly reported, not silent
   in-process success. Preserve the in-memory demo's documented non-durability.
   No training, live model promotion, provider spend or frozen/UI changes included.

### Implementation dependency plan and accounting

Approved execution order: policy/codec failing tests → additive schema/repository → genuine
transactional coordinator → lifecycle read/write/recovery binding → actual runtime
and API/intake composition → live retry/concurrency/crash probes → full validation.
Record a new independent production-file list/cap BEFORE editing. Expected areas:
core learning ports/service (pure), infrastructure metadata/migration/repository,
apps ingestion/composition/runtime/request admission. Old 5/5 subject + 1/1 codec
budgets stay closed. Do not introduce a second state journal or evaluation store.

### Acceptance, risks, rollout and rollback

- Both committed restart failures must turn green through actual runtime storage,
  NOT a test-only map hydrator; add true process-restart and interrupted-write tests.
- Lost response, same/different-content concurrent retries, foreign tenant/row,
  malformed/unsupported snapshot, stale writer, evaluation append/state-commit
  failure, expiry/revocation and quarantined-source recovery must be exercised.
- Secret sentinel absent from all persisted rows/receipts/logs. Missing policy
  never confers rights/eligibility; unavailable payload never becomes clean data.
- Migration forward/compatibility rehearsal in the local disposable DB before any
  rollout. Rollback disables new intake, preserves evidence and uses a fail-closed
  reader; do not DROP populated stores or restore permissive promotion.
- Full unchanged hermetic gate, gateway, original P01/P03 and live DB suite pass
  together. Browser/two-account provider and trained-model limitations stay explicit.

**Decision: APPROVED.** The operator approved R178-DEC-03 option B's custody,
quarantine, retention and fail-closed admission envelope for tests-first
implementation. Retention values remain explicit operator configuration. Do not
request approval again or treat older pending-decision text as current authority.

At published `84563ab9`, the policy primitive, additive custody schema/migration,
atomic repository, idempotency, CAS state writes, expiry and revocation operations
exist. `dec03_custody_migration.txt` records 12 passing focused live tests, including
local empty migration rollback/upgrade and populated rollback refusal. This is
not a production rollout or a full historical migration-chain proof.

The safe recovery codec is now implemented and verified in recovered product
`414d7389` (tests and retained live/gate evidence included through `96d0e5d6`).
It validates identity, metadata versions, digests and payloads without restoring
unavailable content as clean data. Actual lifecycle/runtime/API policy admission,
automatic expiry/revocation and derived-copy reconciliation are still unbound.
The original two sample-restart acceptance failures remain open. Backend Closure
and UI readiness must not be declared from repository-only tests.

At receipt checkpoint `fd4afd5c`, `build_external_ingestion_report` separates the
real scan/metadata-only report construction from ExternalIngestionRecorder's
legacy store.put. Atomic custody callers can now pass execution/nodes directly;
this is not yet the actual lifecycle/runtime binding. Live custody fixtures use
this path without an intermediate store; focused evidence is 20 passed, 4
deselected. Post-receipt full gate is 3409 passed, 0 failed/errors, 64 skipped;
Gateway 194 passed and original adversarial harness exit 0 are retained in
`dec03_receipt_*` evidence files. Full live suite still has 22 passed and the two
original restart failures. DEC03 accounting is 5/11, with the approved ingestion
file added; six remaining production surfaces are lifecycle, composition/learning,
API app/admin/intake and composition/runtime. Next is explicit policy/atomic
adapter composition and lifecycle binding, not another approval or receipt rewrite.

Current adapter checkpoint: `apps/composition/learning.py` is implemented with
closed explicit policy configuration, atomic external capture, safe decoded
reads/list and guarded CAS saves. Tests-first evidence is 38 failed -> 38 passed.
Retained post-adapter gate: 3447 passed, 0 failed/errors, 64 skipped, all checks
PASS, not_evaluated=2. Gateway 194 passed; original adversarial harness exit 0.
Six actual PostgreSQL adapter cases pass (24 deselected), including fresh retry
identity, quarantine, removed-policy denial, CAS/revocation, response loss after
real commit and concurrent callers. Complete live suite at d0ba8032, saved
bce9cb79: 28 passed / 2 original restart failures, exit 1. This is adapter proof,
not actual runtime/process-crash closure.

Current accounting **6/11**; five approved production files remain: lifecycle,
API app/admin/intake and runtime. Next: execution-born capture using actual
stored source records, Core-facing lifecycle custody binding and durable CAS
state, explicit runtime/API policy/rights/idempotency admission. Policy snapshots
are not durable revocation registries or automatic purge; repository revoke_policy
alone cannot deny new capture by stale configured processes. Expiry/revocation
and derived-copy reconciliation remain mandatory. No Backend Closure/UI claim.


Current execution-source checkpoint (0fa16e80, verified c659be07..2e7385f3):
read-only tenant-scoped ExecutionRecord source binding, no new ingestion source
or node rewrite; explicit policy/rights/idempotency and RAW/PENDING admission.
Stored source actor is provenance, not caller authorization. Source read and
custody write are separate; repository rechecks tenant/source and FKs on capture.
Retained evidence: 11 failing-first cases -> 49 adapter passes; four real
PostgreSQL source cases; full gate 3458/0/0/64; Gateway 194; original adversarial
exit 0. Full live suite 32 passed / 2 original restart failures. Accounting 6/11.
Next: Core lifecycle custody binding, then runtime/API/intake admission, expiry/
revocation and derived-copy reconciliation. No Backend Closure or UI readiness.

Current Core lifecycle checkpoint supersedes the execution-source checkpoint
above: product 45e1f4b3, tests 7afc02e0, live cef5a0fe, full gate 42fc734b.
Optional Core-owned custody delegates both captures, detached read/list/report
and closed-state revision CAS without raw local shadows. Unavailable content
never becomes clean empty content; evaluation references bind tenant/source.
182 learning/adapter units pass; five direct PostgreSQL lifecycle cases pass;
full gate 3477 passed, 0 failed/errors, 64 skipped, all checks PASS, not_evaluated=2.
Gateway 194 and original adversarial exit 0 retained at 2e5eedad. Complete live
37 passed / two unchanged runtime restart failures: NOT Backend Closure.

Current accounting **7/11**; four approved production files remain: API app,
admin, intake and runtime. Durable GOLD assignment/promotion/retrieval refuses
until coordinated derived memory/audit/retention handling. Dedup is a snapshot,
not cross-sample atomic admission proof. Policy snapshots/repository revocation
alone still cannot deny new capture by stale configured processes. Next is
actual API/runtime custody composition, explicit policy/rights/idempotency and
requesting-actor admission, safe refusals; then retention/revocation, derived
copies, concurrency and true process restart/crash. DEC03 B remains APPROVED.
