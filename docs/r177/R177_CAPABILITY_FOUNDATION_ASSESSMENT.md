# R177 — Capability Foundation Assessment (CFA)

Round: R177 (bounded, operator-authorized). Repository: `belalalibb/general_ai_core` main. Baseline HEAD at round start: **13be858d**.
Phase A was READ-ONLY on the product tree; every artefact lives under `evidence/r177/**`, `docs/r177/**`, `evidence/r177_state_ledger.md`
and appended entries in `final_docs_v3/60_DECISION_LOG.md`. Nothing under core/ apps/ ui/ infrastructure/ providers/ gateway-service/
engineering/verification/ or the canonical prompt was modified (KNOWN: `git diff --stat 13be858d -- core apps ui infrastructure providers
gateway-service engineering` → empty). This document does **not** declare QEVION complete; it classifies every investigated area with the
§19 closed set and states KNOWN vs INFERRED throughout.

## 1. Baseline reconciliation (A01) — `evidence/r177/A01_baseline/baseline_reconciliation.md`
All 13 rows of directive §2 CONFIRMED against git/ledger/evidence: HEAD 13be858d == origin/main, clean; R176 A0–A13 + B FIX-02..07 SHAs
present (bf5d0f9, ff38b07, bd4bdd9+eb44553, 005aa45, 4839b7b0, f44cc703); final gate artefact `pytest passed=3196 failed=0 errors=0
skipped=64`, ruff/format/mypy/import-linter PASS, `RESULT: FAIL` solely on the secret scan hit at canonical prompt line 132; gateway 194
passed. FIX-01 untouched — PENDING APPROVAL / OPERATOR-OWNED. **Divergences: none** for §2. Two divergences vs directive text elsewhere:
`CAPABILITY_IDS` has **17** ids (not 16; `dev.publish_modes`, R172 C7) and `create_app` has **37** parameters (not ~35). Repository wins.

Round operations: 4 sandbox resets; one erased two local-only commits while publication was blocked (no credential) — rewritten from the
same evidence and pushed; every later chunk was committed+pushed in one shell call. The R177 baseline gate re-run was started twice and
lost to resets both times; because the product tree is byte-identical to 13be858d, the R176 final-gate artefact is the pinned baseline.

## 2. Governance-constraint confirmation (A03) — `evidence/r177/A03_governance/governance_constraints.md`
All §3 items confirmed from `check_repo.sh` / `green_manifest.json`: forbidden filenames (:41), v3 pack = 20 (:50-54), 5 state header
fields (:56), secret-scan patterns + exceptions **5/5 full**, hardcoded budget tuple (:143), not_evaluated **2/2 full**, closed sets
(VerificationLevel 5, ErrorCode 11, CAPABILITY_IDS 17, FirewallDecision 4), import-linter 13, frozen trees (ui/, apps/admin_agent/,
core/tools/gate.py), pytest floor 3127/64.

**Secret-scan honesty (§3.4)**: of canonical prompt lines 132/133/134, ONLY line 132 (GitHub PAT shape) matches the gate patterns; lines
133 (Groq `gsk_` shape) and 134 (32-hex) do NOT. A green scan after a line-132-only redaction would not prove the file credential-free;
FIX-01 must redact all three (DEC-02). Values were never printed, copied or reconstructed in this round.

**F-R177-01 (S3, governance) — change-budget enforcement hole.** `check_repo.sh:143` iterates a hardcoded tuple
`("round_a","round_b","round_r169","round_r172","round_r173")`; `:144 if r not in cb: continue`. Any other manifest round is silently
ignored. Consequence (KNOWN): R176 Phase B changed six production files with no `round_r176` entry and thus no ceiling check — the gate's
"change budget within ceilings" PASS was true and irrelevant. Fix = R177-FIX-01 (needs DEC-05; `engineering/verification/*` edit).

## 3. Composition-surface map (A04) — `evidence/r177/A04_composition/`
`create_app(...)` exposes **37** parameters; three absent-seam postures coexist: mount-time gating (agent, admin, learning → true 404),
defaults-in-place (skills/roles registries, projects/workspaces, source_proposals/snapshots, idempotency_index → always present
in-process; the seam controls durability), response-shape gating (usage block absent, never faked). Published catalog
`GET /v1/admin/capabilities` = 17 ids with per-row state rule/seam/route. Env-composed profile = **79 routes** (57 admin, 5 agent, 5 auth,
4 execute, 3 webhooks, 2+2 workspaces/projects, 3 listing, 1 healthz; `routes_env_composed.json`). Operator-desired capabilities map
onto existing seams (table in evidence). Catalog completeness observation: agent runtime, source-change, skills import,
workspaces/projects and evaluation are mounted and exercised but have **no CAPABILITY_IDS row** (closed-set edit → R177-FIX-02).

