# Contract Freeze Record — R192 update

Round: R192 — claim verification (H1–H11) + smallest safe App Factory closure.
Baseline: `main = fde5276d`. Branch: `genspark_ai_developer_r192`.

## 1. Shape impact on the frozen contract set

**NONE.** `contract_freeze_derive.py --check` → `contract freeze baseline: MATCHES current tree` at a11b7088 (after both production edits).

| Touched file | Change | Frozen set touched? |
|---|---|---|
| `core/agent/app_factory.py` (R191 module) | + `BindingInspectorPort` protocol; `AppFactoryCapability(binding_inspector=None)`; `context.binding_id` path | No — R191 module, not in the frozen set; all existing constructor calls remain valid (new kwarg defaults to None) |
| `apps/agent_dev/project_inspector.py` (R191 module) | + `BoundProjectInspector` | No — no route, no contract |

No served route added/removed/reshaped. No existing module outside the two R191 modules touched.

## 2. Authorities reused (none duplicated)

`RepoBindingRegistry.get(binding_id, tenant_id=)` · `RemoteTrustPort.is_trusted` · `SecretManagerPort.resolve` · `GitRefusalCode` / `BindingLookupRefused` · `GitHubProjectInspector` (R191) · `parse_github_remote`. Order and codes mirror `GitToolset._binding/_require_trust/_token` exactly (trust BEFORE credential; registry fault = not trusted; `SecretNotFound` = `credential_unresolved`).

## 3. Operator decisions required (STOP points — nothing below was implemented)

### P-R191-01 — served `/v1/templates` (re-verified: STILL REQUIRED)
- **Re-derivation**: no `/v1/*template*` route exists (`grep '@app\.(get|post)\("/v1/[a-z-]*template' apps/api/app.py` → none); `create_app(strategy_templates=)` is the only seam and composition passes none.
- **Why the existing seam is insufficient**: templates cannot be listed/selected by a UI or operator without a served surface; `TemplateRegistry.list/get/resolve_ref` are exactly the operations, but exposing them is a SHAPE change.
- **Compatibility**: additive route; no existing route changes. **Security/tenancy**: read routes tenant-neutral for system templates; register route needs P-R192-03 first. **Migration**: none. **Tests**: contract tests + freeze re-derive.
- **Decision requested**: YES/NO to a served read-only `/v1/templates` + `/v1/templates/{ref}`.

### P-R192-02 — skill instruction content channel
- **Finding (H3)**: `SkillManifest` (frozen) has no instruction body; `/v1/execute` carries `{id,name,version}` only by recorded decision ("payload never becomes a skill-content channel"). Skills today influence execution via tool disclosure (`skill_tools`) and capability requirements (routing filter) — both deterministic.
- **Options**: (a) keep as-is (skills = manifest + tools + capabilities); (b) NEW optional `SkillManifest.instructions` field = **frozen shape change**; (c) side-car `SkillContentPort` keyed by `id@version`, applied by the prompt composer under firewall-neutral rules = additive but needs an authority statement in 14.
- **Decision requested**: which option; none implemented.

### P-R192-03 — template ownership / durability model
- **Finding (H4)**: `TemplateOrigin` is provenance, not ownership; no tenant/workspace id on `StrategyTemplate`; no store. V3 does not define whether user/workspace templates are tenant-scoped, workspace-scoped (`core/contracts/identity.py:87 Workspace`), or user-scoped.
- **Decision requested**: ownership axis + whether durability is in scope; then an additive `TemplateStorePort` can be specified.

### P-R192-04 — compose the REST Git path into production (dev bindings + GitToolset in the agent catalog)
- **Finding (H6)**: IMPL-024 owner decision keeps `dev_bindings` uncomposed ("production stays inert"); `docs/r172/BACKEND_STATE_OF_TRUTH.md` §E lists it as an open owner item depending on C2 (binding store source) + C3 (remote trust source). `GitToolset` is registered in no agent catalog. Without this, `BoundProjectInspector` (R192) and any future generation/commit/publish stage have no production composition.
- **Smallest proposal**: env-gated composition in `apps/composition/runtime.py` (like `build_engineering`): `RepoBindingRegistry(store=JsonBindingStore(...))` + `RemoteTrustRegistry(...)` + existing `SecretManager` → `create_app(dev_bindings=…)` and `GitToolset` tools appended to the agent catalog; `BoundProjectInspector` bound per request tenant. Additive; no route shape change (`/v1/dev` already exists behind the seam).
- **Decision requested**: YES/NO + the binding-store and trust-store sources.

## 4. Deferred (re-checked, still deferred; not reopened)

1. App Factory generation lifecycle wiring — primitives exist (H7 map); wiring requires P-R192-04; remote test execution in the REST topology has **no primitive** (sandbox runner = new subsystem → STOP).
2. Stage-level resume of a `StrategyReport` — 12 §9 delegates to a durable workflow runtime; per-call idempotency exists and suffices for single-request runs.
3. Strategy-output evaluation — per-stage Executions are already evaluable by id; not required by App Factory now.
4. Composition wiring of built-in templates (R191-C) — depends on P-R191-01 / P-R192-03.
5. Template durability — P-R192-03.

## 5. Backward compatibility

All existing suites unchanged (regression recorded in `evidence/r192_state_ledger.md`). `AppFactoryCapability(inspector=…)` calls without `binding_inspector` behave exactly as in R191 (pinned by `tests/agent/test_r191_app_factory_slice.py` 11/11).
