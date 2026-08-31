# V8 — R3 Source-Change Workflow: Acceptance Evidence + Activation-Boundary STOP Report

```text
STATUS: HERMETIC BUILD COMPLETE — REAL R3 ACTIVATION GATED (§14, OPERATOR)
DATE: 2026-08-31 (R132)
AUTHORITY: ADR-0009 (ACCEPTED — split authorization: hermetic build
           authorized; real activation NOT authorized)
GATES AT WRITING: 2121 passed + 60 skipped hermetic tests; mypy --strict
           clean; ruff clean; import-linter 12 contracts kept / 0 broken
COMMIT LEDGER (all pushed + ls-remote-verified):
           0f012f6 ADR-0009 · 0635ddb snapshots/patches · 09c7fb3
           proposal lifecycle + stores · c989b77 sandbox + differential
           verifier · 47ab975 workflow · 6df3c1c surface helpers ·
           5d2bfb8 admin routes + composition + guard pins · afff574
           HTTP + adversarial suite
```

Every claim below cites executable evidence: a test that fails if the
claim stops being true, or a structural shape that cannot express the
forbidden act. Nothing is asserted on discipline alone (evidence-first,
41 §49 — no fabricated claims).

---

## 1. Acceptance evidence — the operator's 12 criteria

The criteria are quoted verbatim from the R124 authorization record.

### Criterion 1 — "proposed source changes versioned"

Identity IS content. `snapshot_id = sha256` over the sorted
`(path, content_hash)` manifest; `patch_hash` = canonical patch
serialization + base snapshot id; `ChangeProposal.patch_hash` is
**derived at construction, never supplied** — a caller cannot claim a
version it does not have.

| Evidence | Where |
|---|---|
| id is content-derived + order-independent | `tests/sourcechange/test_snapshot_patch_v8.py::test_snapshot_id_is_content_derived_and_order_independent` |
| id changes with content AND with path | `::test_snapshot_id_changes_with_content_and_with_path` |
| tampered bytes cannot keep an id | `::test_snapshot_integrity_verification` |
| stores refuse integrity-failing snapshots on save | `tests/sourcechange/test_proposal_lifecycle_v8.py::test_snapshot_store_refuses_integrity_failure_on_save` |
| patch_hash binds content + base | `test_snapshot_patch_v8.py::test_patch_hash_binds_content_and_base` |
| patch_hash derived, never supplied | `test_proposal_lifecycle_v8.py::test_patch_hash_is_derived_never_supplied` |

### Criterion 2 — "sandbox isolation structural"

The incapability lives in the **type/interface/composition shape**, not
in behavioral checks: `SandboxPort` exposes ONE method
(`run_verification`) whose signature carries **no write, remote, or
secret parameter** (introspection-pinned); `HermeticSandbox.__init__`
takes **nothing** (nothing injectable = nothing reachable); the sandbox
module imports no IO machinery.

| Evidence | Where |
|---|---|
| one-method port, no capability params (signature pin) | `tests/sourcechange/test_sandbox_differential_v8.py::test_sandbox_port_surface_is_one_method_no_capability_params` |
| nothing-injectable constructor | `::test_hermetic_sandbox_constructor_takes_nothing` |
| no IO imports in the module | `::test_sandbox_module_imports_no_io_machinery` |
| pure-value package (no IO capability) | `test_snapshot_patch_v8.py::test_package_is_pure_values_no_io_capability` |
| snapshots structurally immutable (frozen + MappingProxyType) | `::test_snapshot_is_immutable_structurally` |

### Criterion 3 — "sandbox uses synthetic/sanitized state"

Snapshots are self-contained values (`path -> bytes`); the sandbox
receives ONLY the snapshot and the suite — there is no parameter through
which real credentials, stores, or remotes could arrive (see criterion 2
pins). All V8 test content is synthetic; the planted secret
(`gwsecret_v8testonly01`) exists nowhere outside its test and matches
the R4 scrub patterns by design.

### Criterion 4 — "real execution works inside sandbox"

