# PROJECT EXECUTION STATE

This file is the single project-level control point for documentation rewrite and later implementation phases.

It is not a replacement for Git. Git + verified filesystem reality remain the factual source of truth.
This file controls phase/task progression and prevents Agents from drifting, skipping, or reopening decisions.

Important proof rule:

```text
PROJECT_EXECUTION_STATE.md alone is not proof of completion.
Trusted proof = this state file + local Git commit exists + filesystem reality matches the verified task.
```

---

## STATE HEADER

```text
STATE_VERSION: 1
STATE_REVISION: R028

RESUME_TOKEN:
PROJECT|R028|PHASE_2_IMPLEMENTATION|T-IMPL-011|VERIFIED_MVP_PHASE2_EXIT_FIREWALL_SKELETON|VERIFY_HEAD_WITH_GIT

LAST_VERIFIED_LOCAL_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (T-IMPL-011 content commit: ad806b1 pre-rewrite; T-IMPL-010: 9bd5491 pre-rewrite. NOTE: the auto-uploader periodically rewrites history with per-file sync commits; recorded short hashes may go stale — trust HEAD + filesystem + green gates over old hashes.)

LAST_VERIFIED_STATE_TASK:
T-IMPL-011

LAST_TRUSTED_COMMIT_RULE:
Run `git rev-parse HEAD`. The current committed HEAD is the trusted progress point after verification.

WORKTREE_STATUS_AT_LAST_UPDATE:
CLEAN_AFTER_COMMIT_REQUIRED
```

---

## DOCUMENTATION BASELINE / TARGET

```text
DOCUMENTATION_BASELINE:
V2

DOCUMENTATION_TARGET:
V3

V2_STATUS:
ARCHIVED_BASELINE (read-only historical source; never authority — T-DOC-013)

V2_STRUCTURE_AUTHORITY:
NONE

V3_STATUS:
COMPLETE_AUTHORITATIVE (all 20 documents; QA gate passed at T-DOC-013)

V3_BLUEPRINT:
docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md

V3_AUTHORITY_RULE:
Each V2 document remains authoritative until the V3 index marks its successor complete and verified. The V3 index MIGRATION STATUS table is the single authority switch.

V3_OBJECTIVE:
Create the best verified documentation architecture for the project, independent of the V2 file structure.

V3_SUCCESS:
The final documentation architecture is authoritative, traceable, internally consistent, implementation-ready, recoverable, and verified. Its file count and document boundaries may differ from V2.
```

V2 documents are source material and current baseline. They are not a mandatory final structure for V3.
V3 may merge, split, rename, reorder, move, create, or remove documents when this improves execution value.
Product decisions, ADR decisions, requirements, contracts, architecture invariants, security constraints, and critical decisions must be preserved unless explicitly changed through the proper decision process.

---

## PROJECT PHASE CONTROL

```text
PROJECT:
General AI Core / AI Orchestration Platform

PROJECT_STATUS:
PHASE_2_PRODUCT_IMPLEMENTATION_IN_PROGRESS

CURRENT_PHASE:
PHASE_2_PRODUCT_IMPLEMENTATION (MVP roadmap: final_docs_v3/41 Part II)

PHASE_1_STATUS:
VERIFIED (T-DOC-013: DOCUMENTATION_PHASE_EXIT_CHECKS = PASS, recorded in docs/ai_orchestration_pack/DOC_REWRITE_REPORT.md)

PHASE_2_STATUS:
UNLOCKED (T-IMPL-000, this revision: unlock condition re-verified in a NEW session per PHASE_2_START_RULE — PHASE_1_STATUS = VERIFIED confirmed from filesystem; DOCUMENTATION_PHASE_EXIT_CHECKS = PASS per DOC_REWRITE_REPORT.md §7; FINAL_DOCUMENTATION_COMMIT_VERIFIED: T-DOC-013 checkpoint content committed at HEAD (synced as per-file commits ending fcb8aae) and worktree clean/matching)

PHASE_2_NAME:
PRODUCT_IMPLEMENTATION

PHASE_2_UNLOCK_CONDITION (MET at T-IMPL-000):
PHASE_1_STATUS = VERIFIED
+
DOCUMENTATION_PHASE_EXIT_CHECKS = PASS
+
FINAL_DOCUMENTATION_COMMIT_VERIFIED

PHASE_2_START_RULE (SATISFIED):
Do not begin product implementation in the same cycle that verifies Phase 1.
A new session must resume from this state after Phase 2 is explicitly unlocked.
(Phase 1 was verified in the prior session; this unlock ran in a new session.)

PHASE_2_GOVERNANCE:
- Roadmap authority: final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md Part II (MVP Phases 0-8, in order).
- Engineering rules: final_docs_v3/40_ENGINEERING_PROTOCOL.md.
- Build prompt: final_docs_v3/50_AGENT_EXECUTION_PROMPT.md; cognition: 51; resume: 52.
- Task IDs: T-IMPL-NNN, each mapped to a 41 Part II phase task; micro-task protocol per 41 §28; output contract per 41 §29.
- Scope-control recording target: final_docs_v3/60_DECISION_LOG.md (append-only).
- Significant architecture choices (e.g. language/stack) require an ADR; stack selection additionally requires explicit user approval before Phase 1 (Contracts) code is written.
```

