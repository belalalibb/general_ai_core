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
STATE_REVISION: R005

RESUME_TOKEN:
PROJECT|R005|PHASE_1_DOCUMENTATION|T-DOC-002|VERIFIED|VERIFY_HEAD_WITH_GIT

LAST_VERIFIED_LOCAL_COMMIT:
f10ea536a9ff7049e26e16fea6b3a681561d5c09

LAST_VERIFIED_STATE_TASK:
T-DOC-002

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
T-DOC-002

TASK_OBJECTIVE:
Design the real V3 documentation architecture: audit V2, produce the V3 blueprint index with full V2→V3 traceability map, structural decision-preservation ledger, migration order, and migration authority rule. Blueprint-first so each subsequent migration commit stays small and reviewable.

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

ALLOWED_SCOPE:
- audit final_docs_v2 for duplicates, contradictions, stale sections, authority overlaps
- create final_docs_v3/00_INDEX.md as the V3 blueprint and live migration index
- record traceability map and structural decision-preservation ledger
- define migration order as future micro-tasks
- add the V3 pointer + authority rule to final_docs_v2/00_INDEX.md

FORBIDDEN_SCOPE:
- change product requirements, contracts, or architecture decisions
- migrate document content in this task (content migration starts at T-DOC-003)
- implement product code
- create additional mutable state files

TASK_COMPLETION_CRITERIA:
- final_docs_v3/00_INDEX.md exists with: authority rule, full traceability map covering all 26 V2 files (00–25), structural ledger, capability coverage check, migration order.
- final_docs_v2/00_INDEX.md points to the V3 blueprint with the authority rule.
- No V2 spec content was rewritten or deleted.
- No decisions/invariants changed.
- Git diff reviewed; local commit created and verified.

VERIFICATION_EVIDENCE:
- final_docs_v3/00_INDEX.md exists on filesystem and in commit.
- Traceability map covers all 26 V2 files (00–25); coverage check maps all 25 required capability areas.
- Structural ledger classifies every merged/superseded V2 file with a one-line reason.
- V2 documents untouched except the V3 pointer block in final_docs_v2/00_INDEX.md.
- Secret scan of docs/ passed (no tokens/keys found).
- Local commit created and verified; use `git rev-parse HEAD` for the exact trusted commit.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-002

LAST_VERIFIED_TASK_COMMIT:
VERIFY_WITH_CURRENT_LOCAL_HEAD_AFTER_COMMIT

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
DOCUMENTATION_REARCHITECTURE_V3_MIGRATION

NEXT_TASK:
T-DOC-003

NEXT_TASK_OBJECTIVE:
Create final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md by merging v2 24_FINAL_PROVIDER_ARCHITECTURE_SPEC.md (authoritative base) with v2 05_PROVIDER_PLUGIN_SPEC.md (detail), preserving all provider decisions (capability-driven, no forced lifecycle, Core isolation, no real providers yet), mark both V2 sources SUPERSEDED with pointers, and flip their MIGRATION STATUS in final_docs_v3/00_INDEX.md in the same commit.

NEXT_TASK_AUTHORIZED:
YES_AFTER_T_DOC_002_COMMIT_VERIFIED

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