`python_syntax_valid` genuinely **compiles** snapshot code in-sandbox
(`compile()` over every `.py` file) — a broken module really fails.

| Evidence | Where |
|---|---|
| the check really compiles code | `test_sandbox_differential_v8.py::test_python_syntax_check_really_compiles` |
| a broken check = a failing check, never a silent error | `::test_broken_check_is_a_failing_check_not_an_error` |
| regression detected via real compilation over HTTP | `tests/api/test_source_changes_v8.py::TestLifecycleRefusalsOverHttp::test_regression_fails_verification_and_blocks_approval` |

### Criterion 5 — "deterministic differential verification"

The verifier runs the suite over base and patched, and **verifies twice**
— a sandbox that cannot reproduce its own report is refused
(`NonDeterministicVerification`), never half-trusted.

| Evidence | Where |
|---|---|
| canonical-json determinism | `test_sandbox_differential_v8.py::test_verification_is_deterministic_canonical_json` |
| flaky sandbox refused | `::test_nondeterministic_sandbox_is_refused_never_half_trusted` |
| PASS / REGRESSION / FAILED_ON_PATCHED closed verdicts | `::test_differential_pass_when_patched_holds_everything`, `::test_differential_regression_base_pass_patched_fail`, `::test_differential_failed_on_patched_without_regression` |
| end-to-end reproducibility | `::test_differential_is_reproducible_end_to_end` |

### Criterion 6 — "regression failures block promotion"

Structural, not policy: `FAILED_VERIFICATION` has **zero outgoing
transitions** in the closed `PROPOSAL_TRANSITIONS` map — a failed
proposal cannot be approved by any code path, and the failing candidate
snapshot is **never stored** (never becomes addressable content).

| Evidence | Where |
|---|---|
| exhaustive: FAILED never approvable | `test_proposal_lifecycle_v8.py::test_failed_verification_can_never_be_approved_exhaustive` |
| transition map total + closed | `::test_transition_map_is_total_and_closed` |
| failing candidate never stored | `tests/sourcechange/test_workflow_v8.py::test_verify_regression_marks_failed_and_stores_no_candidate` |
| blocked over HTTP (422, named) | `test_source_changes_v8.py::TestLifecycleRefusalsOverHttp::test_regression_fails_verification_and_blocks_approval` |

### Criterion 7 — "approval binds to exact proposal version"

`ChangeProposal.with_approval` refuses any approval whose `cited_hash`
differs from the proposal's derived `patch_hash`
(`ApprovalHashMismatch`, naming both hashes) — one door, one check; the
route and workflow add nothing they could get wrong.

| Evidence | Where |
|---|---|
| exact hash binds | `test_workflow_v8.py::test_approve_with_exact_hash_succeeds_and_binds` |
| forged hash refused, named, persists NOTHING | `::test_approve_with_forged_hash_refused_named_persists_nothing` |
| over HTTP: 422 naming BOTH hashes, store still VERIFIED | `test_source_changes_v8.py::TestLifecycleRefusalsOverHttp::test_forged_hash_approval_is_422_naming_both_hashes` |
| correct hash from wrong state still refused | `test_proposal_lifecycle_v8.py::test_approval_from_draft_is_refused_even_with_correct_hash` |

### Criterion 8 — "rollback real and tested"

Rollback replays the **recorded inverse patch** through the SAME apply
machinery (one code path), and the restored snapshot must equal the base
**by content address** — verified and recorded.

| Evidence | Where |
|---|---|
| invert round-trips every operation kind | `test_snapshot_patch_v8.py::test_invert_round_trip_every_kind` |
| exact prior content restored | `::test_invert_restores_exact_prior_content` |
| rollback restores base by content address | `test_workflow_v8.py::test_rollback_restores_base_by_content_address` |
| rollback-before-apply refused | `::test_rollback_before_apply_is_refused` |
| full lifecycle incl. rollback over HTTP | `test_source_changes_v8.py::TestSourceChangeLifecycleOverHttp::test_full_lifecycle_snapshot_to_rollback` |

