# PROJECT EXECUTION STATE

This file is the single project-level control point for documentation rewrite and later implementation phases.

It is not a replacement for Git. Git + verified filesystem reality remain the factual source of truth.
This file controls phase/task progression and prevents Agents from drifting, skipping, or reopening decisions.

---

## STATE HEADER

```text
STATE_VERSION: 1
STATE_REVISION: R001

RESUME_TOKEN:
PROJECT|R001|PHASE_1_DOCUMENTATION|T-DOC-STATE-001|VERIFIED|VERIFY_HEAD_WITH_GIT

LAST_BASELINE_COMMIT_BEFORE_THIS_STATE:
d8087419b6be09ee52b642a4bfcad2c0529abd2b

LAST_TRUSTED_COMMIT_RULE:
Run `git rev-parse HEAD`. The current committed HEAD is the trusted progress point after verification.

WORKTREE_STATUS_AT_LAST_UPDATE:
CLEAN_AFTER_COMMIT_REQUIRED
```

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
T-DOC-STATE-001

TASK_OBJECTIVE:
Add the project-level execution state and local-only/auto-upload boundary rules.

TASK_STATUS:
VERIFIED_AFTER_LOCAL_COMMIT

TASK_COMPLETION_CRITERIA:
- PROJECT_EXECUTION_STATE.md exists.
- README documents local-only Agent boundary.
- Lightweight resume protocol references PROJECT_EXECUTION_STATE.md.
- Push/upload responsibility is explicitly external unless user instructs otherwise.
- Agent may mark a task verified after local verification + local commit, without requiring remote push.
- State distinguishes current progress from resume checkpoint.
- Documents use static resume pointer only, not per-step progress state.
- Git diff reviewed.
- Local commit created and verified.

VERIFICATION_EVIDENCE:
- git status before work inspected.
- git diff reviewed before commit.
- grep checks for new boundary terms should pass.
- final commit hash must be reported by the Agent after commit.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-STATE-001 after commit verification

NEXT_TASK:
T-DOC-002

NEXT_TASK_OBJECTIVE:
Audit final_docs_v2 for required static Resume/Handoff pointers and document completion criteria strategy without duplicating project state in every document.

NEXT_TASK_AUTHORIZED:
YES_AFTER_T_DOC_STATE_001_COMMIT_VERIFIED

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
6. If conflict exists, Git/filesystem reality wins for facts.
7. Reconcile this file before advancing tasks.
8. Continue only the authorized NEXT_TASK.
9. Do not infer progress from chat history.
10. Do not push unless explicitly instructed.
```

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
