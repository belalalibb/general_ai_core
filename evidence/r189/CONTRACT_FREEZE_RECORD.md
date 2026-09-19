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

---

## 3. Required dispositions (repository truth; directive expectations checked against the tree)

### Disposition A — `modality_limits`
- **Where it exists:** `core/contracts/plan.py:PlanLimits.modality_limits: JsonObject` (declared; per-modality caps such
  as `image_generations`); carried through `core/admin/service.py` (plan read/write, :292, :829-835, :953).
- **Where it is consumed on the execute path:** NOWHERE. Reservation is scalar — `core/usage/estimation.py`
  (`estimated_units`) and `core/usage/memory.py` (`task_units_limit`). No filter, no refusal, no accounting keyed by
  modality.
- **Disposition:** **FROZEN AS-IS (shape only) — VERIFIED as declared-but-unenforced.** The field stays in the frozen
  `PlanLimits` shape because the admin surface already serves it; its *semantics* are NOT frozen and NOT claimed.
  Anyone reading the plan must treat `modality_limits` as advisory metadata until a declared round adds a consumer.
  Recorded as DEFERRED (§6.1). Nothing was implemented for it in R189.

### Disposition B — `admin_fallback_chain`
- **Where it exists:** `SimpleScoringRouter(admin_fallback_chain: tuple[str, ...] | None = None)`
  (`core/routing/router.py:117,125`); `FallbackScope.ADMIN_DEFINED_CHAIN` resolves to `FallbackNotConfigured` when the
  chain is absent (`router.py:495-499`).
- **Producer:** the ONLY caller that passes a chain is a test (`tests/routing/test_router_scoring.py:557`).
  Composition (`apps/composition/runtime.py`) never passes one; no admin surface stores or serves an ordered chain.
- **Disposition:** **FROZEN AS-IS — the scope value and the loud refusal are the contract; the source is DEFERRED.**
  `FallbackScope.ADMIN_DEFINED_CHAIN` remains a legal, guarded enum member whose served behaviour on main is
  `FallbackNotConfigured` (explicit, not silent). Recorded as DEFERRED (§6.2). Nothing was implemented for it in R189.

### Disposition C — Account pool / lease / fencing = OPTIONAL in v1
- **Spec citations (repository):** `docs/ai_orchestration_pack/final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md`
  §10.1 "Account Pool Is Optional" (line 440); §10.4 "If a provider uses account pools, concurrent execution must use
  leases" (lines 512-514) — the lease/fencing obligation is CONDITIONAL on a provider opting into pools.
- **Contract defaults (repository):** `core/contracts/provider.py:77-86 ManifestAccountPool(supported: bool [required],
  lease_required: bool = False, fencing_required: bool = False)`. Runtime-profile providers declare
  `supports_account_pool=False` (`apps/composition/runtime.py:594,689`).
- **Consumers:** `core/routing/resources.py ResourceSelector`, `core/providers/accounts.py AccountPool/AccountPoolManager`
  exist and are hermetically tested; no composition call site (`grep -rn ResourceSelector apps/` → none); no producer of
  `RateLimitStatus`.
- **Disposition (restated as frozen policy):** **OPTIONAL IN V1 — VERIFIED against spec + contract + composition.**
  Consequences:
  1. A provider manifest with `account_pool.supported=false` is complete; the Core must not require pools, leases or
     fencing from it (it does not — `supports_account_pool=False` is the served default profile).
  2. `lease_required` / `fencing_required` are provider-declared obligations; a provider that sets them true and is
     executed concurrently WITHOUT a lease path is a v1 limitation of the composition, not a Core defect, and must be
     recorded when such a provider is onboarded (none exists on main).
  3. The account-pool code path is NOT part of the served surface today and is NOT frozen as behaviour — only the
     manifest shape (`ManifestAccountPool`) is frozen.
  4. **D-03 (credential unavailable) stays NOT EVALUATED and SEPARATE** — it is a credential-rotation dependency
     (F-CS1-04, operator-owned), not an account-pool question. `green_manifest.json.not_evaluated` is unchanged (1 item).
  Recorded as DEFERRED (§6.3, §6.4).