## 4. Approval-and-policy map (A05) — `evidence/r177/A05_approval/approval_policy_map.md`
Enforcement of "Core policy > approval > application configuration, most-restrictive-wins" is **ALREADY COVERED**:
`CapabilityFirewall.decide` 6 ordered paths; `ToolCallGate` "both authorities must consent", tightening only;
`DEFAULT_APPROVAL_REQUIREMENT = ALWAYS`; `approval_state` closed to `"approved" | None`; R172 payload binding ties approval to the
argument hash. Recording is **PARTIALLY COVERED**: admin config lifecycle, sourcechange (approve{cited_hash}/reject{reason} →
APPROVAL_DECISION), skills import, learning promotion (approval_required=True / admin_approved=False defaults), engineering tickets
(issue/consume/refuse → APPROVAL_DECISION) each persist their own decision. **MISSING**: a persisted, auditable composition-level
*capability proposal* record (the §7 decision sheet). KNOWN: shipped TenantPolicies have empty `approval_gated_permissions` — firewall
REQUIRE_APPROVAL is exercised by tests, not by the composed app (CSE).
**DEC-01 verification**: memory/composer paths are governed by their own closed gates (sensitivity HIGH refused unless the *app* sets
`allow_high_sensitivity`; scope priority 13 §4; secret boundary guard; tenant-scoped keys) — not by the firewall vocabulary. No divergence;
no second precedence model exists. Confirmation appended to 60_DECISION_LOG (R177-DEC-01).

## 5. Vocabulary mapping (A06) — `evidence/r177/A06_vocabulary/vocabulary_mapping.md`
Explicit statement: no term below claims emotions, consciousness or a "self"; "Soul" = durable, tenant-scoped personalization context.
Contract facts (KNOWN): **no `MemoryType` enum** — a memory's "type" is `scope` × `source` × `user_id`; the ONLY runtime writer of
`MemoryStorePort.upsert` is GOLD promotion (`source=learning.gold`); `PreferenceLearningGate` (13 §6) is exported but **never called**
at runtime; identity = device/session, no persona object; "Teacher" exists only in docs 21/22/41 and one unused admin field.

| term | anchor | class | minimum expression (no new subsystem) |
|---|---|---|---|
| Identity | core/identity (devices, sessions), auth router | AC (device/session) · M (cross-device profile) | `user_id` stays the key; profile = tenant-scoped MemoryItems |
| Preferences | core/memory/preferences.py + memory store | **PC** (gate unwired; no 13 §8 visibility routes) | wire the gate as an OPTIONAL seam; visibility = 2–3 routes over MemoryStorePort |
| Memory (6 types) | scope/source convention | **CSE** | documented type→(scope,source) convention pinned by test; no enum unless approved |
| Conversation / Working Context / Verified Intelligence | ConversationStorePort / composer / GOLD | **AC** | — |
| Project / Semantic-User / Episodic | scopes exist; **no writer** | PC / PC / **M** | same optional writer seam; episodic = `source="episode"` + `expires_at` |
| Soul / personalization | preferences + user-scoped items + composer | **new vocabulary, not a component** | docs/architecture note; NO `core/soul`, NO `SoulProfile` contract without approval (HIGH parallel-concept risk) |
| Knowledge | GOLD items + ask_learned/learned_keys | AC (promoted) · PC (intake) | intake adapters outside core/ feeding `capture_external` |
| Teacher | ModelJudgePort + PromotionGate.admin_approved | **PC** (role exists, name absent, 22 §10 selector absent) | judge binding + selection policy data; disabled ⇒ deterministic graders + gates + human approval still run |

Findings: **F-R177-02** (S3) PreferenceLearningGate dead at runtime, no memory visibility routes; **F-R177-03** (S4) 13 §2 types have no code
expression; **F-R177-04** (S4) Soul/Teacher absent from code, literalisation risk.

