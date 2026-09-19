# R188 Provider / Model / Routing audit — tree `a99e2545` (carried into the repository in R189)

**Status of this artifact.** RECORD (audit; not a decision). Created in R189 under R189-DEC-01
("disagreement recorded": the R189 directive cites `evidence/r188/audit_routing_a99e2545.md`, but R188 kept
the audit only inside the R188-DEC-01 discovery table in `docs/ai_orchestration_pack/final_docs_v3/60_DECISION_LOG.md`).
This file carries that table into `evidence/` verbatim in substance, and adds a re-verification column read on the
current `main` (`9831c81b`, R188 closed).

**Tree identity.**
- `a99e2545` = CS1-certified `main` (merge of PR #30, R186 closure) — the LAST tree whose `core/ apps/ infrastructure/`
  content the R188 discovery audited. R187 (`cc6c3537`) touched `ui/` only:
  `git diff a99e2545 cc6c3537 -- core apps infrastructure` → empty (27 files / +1726 −26, all outside the counted roots).
  Therefore "audited at a99e2545" and "audited at cc6c3537 (R188 baseline)" describe the same production tree.
- R188 closed on `7cc1c6bc` (PR #34) + `9831c81b` (PR #35, records only). Every "what is open" row below is
  re-read on `9831c81b` and marked CLOSED IN R188 / STILL OPEN / DEFERRED.

**Method.** Read on the tree, not from history (grep/ripgrep for consumers; a fact is "proven" only when a caller
exists outside tests). No provider call, no App Factory work.

## Audit table (R188-DEC-01 discovery, re-verified on main 9831c81b)

| Area | What existed at a99e2545 (proven consumer) | What was open at a99e2545 | Re-verification on main 9831c81b |
|---|---|---|---|
| Router | `core/routing/router.py` `SimpleScoringRouter` — AUTO / TIER / EXPLICIT_MODEL, hard filters (capabilities, modalities, context, binding availability, explicit provider narrowing by `provider_key`), default fallback scope `same_model_different_provider` (`router.py:483`), widening scopes for explicit models. Consumers: `/v1/execute`, worker, agent runtime, multi-model executor, admin agent. | Docstring recorded the "rate-limit budget" filter as NOT implemented; no runtime signal (health / rate-limit / cooldown) reached the router — every call routed over static binding availability. | **CLOSED IN R188 (A1/A2):** `SimpleScoringRouter(signals: ResourceSignalPort | None)` (`router.py:118,127`); ineligible candidates excluded with an explainable record; `NoEligibleCandidates` carries earliest `retry_after_ms`. Board is process-local (`core/routing/capacity.py ResourceSignalBoard`) — durable/shared signals DEFERRED (P-R188-04 NO; needs multiple independent replicas). |
| Execution | `core/execution/service.py` walks `[selected, *fallback_candidates]`, bounded retry, Retry-After honoured ≤ 60 s, request-indicting categories never fail over, per-account credential refs (R168 D-03). | Outcomes (rate_limited + retry_after, provider_unavailable, quota) recorded in attempts but NEVER fed back to shared state — next request re-sent to the known-exhausted candidate. | **CLOSED IN R188 (A3):** `ExecutionService(signals=…)` sink (`service.py:256,284,543`) reports every attempt outcome; ONE board wired in composition (`apps/composition/runtime.py:767 ResourceSignalBoard()`). |
| Resource selector / accounts | `core/routing/resources.py ResourceSelector.complete()` + `core/providers/accounts.py AccountPool / AccountPoolManager` accept `rate_limits: dict[UUID, RateLimitStatus]`; hermetic 2-account failover proven in tests. | No composition call site; no producer of `RateLimitStatus`. Runtime-profile providers declare `supports_account_pool=False` (`apps/composition/runtime.py:594,689`), so the Core does NOT force account mechanics. | **STILL OPEN — by design (Disposition C, R189):** account pool / lease / fencing are OPTIONAL in v1 (30 §10.1 "Account Pool Is Optional"; 30 §10.4 lease requirement applies only IF a provider uses pools; `ManifestAccountPool.lease_required/fencing_required` default False). No composition consumer of `ResourceSelector` on main (`grep -rn ResourceSelector apps/` → none). Not a defect. D-03 (credential) stays NOT EVALUATED, separate. |
| Health | `aggregate_provider_health` (`core/providers/registry.py:348`) + `ProviderHealth`/`ProviderHealthState` contracts; adapters implement `health_check`. | Health is an onboarding/admin read, not a routing input. | **UNCHANGED (recorded, not a defect):** health remains an admin/onboarding read. Routing eligibility now uses runtime OUTCOME signals (board), not health polls. |
| Model identity | Onboarded models keyed `"<provider_key>/<name>"` (`core/providers/onboarding.py:274`, prefix default = provider key); env-bound Groq/Genspark models keyed by bare name (`apps/composition/runtime.py:450 _model`). | A model onboarded through two providers gets two DIFFERENT keys, so same-model-different-provider cannot exist for onboarded providers unless `model_key_prefix` is passed (service supported it; API did not expose it). → P-R188-01. | **PARTIALLY CLOSED IN R189 (P-R188-01 YES):** `GatewayOnboardRequest.model_key_prefix` additive on the API (`apps/api/provider_onboarding.py`), threaded to `onboard(model_key_prefix=…)`. **Repository fact discovered:** step 12 registers a NEW `Model` per key and REFUSES a duplicate key with full rollback (`OnboardingRefused("step-12-register-bindings", …)` → 409), so a shared prefix across two providers is refused today. Same-model-different-provider for onboarded providers therefore needs a further decision (PROPOSAL P-R189-01, not implemented). |
| Multi-model / graph | `MultiModelExecutor` (`core/execution/multi_model.py:148`; fallback_chain, parallel_compare with judge), `AgentNodeMappingPolicy` → straight node sequence, `ExecutionGraphSpec` + `GraphPlanner` (`core/execution/graph_planner.py:48`; spec layer, no executor). | No caller-defined stage composition beyond straight sequence; no per-stage parallel groups; no review/retest semantics; AUTO strategy = `StrategyPlanner` (`core/routing/planner.py:46`) mapping only `needs_agent → agent`. | **CLOSED IN R188 (C1–C3):** `core/contracts/execution_strategy.py ExecutionStrategySpec` + `core/execution/strategy.py StrategyExecutor` (`:130`), additive `ExecuteRequest.execution_strategy`, sync path only. Async strategy DEFERRED (P-R188-03 NO). |
| Learning | `LearningLifecycleService` (`core/learning/lifecycle.py:273`), `TrainingEligibilityGate` / `PromotionGate` (`core/learning/gates.py:99,142`; feedback structurally excluded per 41 §20), sanitizer, durable custody/storage policies (R178). | Gate-before-answer on execute path, tenant isolation of GOLD retrieval, poisoned-input regression — to be verified by focused tests. Training consumer absent by design. | **VERIFIED IN R188 (B):** focused pins GREEN (`evidence/r188/green_b_learning.txt` 8/8). Training consumer, feedback intake, strategy-output evaluation remain DEFERRED with 6-field blocks in `evidence/r189/CONTRACT_FREEZE_RECORD.md`. |

## Boundaries observed
- ONE router (`SimpleScoringRouter`), ONE execution service, ONE registry set — no second router was created in R188 or R189.
- Nothing in this audit is "declared stable because it exists": the R189 freeze baseline
  (`engineering/verification/contract_freeze_baseline.json`) is DERIVED by introspection of the modules above, and the
  served surface is read from `app.openapi()`.

## Provenance
- Source table: `60_DECISION_LOG.md` § R188-DEC-01 "Discovery (read on the current tree, not from history)".
- Re-verification performed 2026-09-19 on `main 9831c81b` (R189, branch `genspark_ai_developer_r189`).