---

## 4. Operator decisions carried out (APPROVED → IMPLEMENTED / VERIFIED / recorded)

### P-R188-01 — YES (additive `model_key_prefix` on the existing onboarding request)
- **APPROVED:** operator YES (R189 directive). **IMPLEMENTED:** `apps/api/provider_onboarding.py` (+9/-0, commit
  9b2ce91e; `round_r189.log` item `P-R188-01`, 1 of ceiling 2). `GatewayOnboardRequest.model_key_prefix: str | None =
  Field(default=None, min_length=1, max_length=512)`; route passes `model_key_prefix=body.model_key_prefix` into the
  EXISTING `ProviderOnboardingService.onboard(model_key_prefix=…)` (`core/providers/onboarding.py:167`). Hydration
  re-validates the persisted definition with the SAME request model (`apps/composition/provider_onboarding.py:253`), so
  no second production file was needed.
- **VERIFIED:** RED at f83d0ca3 (4 failed, `extra_forbidden` 422 — `evidence/r189/red_p_r188_01.txt`) → GREEN 40/40
  (`green_p_r188_01.txt`): served OpenAPI schema declares the field as optional; old payload (field absent) → stored key
  `gw_alpha/cand-1`, persisted `model_key_prefix is None` (identical to pre-R189 behaviour); payload with prefix
  `"shared"` → `shared/cand-1`, prefix persisted; explicit provider+model routing unchanged.
- **Repository disagreement recorded (THE REPOSITORY WINS):** the directive's motivating expectation — "same model,
  different provider" for onboarded providers via a shared prefix — does NOT hold on the tree: onboarding step 12
  registers a NEW `Model` per key and refuses a duplicate key with full rollback
  (`OnboardingRefused("step-12-register-bindings", "duplicate model key …")` → HTTP 409; pinned by
  `TestPrefixAndRoutingOnCurrentTree::test_same_prefix_second_provider_is_refused_and_rolled_back`). The field is
  therefore a correct, additive, served input whose cross-provider use case needs a further decision:
  **PROPOSAL P-R189-01 (RECOMMENDED, not implemented):** at step 12, when a `Model` with the computed key already exists
  AND the caller supplied an explicit `model_key_prefix`, bind the new provider to the EXISTING model instead of
  refusing (additive behaviour; keeps `Model.key` as the identity; no aliases). Alternatives: (b) `Model.aliases`
  (contract change — refused after freeze without a declared round); (c) keep refusing (status quo). Requires operator
  YES/NO before any code.

### P-R188-03 — NO (async execution strategy)
- **APPROVED (NO):** `execution_strategy` stays sync-only; `POST /v1/execute` with `execution_strategy` + async mode is
  refused loudly with 422 "execution_strategy runs synchronously in this slice." (`apps/api/app.py:884-889`).
- **Continuation recorded (not scheduled):** a worker-side `StrategyExecutor` invocation becomes possible once the
  outbox/worker payload carries the resolved `ExecutionStrategySpec` (today the worker path resolves a single routing
  decision). See §6.5.

### P-R188-04 — NO (durable / shared resource signals)
- **APPROVED (NO):** `ResourceSignalBoard` remains process-local (`core/routing/capacity.py`; ONE instance wired at
  `apps/composition/runtime.py:767`).
- **Dependency recorded:** shared/durable signals are needed ONLY when multiple independent replicas serve
  `/v1/execute` concurrently against the same providers; a single replica is fully served by the in-process board.
  See §6.6.

---

## 5. What this round did NOT do (boundary statement)
- No new served contract (44 `/v1/` routes before and after; the only served change is one OPTIONAL body field on an
  EXISTING route — additive, backward-compatible, proven by the old-payload test).
- No provider calls; no App Factory work; no UI change; no change under `infrastructure/`; `core/` untouched
  (`git diff origin/main -- core/ infrastructure/` is empty).