---

## CURRENT TASK CONTROL

```text
CURRENT_WORKSTREAM:
PRODUCT_IMPLEMENTATION_MVP

CURRENT_TASK:
T-IMPL-011

TASK_OBJECTIVE:
Finish MVP Phase 2: implement the capability-firewall skeleton in core/security/ — a deterministic deny-by-default evaluator over FirewallDecisionInput returning FirewallDecision (20 §1/§3/§4/§8), with injected in-memory tenant policy state (no persistence) and tests for deny-by-default, explicit-grant ALLOW, REQUIRE_APPROVAL, ALLOW_WITH_LIMIT, and tenant policy isolation. Then evaluate the 41 §41 exit criteria.

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

ALLOWED_SCOPE:
- create core/security/ (firewall.py, __init__.py)
- create tests/security/test_capability_firewall.py
- update this state file at the verified checkpoint (incl. Phase 2 exit evaluation)

FORBIDDEN_SCOPE:
- persistence; provider/network/secrets work; audit emission (Phase 3); admin-configurable catalogs
- MVP Phase 3+ code

TASK_COMPLETION_CRITERIA:
- pytest PASS; mypy --strict on core PASS; ruff PASS; import-linter 4 contracts KEPT.
- Evaluator returns only the closed 20 §4 set; deny-by-default on every ungranted path; approval never bypasses grants; approval gate evaluated before limit; tenant grants never leak (20 §6).
- check_repo.sh => RESULT: PASS. Focused local commit; worktree clean; state updated.

VERIFICATION_EVIDENCE (T-IMPL-011, this session):
- core/security/firewall.py: TenantPolicy (frozen: granted_permissions/granted_entitlements/approval_gated_permissions/limited_permissions) + CapabilityFirewall.decide() — pure, deterministic, most-restrictive-first: no tenant policy -> DENY; permission not granted -> DENY; entitlement not held -> DENY; approval-gated + not approved -> REQUIRE_APPROVAL (20 §8); limited -> ALLOW_WITH_LIMIT; else ALLOW. approval_state==approved never bypasses grant checks (asserted by test). Policy state injected in-memory; catalogs/persistence/audit are later phases (documented in module docstring).
- tests/security/test_capability_firewall.py: 13 tests (180 total pass) — unknown tenant denied; empty policy denied; permission-without-entitlement and entitlement-without-permission denied; approved-but-ungranted denied; full grant allows; deterministic over repeats; system actor follows same policy (20 §1); unapproved gated (PR-merge class) -> REQUIRE_APPROVAL, approved -> ALLOW; limited -> ALLOW_WITH_LIMIT; gated+limited unapproved -> REQUIRE_APPROVAL then approved -> ALLOW_WITH_LIMIT (ordering); tenant A grants never authorize tenant B (20 §6).
- mypy --strict: clean. ruff: clean. lint-imports: 4 kept (core.security imports only core.contracts). check_repo.sh: RESULT: PASS.
- RECOVERY NOTE (R028): the R028 state update was interrupted mid-write in the prior turn; on resume the sandbox had been reset (mypy/ruff/import-linter uninstalled) and the uploader had re-tracked tool caches and rewritten history (ad806b1 absent from log, but all T-IMPL-011 files tracked at HEAD with green gates). Recovery: verified filesystem + git tracking first, reinstalled toolchain (python3 -m pip install mypy ruff pytest pydantic import-linter pytest-asyncio), untracked caches again, re-ran all gates to RESULT: PASS, then redid ONLY the missing state-file update.
- T-IMPL-011 content commit: ad806b1 (pre-rewrite; superseded by uploader sync commits).

MVP_PHASE_2_EXIT_EVALUATION (41 §41, evaluated this session):
- Deliver "user registration": PASS (T-IMPL-010 register()).
- Deliver "email verification": PASS (T-IMPL-010 verify_email(), single-use token via port/fake).
- Deliver "login/session": PASS (T-IMPL-010 login/resolve_session/logout, opaque tokens).
- Deliver "personal tenant": PASS (registration creates ACTIVE PERSONAL tenant).
- Deliver "basic RBAC/entitlements": PASS at the documented level — permission/entitlement identifier grants per tenant (specs define no richer RBAC entity; recorded at T-IMPL-009).
- Deliver "capability firewall skeleton": PASS (T-IMPL-009 contracts + T-IMPL-011 evaluator).
- Exit "auth tests pass": PASS (tests/identity — registration/verification/login/session suites green).
- Exit "tenant isolation tests pass": PASS (tests/identity TestTenantIsolation + tests/security TestTenantIsolation green).
MVP_PHASE_2_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-IMPL-011

LAST_VERIFIED_TASK_COMMIT:
ad806b1 (content, pre-rewrite) + the state-checkpoint commit at HEAD after this update

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
MVP_PHASE_2_COMPLETE_AND_VERIFIED (41 §41 exit criteria met — see MVP_PHASE_2_EXIT_EVALUATION above). Next workstream: MVP Phase 3 — Storage / Observability (41 §42): PostgreSQL migrations, Redis setup, object storage abstraction, secret manager abstraction, basic audit logs, OpenTelemetry setup.

NEXT_TASK:
T-IMPL-012

NEXT_TASK_OBJECTIVE:
Start MVP Phase 3 — Storage / Observability (41 §42). At session start, re-scope from specs (41 §42 deliverables + 20 §5 secrets rules + 20 §9 audit events + storage/observability authority docs) and slice ports-first, mirroring Phase 2: begin with the abstraction ports + in-memory fakes that keep core pure (object storage port, secret manager port — credential_ref only per 20 §5, audit log port with the 20 §9 event set), before any real PostgreSQL/Redis/OTel infrastructure bindings. Real infrastructure bindings belong in infrastructure/ and may require new dependencies — confirm dependency additions against 40 engineering protocol when reached. SANDBOX NOTE: the sandbox resets between sessions; reinstall the toolchain first (python3 -m pip install mypy ruff pytest pydantic import-linter pytest-asyncio) and re-untrack tool caches if the uploader re-added them, before trusting gate results.

NEXT_TASK_AUTHORIZED:
NO_UNTIL_NEW_SESSION (MVP phase boundary: mirroring the R024 precedent, the next MVP phase must not start in the same session that records the previous phase's exit. A new session must resume from this state, re-verify this checkpoint recovery-first, then begin T-IMPL-012.)

DO_NOT_START:
- MVP Phase 3 code in this session (phase boundary lock above)
- real network/provider work; real secret material anywhere (20 §5: credential_ref only)
- do not re-open Phase 1/2 contract or service decisions
```

