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
STATE_REVISION: R016

RESUME_TOKEN:
PROJECT|R016|PHASE_1_DOCUMENTATION|T-DOC-013|VERIFIED|VERIFY_HEAD_WITH_GIT

LAST_VERIFIED_LOCAL_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (T-DOC-013 commit; the prior session's T-DOC-013 partial work — v3 index QA-gate marks, v2 00_INDEX ARCHIVED_BASELINE block, 41 authoritative header, README repointing — was synced by the external auto-uploader as per-file commits ending at 8967f06; this session verified those artifacts from the filesystem, completed the remaining exit checks, created DOC_REWRITE_REPORT.md, and committed this checkpoint — facts verified from filesystem, not commit hashes)

LAST_VERIFIED_STATE_TASK:
T-DOC-013

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
PHASE_1_DOCUMENTATION_VERIFIED_PHASE_2_LOCKED

CURRENT_PHASE:
PHASE_1_DOCUMENTATION_REARCHITECTURE (COMPLETE)

PHASE_1_STATUS:
VERIFIED (T-DOC-013: DOCUMENTATION_PHASE_EXIT_CHECKS = PASS, recorded in docs/ai_orchestration_pack/DOC_REWRITE_REPORT.md)

PHASE_2_STATUS:
LOCKED

PHASE_2_NAME:
PRODUCT_IMPLEMENTATION

PHASE_2_UNLOCK_CONDITION:
PHASE_1_STATUS = VERIFIED
+
DOCUMENTATION_PHASE_EXIT_CHECKS = PASS
+
FINAL_DOCUMENTATION_COMMIT_VERIFIED

PHASE_2_START_RULE:
Do not begin product implementation in the same cycle that verifies Phase 1.
A new session must resume from this state after Phase 2 is explicitly unlocked.
```

---

## CURRENT TASK CONTROL

```text
CURRENT_WORKSTREAM:
DOCUMENTATION_REARCHITECTURE

CURRENT_TASK:
T-DOC-013

TASK_OBJECTIVE:
V3 finalization: QA gate + Phase 1 exit checks. (1) Cross-reference audit of all 20 v3 docs: no reference to a v2 doc as authority, no dead paths, index table consistent with filesystem. (2) Verify every v2 doc (01-25) carries a SUPERSEDED banner pointing to its v3 successor. (3) Mark the v2 pack ARCHIVED_BASELINE in the v3 index and v2 00_INDEX.md. (4) Run the DOCUMENTATION_PHASE_EXIT_CHECKS and record results. (5) If all checks pass, set PHASE_1_STATUS = VERIFIED in this state file (Phase 2 stays LOCKED; per PHASE_2_START_RULE it must not start in the same session that verifies Phase 1).

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

ALLOWED_SCOPE:
- audit-only edits: QA-gate marks in final_docs_v3/00_INDEX.md, ARCHIVED_BASELINE block in final_docs_v2/00_INDEX.md, README repointing to v3
- create DOC_REWRITE_REPORT.md (audit artifact, not task-control state)
- update this state file at the verified checkpoint (PHASE_1_STATUS = VERIFIED)

FORBIDDEN_SCOPE:
- change any decision, rule, checklist, or output contract
- migrate or rewrite any document content
- implement product code (Phase 2 LOCKED)
- create additional mutable state files

TASK_COMPLETION_CRITERIA:
- All 20 v3 docs audited: no v2 doc cited as authority; no dead paths; index table matches filesystem.
- 26/26 v2 docs (00 index + 01-25) carry SUPERSEDED/ARCHIVED banners; every successor path exists.
- v2 pack marked ARCHIVED_BASELINE in v3 index and v2 00_INDEX.md.
- DOCUMENTATION_PHASE_EXIT_CHECKS run and recorded (DOC_REWRITE_REPORT.md).
- PHASE_1_STATUS = VERIFIED in this state file; PHASE_2 stays LOCKED.
- Git diff reviewed; focused local commit created and verified.

VERIFICATION_EVIDENCE (T-DOC-013, verified this session from filesystem):
- Index-vs-filesystem: 20 files on disk = 20 rows in the v3 index table; the 4 extra names parsed from the index are the Removed/Superseded ledger (17/16/21/05), expected.
- Banner audit: 26/26 v2 files carry SUPERSEDED/ARCHIVED banners; every final_docs_v3 successor path referenced by a banner exists on disk (0 dead successors).
- Authority audit: every final_docs_v2/ mention inside v3 docs is a SOURCES/SUPERSEDES/historical block, never an authority citation.
- Dead-path audit: all repo paths referenced from v3 docs + README exist (DOC_REWRITE_REPORT.md was the single missing referenced artifact; created by this task as an audit artifact).
- ARCHIVED_BASELINE marks present: v3 index header + §2 row; v2 00_INDEX.md PACK STATUS block; README authority order updated.
- Exit checks: all rows PASS — full scorecard in docs/ai_orchestration_pack/DOC_REWRITE_REPORT.md §7 (incl. secret scan pass and build-agent readiness test mapping).
- Prior-session partial work (interrupted) reconciled: v3 index QA marks, v2 index block, README repointing, 41 header — all found intact on disk and in synced commits ending at 8967f06 before this session's completion work.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-013

LAST_VERIFIED_TASK_COMMIT:
VERIFY_WITH_CURRENT_LOCAL_HEAD_AFTER_COMMIT

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
PHASE_1_COMPLETE_AWAITING_PHASE_2_UNLOCK

NEXT_TASK:
T-IMPL-000 (PHASE_2_UNLOCK_GATE)

NEXT_TASK_OBJECTIVE:
Phase 2 unlock gate — must run in a NEW session (PHASE_2_START_RULE forbids starting Phase 2 in the session that verified Phase 1). In the new session: (1) re-verify PHASE_1_STATUS = VERIFIED against filesystem + Git; (2) confirm FINAL_DOCUMENTATION_COMMIT_VERIFIED (the T-DOC-013 checkpoint commit exists and worktree matches); (3) explicitly flip PHASE_2_STATUS from LOCKED to UNLOCKED in this state file with a focused commit; (4) then, and only then, authorize the first implementation micro-task from final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md (MVP Part II order), governed by 40_ENGINEERING_PROTOCOL.md and 50_AGENT_EXECUTION_PROMPT.md. No product code before the unlock commit.

NEXT_TASK_AUTHORIZED:
YES_IN_A_NEW_SESSION_ONLY (per PHASE_2_START_RULE)

DO_NOT_START:
PHASE_2_PRODUCT_IMPLEMENTATION_IN_THIS_SESSION
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