## 6. Learning & knowledge lifecycle (A07) — `evidence/r177/A07_learning/learning_knowledge_lifecycle.md`
Ladder (5, closed), TrainingEligibilityGate (8 conditions), PromotionGate (7 + approval), lifecycle service, sanitizer (FIX-06) are real
and deny-by-default (R176 A8 probed). Gaps: **G-A07-1** PromotionSignals are caller-asserted booleans (admin.py:212-232) — the gate is a
correct policy engine over unverified inputs (CSE/PC); **G-A07-2** `ModelJudgePort` is NOT composed (app.py:2086) ⇒ *Teacher-disabled is
the current state*: `evaluate()` ceiling is VALIDATED, GOLD remains reachable via human-approved promotion, pipeline unbroken (answers §9);
22 §10 selective policy has no selector; **G-A07-3** no structured intake (CSV/Excel/JSON/file/API) — MISSING, must live outside core/;
**G-A07-4** evaluation store in-memory even in the durable profile; **G-A07-5** learning observability admin-only and split across routes.

## 7. Repository discovery vs execution authority (A08) — `evidence/r177/A08_discovery/discovery_vs_authority.md`
Separation is **structurally held**: read-only default TenantPolicy (`source.read` + `agent.tools`); write/exec are distinct permissions
(`workspace.read/write/exec`, `git.read/write`) each needing admin grant + one-use ticket + approval_policy ALWAYS + payload binding;
jail resolve-then-relative_to; shared reader/writer denylist (27 hardened rows); command allowlist (python3/pytest/ruff) + env allowlist;
per-tenant remote-trust; deny-by-default tool selection (no allow-list AND no skills ⇒ NO tools). Gaps: **F-R177-05** (S3) no persisted
repository model — discovery is transient per run; **F-R177-06** (S4) `list_files` truncates at 500 with no cursor. Large-repo scalability
CSE (no executed probe).

## 8. Capability completeness matrix (A09) — `evidence/r177/A09_matrix/capability_completeness_matrix.md`
26 §12 items classified with the §19 set: **ALREADY COVERED 15** (context, working memory, tools, skills, execution, verification,
testing, recovery, error handling, reasoning, policy enforcement, permission boundaries, provider abstraction, tenant isolation,
reproducibility) · **PARTIALLY COVERED 9** (planning, decomposition, repository understanding, long-term memory, project memory,
evaluation, learning, knowledge management, durable state) · **COVERED BUT NEEDS STRONGER EVIDENCE 1** (observability) · human approval =
AC enforcement / M proposal record · MISSING/NOT NECESSARY/BLOCKED 0 standalone · UI **DEFERRED** (§15, frozen tree).
Confirmed gaps admitted to research: persisted repository model; composition-level proposal record; structured intake; evidence-bound
promotion signals.

## 9. Bounded landscape findings (A10) — `evidence/r177/A10_landscape/landscape_findings.md` (Level 3/5, 2026-09-08)
1. Repository map (aider / tree-sitter / "Codebase-Memory"): compact ranked *context-selection* artefact → QEVION minimum = MemoryItem
   `scope=project, source="repo.map"` via the existing port; parsers/ranking outside core/.
2. ADR pattern (Nygard / Fowler): closed status ladder, immutable once accepted → the §7 decision sheet is ADR-shaped; documentary in
   60_DECISION_LOG now; optional admin-lifecycle kind `capability_proposal` later.
3. Expectation-based validation + quarantine (Great Expectations): intake adapter outside core/ validates per batch, emits RAW
   `capture_external` items, refused rows recorded as reports — trust ladder unchanged.
4. Registry-gated promotion (MLflow/Databricks): derive eval/regression/security signals from referenced artefacts; refuse caller-asserted
   True; `admin_approved` stays human; shadow/canary labelled UNVERIFIED until a producer exists.

## 10. Consolidated finding register
| id | sev | area | statement | class | fix |
|---|---|---|---|---|---|
| F-R177-01 | S3 | governance | budget tuple hardcoded; R176 B changes unguarded | — | R177-FIX-01 (DEC-05) |
| F-R177-02 | S3 | memory | PreferenceLearningGate unwired; no memory visibility routes | PC | R177-FIX-04 |
| F-R177-03 | S4 | contract/docs | 13 §2 six types have no code expression | CSE | R177-FIX-05 (docs+test pin) |
| F-R177-04 | S4 | vocabulary | Soul/Teacher absent; literalisation risk | — | documentary only (this report + DEC-LOG) |
| F-R177-05 | S3 | discovery | no persisted repository model | PC | R177-FIX-06 |
| F-R177-06 | S4 | tools | list_files truncation without cursor | PC | R177-FIX-07 (optional) |
| G-A07-1 | S3 | learning | promotion signals caller-asserted | CSE/PC | R177-FIX-08 |
| G-A07-2 | S4 | evaluation | model judge not composed; no 22 §10 selector | PC | R177-FIX-09 (composition) |
| G-A07-3 | S3 | knowledge | no structured intake | M (sub-gap) | R177-FIX-10 |
| G-A07-4 | S4 | durability | evaluation store in-memory in durable profile | PC | R177-FIX-11 |
| G-A07-5 | S4 | observability | learning observability split/admin-only | PC | DEFERRED |
| A04 catalog | S4 | catalog | mounted capabilities without CAPABILITY_IDS rows | — | R177-FIX-02 |
| A05 §6.1 | S3 | approval | no composition-level proposal record | M (sub-gap) | R177-FIX-03 |