- Nothing hand-listed: the baseline and the served-route set are derived.

---

## 6. NO SILENT LOSS — deferred items (6-field blocks)

### 6.1 Modality limits enforcement
- **REMAINING:** an execute-path consumer of `PlanLimits.modality_limits` (per-modality reservation/refusal).
- **WHY:** reservation is a single scalar (`task_units`); adding per-modality accounting changes `core/usage/*`
  behaviour and the usage ledger shape — outside R189's stabilization scope and would touch frozen `core.contracts.usage`.
- **DEPENDENCIES:** decision on the unit model (per-modality units vs. per-modality counters beside `task_units`);
  additive `UsageLedger` fields under the freeze rule; declared round.
- **EXACT NEXT STEPS:** (1) decision record choosing the unit model; (2) RED test: plan with `modality_limits.image_generations=0`
  → image request refused with an explicit `ErrorCode`; (3) implement in `core/usage/*` + `apps/api/app.py` under a declared ceiling.
- **VERIFICATION REQUIRED:** RED→GREEN focused tests; freeze guard shows only ADDED lines; gate of record.
- **RECOMMENDATION:** schedule after the freeze round closes; keep field advisory until then.

### 6.2 Admin fallback source (`admin_fallback_chain`)
- **REMAINING:** a producer (admin-stored ordered chain) and its composition wiring into `SimpleScoringRouter`.
- **WHY:** no served admin write path stores a chain; adding one is a NEW served contract (forbidden this round).
- **DEPENDENCIES:** admin config schema for the chain (additive field on the existing routing config), persistence,
  the router already accepts the tuple.
- **EXACT NEXT STEPS:** (1) decision record; (2) RED test: `/v1/admin/routing` accepts `fallback_chain` and
  `ADMIN_DEFINED_CHAIN` no longer raises `FallbackNotConfigured`; (3) wire in `apps/composition/runtime.py`.
- **VERIFICATION REQUIRED:** router tests + admin API pins; freeze guard ADDED-only.
- **RECOMMENDATION:** low priority — same-model fallback is the default safety path (R188).

### 6.3 D-03 — credential unavailable (NOT EVALUATED, separate)
- **REMAINING:** live-credential evaluation of the provider path listed in `green_manifest.json.not_evaluated`.
- **WHY:** credential is unavailable (F-CS1-04 credential rotation is operator-owned); ZERO provider calls this round.
- **DEPENDENCIES:** operator supplies a rotated credential out-of-band.
- **EXACT NEXT STEPS:** operator rotation → run the D-03 check → move the item from `not_evaluated` with evidence.
- **VERIFICATION REQUIRED:** the D-03 evidence file + manifest update in a records PR.
- **RECOMMENDATION:** keep NOT EVALUATED; do not conflate with account-pool policy (Disposition C).

### 6.4 Account pool lease / fencing consumer
- **REMAINING:** composition wiring of `ResourceSelector`/`AccountPoolManager` and a `RateLimitStatus` producer.
- **WHY:** optional in v1 (30 §10.1); no onboarded provider declares `account_pool.supported=true`.
- **DEPENDENCIES:** a real provider that needs pools; lease store; declared round.
- **EXACT NEXT STEPS:** only when such a provider is onboarded: decision record → RED (concurrent execution without
  lease refused when `lease_required`) → wire.
- **VERIFICATION REQUIRED:** hermetic lease tests + gate.
- **RECOMMENDATION:** do nothing until a pooled provider exists.

### 6.5 Async execution strategy (P-R188-03 NO)
- **REMAINING:** running `ExecutionStrategySpec` on the worker/outbox path.
- **WHY:** operator NO; today's refusal is explicit (422).
- **DEPENDENCIES:** outbox payload carries the resolved spec; worker invokes `StrategyExecutor`; report persistence per stage.
- **EXACT NEXT STEPS:** decision record → RED (async + strategy accepted, report has one node per stage) → implement.
- **VERIFICATION REQUIRED:** worker tests, `GET /v1/executions/{id}` unchanged shape, gate.
- **RECOMMENDATION:** after freeze; additive only (no new route).

