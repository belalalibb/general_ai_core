# Contract Freeze Record — R196 update (DECLARED additive shape change)

Round: R196 — read-only `/v1/templates` surface + built-in template registry composition (AD-3). Baseline: `main = f7a127fd`. Branch: `r196_templates_read_surface`. Authority: R196-DEC-01 (operator "APPROVE R196 with confirmation", D1 = re-derive in this declared round).

## 1. Shape impact on the frozen set — ADDITIVE, DECLARED, RE-DERIVED

`contract_freeze_derive.py --check` at 95ad78fd → `DRIFT detected` (expected: two new served routes). Baseline re-derived with `--write` at 0564e85b → `MATCHES current tree`.

Diff of `contract_freeze_baseline.json` (before → after), verified programmatically:

| Section | Before | After | Change |
|---|---|---|---|
| `frozen_modules` | 15 | 15 | identical |
| `modules` (contracts per module) | unchanged | unchanged | identical |
| `resource_signal_snapshot` | — | — | identical |
| `served_routes_v1` | 44 | **46** | **+ `GET /v1/templates`, + `GET /v1/templates/{ref}`**; 0 removed |

The R189 rule ("additions are admitted only by re-deriving this baseline in an explicitly declared round") is satisfied: the round was declared in R196-DEC-01 and manifest `round_r196` BEFORE the first production commit, naming the two routes.

`_served_routes()` now binds `templates=TemplateRegistry()` in its hermetic composition so the conditional family is derivable (same posture as the other optional seams bound there).

## 2. Touched production files vs. frozen set
| File | Change | Frozen set touched? |
|---|---|---|
| `core/contracts/agent_template.py` | `TemplateListEntry`, `TemplatesListResponse` | No — module is not frozen (R191 additive module) |
| `apps/api/app.py` | `templates=` seam; 2 GET routes; capability row | Only `served_routes_v1` (+2, declared) |
| `apps/api/capabilities.py` | `CAPABILITY_IDS` +1 (closed set, operator D2) | No (not a frozen contract module; pinned by test 23 → 24) |
| `apps/composition/runtime.py` | `build_template_registry`; `RuntimeProfile.templates` | No |

`ExecutionStrategySpec.template_id` (frozen) is consumed, not changed — template mode now resolves because a registry is composed.

## 3. Proposals / deferred blocks
- **P-R191-01 — served `/v1/templates`: EXECUTED (read-only half).** The "register-user-template" write half is NOT executed (depends on P-R192-03).
- **R191-C — composition wiring of built-in templates: CLOSED** (`build_template_registry()`; proof `tests/composition/test_r196_template_composition.py`).
- **P-R192-03 — template ownership / durability: still OPEN.** Operator direction recorded (AD-3): workspace ownership is the LATER ownership direction; no field, store or write route exists yet.
- All other R189 §6 / R191 §3 / R192 §3–4 deferred blocks: unchanged.
