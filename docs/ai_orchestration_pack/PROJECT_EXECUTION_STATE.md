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
STATE_REVISION: R009

RESUME_TOKEN:
PROJECT|R009|PHASE_1_DOCUMENTATION|T-DOC-006|VERIFIED|VERIFY_HEAD_WITH_GIT

LAST_VERIFIED_LOCAL_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (T-DOC-006 commit; prior T-DOC-005 work verified during R009 reconciliation as present in HEAD via external uploader sync commits ending at bf421c8)

LAST_VERIFIED_STATE_TASK:
T-DOC-006

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
T-DOC-006

TASK_OBJECTIVE:
Carry cluster: create final_docs_v3/01_PRODUCT_REQUIREMENTS.md (from v2 01), final_docs_v3/02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md (from v2 02), and final_docs_v3/03_DOMAIN_MODEL.md (from v2 03) as CARRY migrations (surgical cleanup only; invariants unchanged; no decision changes), mark v2 01/02/03 SUPERSEDED with pointers, and flip their MIGRATION STATUS rows in final_docs_v3/00_INDEX.md in the same commit.

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

ALLOWED_SCOPE:
- create final_docs_v3/01_PRODUCT_REQUIREMENTS.md (carry of v2 01)
- create final_docs_v3/02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md (carry of v2 02)
- create final_docs_v3/03_DOMAIN_MODEL.md (carry of v2 03)
- add SUPERSEDED pointer banners to v2 01, 02, 03 (no content deletion)
- flip MIGRATION STATUS for docs 01/02/03 in final_docs_v3/00_INDEX.md
- update this state file at the verified checkpoint

FORBIDDEN_SCOPE:
- change any requirement, invariant, entity schema, or decision
- migrate any other document
- implement product code
- create additional mutable state files

TASK_COMPLETION_CRITERIA:
- All three v3 files exist, content-complete, no stubs (CARRY: content preserved verbatim; only V3 authority header + traceability footer added).
- v3 01 preserves: vision, 4 use-case groups, primary users table, FR-001..FR-015, NFR table, MVP out-of-scope list, success criteria list.
- v3 02 preserves: architecture statement + flow diagram, all 15 non-breakable invariants verbatim, module layout, core may/must-not lists, technology shape, production baseline, quality bar.
- v3 03 preserves: all entities, all schemas incl. ProviderAccount lifecycle_state, Execution strategies/statuses, relationship rules, section 9 agent-capability model incl. rule Provider Agent Capability != Platform Agent Runtime + platform ownership list.
- v2 01/02/03 carry SUPERSEDED banners pointing to successors; their content otherwise untouched.
- final_docs_v3/00_INDEX.md rows for docs 01/02/03 = COMPLETE_AUTHORITATIVE in the same commit.
- Git diff reviewed; single local commit created and verified.

VERIFICATION_EVIDENCE:
- Three successor files exist on filesystem and in commit, each with a V2->V3 traceability section stating CARRY (verbatim).
- Decision-preservation grep passed (all 15 FR ids, 15 invariants count, lifecycle states, strategies list, Provider Agent Capability != Platform Agent Runtime, deny-by-default, LLM never a security authority).
- V3 index authority switch flipped for docs 01/02/03 only.
- Secret scan of changed files passed (no tokens/keys).
- Local commit created and verified; use `git rev-parse HEAD` for the exact trusted commit.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-006

LAST_VERIFIED_TASK_COMMIT:
VERIFY_WITH_CURRENT_LOCAL_HEAD_AFTER_COMMIT

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
DOCUMENTATION_REARCHITECTURE_V3_MIGRATION

NEXT_TASK:
T-DOC-007

NEXT_TASK_OBJECTIVE:
Carry cluster: create final_docs_v3/10_API_CONTRACTS.md (from v2 04) and final_docs_v3/11_MODEL_ROUTING_AND_MODEL_CONTROL.md (from v2 06, keeping all modes AUTO / TIER / EXPLICIT_MODEL / EXPLICIT_MODELS / AGENT_NODE_MAPPING) as CARRY migrations (no decision changes), mark v2 04 and v2 06 SUPERSEDED with pointers, and flip their MIGRATION STATUS rows in final_docs_v3/00_INDEX.md in the same commit.

NEXT_TASK_AUTHORIZED:
YES_AFTER_T_DOC_006_COMMIT_VERIFIED

DO_NOT_START:
PHASE_2_PRODUCT_IMPLEMENTATION
```

---

## CONFIRMED DECISIONS

```text
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
Complete one authorized task only.
Verify locally.
Update this state only at a verified checkpoint.
Create local commit.
Report commit hash and next task.
Stop.
```
