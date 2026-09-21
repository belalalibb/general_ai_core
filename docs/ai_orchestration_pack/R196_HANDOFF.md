# R196 HANDOFF — read-only `/v1/templates` surface + built-in template registry composition (AD-3)

## 1. Status
OPEN (declared 2026-09-20). Base `main f7a127fd`. Branch `r196_templates_read_surface`. Authority: `60_DECISION_LOG.md` R196-DEC-01 (operator "APPROVE R196 with confirmation", D1–D5).

## 2. Scope (ceiling 4 production files)
| Item | File | Purpose |
|---|---|---|
| R196-A | `core/contracts/agent_template.py` | `TemplateListEntry` + `TemplatesListResponse` read models |
| R196-B | `apps/api/app.py` | `create_app(templates=)`; `GET /v1/templates`, `GET /v1/templates/{ref}`; executor consumes the same registry; `templates.listing` capability row |
| R196-C | `apps/composition/runtime.py` | `build_template_registry()` with the ONE built-in `APP_FACTORY_TEMPLATE`; `RuntimeProfile.templates` |
| R196-D | `apps/api/capabilities.py` | `CAPABILITY_IDS` + `templates.listing` (23 → 24) |
| tooling | `engineering/verification/contract_freeze_derive.py`, `contract_freeze_baseline.json` | bind the seam in the hermetic derivation; baseline 44 → 46 routes |

Excluded: write routes, template durability, user/workspace templates (workspace ownership = recorded later direction), App Factory generation (AD-7), UI (R197).

## 3. Consumer view (after merge)
- `GET /v1/templates` (bearer) → `{templates:[{ref:"app_factory.plan@<ver>", id, version, name, origin:"system", status:"active", description, tags, stage_count, stage_keys, skills, required_capabilities}]}`
- `GET /v1/templates/app_factory.plan` or `/app_factory.plan@<ver>` → full `StrategyTemplate` JSON; unknown/inactive/non-system → 404 `validation_error`.
- `POST /v1/execute` with `execution_strategy: {"mode":"template","template_id":"app_factory.plan"}` resolves.

## 4. Evidence (filled at closure)
`evidence/r196/{red_r196.txt, green_r196.txt, regression_<sha>.txt, gate_head_<sha>.txt, gateway_head_<sha>.txt, gate_merge_<sha>.txt, gateway_merge_<sha>.txt, CONTRACT_FREEZE_RECORD_R196_UPDATE.md}`; ledger `evidence/r196_state_ledger.md`.

## 5. Next decision gate
After closure: R197 (UI closure) requires its own proposal + approval. D-03 remains operator-owned and unclaimed.
