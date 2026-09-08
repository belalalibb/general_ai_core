# R177 state ledger (checkpoint discipline: one row appended BEFORE each item; recoverable from this file alone)

Contract: operator directive **R177 — CAPABILITY FOUNDATION ASSESSMENT (CFA)** (bounded round, level-3 authority; canonical prompt
`docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md` untouched and its invariants win). R176 is CLOSED (its ledger
is immutable evidence; only FIX-01 remains, OPERATOR-OWNED, PENDING APPROVAL).
Governing rules: Phase A is READ-ONLY on the product tree (core/ apps/ ui/ infrastructure/ providers/ gateway-service/ engineering/verification/);
the only writes are `evidence/r177/**`, `docs/r177/**`, this ledger, and APPENDED entries in `final_docs_v3/60_DECISION_LOG.md`.
Phase B needs `APPROVED: R177-FIX-nn` AND DEC-05 (budget-enforcement governance fix) first. Never ARCHITECTURE_GAPS.md / FUTURE_IMPROVEMENTS.md;
v3 pack stays 20 files; PROJECT_EXECUTION_STATE.md frozen; not_evaluated stays 2/2; closed sets (§3.7) stay closed.

## Resume protocol in force (Fable 5.1 — preserved exactly)

```text
RESUME ARTIFACT (round):    evidence/r177_state_ledger.md          <- THIS FILE; last row = where to continue
RESUME ARTIFACT (project):  docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md (frozen R168; FIX-02 pointer → highest evidence/rNNN_state_ledger.md)
PROTOCOL DOC:               docs/ai_orchestration_pack/final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md
RESUME COMMAND:             git fetch origin main && git status -sb && tail -3 evidence/r177_state_ledger.md
                            && pip install -e ".[dev]" && env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY -u DATABASE_URL python3 -m apps.cli check
TRUST:                      committed git state > filesystem > this ledger > chat memory
RECOVERY ORDER:             Repository → this ledger → Git state → evidence/r177/** → verified runtime → exact NEXT ACTION (last row)
PUBLICATION:                push failure = PUBLICATION_BLOCKED (local work continues; push at first authorized opportunity) ≠ EXECUTION_BLOCKED
LESSON (reset #1 of R177):  unpushed local commits DO NOT survive a sandbox reset → when publication is blocked, keep chunks tiny and re-push at the first credentialed turn
```

## Checklist (status is only trusted when the matching row below exists AND is committed)

| # | item | status |
|---|---|---|
| A01 | Baseline reconciliation (§2 row by row) | DONE |
| A02 | Continuity setup: this ledger; recovery protocol confirmed | DONE |
| A03 | Governance-constraint confirmation (§3) + F-R177-01 + R177 baseline gate | DONE (gate re-run UNVERIFIED: lost to resets twice; product tree byte-identical to 13be858d → R176 artefact stands) |
| A04 | Composition-surface map (create_app seams, CAPABILITY_IDS, routes) | DONE |
| A05 | Approval-and-policy map (firewall, gate, admin lifecycle, sourcechange, skills import, promotion) | DONE |
| A06 | Vocabulary mapping table (§8) | DONE |
| A07 | Learning & knowledge lifecycle assessment (§9) incl. Teacher-disabled | DONE |
| A08 | Repository-discovery vs execution-authority (§11) | DONE |
| A09 | Agent capability completeness matrix (§12) | DONE |
| A10 | Bounded landscape research for CONFIRMED gaps only (§5) | DONE |
| A11 | Deliverable assembly docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md + decision-log entries | DONE (§1–§10; §11–§12 added by A12) |
| A12 | Proposal pack: decision sheets (PENDING APPROVAL) + R177-FIX-nn register | DONE |
| A13 | STOP at §20 and report | DONE |
| B0 | Phase B approval recorded (operator message names ids) | DONE |
| B-01 | R177-FIX-01 budget-loop generalisation + round_r177 ceiling (DEC-05) | IN_PROGRESS |
| B-05 | R177-FIX-05 memory-type mapping doc + convention test | PENDING |
| B-02 | R177-FIX-02 +5 CAPABILITY_IDS (closed-set extension, test-pinned) | PENDING |
| B-08 | R177-FIX-08 promotion evidence_refs + strict mode | PENDING |
| B-04 | R177-FIX-04 PreferenceLearningGate seam + preference routes | PENDING |
| B-06 | R177-FIX-06 repo_map tool → MemoryItem scope=project | PENDING |
| B-11 | R177-FIX-11 migration 0019 + PostgresEvaluationStore | PENDING |
| B-03 | R177-FIX-03 admin draft kind capability_proposal → APPROVAL_DECISION | PENDING |
| B-10 | R177-FIX-10 learning intake adapter + route | PENDING |
| B-09 | R177-FIX-09 AdapterModelJudge composition (env-gated) | PENDING |
| B-07 | R177-FIX-07 list_files `after` cursor | PENDING |
| B-D2 | DEC-02 redact prompt lines 132–134 values | PENDING |
| B-G | Final gate + gateway suite + assessment status update + report | PENDING |

