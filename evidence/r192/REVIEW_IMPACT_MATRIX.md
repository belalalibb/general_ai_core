# R192 — Review / Impact Matrix (claim verification BEFORE any production write)

Baseline verified: `main = fde5276d` (PR #41 merge), clean tree, open PRs 0, `.git/config` token count 0.
Records read: `PROJECT_EXECUTION_STATE.md` R191 pointer (line 707), `R191_HANDOFF.md` §7, `evidence/r191_state_ledger.md` rows 1–15, `evidence/r191/CONTRACT_FREEZE_RECORD_R191_UPDATE.md`.
Authorities read (V3): 12 (Execution Graph / Agent Mode — §2 strategies, §9 durable runtime, §10 idempotency, §11 approval gates, §13 per-node policy), 14 (Skills/Tools §1–3), 20 (Security §8 approvals, §9 audit), 40 (Engineering §2.8, §4.2–4.7), 60 (IMPL-018..025 R172), plus code: `core/agent/runtime.py`, `core/execution/strategy.py`, `core/tools/gate.py`, `core/execution/agent.py`, `apps/api/app.py` (:483–:1600), `apps/composition/{runtime,agent,engineering}.py`, `apps/agent_dev/{git_tools,github_transport,surface,http,project_inspector}.py`, `core/engineering/tools.py`, `core/agent/{general,app_factory}.py`, `core/execution/templates.py`.

Verdict vocabulary: CONFIRMED · PARTIALLY_CONFIRMED · FALSE · INTENTIONALLY_DEFERRED · OPERATOR_DECISION_REQUIRED.

---

## H1 — GeneralAgent vs actual runtime

**CLAIM.** GeneralAgent is a planning abstraction not on any production execution entrypoint.
**EVIDENCE.** `grep -rn "GeneralAgent|TemplateRegistry|AppFactoryCapability|GitHubProjectInspector" core apps` → consumers **only inside the four R191 modules themselves**; zero references in `apps/api`, `apps/composition`, `apps/admin_agent`. `POST /v1/execute` dispatch (`apps/api/app.py:1385–1470`): `agent_strategy` → `agent.runtime.run(...)` (AgentRuntime, tool-capable); `strategy_spec` → `strategy_executor.execute(...)` (StrategyExecutor, model-only stages); `multi_model_policy` → `multi_model_executor`. `AgentRuntime` instantiated in `apps/composition/agent.py:218` (`build_agent`, consumed at `runtime.py:948`) and `apps/admin_agent/service.py:187`. `StrategyExecutor` instantiated once at `app.py:621`. `/v1/execute` refuses `execution_strategy` + `strategy=agent` together (`:892`).
**VERDICT.** **CONFIRMED** — and the separation is *intentional* by V3 12 §2 (strategies `pipeline/review_judge/...` vs `agent` are distinct strategies of ONE graph), not accidental. GeneralAgent is a **library layer** that composes the two existing authorities; it is not (yet) served. That is exactly the R191 declaration ("no served route; P-R191-01 proposal").
**IMPACT.** No duplicate runtime exists. The relationship is implicit only in docstrings; it is not pinned by a test that GeneralAgent never bypasses the two dispatch authorities.
**AUTHORITY TO REUSE.** `StrategyExecutor` (model stages) + `AgentRuntime` (tool loop) + `/v1/execute` dispatch.
**MINIMAL SAFE ACTION.** Records + one guard test making the layering explicit: GeneralAgent has no router/execution/tool references of its own (imports pin). No production change.
**CONTRACT.** NONE. **SECURITY/TENANCY/PERSISTENCE.** None. **TESTS.** `tests/agent/test_r192_layering_guard.py` (static import/attribute pins). **ORDER.** 1 (records/guards only).

## H2 — StrategyExecutor vs tool-capable AgentRuntime

**CLAIM.** Two complementary engines; App Factory generation may need the tool-capable one; a "missing engine" is suspected.
**EVIDENCE.** `core/execution/strategy.py:14` "every stage is ONE `ExecutionService.execute_single` call"; `grep tool core/execution/strategy.py` → **no tool concept**; `StageKind ∈ {generate, review, retest}` (`execution_strategy.py:51–53`) — all model calls. `AgentRuntime.run(tenant_id, user_id, task, tools: Sequence[AgentToolSpec], model_policy, max_steps, deadline_ms, ...)` (`runtime.py:349`) drives `AgentLoop` with `ToolCallGate(tools, firewall, devices)` → `ToolExecutor`; every reasoning call is `router.route → execution_service.execute_single`. So: generation of files / running tests / git operations are TOOL actions → owned by AgentRuntime + firewall chain; drafting/reviewing text → StrategyExecutor stages.
**VERDICT.** **CONFIRMED** (two authorities, each complete for its class). "Missing engine" → **FALSE**: AgentRuntime + engineering tools (`core/engineering/tools.py`: workspace.read/write/exec, git.read/write) + `GitToolset` (fetch/status/commit/publish) already express model→tool→observe→verify with approval gates.
**IMPACT.** App Factory generation must be expressed as: (a) StrategyExecutor stages for plan/review (exists, R191), (b) an AgentRuntime run with an admitted engineering tool subset for generation/test/fix (exists), never a third engine.
**AUTHORITY TO REUSE.** AgentRuntime, ToolCallGate, ToolExecutor, CapabilityFirewall, EngineeringBundle, GitToolset.
**MINIMAL SAFE ACTION.** None in Core. Record the ownership map (this matrix + freeze record). **CONTRACT.** NONE. **ORDER.** — (no implementation).

## H3 — Skill semantics

**CLAIM.** Admission is proven; actual skill-instruction application at runtime may not be.
**EVIDENCE.** `SkillManifest` (`core/contracts/skills.py:115–135`) = id/name/version/type/source/status/capabilities/inputs_schema/outputs_format/requires_tools/permissions_requested/runtime. **There is no instruction body/content field in the frozen Skill contract.** `/v1/execute` rides admitted skills as `payload["skills"] = [{id,name,version}]` (`app.py:1284–1288`) with the recorded decision: "the payload never becomes a skill-content channel"; skill tools are disclosed as DATA via `payload["skill_tools"]` (`:1289`) and, in agent strategy, `agent.select(body.tools, admitted_skill_objects)` (`:1052`) resolves skill `requires_tools` into the admitted `AgentToolSpec` subset — permissions still decided by the firewall. V3 14 §1: "Skill = instruction/workflow/capability module"; §2 manifest shows no content field; 14 §3 lifecycle enforced by `SkillRegistry.list_selectable` (ACTIVE+LOCAL). R191 `GeneralAgent.plan` mirrors this exactly (`payload["skills"]`, `required_capabilities` union).
**VERDICT.** **PARTIALLY_CONFIRMED**: identity/version/tool-requirement/capability flow is proven and applied (tool selection + routing filter); **instruction content is NOT modelled by the frozen contract at all** — so "not applied" is not a defect of R191 but the recorded posture of 14 §2 + IMPL decision at `app.py:1284`. Adding a content channel = **frozen contract shape change** (SkillManifest is in the frozen set) → OPERATOR_DECISION_REQUIRED, not to be done here.
**IMPACT.** App Factory can legitimately rely on skills for tool disclosure and capability requirements only. **Skill content can never grant permissions** (firewall decides; `ToolCallGate` step 5 tightening) — already true.
**MINIMAL SAFE ACTION.** None. Record PROPOSAL **P-R192-02** (skill instruction body as a NEW optional manifest field or side-car registry) for operator decision; do not implement.
**CONTRACT.** FROZEN SHAPE CHANGE if pursued → STOP. **ORDER.** — (proposal only).

## H4 — Template control plane

**CLAIM.** In-memory, versioned, no ownership/durability; P-R191-01 may or may not still be required.
**EVIDENCE.** `StrategyTemplate{id, version, name, origin: TemplateOrigin, status, description, strategy(custom), skills, required_capabilities, tags, metadata}`; `TemplateRegistry` is a plain object with a dict; `grep tenant core/execution/templates.py core/contracts/agent_template.py` → **none**; `grep strategy_templates apps/composition` → **none** (only `create_app(strategy_templates=...)` at `app.py:483/622`); no served `/v1/*template*` route; no template store/port anywhere. `origin` is provenance (system/imported/user/workspace), **not** ownership — confirmed by absence of any tenant/workspace id on the record.
**VERDICT.** **CONFIRMED** (in-memory, process-lifetime, origin≠ownership, not served). P-R191-01 **still required** for any UI/operator template selection; it is a SHAPE change (served route) → **OPERATOR_DECISION_REQUIRED**. Durability/ownership: **INTENTIONALLY_DEFERRED** (R191 freeze record §3.1) and still genuinely absent — no existing template store to reuse; a workspace-scoped store would need `Workspace` (`core/contracts/identity.py:87`) + a `TemplateStorePort` (additive) but ownership semantics (tenant vs workspace vs user) are **undefined** in V3 → STOP condition.
**MINIMAL SAFE ACTION.** None in production. Keep P-R191-01 open; add **P-R192-03** (template ownership model) as a decision request. **CONTRACT.** FROZEN SHAPE CHANGE (route) / undefined semantics → STOP. **ORDER.** — .

## H5 — Project inspection

**CLAIM.** Read access is safe but production credential binding is incomplete.
**EVIDENCE.** `GitHubProjectInspector.inspect(remote_url, branch, *, token)`: token only in `Authorization` header of the per-call `httpx.AsyncClient`; instance stores base_url/transport/timeout/max_paths only (`__repr__` credential-free); `bind(token_source: Callable[[], str])` yields a token-free port. **No tenant identity, no `RemoteTrustPort` check, no `RepoBinding`, no `SecretManagerPort`** in the inspector; `grep tenant|is_trusted apps/agent_dev/project_inspector.py core/agent/app_factory.py` → none. Contrast: `GitToolset._require_trust` runs BEFORE `_token` which resolves via `SecretManagerPort.resolve(tenant_id, credential_ref)` (`git_tools.py:381–407`). Nothing composes the inspector (H1 evidence). Read-only by construction: two GETs, no write verb.
**VERDICT.** **CONFIRMED.** The inspector is a transport primitive; the *governed* path (tenant → RepoBinding → remote trust → credential_ref → SecretManager → token) exists in `GitToolset` and is **not** applied to the inspector.
**IMPACT.** If the inspector were composed with an ad-hoc `token_source`, it would bypass the remote-trust and credential-ref authorities. This is a genuine, additive-closable gap.
**AUTHORITY TO REUSE.** `RepoBinding`, `RepoBindingRegistry.get(binding_id, tenant_id=…)`, `RemoteTrustPort.is_trusted`, `SecretManagerPort.resolve`, `parse_github_remote`.
**MINIMAL SAFE ACTION.** Additive adaptor in `apps/agent_dev/project_inspector.py`: `BoundProjectInspector(inspector, *, tenant_id, bindings, trust, secrets)` implementing `ProjectInspectorPort` by **binding id** (`inspect_binding(binding_id)`): registry lookup (tenant-scoped, same typed refusal), trust check BEFORE credential resolve, `secrets.resolve(tenant_id, binding.credential_ref)` at the last moment, then `inspect(binding.remote_url, binding.branch, token=…)`; token never stored. Plus core-side: `AppFactoryCapability` accepts `context.binding_id` and resolves through the port (the port signature stays token-free). 
**CONTRACT.** ADDITIVE (new adaptor; `ProjectInspectorPort` gains an optional binding-based method — R191 module, not frozen). **SECURITY.** Positive: closes trust/credential bypass. **TENANCY.** Enforced via registry lookup. **PERSISTENCE.** None. **TESTS.** RED-first `tests/agent_dev/test_r192_bound_inspector.py`: untrusted remote → refused BEFORE `secrets.resolve` and BEFORE any HTTP; foreign-tenant binding → refused; missing credential → typed refusal without token; happy path → inventory, token absent from all outputs; MockTransport only. **ORDER.** 2.

## H6 — Generation / engineering bridge

**CLAIM.** Remote inspection and Git write tooling exist but the bridge remote→workspace→tools→tests→git is incomplete.
**EVIDENCE.** Two supported topologies exist today: **(T1) local workspace** — `apps/composition/engineering.py:build_engineering(env)` (opt-in via `ENV_WORKSPACE_ROOT`, jailed `WorkspaceFs`, `CommandPolicy` allowlist, `SubprocessCommandRunner`, `GitCli`, `AuthorizationLedger`) → `engineering_tool_specs` → AgentRuntime tools (`workspace.read/write/exec`, `git.read/write`; writes gated by `grant_engineering_writes` admin decision). **(T2) REST-only remote** — `GitToolset` (fetch/status/commit/publish with BEFORE_ACTION approval on commit/publish, `RepoBinding.allowed_modes`, protected-branch handling, remote trust, credential_ref) over `GitHubRestTransport` (in-memory content-addressed staging, no local `.git`), served read-only via `/v1/dev` **only when `create_app(dev_bindings=…)`** — and `apps/composition/runtime.py` passes **no** `dev_bindings` (IMPL-024 owner decision: "production stays inert"; `docs/r172/BACKEND_STATE_OF_TRUTH.md` §E lists "inject dev_bindings in runtime.py (depends on C2 + C3)" as an **open owner item**). `GitToolset` is not registered in the AgentRuntime tool catalog either (`grep GitToolset( apps core` → none outside tests).
**VERDICT.** **CONFIRMED** — the bridge is incomplete **by recorded owner decision (IMPL-024)**, not by oversight. Wiring `dev_bindings`/`GitToolset` into the production composition is an **owner decision** with prerequisites (binding store C2 + remote trust C3 sources) → **OPERATOR_DECISION_REQUIRED**. Neither topology should be assumed; T2 is the one aligned with R172 §2 (no subprocess in the write path) for *external* repositories; T1 is for the operator's own workspace.
**MINIMAL SAFE ACTION.** None in production this round. Record **P-R192-04**: compose `RepoBindingRegistry` + `RemoteTrustPort` + `SecretManagerPort` in `runtime.py` (env-gated like `build_engineering`), register `GitToolset` tools in the agent catalog behind the same gate. **CONTRACT.** ADDITIVE if approved (new composition seam; no route shape change — `/v1/dev` already exists behind the seam). **ORDER.** — (proposal).

## H7 — App Factory generation lifecycle

**CLAIM.** `ApplicationPlan` exists; the generation lifecycle is not wired.
**EVIDENCE + OWNERSHIP MAP** (from H2/H6):
| Stage | Owner primitive | Class |
|---|---|---|
| inventory | `GitHubProjectInspector` (+H5 bound adaptor) | read-only tool / deterministic |
| architecture | StrategyExecutor stage (`app_factory.plan@1` exists) | model |
| generation (files) | AgentRuntime + `workspace.write` (T1) **or** `GitHubRestTransport.commit` staging via `GitToolset.commit` (T2) | approval-gated tool (BEFORE_ACTION on `git.commit`; T1 write under admin-granted permission) |
| test | AgentRuntime + `workspace.exec` under `CommandPolicy` (T1 only; T2 has **no remote test runner**) | tool / deterministic |
| review | StrategyExecutor `review` stage (exists) | model |
| fix / retest | AgentRuntime loop reassess (bounded by max_steps/max_repeated_failures) + `retest` stage kind (exists) | tool + model |
| verification | `evidence_verifier` in AgentRuntime (exists) | deterministic |
| approval | `ToolCallGate` BEFORE_ACTION + IMPL-023 payload binding (exists) | deterministic |
| commit | `GitToolset.commit` (T2) / `git.write` (T1) | approval-gated tool |
| publish | `GitToolset.publish` (modes, protected-branch) | approval-gated tool |
**VERDICT.** **CONFIRMED** that lifecycle is not wired; **FALSE** that primitives are missing — every stage has an existing owner except *remote test execution in T2* (no primitive; would need a sandbox runner — new subsystem → STOP). No lifecycle *record* type exists beyond `ExecutionReport`/`AgentRunReport` (persisted via `store_report`) — 12 §9 says "do not build an ad-hoc workflow engine inside Core; rely on a durable workflow runtime", which does not exist in the repo → defining a multi-stage lifecycle record now would be a new subsystem.
**MINIMAL SAFE ACTION.** None beyond H5. Record the ownership map. **ORDER.** — .

## H8 — Failure / retry / resume / idempotency

**EVIDENCE.** `ExecutionService.execute_single(idempotency_key=…)` (`service.py:302–496`); StrategyExecutor derives `request_hash:{stage.key}` and `idempotency_key:{stage.key}` per stage (`strategy.py:211–214`); `/v1/execute` idempotency index `(tenant_id, idempotency_key) → execution_id` (`app.py:1381`); outbox at-least-once with consumer dedup (`core/runtime/outbox.py` header); `claim_stale` in `core/runtime/memory.py:73`; Git write idempotency: `GitHubRestTransport.commit` is content-addressed staging keyed by binding id; publish moves a ref — repeated publish of the same commit is a no-op ref update at GitHub; approval replay protected by IMPL-023 payload hash. **No stage-level resume** of a StrategyReport (all-or-nothing per request) — consistent with 12 §9 delegating durability to an external runtime.
**VERDICT.** **PARTIALLY_CONFIRMED**: per-call idempotency and at-least-once posture exist and are sufficient for single-request generation runs; cross-request *resume from completed stages* does not exist and must not be invented (12 §9). **INTENTIONALLY_DEFERRED** to a durable workflow runtime. **ACTION.** None. **ORDER.** — .

## H9 — Model / provider flexibility (preservation check)

**EVIDENCE.** `grep -i "openai|anthropic|gpt|claude|gemini|provider_id=\"" core/agent/*.py core/execution/templates.py apps/agent_dev/project_inspector.py` → **none**. All model choice flows through `NodeModelPolicy` on stages / `TemplateOverride` / request policy; routing through the one `SimpleScoringRouter` and one `ExecutionService`; R191 tests G/I/J re-prove same-model fallback + explicit provider+model through the agent; R190/R188 suites in the gate.
**VERDICT.** **CONFIRMED preserved**; nothing hardcoded. **ACTION.** Re-run R188/R190/R191 suites in regression (Step 9). **ORDER.** 9.

## H10 — Security / tenancy / approval

**EVIDENCE.** Chain: `_principal` → tenant → `CapabilityFirewall.decide` (permission/entitlement/scope/`approval_gated_permissions`) → `ToolCallGate` step 5 tool `approval_policy` tightening (`gate.py:145–158`: BEFORE_ACTION unmet unless `approval_state == "approved"`) → `ToolExecutor` → audit `TOOL_CALL`. `approval_state` is `Literal["approved"] | None` on `AgentToolBinding` (`execution/agent.py:150`); `AgentToolSpec.binding()` never sets it (so AgentRuntime tool calls can never self-approve — approval-gated tools are REFUSED in the loop); only the dev surface passes it from the caller with IMPL-023 payload binding. Secrets: opaque `credential_ref` everywhere; `SecretManagerPort.resolve` last-moment in `GitToolset`. 
**VERDICT.** **CONFIRMED intact**; the R191 inspector gap (H5) is the only place where a new path would sit outside this chain — closed by H5's action, which places trust-check before secret resolve and never lets the token into Core state. **ACTION.** H5 tests assert token absence in inventory/plan/exception text and trust-before-resolve ordering. **ORDER.** 2.

## H11 — Evaluation / verification / learning

**EVIDENCE.** `EvaluationPolicy.evaluate` / `judge(tenant_id, execution_id, output)` operate on an `Execution` id + output (`core/evaluation/policy.py:153–263`); StrategyExecutor stages are ordinary Executions (each `execute_single`) so each stage output is already evaluable by id; `StrategyReport`-level scoring does not exist (R188/R191 deferred "strategy-output evaluation"). Learning eligibility (`core/learning/gates.py`) consumes execution/evaluation records, not App Factory artefacts.
**VERDICT.** **CONFIRMED** existing intake covers per-stage executions; strategy-level evaluation **INTENTIONALLY_DEFERRED** and **not required** by App Factory now (the plan is reviewed by a `review` stage, itself an evaluable Execution). **ACTION.** None. **ORDER.** — .

---

## Proven gaps requiring implementation this round

| # | Gap | Action | Contract |
|---|---|---|---|
| G1 (H5/H10) | Project inspection has no governed path: tenant → RepoBinding → remote trust → credential_ref → SecretManager | Additive `BoundProjectInspector` in `apps/agent_dev/project_inspector.py` + `AppFactoryCapability` accepting `context.binding_id` via the token-free port | ADDITIVE |
| G2 (H1) | Layering (GeneralAgent composes; never owns router/execution/tools) is not pinned | Guard test only | NONE |

Everything else: already solved, intentionally deferred, or **operator decision** (P-R191-01 served templates; P-R192-02 skill instruction body; P-R192-03 template ownership; P-R192-04 compose dev bindings/GitToolset). Production ceiling for R192: **2 files** (`apps/agent_dev/project_inspector.py`, `core/agent/app_factory.py`) — declared here BEFORE the first production commit; STOP at 3.
