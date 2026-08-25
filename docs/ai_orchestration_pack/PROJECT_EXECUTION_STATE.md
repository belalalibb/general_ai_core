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
STATE_REVISION: R014

RESUME_TOKEN:
PROJECT|R014|PHASE_1_DOCUMENTATION|T-DOC-011|VERIFIED|VERIFY_HEAD_WITH_GIT

LAST_VERIFIED_LOCAL_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (T-DOC-011 commit; prior T-DOC-010 local commit 71484af was re-synchronized by the external auto-uploader as per-file sync commits ending at da22183 — facts verified from filesystem)

LAST_VERIFIED_STATE_TASK:
T-DOC-011

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
SOURCE_BASELINE_ONLY

V2_STRUCTURE_AUTHORITY:
NONE

V3_STATUS:
BLUEPRINT_APPROVED_MIGRATION_IN_PROGRESS

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
PHASE_1_DOCUMENTATION_IN_PROGRESS

CURRENT_PHASE:
PHASE_1_DOCUMENTATION_REARCHITECTURE

PHASE_1_STATUS:
IN_PROGRESS

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
T-DOC-011

TASK_OBJECTIVE:
Merge: create final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md from v2 14 + v2 15 as one plan with explicit FINAL vs MVP vs FUTURE separation; remove duplicated phase lists and legacy state-file references (superseded by D10/D11); preserve all phase content, MVP scope decisions, and roadmap decisions (preserved or explicitly superseded, never silent). Mark v2 14 and v2 15 SUPERSEDED with pointers and flip the MIGRATION STATUS row for doc 41 in final_docs_v3/00_INDEX.md in the same commit.

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

ALLOWED_SCOPE:
- create final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md (merge of v2 14 + 15)
- add SUPERSEDED pointer banners to v2 14 and v2 15 (no content deletion)
- flip MIGRATION STATUS for doc 41 in final_docs_v3/00_INDEX.md
- update this state file at the verified checkpoint

FORBIDDEN_SCOPE:
- change any phase content, MVP scope decision, or roadmap decision silently
- migrate any other document
- implement product code
- create additional mutable state files

TASK_COMPLETION_CRITERIA:
- v3 41 exists, content-complete, no stubs, with Part I (FINAL plan), Part II (MVP roadmap), Part III (FINAL/MVP/FUTURE map + traceability ledger).
- Preserved verbatim: 15 non-breakable rules; repo layout (minus engineering/state/ per D10/D11, explicit); all 24 FINAL phases with tasks/exit criteria; micro-task protocol; task output contract; scope-control rule; architecture change protocol; gate system; Definition of Done; success criteria; build prompt requirement; MVP philosophy; MVP include/exclude scope; MVP phases 0-8; MVP DoD; scaffold-only start rules (allowed/forbidden).
- Explicit supersessions (D10/D11 only, never silent): v2 14 SS32 (multi-file resume), SS33 (NEXT_PLAN.md), SS35/SS37 (FUTURE_IMPROVEMENTS.md/ARCHITECTURE_GAPS.md ledgers), SS39 (handoff files), SS42 (static resume prompt); v2 15 legacy state-files wording. All recorded in the successor ledger + v2 banners.
- Commit/interrupt/recovery detail deduplicated to a summary + pointer to 40 SS9-SS10 (owning authority); no rule changed.
- Provider references repointed to v3 successors 30/31 (same targets post-migration).
- v2 14 + 15 carry SUPERSEDED banners pointing to successor; content otherwise untouched.
- final_docs_v3/00_INDEX.md row for doc 41 = COMPLETE_AUTHORITATIVE in the same commit.
- Git diff reviewed; single local commit created and verified.

VERIFICATION_EVIDENCE:
- Successor file exists on filesystem and in commit (1631 lines), with full section-by-section V2->V3 traceability and decision ledger (SS51).
- Mechanical grep verification passed: 15/15 rules, 25/25 FINAL phase markers, all key decisions (credential policies, account lifecycle, bootstrap router, strategies, async fabric, memory rules, skill sources, evaluation levels, usage flow, learning pipeline, API surface, admin invariants, production topology, micro-task protocol, success criteria), all MVP markers (scope include/exclude, DoD, scaffold rules).
- No legacy state-file scheme reintroduced as authority (all mentions are explicit negations/supersessions).
- V3 index authority switch flipped for doc 41 only.
- Secret scan of changed files passed (no tokens/keys).
- Local commit created and verified; use `git rev-parse HEAD` for the exact trusted commit.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-011

LAST_VERIFIED_TASK_COMMIT:
VERIFY_WITH_CURRENT_LOCAL_HEAD_AFTER_COMMIT

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
DOCUMENTATION_REARCHITECTURE_V3_MIGRATION

NEXT_TASK:
T-DOC-012

NEXT_TASK_OBJECTIVE:
Agent-operation cluster: create final_docs_v3/50_AGENT_EXECUTION_PROMPT.md (MERGE v2 20 base + v2 16 as its short standard-mode profile — one build prompt authority), final_docs_v3/51_AGENT_COGNITIVE_PROTOCOL.md (CARRY of v2 19), final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md (CARRY of v2 22 + ABSORB/retire v2 17 which is stale: dead final_docs/ paths and forbidden legacy state-file scheme), and final_docs_v3/60_DECISION_LOG.md (CARRY of v2 18; migration conflict resolutions appended). Mark v2 16/17/18/19/20/22 SUPERSEDED with pointers and flip MIGRATION STATUS rows for docs 50/51/52/60 in the same commit. All decisions preserved or explicitly superseded by D10/D11; never silent.

NEXT_TASK_AUTHORIZED:
YES_AFTER_T_DOC_011_COMMIT_VERIFIED

DO_NOT_START:
PHASE_2_PRODUCT_IMPLEMENTATION
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
