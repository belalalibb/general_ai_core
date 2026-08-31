# Internal Agent Self-Sufficiency — Final Handoff Record

Date: 2026-08-31 · Branch: `feature/post-v9-durability-runtime`
Baseline: db7f02e (P-D complete) + 032c856 (/admin in runtime) + this handoff's fixes.
Review method: adversarial ("prove it is NOT ready") → live exercises against a
real model (genspark_llm via GSK_API_KEY) over the WIRED runtime — then the
smallest set of fixes, each pinned hermetically.

---

## 1. Current platform baseline

One modular monolith, one composition root (`apps/composition/runtime.py::build_runtime_profile`),
two profiles (in-memory / durable via DATABASE_URL), all capabilities injected:

runtime · persistence (P-A) · identity (register/verify/login, both profiles) ·
context (13 §5 composer) · execution (sync + async outbox→relay→worker) ·
models/providers/routing · usage/budgets · audit · admin config lifecycle ·
capabilities/exercise (V7) · scenarios/regression (V7) · context lab ·
learning observability · self-review · source-change workflow (V8, R3 gated) ·
skills (registry + import pipeline) · workspace files (core, ports-clean) ·
admin console `/admin` + agent `/v1/agent/*` (in runtime since 032c856) ·
end-user UI `/app` (P-D) · notifications · webhooks/events.

## 2. The Internal Agent (what it actually is)

`apps/admin_agent/`: a conversation loop whose reasoning call goes through the
platform's OWN execute path (stored, labeled, billed — no side-channel LLM).
Model output is parsed as a JSON proposal; tool calls dispatch through a
deterministic dispatcher over a **closed registry of 24 tools** (R0 read /
R1 test-execute / R2 config-change ONLY — R3/R4 structurally unregistrable).
Claims are admitted only with evidence refs that this turn's tool results
actually surfaced. `trace`/`diagnosis` are deterministic post-hoc readers.

Registry (24): list_models, list_providers, list_executions, read_execution,
usage_summary, read_audit, run_test_execution, save_scenario, list_scenarios,
replay_scenario, run_regression_pack, list_capabilities, list_exercisable,
exercise_capability, list_lab_checks, validate_context, self_review,
changes_since_review, mark_reviewed, draft_change, validate_change,
preview_change, propose_change, list_changes.

## 3. Actual exercises (live, real model, wired runtime)

| # | Workflow | Result |
|---|----------|--------|
| E1 | Natural-language ask → run_test_execution + list_executions | PASS (after GAP-1) — both tools dispatched, execution real+settled |
| E2 | Two-turn: act, then read_execution + evidence-cited claim | PASS — claim ADMITTED with `{"kind":"execution","ref":<id>}`; invented-evidence path still refuses (E1 showed 2 claims refused when refs missing) |
| E3 | Deterministic trace + diagnosis readers | PASS — trace status=succeeded; diagnosis tier=proven_cause |
| E4 | R2 engineering change: draft→(validate)→propose routing weights | PASS — draft ok; propose executed the lifecycle honestly (outcome `rejected` when validation preconditions unmet — the lifecycle refusing is correct behavior, not a failure) |
| E5 | Skill/test workflow: save_scenario → run_regression_pack | PASS — scenario_count=1, regression_pass=true |
| E6 | Source change: snapshot→propose→verify→wrong-hash approve (refused: ApprovalHashMismatch)→cited-hash approve→apply | PASS — apply is snapshot-space ONLY; `authoritative_apply_status() = {available: false, gate: S14_OPERATOR_GATE}`; apply-before-approve refused (InvalidTransition) |
| E7 | Console auth boundary | PASS (pinned in test_admin_console_runtime.py) — anonymous/garbage ⇒ ONE constant 401; non-admin ⇒ 403 |

## 4. Real gaps found — and closed during this handoff

Proven live first, then fixed at the shared layer, then pinned
(`tests/admin_agent/test_handoff_gaps.py`, 8 tests):

- **GAP-1a (blocker): reasoning prompt had no protocol.** `_reason` sent the
  admin message bare; a real model answered in prose; the parser (correctly)
  refused; the loop was inert — every scripted test passed because tests
  scripted valid proposals. Fix: `_PROPOSAL_PROTOCOL` + `registry.describe()`
  now frame the ask (pure composition data — the contract the parser already
  enforces, stated to the model). No parsing/evidence rule was relaxed.