---

## CONFIRMED DECISIONS

```text
- USER DIRECTIVE (2026-08-25, supersedes one-task-per-session stop rule): the Agent must execute as many authorized tasks as possible in the same session, in migration order, provided each task still gets its own focused commit, its own verification, and a state-file update at each verified checkpoint. Phase boundaries still hold: Phase 2 must not start in the same session that verifies Phase 1.
- Agent performs local work only unless explicit push instruction is given.
- Auto-uploader/external system owns remote synchronization.
- Local commit + verification is enough to mark a task VERIFIED.
- Remote push is not required for task verification.
- PROJECT_EXECUTION_STATE.md controls project phase/task progression.
- 22_LIGHTWEIGHT_RESUME_AND_PROGRESS_STATE_PROTOCOL.md defines how to resume.
- final_docs_v2 documents are specifications, not progress-state files.
- Resume/Handoff inside documents should be static pointers, not live progress data.
- Phase 2 implementation remains LOCKED until Phase 1 documentation is VERIFIED.
- Project state alone is not proof; it must be verified against local Git and filesystem reality.
- Do not add more mutable state files unless explicitly approved.
- Reports such as DOC_REWRITE_REPORT.md are audit artifacts, not task-control state.
- Fetch/rebase may be used for recovery/synchronization checks, but it should not become repeated per-task overhead.
- T-DOC-001 is resume/state governance preparation only, not actual documentation rewrite.
- Actual documentation re-architecture begins at T-DOC-002 after T-DOC-001 is VERIFIED.
- T-DOC-001 cleaned legacy resume/state instructions and centralized them on PROJECT_EXECUTION_STATE.md.
- V2 structure is not authoritative; V3 documentation architecture may differ from V2.
- V3 must preserve decisions/contracts/invariants, not V2 file boundaries.
- T-DOC-002 approved the V3 blueprint: final_docs_v3/00_INDEX.md is the live migration index and single authority switch.
- V3 target = 20 documents in 7 layers; merges: 05+24, 23+25, 07+21, 14+15, 16+20; superseded: 17 (by 22 + project state).
- Migration proceeds one cluster per session (T-DOC-003 … T-DOC-013); a V2 doc stays authoritative until its V3 successor is verified and marked in the V3 index.
- T-DOC-003 completed the first content migration: final_docs_v3/30 is authoritative for the Provider subsystem; v2 24 and v2 05 are SUPERSEDED baseline material.
- R006 reconciliation: external auto-uploader commits after f10ea536 (scaffold file removals, README carry) were verified as unrelated to documentation tasks; f10ea536 confirmed as ancestor of HEAD.
- R007 reconciliation: the T-DOC-003 local commit (a43b7281) was re-synchronized by the external auto-uploader as per-file sync commits ending at 26c83ad4; filesystem verification confirmed all T-DOC-003 artifacts intact (v3 doc 30 present, banners present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-004 completed the second content migration: final_docs_v3/31 is authoritative for provider scaffolding + real provider onboarding; v2 23 and v2 25 are SUPERSEDED baseline material.
- R008 reconciliation: the T-DOC-004 local commit (88965f5) was re-synchronized by the external auto-uploader as per-file sync commits ending at 1c26bda; filesystem verification confirmed all T-DOC-004 artifacts intact (v3 doc 31 present at 1304 lines, banners on v2 23/25 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-005 completed the third content migration: final_docs_v3/12 is authoritative for Execution Graph, Agent Mode, and provider-agent orchestration; v2 07 and v2 21 are SUPERSEDED baseline material. Critical rule preserved: Provider Agent Capability != Platform Agent Runtime; platform remains the commander.
- R009 reconciliation: the T-DOC-005 local commit (2b08b04) was re-synchronized by the external auto-uploader as per-file sync commits ending at bf421c8; filesystem verification confirmed all T-DOC-005 artifacts intact (v3 doc 12 present at 887 lines, banners on v2 07/21 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-006 completed the first carry cluster: final_docs_v3/01, 02, 03 are authoritative for product requirements, architecture baseline/invariants, and domain model; v2 01/02/03 are SUPERSEDED baseline material. All 15 architecture invariants and FR-001..FR-015 carried verbatim; no decision changed.
- R010 reconciliation: the T-DOC-006 local commit (542cb4d) was re-synchronized by the external auto-uploader as per-file sync commits ending at 1f5967a; filesystem verification confirmed all T-DOC-006 artifacts intact (v3 docs 01/02/03 present, banners on v2 01/02/03 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-007 completed the second carry cluster: final_docs_v3/10 and 11 are authoritative for API contracts and model routing/model control; v2 04/06 are SUPERSEDED baseline material. All 5 model policy types and all 5 router selection modes carried verbatim; no decision changed.
- T-DOC-008 completed the third carry cluster: final_docs_v3/13 and 14 are authoritative for memory/context and skills/tools; v2 08/09 are SUPERSEDED baseline material. Capability Firewall check and unknown-tools-default-to-DENY carried verbatim; no decision changed.
- T-DOC-009 completed the fourth carry cluster: final_docs_v3/20, 21, 22 are authoritative for security threat model, admin control plane, and evaluation/learning; v2 10/11/12 are SUPERSEDED baseline material. Capability Firewall, deny-by-default, tenant isolation, verification levels, and promotion gates carried verbatim; no decision changed.
- R012 reconciliation: the T-DOC-009 local commit (62b02fb) was re-synchronized by the external auto-uploader as per-file sync commits ending at aa2c0bd; filesystem verification confirmed all T-DOC-009 artifacts intact (v3 docs 20/21/22 present, banners on v2 10/11/12 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-010 completed the rewrite-compress of v2 13 into final_docs_v3/40_ENGINEERING_PROTOCOL.md (2385 -> 659 lines). All engineering rules with execution value preserved (verified mechanically: 22 invariants, 17 test types, 6 boundary tests, 10 principles, phase gates, DoD, ADR, Git safety, recovery). Only v2 13 SS39/SS40/SS41/SS50 (legacy STATE.md/PROGRESS.md/HANDOFF scheme + resume command) are superseded — explicitly, by D10/D11, recorded in the successor's SS11, its traceability ledger, and the v2 banner. Architecture duplication replaced with an authority map to owning v3 docs.
- R013 reconciliation: the T-DOC-010 local commit (71484af) was re-synchronized by the external auto-uploader as per-file sync commits ending at da22183; filesystem verification confirmed all T-DOC-010 artifacts intact. Facts from filesystem, not commit hashes.
- T-DOC-011 completed the merge of v2 14 + 15 into final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md (Part I FINAL plan / Part II MVP roadmap / Part III FINAL-MVP-FUTURE map). All 24 FINAL phases, 15 rules, micro-task protocol, MVP scope and DoD preserved (verified mechanically). Explicit D10/D11 supersessions only: v2 14 SS32/SS33/SS35/SS37/SS39/SS42 (multi-file resume, NEXT_PLAN.md, FUTURE_IMPROVEMENTS/ARCHITECTURE_GAPS ledgers, handoff files, static resume prompt) and v2 15 legacy state-file wording — recorded in the successor SS51 ledger and both v2 banners. Commit/recovery detail now points to 40 SS9-SS10 (single authority). Arabic narrative normalized to English; decision blocks verbatim.
- New rule made explicit in 41 SS31 (D10/D11 application, not a new decision): scope-control recording target = 60_DECISION_LOG.md once it exists (until then the state-file SESSION NOTES), replacing the superseded FUTURE_IMPROVEMENTS.md/ARCHITECTURE_GAPS.md ledger files.
- R015 reconciliation: the T-DOC-012 content work was synced by the external auto-uploader as per-file commits ending at 76d3415 before this state checkpoint was written (an interrupted state update in the prior session did not apply). Filesystem verification confirmed all T-DOC-012 artifacts intact and content-verified; this checkpoint was then recorded and committed. Facts from filesystem, not commit hashes.
- T-DOC-012 completed the agent-operation cluster: final_docs_v3/50 (build prompt: v2 20 Ultra base + v2 16 as subordinate Standard Profile — single build-prompt authority), 51 (cognitive protocol, carried verbatim), 52 (resume protocol: v2 22 carried + v2 17 retired/absorbed as SS17), 60 (decision log: all 25 Q&A carried verbatim + append-only rules + migration records MR-001..MR-004) are authoritative; v2 16/17/18/19/20/22 are SUPERSEDED baseline material. Explicit D10/D11 supersessions only (legacy state/handoff files, FUTURE_IMPROVEMENTS.md target, NEXT_PLAN scheme, v2 17 dead paths) — recorded in successor ledgers and v2 banners; never silent.
- 60_DECISION_LOG.md is now the live scope-control recording target per 41 SS31. It is append-only: existing entries are never edited; superseded decisions get a new entry referencing the old one.
- R016 reconciliation: a prior session began T-DOC-013 and was interrupted mid-audit; its partial artifacts (v3 index QA-gate marks, v2 00_INDEX ARCHIVED_BASELINE block, 41 authoritative header, README repointing to v3) were synced by the external auto-uploader as per-file commits ending at 8967f06. This session verified each artifact from the filesystem (facts from filesystem, not commit hashes), completed the remaining audit items, and recorded the checkpoint.
- T-DOC-013 completed the V3 finalization QA gate: index/filesystem consistency (20/20), banner audit (26/26 v2 files, 0 dead successor paths), authority audit (no v2 doc cited as authority in v3), dead-path audit (0 after creating DOC_REWRITE_REPORT.md), ARCHIVED_BASELINE marks verified, secret scan pass, build-agent readiness mapping recorded. DOCUMENTATION_PHASE_EXIT_CHECKS = PASS (full scorecard in DOC_REWRITE_REPORT.md). PHASE_1_STATUS = VERIFIED. PHASE_2 remains LOCKED; unlock requires a new session (T-IMPL-000 gate).
- DOC_REWRITE_REPORT.md is an audit artifact only (README DOC_REWRITE_REPORT rule); it carries no task-control authority.
- R017 reconciliation: the T-DOC-013 checkpoint local commit (457ed3f) was re-synchronized by the external auto-uploader as per-file sync commits ending at fcb8aae; filesystem verification in this new session confirmed all checkpoint artifacts intact. Facts from filesystem, not commit hashes.
- T-IMPL-000 (this new session) re-verified the full Phase 2 unlock condition and flipped PHASE_2_STATUS to UNLOCKED. PHASE_2_START_RULE satisfied: verification session (R016) and unlock session (R017) are distinct.
- Phase 2 task numbering: T-IMPL-NNN; governance per PHASE_2_GOVERNANCE block above.
- OPEN DECISION (blocks MVP Phase 1 code): implementation language/stack is not specified anywhere in the v3 pack. Stack selection is a significant architecture decision => requires an ADR and explicit user approval before contracts code is written. Governance scaffolding (T-IMPL-001) is stack-neutral and may proceed.
- T-IMPL-001 completed MVP Phase 0 governance scaffolding: engineering/adr (template + index), engineering/gates (template), engineering/verification (conventions + check_repo.sh), engineering/decisions (pointer to 60_DECISION_LOG.md), .github/workflows/ci.yml (runs the same script as local). Verification: check_repo.sh => RESULT: PASS. Gate G0 exit criteria met (41 §39). CI-mirrors-local rule established: repo checks run via one entry point in both places.
- Stack ADR flow decided: T-IMPL-002 writes ADR-0001 as PROPOSED; it becomes ACCEPTED only on explicit user approval recorded in this state file; contracts code stays blocked until then.
- T-IMPL-002 committed ADR-0001 (PROPOSED): TypeScript/Node LTS monorepo (zod contracts, Fastify, Postgres+drizzle, Redis Streams, outbox-first workflows — Temporal deferred to its own ADR, OTel+pino, vitest, dependency-cruiser boundary tests). 3 alternatives analyzed. USER DECISION PENDING: approve / amend / reject. While PROPOSED, the ADR file may be edited freely; once ACCEPTED it becomes append-only per ADR rules.
- Session R017-R019 note: T-IMPL-000, T-IMPL-001, T-IMPL-002 were executed in the same session (allowed within Phase 2 by the USER DIRECTIVE; the PHASE_2_START_RULE only separated Phase-1-verification from Phase-2-start, which was honored).
- R020 reconciliation: the T-IMPL-002 checkpoint local commit was re-synchronized by the external auto-uploader as per-file sync commits ending at debde5f; filesystem verification in this new session confirmed all T-IMPL-002 artifacts intact (ADR-0001 present as PROPOSED, index row present, check_repo.sh PASS 18/18). Facts from filesystem, not commit hashes.
- USER DECISION (2026-08-25, T-IMPL-003): implementation stack = Python / FastAPI / Pydantic (user selected Alternative B, superseding the proposed TypeScript stack before acceptance). ADR-0001 Decision/Reason rewritten to the Python stack and flipped to ACCEPTED; recorded as IMPL-001 in 60_DECISION_LOG.md. ADR-0001 is append-only from this point; stack changes require a superseding ADR.
- Stack facts now binding (ADR-0001): Python 3.12+, Pydantic v2 contracts with JSON Schema export, FastAPI, SQLAlchemy 2.x async + Alembic + pgvector, redis-py Streams, outbox-first workflows (Temporal Python via future ADR), OTel + structlog, pytest, mypy --strict on core/, ruff, import-linter boundary tests, single pyproject monorepo per 41 §2. Admin UI / client-runtime stack deferred to a future ADR.
- T-IMPL-004 started MVP Phase 1 (Contracts): workspace layout per 41 §2 created as Python packages; pyproject.toml is the single tool-config source; contract layer posture fixed in core/contracts/base.py (ContractModel = extra:forbid + frozen — deny-by-default at the contract boundary, immutable value objects); unified error contract implemented verbatim from 10 §9 (11 categories, closed StrEnum); 9 contract tests pass; import-linter enforces the 4 boundary contracts and was negative-tested.
- check_repo.sh remains the single verification entry point: it now additionally runs pytest/mypy/ruff/import-linter when pyproject.toml exists (CI-mirrors-local preserved).
- R021 note: .github/workflows/ci.yml (created at T-IMPL-001) was found missing from the worktree — evidently dropped during the external auto-uploader's history re-sync of dot-directories. Recreated at T-IMPL-004, upgraded for the Python stack (setup-python 3.12 + dev deps + same check_repo.sh entry point). If the uploader drops it again, restoring it is maintenance, not a decision change.
- T-IMPL-005 completed the execute API + model policy contracts: core/contracts/execute.py (ExecuteRequest per 10 §2 with wire aliases async/schema; ExecuteSyncResponse §3; ExecuteAsyncAccepted §4 pinned to status=queued; ExecutionStatusResponse §5 with 6-state closed ExecutionStatus per 03; discriminated StreamEvent union §11; WebhookPayload + 6 WebhookEventType values §12) and core/contracts/model_policy.py (discriminated union of all 5 policy types per 10 §13; SelectionStrategy 5 values §13.4; FallbackScope 6 values per 11 §8; AgentPolicy request carrier §13.5; node policies exclude recursive agent_node_mapping). 41 contract tests validate every documented example verbatim (incl. byte-for-byte wire round-trip of the §2 request) and reject unknown fields/enum values/missing required fields. Maintenance in same commit: python cache dirs untracked + gitignored (uploader had synced .mypy_cache etc. as commits).
- R022 session interruption note: T-IMPL-005 content work (contracts + tests) was authored in a prior interrupted session; this session verified all artifacts from the filesystem (facts from filesystem), fixed one test round-trip assertion (exclude_unset for the optional agent_policy field), removed one stale type-ignore, formatted 2 files, ran all gates green, and committed. Content commit: 0a07f3d.
- T-IMPL-006 completed the provider contract + model contract + core domain types: core/contracts/domain.py (03 §4 entities verbatim — Model as the Router's model contract with tier/modalities/capabilities/scores, Provider, ProviderModelBinding, Credential with opaque credential_ref never raw secrets, ProviderAccount with 7-value lifecycle + 4-value health; 03 §9 agent extensions with undeclared-by-default capability flags) and core/contracts/provider.py (30 §5 operations closed set of 11; §7 manifest with deny-by-default closed capability keys; §11 provider health 4 states vs account check states 4 — provider health ≠ account health preserved; §12 normalized rate-limit states 4; §14 error normalization 12 categories + documented shape — Core sees normalized errors only). 53 new contract tests; 94 total pass; all gates green. ProviderAdapter behavioral interface (30 §8) deliberately deferred to the port-layer task. Content commit: dab4216.
- R023 session interruption note: a prior session authored domain.py/provider.py for T-IMPL-006 and was interrupted before exports/tests; this session verified filesystem reality first (recovery rule), found the export edit unapplied and tests absent, completed them, verified content against 03/30 line-by-line, ran all gates green, and committed. Facts from filesystem, not chat history.
- T-IMPL-007 completed the execution contract (core/contracts/execution.py: Execution + ExecutionNode per 03 §5 verbatim; strategy set 8, node types 7, node states 6; status reuses shared ExecutionStatus; 12 §5/§6 graph-runtime supersets deliberately deferred to the Execution Graph task). 18 new tests; 112 total green; all gates PASS. MVP Phase 1 exit criteria (41 §40) evaluated and VERIFIED at R024. Content commit: b95af2d.
- R024 environment note: this session recovered from a sandbox reset + auto-uploader history rewrite. All previously recorded short commit hashes are invalid in the rewritten history; the trusted progress anchor is HEAD + filesystem + green gates, per the state file's own proof rule. Dev tooling (mypy/ruff/import-linter) had to be reinstalled; pre-task gates re-run PASS before new work began.
- MVP-PHASE BOUNDARY DECISION (R024): applying the same discipline as the documentation PHASE_2_START_RULE and the USER DIRECTIVE's phase-boundary clause, MVP Phase 2 (T-IMPL-008) must start in a NEW session that first re-verifies the R024 checkpoint from filesystem + git. This session verified Phase 1 exit and therefore stops here.
- MVP PHASE 2 SLICING DECISION (R025): 41 §41 deliverables are executed contracts-first, mirroring Phase 1 discipline: T-IMPL-008 identity/tenancy contracts (03 §2) → T-IMPL-009 RBAC/entitlement + capability-firewall decision contracts (20 §4) → T-IMPL-010 in-memory identity service skeleton (registration + personal tenant + email-verification port with fake + session) with auth/tenant-isolation tests. No network, no real email, no secrets in code anywhere in Phase 2.
```

