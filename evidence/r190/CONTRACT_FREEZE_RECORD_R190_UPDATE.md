# Contract Freeze Record — R190 update (P-R189-01 resolved)

**Relation to R189.** `evidence/r189/CONTRACT_FREEZE_RECORD.md` is preserved verbatim as R189 history (its §4 and
§6.10 describe P-R189-01 as RECOMMENDED / not implemented — true at the time). This file records what R190 changed.
The freeze rule (ADDITIVE-ONLY on the derived SHAPE baseline) is unchanged.

## 1. Contract-shape impact: NONE
`engineering/verification/contract_freeze_derive.py --check` → **MATCHES current tree** on the R190 head
(`evidence/r190/static_checks_51bf19e1.txt`). No field, type, default, enum member, route or constant changed; no
alias, no second registry, no new served contract. The baseline file was therefore NOT re-derived (the directive:
"do not manufacture a contract-shape change merely to make the record look active").

## 2. Behavior resolved (BEFORE → AFTER)

| | BEFORE (R189, main c9730d9d) | AFTER (R190) |
|---|---|---|
| Same explicit `model_key_prefix` across two onboarded providers | step 12 constructs a NEW `Model` per key → `DuplicateRegistration` → whole onboarding rolled back → `OnboardingRefused("step-12-register-bindings", "duplicate model key …")` → HTTP 409 | step 12 looks the computed logical key up; if a `Model` exists, the new provider is **bound to that existing Model** (one logical Model, N `ProviderModelBinding`s) → HTTP 201, `registered_model_keys` lists the shared key |
| Modality disagreement on a shared logical key | n/a (never reached) | refused loudly: `step-12-register-bindings`, "logical model modality mismatch for <key>: registered […], provider declares […]" — no provider facts copied into the Model |
| Default prefix (no `model_key_prefix` in the payload) | key `<provider_key>/<name>`; collision refused | **unchanged** — collision still refused with full rollback (`test_default_prefix_collision_is_still_refused_and_rolled_back`, `test_j_old_payload_shape_without_prefix_is_unchanged`) |
| Rollback scope on a failed step 12 | removes every key registered in this call (all were created here) | removes the bindings created here and ONLY the Models created here; a pre-existing shared Model and other providers' bindings are never touched (`test_e_failed_second_onboarding_leaves_existing_state_intact`) |
| Durable write-through | provider + every model + every binding | provider + **created** Models only + every new binding (`TestDurabilityOfTheSharedModel`) |
| Gateway hydration on restart with a shared Model | would raise `DuplicateRegistration` on the second binding's `models.register` | Model row registered once (`get_by_id` before `register`); binding-without-model corruption stays loud (`test_shared_model_hydrates_once_with_two_bindings`) |

## 3. Frozen-set table deltas (rows of R189 §2 whose "Known limitations" / "Deferred dependencies" changed)

| # | Module | R189 text | R190 text |
|---|---|---|---|
| 2 | `core.contracts.domain` | limitations: "duplicate key refused at onboarding step 12"; deferred: P-R189-01 | limitations: "explicit-prefix reuse requires an identical modality set (else refused)"; deferred: — (P-R189-01 IMPLEMENTED + VERIFIED). `Model` identity = `key` string, unchanged, no aliases. |
| 15 | `apps.api.provider_onboarding` | limitations: "shared prefix across providers refused (409 step-12)"; deferred: P-R189-01 | limitations: "shared prefix binds to the existing Model; modality mismatch → 409"; deferred: — |

All other rows unchanged. The router (row 3/4), execution and resource-signal contracts (row 14) were **not modified**
— the directive's F/G/H/I requirements were VERIFIED on the unchanged code paths
(`tests/providers/test_r190_logical_model_identity.py::TestRoutingOverTheSharedModel`).

## 4. Status separation
- **APPROVED:** P-R189-01 = YES (R190 directive).
- **IMPLEMENTED:** `core/providers/onboarding.py` (+60/-22), `apps/composition/provider_onboarding.py` (+6/-1) — `round_r190` 2/2.
- **VERIFIED:** RED 6 failed at 8ff3e78c → GREEN 9/9; BEFORE pins fail on the new tree (`before_pins_now_fail_7a846a46.txt`) and were inverted; focused regression 2390/13/0; mypy/ruff clean; freeze `--check` MATCHES; gate of record + gateway (see ledger rows 8–9).
- **RECOMMENDED (not implemented):** none new.
- **DEFERRED / NOT IN SCOPE:** see §5.

## 5. NO SILENT LOSS — R190 discoveries

### 5.1 Tenant ownership of logical Models — NOT IN SCOPE (observation, no rule invented)
- **REMAINING:** nothing to implement now. `Model` / `Provider` registries are platform-global; the onboarding route is admin-only (`caller.is_admin`). Model reuse therefore adds no path by which one tenant attaches to another tenant's Model, because Models are not tenant-owned today.
- **WHY:** the directive requires recording rather than inventing an ownership rule; none exists and none is needed for the current registry model.
- **DEPENDENCIES:** would become material only if tenant-owned Models/Providers are introduced.
- **EXACT NEXT STEPS:** if that happens → PROPOSAL (ownership check at step 12 before reuse) in a declared round.
- **VERIFICATION REQUIRED:** admin/security regression stayed GREEN this round (`tests/admin tests/security` in `regression_focused_51bf19e1.txt`).
- **RECOMMENDATION:** none until the dependency exists.

### 5.2 Modality-mismatch relaxation — DEFERRED (conservative refusal chosen)
- **REMAINING:** policy for a provider that serves the same logical Model with a different modality set.
- **WHY:** `Model.modalities` drives routing eligibility; silently reusing would misroute; silently widening would copy provider facts into the Model (forbidden by the directive).
- **DEPENDENCIES:** operator decision whether the logical Model's modality set is the intersection, the first declarer's, or per-binding (the latter needs an additive binding field → declared round).
- **EXACT NEXT STEPS:** decision record → RED → implement.
- **VERIFICATION REQUIRED:** routing eligibility tests per modality.
- **RECOMMENDATION:** keep the loud refusal; revisit only when a real provider hits it.

### 5.3 Admin REGISTER_MODEL rollback on a shared Model — NOT IN SCOPE (behavior unchanged, recorded)
- **REMAINING:** `AdminConfigService` REGISTER_MODEL rollback removes the Model after removing the bindings listed in the change payload; a Model shared with an onboarded provider outside that payload is not a case the admin path constructs today.
- **WHY:** admin paths do not create Models from onboarding; no observed defect; R190 froze `core/admin/*`.
- **DEPENDENCIES:** an admin flow that registers a Model already bound by onboarding.
- **EXACT NEXT STEPS:** if such a flow is added → guard that rollback refuses while foreign bindings exist.
- **VERIFICATION REQUIRED:** admin regression (GREEN this round).
- **RECOMMENDATION:** record only.

### 5.4 Items explicitly NOT reopened (unchanged from R189)
modality_limits DEFERRED · admin_fallback_chain DEFERRED · account pool/lease/fencing OPTIONAL in v1 · D-03 NOT EVALUATED
(`not_evaluated` = 1, unchanged) · P-R188-03 NO · P-R188-04 NO · training consumer / feedback intake / strategy-output
evaluation DEFERRED · App Factory OUT OF SCOPE · F-CS1-04 operator-owned.