- **GAP-1b (blocker): fenced JSON refused.** Real models wrap JSON in ```
  fences. Fix: deterministic fence-stripping only — no repair, no guessing;
  prose and fenced garbage still refuse identically.
- **GAP-2 (blocker, in-memory profile): registered users had no budget.**
  Only the demo principal was granted task units, so an admin registering to
  use `/admin` got EntitlementNotConfigured on the agent's first reasoning
  call. Fix: the SAME `BudgetGrantingIdentity` wrapper the durable branch
  already used (symmetry — recorded decision 5; Fix Once → Benefit Everywhere).
- **GAP-3 (friction): two tool descriptions under-specified.**
  `draft_change` now lists the closed AdminAction set; `save_scenario` states
  checks is optional. Descriptions are the agent's only tool documentation —
  this is configuration data, not new capability.

## 5. Self-sufficiency classification

| Workflow | Verdict |
|----------|---------|
| Repository/project understanding (platform records: executions, audit, changes, capabilities, scenarios) | SELF-SUFFICIENT |
| Complex debugging (reproduce via run_test_execution → read_execution/trace/diagnosis → evidence-cited findings) | SELF-SUFFICIENT |
| Engineering change (R2 config lifecycle: draft→validate→preview→propose; publish stays a human UI act) | SELF-SUFFICIENT WITH OPERATOR APPROVAL (by design) |
| Testing/regression (scenarios, regression pack, capability exercise, context lab, self-review) | SELF-SUFFICIENT |
| Skill workflow (import→scan→validate→review→approve→activate via /v1/admin/skills when SkillReviewSurface composed; enable/disable via R2) | SELF-SUFFICIENT WITH OPERATOR APPROVAL — note: runtime composes NO SkillReviewSurface today, so import routes are absent in the local runtime (20 §4 honest absence; the pipeline itself is proven in tests) |
| Platform maintenance (inspect self via capabilities/exercise/self_review/changes_since_review) | SELF-SUFFICIENT |
| Source change (propose→immutable snapshot→sandbox differential→cited-hash approval→snapshot-space apply→rollback) | SELF-SUFFICIENT WITH OPERATOR APPROVAL; **authoritative apply = PLATFORM GAP by design** (R3 §14 operator gate — refusing is the contract) |
| Arbitrary file-tree editing of the live repo | EXTERNAL EXECUTION AGENT REQUIRED — **intentionally**: this is exactly the R3 authority the operator reserved. The platform's own path for it is the source-change workflow above. |

**Verdict: no external execution agent is required for the ordinary intended
platform workflows.** The only remaining external role is (a) the reserved R3
authoritative apply, and (b) work on the platform's own repository until R3 is
activated — both deliberate authority boundaries, not capability gaps.

## 6. Admin operability (from /admin + agent tools)

VISIBLE + OPERABLE: models, providers (enable/disable via R2), routing weights,
plans/budgets (set_plan), executions (list/read/trace/diagnosis), scenarios +
regression, capabilities + exercise, context validation, learning
observability, self-review, config-change lifecycle, notifications, audit.
VISIBLE ONLY: usage summaries (per-tenant), source-change evidence (apply is
gated). OPERABLE ONLY: —. SOURCE EDIT REQUIRED: adding providers/models
(composition data — correctly so), composing SkillReviewSurface, REGISTER/EXECUTE
rate limits (env). NOT APPLICABLE: tenant CRUD in-memory (durable profile owns it).

## 7. Authority boundaries (exercised, not assumed)

- Registry constructionally refuses R3/R4 tools (pinned).
- Anonymous/garbage token ⇒ ONE constant 401; non-admin ⇒ 403 (pinned + live).
- Claims without surfaced evidence are refused (live: E1 refused 2, E2 admitted 1).
- Approval must cite the exact patch hash (live: ApprovalHashMismatch).
- Apply never leaves snapshot space; authoritative applier stays None
  (`S14_OPERATOR_GATE`). **R3 remains gated. Nothing in this handoff weakened
  sandbox, approval, audit, or tenant isolation.**

## 8. Competitive self-challenge (focused)

Compared against the relevant strengths of agent platforms in our domain
(OpenAI Assistants-style tool loops; Claude-style agentic coding; LangGraph-style
orchestration):

- **Their strength: fluent multi-step tool loops.** Ours dispatches from a
  single reasoning turn (flood-bounded at 8) and chains across turns via the
  admin. Material? Minor — E4/E5 showed multi-call turns work; iterative
  re-reasoning within one turn is a future direction, not a gap for intended
  admin workflows. One shared improvement (feed tool results back for one more
  reasoning pass) would close it if ever justified.
- **Their strength: repository-native file editing.** Deliberately reserved
  (R3). Our differential-verified, hash-cited, rollback-capable source-change
  workflow is *stronger* on governance than typical agent file-editing.
- **Our differentiators they lack:** evidence-gated claims (invented citations
  structurally refused), reasoning-as-billed-execution (agent activity is
  first-class audited platform work), closed tool registry with risk classes.

No feature-count chasing: no other change justified by comparison.

## 9. No-op areas (reviewed, deliberately unchanged)

- Iterative multi-pass reasoning loop — not needed for intended workflows.
- Workspace-file tools for the agent — core/workspace exists and is
  ports-clean, but no intended admin workflow requires agent file I/O today;
  adding tools would expand attack surface without a driving use case.
- SkillReviewSurface composition in runtime — absent seam = absent routes is
  the honest posture until the operator wants skill-import in the local runtime.
- Notifications/webhooks/SSE — already proven in suites; not re-exercised.

## 10. Future directions (directional only — separately authorized)

R3 activation (authoritative applier binding) · durable usage accounting ·
skill-import composition in runtime · multi-pass agent reasoning · learning
flywheel (13 §future). None fabricated, none started.

## 11. Evidence

- Live transcripts: this handoff session (E1–E6 outputs recorded in session log).
- Hermetic pins: `tests/admin_agent/test_handoff_gaps.py` (8),
  `tests/composition/test_admin_console_runtime.py` (7),
  `tests/admin_agent/test_aa2_admin_agent.py` (49) + aa3 (25) — evidence &
  authority invariants.
- Gates at handoff: **2220 passed / 64 skipped**; ruff clean; mypy --strict
  clean (service.py, tools.py, runtime.py); import-linter 12 kept / 0 broken.
- Prior evidence: FINAL_VALIDATION.md, V8_R3_ACCEPTANCE_EVIDENCE.md,
  V9_FULL_VALIDATION.md.

## 12. Final verdict

The Internal Agent, running on the platform's own capabilities, carries the
intended engineering, testing, evaluation, maintenance, and governed
source-change workflows itself — with evidence, within authority, in both
profiles. The remaining external role is exactly the reserved operator
authority (R3 authoritative apply) and platform-repo work until R3 activation.

**EXTERNAL EXECUTOR HANDOFF COMPLETE — INTERNAL AGENT IS NOW THE PRIMARY
EXECUTOR FOR THE INTENDED PLATFORM WORKFLOWS.**