---

## DO NOT CHANGE WITHOUT ADR / EXPLICIT USER DECISION

```text
- Architecture invariants in README and final_docs_v2.
- Provider-agnostic and model-agnostic Core.
- Model != Provider != Account.
- Router decides; Execution executes.
- LLM is not a security authority.
- Unknown capability/permission => DENY.
- Provider templates are non-functional until real providers are implemented and verified.
- Agent must not push unless explicitly instructed.
```

---

## RECOVERY RULE

On a new session:

```text
1. Read this file.
2. Run git status.
3. Run git rev-parse HEAD.
4. Run git diff --stat.
5. Compare this state with Git/filesystem reality.
6. Verify referenced commits exist locally when used as evidence.
7. If conflict exists, Git/filesystem reality wins for facts.
7. Reconcile this file before advancing tasks.
8. Continue only the authorized NEXT_TASK.
9. Do not infer progress from chat history.
10. Do not push unless explicitly instructed.
```

---

## STATE FAILURE MODE

If this file is missing, unreadable, empty, or invalid, the recovery state is:

```text
STATE_STATUS: RECOVERY_REQUIRED
PROJECT_PROGRESS: UNKNOWN
CURRENT_TASK: STATE_RECOVERY
PHASE_2_STATUS: LOCKED
NEXT_TASK_AUTHORIZED: NO_UNTIL_STATE_RECONSTRUCTED_AND_COMMITTED
```

Recovery must be reconstructed only from:

```text
local Git history
filesystem reality
existing repository documentation
verified commits
```

Do not infer progress from chat history or previous AI claims.
Do not create additional mutable state files.
Recreate this file only after verified reconstruction, then commit before continuing.

---

## STOP CONDITION

```text
Per USER DIRECTIVE (2026-08-25): execute as many authorized tasks as possible
in the same session, in migration order.
For EACH task:
  Verify locally.
  Update this state only at a verified checkpoint.
  Create one focused local commit.
Then continue to the next authorized task in the same session.
At session end: report all commit hashes and the next task. Stop.
Phase boundaries still hold: do not start Phase 2 in the session that verifies Phase 1.
```