### Criterion 9 — "prompt-injection + secret-boundary defenses tested"

Adversarial suite (`tests/api/test_source_changes_v8.py`):

| Attack | Defense proven | Test |
|---|---|---|
| register an R3 tool with a **forcibly widened** admission set | `NEVER_REGISTRABLE_CLASSES` enforced unconditionally at registry construction — no parameter can widen past it | `TestAdversarialAgentBoundary::test_r3_tool_cannot_register_even_with_forced_admission_set` (+ R4 twin) |
| smuggle the workflow onto the agent surface | `AgentToolSurface` has **no field** to hold it — absence by dataclass shape | `::test_agent_tool_surface_has_no_source_change_field` |
| any hidden authoritative applier | zero classes across all loaded `apps.*`/`core.*` modules carry `apply_to_authoritative_source` | `::test_no_authoritative_applier_implementation_exists_in_app_layer` (+ core-level scan in `test_workflow_v8.py`) |
| exfiltrate snapshot bytes through responses | full lifecycle driven; planted secret absent from EVERY response body, raw AND base64 | `TestAdversarialSecretBoundary::test_synthetic_secret_bytes_never_cross_any_response` |
| prompt-injection via rationale text | stored verbatim as DATA on the human-only surface; R4 scrub redacts both markers at the agent boundary (the only surface where text meets a model) | `::test_hostile_rationale_is_data_and_scrub_would_catch_markers` |
| leak bytes through audit evidence | audit rows carry hashes/reports only — json-dump sweep finds no file content | `::test_audit_evidence_carries_no_file_bytes` |

Serialization posture: `proposal_json` carries operation **metadata +
hashes only** (`{kind, path, content_sha256, size_bytes}`, shape-pinned)
— bytes structurally cannot cross the admin surface.

### Criterion 10 — "post-apply verification logic exists"

`apply()` re-runs the suite over the applied snapshot through the SAME
sandbox and stores the full report + `post_apply_passed` in the audit
row — an applied change whose verification cannot be reproduced is a
visible rollback candidate.

| Evidence | Where |
|---|---|
| evidence pair + post-apply row + §14 posture in evidence | `test_workflow_v8.py::test_apply_records_evidence_pair_and_stays_in_store_space` |

### Criterion 11 — "audit evidence durable"

Every lifecycle act appends an `APPROVAL_DECISION` row through the
EXISTING `AuditLogPort` (closed 20 §9 event set untouched); the durable
proposal records themselves are workflow evidence.

| Evidence | Where |
|---|---|
| five-act trail in order, patch_hash on every row | `test_workflow_v8.py::test_every_act_appends_an_approval_decision_row` |
| same trail observed over HTTP | `test_source_changes_v8.py::TestSourceChangeLifecycleOverHttp::test_five_lifecycle_acts_leave_audit_evidence` |
| audit=None seam → workflow still functions (optional honesty seam) | `test_workflow_v8.py::test_workflow_without_audit_seam_still_functions` |

### Criterion 12 — "later activation requires no architectural redesign"

Activation is a **composition act**, proven by the architecture's own
shape:

1. **The seam exists and is typed.** `SourceChangeWorkflow` already
   accepts `authoritative_applier: AuthoritativeApplierPort | None`; the
   `None` default is signature-pinned. Every other port in the workflow
   (`ProposalStorePort`, `SnapshotStorePort`, `SandboxPort`,
   `AuditLogPort`) is a Protocol — swapping in-memory bindings for
   durable ones never touches the workflow (the ADR-0009 recorded
   posture, same as ScenarioService).
2. **Activation = two composition edits, zero workflow edits:**
   implement `AuthoritativeApplierPort` (a new module) and change
   `authoritative_applier=None` to the implementation in `create_app`.
   No route changes, no state-machine changes, no contract changes —
   `authoritative_apply_status()` already answers `{"available": True}`
   for the composed case (currently unreachable, marked as such).
