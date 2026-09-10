# R178-DEC-02 — external ingestion lifecycle design review

Status: DESIGN REVIEW COMPLETE; implementation NOT performed. Authority: operator
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