## 11. Proposal pack — decision sheets (§7 format; every sheet PENDING APPROVAL; none implemented)

```
PROPOSED CAPABILITY: R177-FIX-01 — change-budget enforcement for new rounds (governance; no CAPABILITY_IDS entry)
WHAT:                make the repo gate account every manifest round instead of a hardcoded five-round tuple
DOES:                engineering/verification/check_repo.sh:143 iterate keys starting with "round_"; green_manifest.json add round_r177
                     {ceiling, items, log, counts_production_code_under}; new test tests/engineering/test_budget_rounds_r177.py (fixture
                     manifest with an unlisted over-ceiling round MUST fail the budget step)
WHY:                 F-R177-01 — R176 Phase B production changes were outside budget enforcement; R177 Phase B would be too
REQUIRED:            Yes for ANY R177 production change (§3.5c) — without it every other FIX below is unguarded
DEPENDENCIES:        none (bash + python3 in the gate)
IMPACT:              contracts: none · security: none · architecture: none · governance: stronger
RISK:                Low — gate-only; failing-first test pins the new behaviour; rollback = revert
ALTERNATIVE:         extend the tuple by one literal (weaker: the hole recurs next round)
ENFORCEMENT POINT:   check_repo.sh §6 (the single verifier) + green_manifest.json
DECISION:            APPROVE | REJECT   (= DEC-05)
```
```
PROPOSED CAPABILITY: R177-FIX-02 — catalog completeness (existing seams; EXTENDS closed CAPABILITY_IDS)
WHAT:                add honest rows for capabilities that are mounted but uncatalogued
DOES:                apps/api/capabilities.py CAPABILITY_IDS += agent.runtime, sourcechange.workflow, skills.import, workspaces.projects,
                     evaluation.records (5 ids; final names subject to approval); apps/api/app.py catalog builder adds state rules
                     (agent is not None; source_proposals seam; admin+skills importer; always-in-process; admin evaluation store);
                     tests/api catalog closed-set test updated to 22
WHY:                 A04: 57 admin + 5 agent routes exist with no catalog row → GET /v1/admin/capabilities under-reports the platform
REQUIRED:            No — runtime unchanged; catalog honesty only
DEPENDENCIES:        none
IMPACT:              contracts: closed set 17→22 (deliberate, test-pinned) · OpenAPI: additive
RISK:                Low
ALTERNATIVE:         leave catalog as the "frozen roadmap" view; document the gap (status quo)
ENFORCEMENT POINT:   CAPABILITY_IDS closed-set test
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-03 — composition-level capability-proposal record (existing admin lifecycle; new draft kind)
WHAT:                persist "Agent proposed capability X for app Y; operator APPROVED/REJECTED with reason" as an auditable record
DOES:                core/contracts/admin.py: add draft kind `capability_proposal` (closed change-kind set → approval) whose payload IS the
                     §7 decision sheet fields; publish ⇒ AuditEvent APPROVAL_DECISION with details={proposal_id, decision, reason};
                     read via existing GET /v1/admin/audit and /v1/admin/changes/{id}; no new route, no new store
WHY:                 A05 §6.1 — enforcement complete, recording MISSING; later sessions cannot know what was approved/rejected
REQUIRED:            No (documentary path = 60_DECISION_LOG entries works today)
DEPENDENCIES:        admin lifecycle (draft→validate→preview→publish), audit store
IMPACT:              contracts: admin change-kind set +1 · data: audit rows · security: none (admin-only)
RISK:                Low–Medium (touches a closed admin contract; failing-first test on kind validation + audit emission)
ALTERNATIVE:         documentary only (append sheets + rulings to 60_DECISION_LOG) — zero code, not machine-readable
ENFORCEMENT POINT:   admin lifecycle + AuditEvent
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-04 — wire PreferenceLearningGate + 13 §8 memory visibility (existing memory seam)
WHAT:                learn user preferences from repeated evidence (13 §6) and let users view/delete them (13 §8)
DOES:                apps/composition: OPTIONAL `preferences` seam → after a succeeded execution, feed observations to
                     core/memory/preferences.PreferenceLearningGate; admitted ⇒ MemoryItem(scope=tenant, user_id, source="preference");
                     routes GET /v1/memory/preferences, DELETE /v1/memory/preferences/{id} over MemoryStorePort filtered by source; tenant+user
                     scoped; memory write guard (FIX-06 table) applies
WHY:                 F-R177-02 — gate is dead code; "Soul"/personalization has no writer; 13 §8 promise unmet
REQUIRED:            No — absent seam ⇒ no preference learning, execute unaffected (honest INERT)
DEPENDENCIES:        memory seam; conversations optional
IMPACT:              contracts: none new (MemoryItem reused) · data: new tenant/user-scoped items · security: sensitivity gate + secret guard
                     already apply · privacy: users can delete (13 §8)
RISK:                Medium — first runtime writer of non-GOLD memory; failing-first tests: gate refusal on <2 evidence, cross-tenant read 404,
                     secret-shaped preference refused
ALTERNATIVE:         keep memory read-only (status quo); personalization stays unavailable
ENFORCEMENT POINT:   PreferenceLearningGate + memory write guard + tenant-scoped keys
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-05 — memory type convention pinned (docs + test; no contract change)
WHAT:                make the six 13 §2 memory types expressible and checkable without a new enum
DOES:                docs/architecture/MEMORY_TYPES_MAPPING.md (type → scope × source × user_id, incl. "preference", "episode", "repo.map",
                     "learning.gold"); tests/memory/test_memory_type_convention_r177.py pins the source vocabulary used by runtime writers
WHY:                 F-R177-03 — types are documentary only; new writers (FIX-04/06) need one vocabulary
REQUIRED:            No; recommended before FIX-04/06
DEPENDENCIES:        none
IMPACT:              contracts: none · closed-set: none (a MemoryType enum is explicitly NOT proposed — see R177-DEFER-01)
RISK:                Low
ALTERNATIVE:         MemoryType enum (new closed set; higher blast radius) — deferred
ENFORCEMENT POINT:   test pin
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-06 — persisted repository model via memory (existing agent + memory seams; OPTIONAL tool)
WHAT:                a bounded discovery tool that writes a compact, ranked repository map as project-scoped memory items
DOES:                apps/composition (or providers/) `repo_map` tool: uses the existing jailed SourceReader (bounds, denylist) to list files
                     and top-level symbols (stdlib `ast` for Python first; other languages "unknown"), ranks by import-degree, writes
                     MemoryItem(scope=project, source="repo.map", confidence, evidence_count) via MemoryStorePort; composer already ranks
                     project scope; permission = source.read only (no new permission); exposed through /v1/agent-tools like other tools
WHY:                 F-R177-05 — discovery is transient per run; planner cannot cite a persisted model; §11 asks for a project map
REQUIRED:            No — absent ⇒ agent discovers live as today
DEPENDENCIES:        memory seam, agent seam, projects store
IMPACT:              architecture: none in core/ (parser outside) · data: project-scoped items · security: read-only, jail applies, NO execution
                     authority conferred · performance: bounded by reader limits
RISK:                Medium — stale maps mislead; mitigations: confidence + last_seen on MemoryItem, recompute on demand
ALTERNATIVE:         status quo (live discovery only); or vendor tool outside QEVION
ENFORCEMENT POINT:   SourceReader jail/denylist + firewall source.read + tenant-scoped memory keys
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-07 — list_files continuation cursor (core/tools/source_reader.py; optional ergonomics)
WHAT:                let bounded listing continue past max_entries deterministically
DOES:                add `after: str | None` (last returned rel path) to `SourceReader.list_files` and `ws_list`; response carries
                     `truncated`+`next_after`; bounds unchanged
WHY:                 F-R177-06 — 500-entry hard truncation without a cursor on large trees
REQUIRED:            No
DEPENDENCIES:        none
IMPACT:              contracts: additive tool arg · security: none (same jail)
RISK:                Low
ALTERNATIVE:         directory-wise recursion by the agent (works today)
ENFORCEMENT POINT:   SourceReader
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-08 — evidence-bound promotion signals (existing learning + evaluation seams)
WHAT:                derive offline_eval_pass / regression_pass / security_eval_pass from recorded artefacts instead of trusting booleans
DOES:                apps/api/admin.py promote request: optional `evidence_refs {evaluation_id?, regression_run_id?, security_eval_id?}`;
                     resolver in apps/composition reads the evaluation store / scenarios store and SETS the three signals; composition flag
                     `strict_promotion_evidence=True` refuses caller-asserted True for those three without refs (naming the condition);
                     shadow/canary stay caller-asserted and are labelled UNVERIFIED in the sample report; PromotionGate unchanged
WHY:                 G-A07-1 — the gate is correct over unverified inputs; landscape: registries gate on recorded artefacts
REQUIRED:            No (but strongly recommended before any GOLD knowledge is relied upon)
DEPENDENCIES:        evaluation store (in-memory today → see FIX-11), scenarios store
IMPACT:              contracts: additive request field · closed sets: none · security: stronger (no self-asserted pass)
RISK:                Low–Medium (failing-first: asserted True without refs ⇒ refused)
ALTERNATIVE:         status quo + operator discipline
ENFORCEMENT POINT:   PromotionGate (unchanged) fed by resolver
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-09 — compose the model judge behind a 22 §10 selection policy ("Teacher", composition only)
WHAT:                enable VERIFIED-level evaluation selectively; keep Teacher replaceable/disable-able
DOES:                apps/composition: bind `AdapterModelJudge` (existing) into EvaluationPolicyService(judge=…) when env
                     `EVAL_JUDGE_MODEL_POLICY` is set; new small policy object (composition data) selecting samples by 22 §10 criteria
                     (uncertain = confidence below threshold, new task category, calibration set, canary); disabled ⇒ today's behaviour
WHY:                 G-A07-2 — VERIFIED unreachable via evaluate(); Teacher role has a seam but no composition or selector
REQUIRED:            No — disabled = current state, pipeline unbroken (A07 §2)
DEPENDENCIES:        routing + a provider binding (cost!); evaluation store
IMPACT:              cost: paid inference per judged sample (selective by design) · provider independence: via routing · contracts: none
RISK:                Medium (spend; judge failures raise JudgeFailure and never fake a level)
ALTERNATIVE:         admin `set_verification_level` override (exists) — human, not scalable
ENFORCEMENT POINT:   EvaluationPolicyService level ladder + selection policy
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-10 — structured knowledge intake adapter (outside core/; feeds capture_external as RAW)
WHAT:                CSV/JSON (Excel optional) batch intake validated against declared expectations, quarantined on failure
DOES:                apps/composition/intake.py (or providers/intake): parse → validate against expectation set (composition data: required
                     columns, types, max rows) → per admitted row `lifecycle.capture_external(knowledge_key, knowledge_value)`; refused rows
                     + validation report recorded as a sample report; admin route POST /v1/admin/learning/intake (multipart or JSON);
                     every item lands RAW and traverses sanitize → eligibility → evaluate → promote unchanged
WHY:                 G-A07-3 — no bulk/structured intake; §9 asks for CSV/Excel/JSON/API paths
REQUIRED:            No
DEPENDENCIES:        learning seam; optional openpyxl (Excel) outside core/
IMPACT:              data: RAW samples only · security: sanitizer + eligibility gate apply per item; upload size bounds · contracts: none
RISK:                Medium (poisoning surface widens — bounded by RAW + gates; failing-first: secret-shaped cell refused at scan)
ALTERNATIVE:         status quo (one item per admin call)
ENFORCEMENT POINT:   TrainingEligibilityGate + sanitizer (unchanged)
DECISION:            APPROVE | REJECT
```
```
PROPOSED CAPABILITY: R177-FIX-11 — durable evaluation store in the durable profile (infrastructure; migration 0019)
WHAT:                evaluation records survive restart like executions do
DOES:                infrastructure/db: table `evaluation_records` (migration 0019) + PostgresEvaluationStore implementing
                     EvaluationStorePort; apps/composition/database.py binding; app.py composes it when DATABASE_URL is set; in-memory
                     stays the hermetic default
WHY:                 G-A07-4 — evaluations are the evidence FIX-08 would rely on; today they vanish on restart
REQUIRED:            No (hermetic profile unaffected)
DEPENDENCIES:        durable profile; alembic
IMPACT:              data: new table · durability envelope widens honestly · contracts: none
RISK:                Low–Medium (migration; durable pytest slice must pass)
ALTERNATIVE:         status quo; label evaluation evidence as process-local
ENFORCEMENT POINT:   EvaluationStorePort
DECISION:            APPROVE | REJECT
```