## Rows (task_id · phase · status · exact_next_action · evidence_location · git_head · worktree · blocker · completed_at)

| task | entry | head |
|---|---|---|
| A01 | phase A · **VERIFIED+PERSISTED** · §2 verified row by row against git/ledger/evidence/gate artefacts → `evidence/r177/A01_baseline/baseline_reconciliation.md`. Divergences: **none** for §2. First session: HEAD 13be858d == origin/main, worktree clean, no git credential → PUBLICATION_BLOCKED; a sandbox reset then erased the two local-only commits (A01–A04) → **rewritten verbatim from the same evidence in this credentialed session and pushed**. next_action: A03. | 13be858d |
| A02 | phase A · **VERIFIED+PERSISTED** · this ledger created with the R176 shape. R176 ledger untouched. Fixed resume line resolves here (NNN=177 highest). next_action: A03. | 13be858d |
| A03 | phase A · **VERIFIED+PERSISTED** (gate re-run → A03b) · §3 re-verified from `check_repo.sh` + `green_manifest.json` → `evidence/r177/A03_governance/governance_constraints.md`. **F-R177-01 recorded**: `check_repo.sh:143` hardcoded round tuple ⇒ R176 Phase B production changes were outside budget enforcement; minimum fix = R177-FIX-01 (needs DEC-05). Secret-scan reality: of prompt lines 132/133/134 only **132** matches the gate patterns (values never printed). **Divergence vs directive**: CAPABILITY_IDS has **17** ids (16 + `dev.publish_modes`, R172 C7). next_action: A04. | 13be858d |
| A04 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A04_composition/composition_surface_map.md` + `routes_env_composed.json`: **37** create_app parameters (directive said ~35), 17 catalog ids with their state rule/seam/route, **79** routes in the env-composed profile (57 admin, 5 agent, 5 auth, 4 execute, 3 webhooks, 2+2 workspaces/projects, 3 listing, 1 healthz), operator-capability → seam table. Catalog completeness observation: agent runtime / source-change / skills import / workspaces-projects / evaluation are mounted but have no CAPABILITY_IDS row (closed-set edit → approval). next_action: A05. | 13be858d |
| A05 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A05_approval/approval_policy_map.md`. Enforcement of most-restrictive-wins is ALREADY COVERED (firewall 6 ordered paths; ToolCallGate both-authorities-consent; `DEFAULT_APPROVAL_REQUIREMENT=ALWAYS`; closed `approval_state`; R172 payload binding). Recording: five lifecycles persist their own decisions (`APPROVAL_DECISION` emitted by sourcechange + engineering ledger only); **MISSING**: a persisted composition-level capability-proposal record (the §7 decision sheet). Runtime TenantPolicies have empty `approval_gated_permissions` (firewall REQUIRE_APPROVAL exercised by tests only). DEC-01 check: memory/composer use their own closed gates (sensitivity/scope/secret guard, tenant-scoped keys), not the firewall vocabulary; no divergence, no second precedence model. next_action: A06 vocabulary table. | 3d688c44 |
| A06 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A06_vocabulary/vocabulary_mapping.md` (one row per operator term + the six 13 §2 types). Contract facts: **no `MemoryType` enum** (type = scope × source × user_id); only runtime writer of `MemoryStorePort.upsert` is GOLD promotion; `PreferenceLearningGate` exported but **never called at runtime** (F-R177-02, S3); 13 §2 types have no code expression (F-R177-03, S4); Soul/Teacher absent from code and fully expressible over memory+composer / ModelJudgePort+PromotionGate (F-R177-04, S4; literalisation = parallel-concept risk, needs approval). Explicit no-consciousness statement recorded. (Sandbox reset #2 between A05 and A06: nothing lost — all pushed.) next_action: A07 learning/knowledge lifecycle. | b740cd37 |
| A07 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A07_learning/learning_knowledge_lifecycle.md`. Ladder/gates/sanitizer real and deny-by-default. Gaps: **G-A07-1** PromotionSignals are caller-asserted booleans (admin.py:212-232) — gate correct over unverified inputs; **G-A07-2** `ModelJudgePort` NOT composed (app.py:2086) ⇒ Teacher-disabled IS the current state: evaluate() ceiling = VALIDATED, GOLD still reachable via human-approved promotion, pipeline unbroken; 22 §10 selector absent; **G-A07-3** no structured intake (CSV/Excel/file/API) — MISSING, must live outside core/; **G-A07-4** evaluation store in-memory even in durable profile; **G-A07-5** learning observability admin-only and split across routes. Teacher minimum design recorded (port binding + selection policy, no new contract term). next_action: A08. | 43c632a3 |
| A08 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A08_discovery/discovery_vs_authority.md`. Separation reading≠authority is **structurally held**: read-only default TenantPolicy, write/exec = distinct permissions (`source.read workspace.read/write/exec git.read/write`) + admin grant + one-use ticket + approval_policy ALWAYS + payload binding; jail resolve-then-relative_to; denylist shared by reader/writer; command + env allowlists; remote-trust allowlist; deny-by-default tool selection. Gaps: **F-R177-05** no persisted repository model (discovery transient per run; minimum = MemoryItem `scope=project, source=repo.map` via existing port); **F-R177-06** `list_files` truncates at 500 with no cursor. Large-repo scalability COVERED BUT NEEDS STRONGER EVIDENCE (no executed probe). (Reset #3 between A07 and A08; nothing lost.) next_action: A09 completeness matrix. | 3037d42c |
| A09 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A09_matrix/capability_completeness_matrix.md`: all 26 §12 items classified with the §19 closed set — **AC 15, PC 9, CSE 1 (observability), M/NN/D/B 0 standalone**; MISSING sub-gaps live inside PC rows (repository model, memory writers, structured intake, composition-level proposal record). R176 probe evidence reused, not re-run. Planning row: graph_planner exists but WorkflowRuntimePort has no engine binding (app.py:86). Four CONFIRMED gaps admitted to A10 research; memory-writer/Teacher/observability explicitly excluded from research (pattern already fixed by docs 13/22 or verification-only). next_action: A10 bounded research (time-boxed, Level 3/5 evidence with source+date). | 388af3d0 |
| A10 | phase A · **VERIFIED+PERSISTED** · `evidence/r177/A10_landscape/landscape_findings.md` — 4 searches (2026-09-08), Level 3/5, patterns only: (1) repo map = compact ranked context-selection artefact (aider/tree-sitter) → QEVION minimum = MemoryItem `scope=project source=repo.map` via existing port, parser outside core/; (2) ADR status ladder proposed→accepted/rejected, immutable → decision sheet = documentary entry in 60_DECISION_LOG now, optional admin-lifecycle kind later; (3) expectation-based validation + quarantine (GX) → intake adapter outside core/ feeding `capture_external` as RAW; (4) registry gated promotion on recorded artefacts (MLflow) → derive eval/regression/security signals from `evidence_refs`, refuse caller-asserted True. (Reset #4 during A10; 3 of 4 searches redone from memory of sources — recorded as such.) next_action: A11 assemble docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md + append 60_DECISION_LOG entries. | fc7d8481 |
| A11 | phase A · **VERIFIED+PERSISTED** · `docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md` §1–§10 (baseline, governance+F-R177-01, composition map, approval map, vocabulary, learning, discovery, completeness matrix, landscape, consolidated finding register of 13 rows). Appended to `final_docs_v3/60_DECISION_LOG.md` (v3 count still 20): **R177-DEC-01** precedence confirmed/no new model + Soul/Teacher vocabulary rulings; **R177-DEFER-01** register of 12 non-adopted ideas (REJECTED-AS-PARALLEL / DEFERRED). (Reset #5 lost part 2 once; re-appended.) next_action: A12 proposal pack — §11 decision sheets (PENDING APPROVAL) + §12 R177-FIX-nn register appended to the assessment. | 8ddfeffa |
| A12 | phase A · **VERIFIED+PERSISTED** · assessment §11 eleven §7-format decision sheets **R177-FIX-01..11, all PENDING APPROVAL, none implemented**; §12 register (sev, evidence, minimum change, files, failing-first test, rollback, closed-set impact, budget impact; ≈20 production files if all approved ⇒ needs round_r177 ceiling ⇒ FIX-01 first); §13 DEC-01 confirmed / DEC-02..05 OPEN with recommendations; §14 stop point + UNVERIFIED list. (Reset #6 lost §12–§14 once; re-appended.) next_action: A13 stop + report. | e664d5eb |
| A13 | phase A · **R177 PHASE A COMPLETE — STOP (§20), WAITING.** Invariants at stop: product-tree diff vs 13be858d = 0 lines (0 = untouched, incl. canonical prompt + frozen state file); v3 pack = 20; forbidden filenames present = 0; not_evaluated untouched (2/2); closed sets untouched. Deliverables on origin/main: `docs/r177/R177_CAPABILITY_FOUNDATION_ASSESSMENT.md` (§1–§14), `evidence/r177/A01…A10`, this ledger, 60_DECISION_LOG entries R177-DEC-01 + R177-DEFER-01. **Exact NEXT ACTION**: none until an explicit operator message names ids (e.g. `APPROVED: R177-FIX-01, DEC-05`); then Phase B row B0 records the approval and FIX-01 runs first through the §14 closed loop. Ambiguous replies ⇒ remain in WAIT. | e664d5eb |
| B0 | phase B · **APPROVAL RECORDED** · operator message (verbatim ids): `APPROVED: R177-FIX-01 … R177-FIX-11, DEC-05`; `DEC-01: CONFIRMED`; `DEC-02: APPROVED — redact all three exposed credential literals and rotate externally` (rotation is operator-owned, out of repo); `DEC-03: DEFERRED`; `DEC-04: APPROVED — execute all FIX-01 through FIX-11 in the dependency-safe order defined by the assessment, starting with FIX-01 … one approved unit at a time … closed-loop verification before proceeding`. Execution order (assessment §13): FIX-01 → FIX-05 → FIX-02 → FIX-08 → FIX-04 → FIX-06 → FIX-11 → FIX-03 → FIX-10 → FIX-09 → FIX-07 → DEC-02 redaction → final gate. Rollback point = 1d0c6388 (product tree byte-identical to 13be858d). Git scope: branch main, push after every unit. (Reset #7 erased the first B0 commit before push → rewritten.) next_action: B-01 failing-first test for the budget loop. | 1d0c6388 |
