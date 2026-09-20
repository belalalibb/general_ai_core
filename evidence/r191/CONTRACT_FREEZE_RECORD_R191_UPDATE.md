# Contract Freeze Record — R191 update

Round: R191 — General Agent + extensible Skills/Strategy/Template foundation + App Factory foundation (first vertical slice).
Baseline: `main = dc1c62de`. Branch: `genspark_ai_developer_r191`.

## 1. Shape impact on the frozen contract set

**NONE.**

`engineering/verification/contract_freeze_derive.py --check` → `contract freeze baseline: MATCHES current tree` (run at e0306dd9, after all five production files).

Why nothing moved:

| New module | Kind | Frozen set touched? |
|---|---|---|
| `core/contracts/agent_template.py` | NEW contract module (StrategyTemplate, TemplateOverride, OverrideRecord, AgentPlan) | No — not in the frozen set; imports frozen types read-only |
| `core/execution/templates.py` | NEW registry + `apply_override` | No — produces the EXISTING `ExecutionStrategySpec`, consumed by the EXISTING `StrategyExecutor(templates=Mapping)` seam |
| `core/agent/general.py` | NEW GeneralAgent + AgentCapabilityRegistry | No — uses `StrategyExecutor.resolve/execute`, `SkillRegistry.list_selectable` unchanged |
| `core/agent/app_factory.py` | NEW capability + DATA template + records | No |
| `apps/agent_dev/project_inspector.py` | NEW read-only inspector | No served route; no contract |

No served route was added, removed or reshaped. `/v1/execute` template mode, skills admission, and the R188 seams are byte-identical.

## 2. PROPOSAL P-R191-01 — served template routes (NOT executed)

- **What**: a served `/v1/templates` (list / get / register-user-template) route so UI and operators can inspect and select templates without code.
- **Why not now**: adding a served route changes the contract SHAPE (freeze rule: "if SHAPE change needed → STOP, record PROPOSAL"). R191 stays additive inside Core.
- **Where the seam already is**: `TemplateRegistry.list/get/resolve_ref/materialize` are the exact operations the route would expose; `apps/api/app.py create_app(strategy_templates=...)` already accepts a template mapping.
- **Trigger**: operator approval of a shape change in a later round.
- **Owner**: next round that owns `apps/api`.
- **Proof plan when executed**: contract tests under `tests/contract`, freeze re-derive, RED-first.

## 3. Deferred items (recorded, not reopened here)

Each block: item / why deferred / seam that exists / trigger / owner / proof plan.

1. **Template durability (persisting user/workspace templates)**
   - Why: R191 proves templates are DATA (JSON round-trip proven); a store is a separate capability with its own tenancy rules.
   - Seam: `StrategyTemplate.model_dump_json()` / `model_validate`; `TemplateRegistry.register` is the single write path.
   - Trigger: first product need for cross-restart templates.
   - Owner: persistence-owning round.
   - Proof: RED test that a dumped template re-registers equal; tenancy isolation test.

2. **UI template CRUD / selection surface**
   - Why: needs P-R191-01 first; UI must never contain workflow logic — it will only call the served route.
   - Seam: P-R191-01.
   - Trigger: P-R191-01 executed.
   - Owner: UI round after P-R191-01.
   - Proof: Playwright slice selecting a template by ref and observing `template_ref` in the plan.

3. **App Factory generation stage(s)**
   - Why: directive — the first slice ends at the application plan; `ApplicationPlan.generation_deferred` is `Literal[True]`.
   - Seam: a NEW data template (e.g. `app_factory.generate@1`) consuming `ApplicationPlan`; GitHub write path already exists in `GitHubRestTransport` (R172) with tool approval + protected-branch handling.
   - Trigger: operator directive for R192+.
   - Owner: the round that receives that directive.
   - Proof: RED-first, MockTransport only, approval gate proven before any write verb.

4. **Composition wiring of built-in templates (R191-C headroom — NOT used)**
   - Why: `apps/composition/runtime.py create_app(...)` does not pass `strategy_templates`; wiring `APP_FACTORY_TEMPLATE` in without a served route or a consumer would be dead code, and no RED test in R191 drives it. Budget 5/6 used; the 6th slot stays unused rather than spent unexercised.
   - Seam: `apps/api/app.py:483 create_app(strategy_templates=...)` and `TemplateRegistry.as_strategy_mapping()`.
   - Trigger: P-R191-01 or the first `/v1/execute` template-mode consumer in composition.
   - Owner: composition-owning round.
   - Proof: composition test asserting `/v1/execute` `mode="template", template_id="app_factory.plan"` resolves.

5. **Evaluation of strategy outputs (per-stage scoring / rubric)**
   - Why: out of R191 scope; the Evaluation subsystem exists and remains platform authority (`GeneralAgent.PLATFORM_AUTHORITY`).
   - Seam: `StrategyReport.outcomes[*].report` carries per-stage `ExecutionReport`s.
   - Trigger: first rubric requirement.
   - Owner: evaluation-owning round.
   - Proof: RED test scoring a `StrategyReport` without touching the executor.

6. **Token-free inspector binding in composition (credential source)**
   - Why: `GitHubProjectInspector.bind(token_source)` exists; which credential store feeds `token_source` is a composition/security decision (20 §5) not taken in R191.
   - Seam: `bind()` + `RepoBinding.credential_ref`.
   - Trigger: first hosted App Factory planning request.
   - Owner: security/composition round.
   - Proof: test that the token never appears in inventory/plan/exception text (already proven at unit level in `test_r191_app_factory_slice.py`).

## 4. Backward compatibility statement

- Every existing test suite passes unchanged (regression run recorded in `evidence/r191_state_ledger.md`).
- No existing signature changed; no default changed; no existing module modified under `core/` or `apps/` in this round (5 new files only — `git diff --numstat dc1c62de HEAD -- core apps` shows additions only).
