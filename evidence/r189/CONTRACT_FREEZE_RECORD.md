# QEVION — Contract Freeze Record (R189)

**Round:** R189 · Contract Freeze Preparation (stabilization + disposition; NOT feature development).
**Authority:** operator directive "QEVION — R189 EXECUTION DIRECTIVE · Contract Freeze Preparation"; declared in
`docs/ai_orchestration_pack/final_docs_v3/60_DECISION_LOG.md` R189-DEC-01 BEFORE any code; closed by R189-DEC-02.
**Governing rule (verbatim anchors):** "Freeze what measurement has actually stabilized" · "Nothing may be declared
stable merely because a class, schema, comment, mock, fixture, or document exists" · "Where this directive and the
repository disagree: THE REPOSITORY WINS. Record the disagreement" · "NO NEW SERVED CONTRACT THIS ROUND".

**Status vocabulary used in this record (kept separate, never merged):**
- **RECOMMENDED** — proposed by engineering; no operator decision yet.
- **APPROVED** — operator decision recorded (P-R188-01 YES; P-R188-03 NO; P-R188-04 NO).
- **IMPLEMENTED** — code exists on the branch and is counted in `round_r189.log`.
- **VERIFIED** — proven by a test or a measured gate on the tree (RED → GREEN, or gate of record).
- **DEFERRED** — explicitly NOT done; carries a 6-field NO SILENT LOSS block (§6).

---

## 1. What "frozen" means here (compatibility rule)

A frozen contract is a module whose *derived* shape (`engineering/verification/contract_freeze_baseline.json`) must
not change except **additively**:

| Allowed after freeze (ADDITIVE-ONLY) | Refused after freeze (guard FAILS) |
|---|---|
| add an OPTIONAL field with a default; add an enum member at the END; add a new contract class; add a new `/v1/` route | remove/rename a field, class, enum member, route; change a field's type/required-ness/default/alias; change `extra`/`frozen` model config; change a frozen constant's value; reorder enum members |

Any refused change requires a **declared round** (decision record + manifest `round_rNNN` + updated baseline via
`contract_freeze_derive.py --write --round=rNNN` in the SAME PR that declares it). Re-deriving the baseline without a
declared round is itself the unauthorized change the guard exists to catch (the baseline carries `frozen_at.round`).

**Derivation, not roster.** The baseline is produced by `engineering/verification/contract_freeze_derive.py`
(pydantic field introspection, enum members, dataclass fields, exception classes, discriminated unions, listed constants,
the live `ResourceSignalBoard.snapshot()` vocabulary, and the served `/v1/` surface read from `app.openapi()["paths"]`
of a hermetically composed app with the admin seam bound). `--check` exits 1 on drift; two `--write` runs are
byte-identical (VERIFIED, ledger row 8). No provider/model names are hand-listed (guard
`test_baseline_is_derived_not_hand_maintained` rejects roster words).

**Guard name:** "Contract Freeze Baseline guard" — `tests/verification/test_contract_freeze_baseline.py`
(distinct from the pre-existing "Port Conformance" tests). Runs inside `check_repo.sh` slice `rest` (tests/verification).

**Guard proof (VERIFIED):** RED with baseline absent (`evidence/r189/red_freeze_guard_absent.txt`) → GREEN 6/6
(`green_freeze_guard.txt`) → deliberate unauthorized mutation (rename `ExecuteRequest.requirements` → `requirement_set`)
→ FAIL with `ADDED … requirement_set` / `REMOVED … requirements` (`red_freeze_guard_mutation.txt`) → revert
(`git diff core/` empty) → PASS 6/6 (`green_freeze_guard_after_revert.txt`).

---

## 2. Frozen set (measured on `main 9831c81b` + branch; 15 modules · 116 contracts · 44 served `/v1/` routes)

Status for every row: **IMPLEMENTED + VERIFIED** (exists on main, exercised by the R188 gate of record 3758/0/0/64 and
the R189 gate of record, and now pinned by the guard). "Served surface" = the `/v1/` path(s) that expose the module's
shapes, taken from the derived `served_routes_v1`.

