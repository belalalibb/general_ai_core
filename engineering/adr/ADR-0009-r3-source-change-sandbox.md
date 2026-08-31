# ADR-0009 — R3 Source-Change Workflow: Ephemeral Pre-Production Sandbox + Differential Verification

```text
STATUS: ACCEPTED (explicit operator authorization, 2026-08-31 — V8 hermetic
        build authorized; REAL R3 ACTIVATION REMAINS §14-GATED)
DATE: 2026-08-31
TASK: V8 chunk 1 (R124) — MASTER_VISION_V2_ROADMAP §V8
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
No significant architecture change is allowed without an ADR.

---

## Context

MASTER_VISION_V2 phase V8 requires the R3 Source-Change Workflow:
*"Isolated proposed-change workspace → patch+tests+verification → admin
review → explicit approval → apply → verify → audit"* — marked **§14 STOP
EXPECTED** and gated on 5 open credential items. The operator has now
issued a split authorization (recorded verbatim in the execution state at
R124):

- **BUILD / DESIGN / HERMETIC VERIFICATION = AUTHORIZED NOW** — using only
  hermetic tests, synthetic secrets, sanitized/representative data,
  isolated ephemeral sandboxes, immutable snapshots, and existing shared
  platform primitives.
- **REAL R3 ACTIVATION / SHIPPING AGAINST AUTHORITATIVE SOURCE = STILL
  GATED** — R3 must remain structurally non-registrable/non-active in the
  real composition until §14 is satisfied. At the activation boundary:
  STOP and report FACT / IMPACT / OPTIONS / RECOMMENDATION / OPERATOR
  DECISION REQUIRED.

Constraints and invariants in force:

- The sandbox MUST be **structurally incapable** of: writing authoritative
  source; pushing to remotes; reading real credentials/secrets; bypassing
  existing security/authority boundaries. "Structurally" means the
  incapability lives in the type/interface/composition shape, not in a
  behavioral check (the AA-2/AA-3 registry precedent: a mutation tool that
  cannot exist cannot be prompt-injected into use).
- `apps/admin_agent/contracts.py` pins
  `NEVER_REGISTRABLE_CLASSES = {R3_SOURCE_CHANGE, R4_FORBIDDEN}` enforced
  unconditionally at registry construction. This pin MUST survive V8's
  hermetic build unchanged.
- `core/workspace/` is frozen as *"deliberately NOT the source-edit area"*
  — the V8 workspace cannot ride it; a new abstraction is required.
- The closed `AuditEventType` set (13 values, 20 §9 "nothing added or
  dropped") already contains `APPROVAL_DECISION` and `TOOL_CALL`.
- P1–P9, shared-platform-first, Fix Once / Benefit Everywhere,
  evidence-first, no-fabrication all apply. The Internal Agent must not
  gain a parallel implementation of generic platform capabilities.
- Acceptance criterion 12 (operator, verbatim): *"the workflow can later
  be activated without redesigning the architecture"* — activation must be
  a composition change, never a redesign.

## Alternatives

**A. Extend `core/workspace/` into a source-edit area.**
Pros: reuses an existing shared primitive; storage/path discipline already
solved. Cons: violates the frozen V5 definition (*"NOT the source-edit
area"*) — reinterpreting a frozen boundary to save a package is exactly the
drift the append-only discipline exists to prevent; workspace files are
mutable-by-design while source-change proposals must be immutable and
version-bound. **Rejected.**

**B. Real git worktree + subprocess sandbox now (containers/branches on the
actual repository).**
Pros: highest fidelity; the eventual production shape probably involves
real VCS. Cons: not hermetic (network, filesystem, git state); would touch
the authoritative repository during the build phase; requires real
credential handling — all three are forbidden by the standing
authorization while §14 is open. **Rejected for the build phase** (a real
binding can later implement the same port behind the activation gate —
that is precisely what the port indirection buys).

**C. New framework-free `core/sourcechange/` package: immutable
content-addressed snapshots + pure patch algebra + a `SandboxPort` whose
INTERFACE has no authoritative-write/push/secret capability, with a
hermetic in-memory binding now and the real binding deferred behind the
§14 activation gate.** Pros: structural incapability by construction; the
hermetic binding satisfies every operator acceptance criterion; activation
later = compose a different `SandboxPort` binding + register the applier
seam — zero redesign (criterion 12); follows the proven platform pattern
(ports in core, bindings at composition, absent seam = absent capability,
20 §4). Cons: the hermetic binding is lower-fidelity than a real git
sandbox — accepted consciously and recorded honestly (V8 completion claims
"hermetic build verified", never "activated"). **Chosen.**

## Decision

Build the R3 Source-Change Workflow as follows (all names final):

### 1. `core/sourcechange/` — new framework-free package (P1 posture)

- **`SourceSnapshot`** — immutable, content-addressed map of
  `path → bytes`. `snapshot_id = sha256` over the sorted
  `(path, content_hash)` manifest. Snapshots are values: never mutated,
  only derived. Path discipline REUSES `core.workspace.files.validate_path`
  verbatim (Fix Once: the path contract is generic; the workspace package
  frozen-boundary applies to its STORAGE surface, not to its pure path
  validator).
- **`SourcePatch`** — ordered tuple of closed-set operations
  (`ADD_FILE` / `MODIFY_FILE` / `DELETE_FILE`, full-content semantics —
  deterministic by construction, no fuzzy hunks). Pure function
  `apply_patch(snapshot, patch) -> SourceSnapshot` with named refusals
  (modify/delete of absent path, add of present path). Every patch is
  **invertible**: `invert_patch(patch, base_snapshot) -> SourcePatch` is
  total for an applicable patch — this IS the rollback model (rollback =
  apply the recorded inverse through the same machinery, not a second code
  path).
- **`ChangeProposal`** — frozen record binding
  `{proposal_id, tenant_id, actor_id, base_snapshot_id, patch,
  patch_hash, rationale, created_at}`. `patch_hash = sha256(canonical
  patch serialization + base_snapshot_id)`: the proposal VERSION is
  content-addressed, so any change to the patch or its base produces a
  different version identity. **Approval binds to `patch_hash`** — an
  approval row citing hash X can never authorize content Y (criterion 7).
- **`ProposalState`** — closed lifecycle StrEnum:
  `DRAFT → VERIFIED | FAILED_VERIFICATION`; `VERIFIED → APPROVED |
  REJECTED`; `APPROVED → APPLIED`; `APPLIED → ROLLED_BACK`. Illegal
  transitions are named refusals. Verification failure is a terminal-for-
  promotion state: a `FAILED_VERIFICATION` proposal can never be approved
  (criterion 6 — regression failures block promotion structurally, not by
  convention).
- **`SandboxPort`** (Protocol) — the ONLY execution surface:
  `run_verification(snapshot, suite) -> VerificationReport`. The interface
  exposes **no** method to write outside the given snapshot, no remote/push
  concept, no secret-resolution parameter. Structural incapability: the
  capability is absent from the type, and the composition passes the
  sandbox only synthetic `SecretManagerPort`-shaped material (hermetic
  in-memory binding; real bindings are an activation-gate concern).
- **`DifferentialVerifier`** — runs the SAME closed verification suite on
  the base snapshot and on the patched snapshot inside the sandbox, then
  compares deterministically: promotion evidence =
  `{base_report, patched_report, regressions, improvements, verdict}`.
  A check passing on base and failing on patched is a **regression** and
  forces `FAILED_VERIFICATION`. Determinism is proven the R121 way: verify
  twice, compare canonical JSON.
- **`SourceChangeWorkflow`** — the state machine over a
  `ProposalStorePort` (in-memory binding now, repository binding later —
  same posture as ScenarioService/markers, recorded). Human acts
  (approve/reject/apply/rollback) append `APPROVAL_DECISION` audit rows via
  the EXISTING `AuditLogPort`; the durable proposal records themselves are
  the workflow evidence (criterion 11). **No new audit event types** — the
  closed 20 §9 set stays closed; lifecycle detail rides
  `AuditEvent.details`.

### 2. Apply / activation boundary (§14 — structural)

`SourceChangeWorkflow.apply()` transitions state and produces the
`{applied_snapshot_id, inverse_patch}` evidence **within the proposal
store's snapshot space only**. Writing an applied snapshot to the
AUTHORITATIVE source requires an `AuthoritativeApplierPort` that:

- has **no implementation anywhere in this repository** during V8;
- is an **optional composition seam defaulting to `None`** (absent seam =
  absent capability, 20 §4);
- when absent, the workflow reports `authoritative_apply:
  {available: False, gate: "S14_OPERATOR_GATE"}` honestly (P6).

Activating R3 later = implement + compose that port and (separately,
consciously) revisit `NEVER_REGISTRABLE_CLASSES` — composition changes
only, no redesign (criterion 12).

### 3. Admin surface + agent posture

Human-only admin routes under `/v1/admin/source-changes/*`
(propose / verify / list / get / approve / reject / apply / rollback),
seam-gated like every V7 surface, guard pins updated consciously.
**The agent gains NO R3 tools**: `NEVER_REGISTRABLE_CLASSES` is untouched,
and V8 ships adversarial tests proving (a) an R3-classed tool cannot be
constructed into any registry at any scope, and (b) prompt-injection
content crossing the workflow surfaces is scrubbed
(`apps/admin_agent/secrecy.scrub_object`) and cannot reach an apply act.

### 4. Verification suite (P1 reuse)

The sandbox verification suite reuses the platform's deterministic check
machinery (`core.evaluation.policy.DeterministicCheck` shape and the
closed-check-set discipline proven in V7 chunks 3–4) — zero new grader
frameworks; V8 defines only source-specific checks (e.g. manifest
integrity, patch applicability, suite pass/fail) as data.

## Reason

- **Structural over behavioral**: every operator "MUST remain incapable"
  item maps to an ABSENT capability in a type or composition — the
  registry-construction precedent (AA-2/AA-3) proved this is the only
  posture that survives adversarial pressure.
- **P1/P2 shared-platform-first**: path validation, audit, secrecy
  scrubbing, deterministic checks, ContractModel discipline, and the
  absent-seam pattern are all reused; the only genuinely new abstractions
  (snapshot/patch/proposal/sandbox port) are generic source-change
  primitives usable by any future application, not agent-private
  machinery.
- **Content-addressed approval** is the smallest mechanism that makes
  criterion 7 unfakeable: identity = hash(content), so approval/content
  binding needs no trust in mutable state.
- **Invertible patches** make rollback (criterion 8) a property of the
  patch algebra rather than a second workflow to verify.
- **§14 compliance by construction**: the hermetic build can be complete,
  verified, and honestly reported while the authoritative-apply seam and
  the R3 registry pin keep real activation impossible without a future
  conscious operator-authorized change.

## Consequences

Easier: real activation later is a bounded composition task
(implement `AuthoritativeApplierPort` + real `SandboxPort` binding +
registry-pin decision), each behind its own review; any future app needing
versioned proposed-change workflows inherits the primitives; differential
verification generalizes to config/data changes.

Harder / accepted costs: full-content patch ops are coarser than line
diffs (deterministic > compact — recorded); the hermetic in-memory sandbox
under-approximates a real build environment (V8 claims are therefore
scoped: "hermetic build verified", never "production-verified");
proposal store is in-process until a conscious durable-binding slice.

Migration/rollback of this decision: the package is additive; removing it
touches no existing surface (all V8 seams default to `None`).

## Status

ACCEPTED — operator authorization recorded 2026-08-31 (execution state
R124): hermetic build authorized; **real R3 activation remains gated on
§14 (5 open credential items) and requires a separate explicit operator
decision at the activation boundary**. Takes effect with the V8 chunk
commits on `feature/platform-agent-vision` following this ADR.