### 6.6 Durable / shared resource signals (P-R188-04 NO)
- **REMAINING:** a shared `ResourceSignalPort` implementation (e.g. Redis/DB) behind the existing port.
- **WHY:** operator NO; single replica is fully served by the in-process board.
- **DEPENDENCIES:** multiple independent replicas serving `/v1/execute` concurrently; a durable store in composition.
- **EXACT NEXT STEPS:** when replicas > 1: decision record → port-conformance tests for the new implementation → wire.
- **VERIFICATION REQUIRED:** port conformance + snapshot vocabulary guard unchanged.
- **RECOMMENDATION:** none needed until deployment topology changes.

### 6.7 Training consumer
- **REMAINING:** any consumer of GOLD/admitted `LearningSample`s for training.
- **WHY:** absent by design (R188 B); no training pipeline exists in this repository.
- **DEPENDENCIES:** external training system; export contract (additive).
- **EXACT NEXT STEPS:** decision record defining the export shape → RED → implement export only.
- **VERIFICATION REQUIRED:** gates (`TRAINING_ELIGIBILITY_CONDITIONS`) unchanged; export tests.
- **RECOMMENDATION:** defer until a consumer exists.

### 6.8 Feedback intake
- **REMAINING:** any served path that accepts end-user feedback.
- **WHY:** 41 §20 excludes feedback from gates structurally (`test_learning_gates_carry_no_feedback_input`); intake without
  a gate consumer would be a new served contract with no verified use.
- **DEPENDENCIES:** decision on where feedback may influence (evaluation only, never training gates).
- **EXACT NEXT STEPS:** decision record → additive route → guard that gates still carry no feedback input.
- **VERIFICATION REQUIRED:** the existing gate guard stays GREEN; new route pinned.
- **RECOMMENDATION:** defer.

### 6.9 Strategy-output evaluation
- **REMAINING:** evaluation records for multi-stage (`execution_strategy`) outputs beyond the single-report grader.
- **WHY:** R188 C-items delivered execution; evaluation of per-stage outputs was not in scope.
- **DEPENDENCIES:** `EvaluationRecord` additive fields (stage key); grader selection per `StageKind`.
- **EXACT NEXT STEPS:** decision record → RED (review stage produces an `EvaluationRecord` tagged with stage) → implement.
- **VERIFICATION REQUIRED:** evaluation tests; freeze guard ADDED-only.
- **RECOMMENDATION:** after freeze.

### 6.10 P-R189-01 — model identity across providers (RECOMMENDED)
- **REMAINING:** operator decision; then step-12 behaviour change (bind to existing `Model` when explicit prefix supplied).
- **WHY:** repository refuses duplicate keys today; changing that silently would violate the freeze rule.
- **DEPENDENCIES:** operator YES/NO; declared round with ceiling ≥ 1 (`core/providers/onboarding.py`).
- **EXACT NEXT STEPS:** YES → RED (`test_same_prefix_second_provider_is_refused_and_rolled_back` inverted to expect a
  second binding on the same model) → implement → GREEN; NO → keep the pin.
- **VERIFICATION REQUIRED:** routing test proving same-model-different-provider fallback for onboarded providers.
- **RECOMMENDATION:** YES (option a), smallest additive change that fulfils the R188 intent.

---

## 7. Evidence index (R189)
`evidence/r189/red_p_r188_01.txt` · `green_p_r188_01.txt` · `red_freeze_guard_absent.txt` · `green_freeze_guard.txt` ·
`red_freeze_guard_mutation.txt` · `green_freeze_guard_after_revert.txt` · `regression_focused_14eb41bf.txt` (1929 passed /
9 skipped / 0 failed) · `static_checks_14eb41bf.txt` (mypy 218 files clean; ruff clean; touched files formatted) ·
gate of record + gateway files added at the gate step · `evidence/r189_state_ledger.md` · `evidence/r188/audit_routing_a99e2545.md`.