| # | Frozen module | Role | Served surface | Compatibility rule | Guard | Extension rule | Known limitations | Deferred dependencies |
|---|---|---|---|---|---|---|---|---|
| 1 | `core.contracts.provider` (23) | Provider manifest / discovery / health shapes (`ProviderManifest`, `ManifestAccountPool`, `DiscoveredModel`, `ProviderHealth*`, …) | `POST /v1/providers/onboard`, `/v1/admin/providers*` | additive-only (§1) | freeze guard | new manifest keys OPTIONAL with defaults | `ManifestAccountPool.supported` is REQUIRED (repo fact); lease/fencing default False | account pool lease/fencing consumer (Disposition C) |
| 2 | `core.contracts.domain` (19) | Registry entities (`Provider`, `Model`, `ProviderModelBinding`, `Credential`, statuses) | `/v1/models`, `/v1/admin/*` | additive-only | freeze guard | new optional fields only; `Model` identity = `key` string (no aliases) | onboarded key `<prefix>/<name>`; duplicate key refused at onboarding step 12 | P-R189-01 (model identity across providers) |
| 3 | `core.contracts.routing` (7) | `RoutingRequest` / `RoutingDecision` / `ExclusionRecord` / `CandidateScore` / `ScoringWeights` / `TaskAnalysis` | `POST /v1/execute` (decision embedded in report) | additive-only | freeze guard | new exclusion reasons appended | admin-defined chain has no producer (Disposition B) | admin fallback source |
| 4 | `core.contracts.model_policy` (11) | `ModelPolicy` discriminated union (`AutoModelPolicy`, `ExplicitModelPolicy`, `ExplicitModelsPolicy`, `AgentPolicy`, …), `FallbackScope`, `SelectionStrategy` | `POST /v1/execute` | additive-only; union members may be ADDED, never removed | freeze guard (unions recorded) | new policy = new union member with new discriminator value | `ExplicitModelPolicy.provider_id` carries the provider **key** string (repo fact) | — |
| 5 | `core.contracts.execute` (25) | `ExecuteRequest` (incl. R188 `requirements`, `execution_strategy`), sync/async responses, stream events, `ExecutionReport`, `EvaluationReport`, `ExecutionPolicy` | `POST /v1/execute`, `POST /v1/execute/stream`, `GET /v1/executions/{execution_id}` | additive-only | freeze guard (mutation proof used THIS module) | new optional request fields with defaults | `execution_strategy` sync-only (422 on async, `apps/api/app.py:889`) | async strategy (P-R188-03 NO) |
| 6 | `core.contracts.execution` (5) | Persisted `Execution` / `ExecutionNode` / statuses / `ExecutionStrategy` enum | `GET /v1/executions/{execution_id}` | additive-only; enum members append-only | freeze guard | — | — | — |
| 7 | `core.contracts.execution_strategy` (4) | `ExecutionStrategySpec` / `StrategyStage` / `StageKind` + `MAX_STAGES`, `MAX_PARALLEL` constants | `POST /v1/execute` | additive-only; constants frozen by value | freeze guard (constants) | new `StageKind` appended | bounded stage count; sync-only | async strategy; strategy-output evaluation |
| 8 | `core.contracts.model_listing` (2) | `ModelListEntry` (incl. R188 `providers`), `ModelsListResponse` | `GET /v1/models` | additive-only | freeze guard | new optional columns | — | — |
| 9 | `core.contracts.usage` (4) | `UsageLedger` / `UsageSummary` / `TaskUnitBudget` / status | `GET /v1/usage`, `/v1/admin/usage*` | additive-only | freeze guard | — | reservation is a scalar `task_units` (no per-modality units) | modality limits enforcement (Disposition A) |
| 10 | `core.contracts.learning` (3) | `LearningSample` / `LearningEligibility` / `SanitizationState` | internal (learning lifecycle; no direct `/v1/` write surface) | additive-only | freeze guard | — | no training consumer | training consumer; feedback intake |
| 11 | `core.contracts.evaluation` (5) | `EvaluationRecord` / `GraderResult` / `GraderType` / `VerificationLevel` + `VERIFICATION_LEVEL_ORDER` | `/v1/admin/evaluations*` | additive-only; order constant frozen | freeze guard (constant) | new grader types appended | — | strategy-output evaluation |
| 12 | `core.contracts.errors` (3) | `ErrorEnvelope` / `ErrorDetail` / `ErrorCode` | every `/v1/` error response | additive-only; `ErrorCode` append-only | freeze guard | new codes appended | — | — |
| 13 | `core.learning.gates` (2 + 2 constants) | `TrainingEligibilityGate` / `PromotionGate` signal shapes; `TRAINING_ELIGIBILITY_CONDITIONS`, `PROMOTION_CONDITIONS` | internal | conditions frozen by value | freeze guard + `test_learning_gates_carry_no_feedback_input` | new condition = declared round | feedback structurally excluded (41 §20) | feedback intake |
| 14 | `core.routing.capacity` (1 + 3 constants) | `Eligibility` + `DEFAULT_COOLDOWN_MS`, `DEFAULT_UNAVAILABLE_MS`, `RPM_WINDOW_SECONDS`; snapshot vocabulary (keys `cooldown_until,last_category,model_id,provider_id,reason,rpm_limit,rpm_used,state`; states `available,unavailable,cooldown,limited`) | `GET /v1/admin/system` (board read-model) | vocabulary closed (`test_resource_signal_vocabulary_is_closed`) | freeze guard | new snapshot key = declared round | process-local board (single replica) | durable/shared signals (P-R188-04 NO) |
| 15 | `apps.api.provider_onboarding` (2) | `GatewayOnboardRequest` (extra=forbid; incl. R189 `model_key_prefix`), `ProviderOnboardingSurface` | `POST /v1/providers/onboard` | additive-only; `extra=forbid` frozen | freeze guard + `tests/api/test_r189_onboarding_model_key_prefix.py` | new optional body fields with defaults | shared prefix across providers refused (409 step-12) | P-R189-01 |

**Served surface frozen as a set:** the 44 `/v1/` `{path, methods}` pairs in `served_routes_v1` (derived from OpenAPI).
Guard `test_served_surface_contains_the_execute_read_paths` additionally pins the four load-bearing paths
(`POST /v1/execute`, `GET /v1/executions/{execution_id}`, `GET /v1/models`, `GET /v1/usage`).

**NOT frozen (deliberately):** `core/execution/*` implementations, `core/routing/router.py` internals (scoring), adapters,
composition, `apps/admin_agent/*` (its own R185 freeze), `ui/*` (R185 freeze), gateway-service. Behaviour there is
protected by the regression gate, not by shape pinning.