3. **The gate is checkable, not aspirational.** Its absence is a test
   (`test_authoritative_applier_has_no_implementation_in_repo` +
   the app-layer scan), so activation will be a loud, reviewed diff that
   flips a known test expectation — not a silent drift.
4. **Precedent:** the identical pattern already activated once in this
   codebase — the Remote Provider Gateway (ADR-0008) went from absent
   seam to composed adapter without redesign.

**Deliberately NOT built (honest exclusions, 11 §14):** durable
store bindings (in-process now, recorded); process/container-level
sandbox jailing (the hermetic sandbox is structurally IO-free — OS-level
isolation becomes relevant only with real activation and belongs to the
activation work); the applier implementation itself (its existence
before operator authorization would BE the violation).

---

## 2. ACTIVATION-BOUNDARY STOP REPORT (§14 — OPERATOR DECISION REQUIRED)

### FACT

- The R3 Source-Change Workflow **hermetic build is COMPLETE**: 7 chunks,
  8 pushed commits (`0f012f6` → `afff574`), 84 dedicated tests
  (64 core + 20 HTTP/adversarial), full suite 2121 passed + 60 skipped.
- **Sandbox isolation: VERIFIED** (structural — shape-pinned, criterion 2).
- **Differential verification: VERIFIED** (deterministic, verify-twice,
  criterion 5).
- **Approval flow: VERIFIED** (exact-hash-bound, criterion 7; regression
  block structural, criterion 6).
- **Rollback: VERIFIED** (content-address-proven, criterion 8).
- **R3 real activation: GATED / NOT ACTIVATED.** No
  `AuthoritativeApplierPort` implementation exists anywhere in the
  repository (tested at core AND app layer); the composition passes
  `authoritative_applier=None`; the agent registry refuses R3
  unconditionally even under a forcibly widened admission set; every
  HTTP response carries `authoritative_apply: {available: false,
  gate: S14_OPERATOR_GATE}`.
- The §14 gate items remain the **5 open credential items** (R108):
  revoke the R060 temporary PAT; rotate the R058 key; rotate the
  in-chat Groq keys; the two Lane C deployment items.

### IMPACT

- **While gated:** admins have a fully working *rehearsal* surface —
  proposals, differential verification, hash-bound approval, hermetic
  apply, rollback — with every act audited. Nothing can touch
  authoritative source; the worst possible outcome of any misuse is
  noise in an in-memory store.
- **If activated without the gate:** an implemented applier would carry
  R3 authority (writing real source) into a platform whose credential
  hygiene items are still open — exactly the coupling §14 exists to
  prevent. The 5 items are not formalities: unrevoked/unrotated
  credentials widen the blast radius of any R3-adjacent compromise.

### OPTIONS

- **A. Keep the gate (default).** Proceed to V9 (Full Validation → Final
  Documentation → Final Completion Report → STOP). R3 remains a
  verified, dormant capability; activation stays available later as a
  composition act (criterion 12 evidence above).
- **B. Authorize activation.** Operator resolves/acknowledges the 5
  credential items and explicitly authorizes; the work is then: durable
  store bindings decision, `AuthoritativeApplierPort` implementation
  (with its own ADR for the write path + OS-level sandbox isolation
  review), composition change, and flipping the absence tests to
  presence tests — no redesign.
- **C. Partial:** resolve the credential items now, defer activation —
  closes the standing security debt without opening R3.

### RECOMMENDATION

**Option A.** V8's purpose — prove the architecture works and can be
activated later without redesign — is fully achieved and evidence-backed.
Nothing in V9 requires activation. The credential items (Option C's
content) are worth resolving regardless, but they are operator acts, not
build acts.

### OPERATOR DECISION REQUIRED

Reply with one of: **"proceed V9"** (keep gate, continue roadmap) ·
**"activate R3"** (only with the 5 items resolved/acknowledged — this
begins a new ADR, not a code flip) · **"pause"** (state is fully
checkpointed; any future session resumes from the R132 record).
