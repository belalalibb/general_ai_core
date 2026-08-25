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
STATE_REVISION: R003

RESUME_TOKEN:
PROJECT|R003|PHASE_1_DOCUMENTATION|T-DOC-001|PLANNED|bd98595

LAST_VERIFIED_LOCAL_COMMIT:
bd98595e797bb4ce0eb9c62e0efa2d46fe6058ce

LAST_VERIFIED_STATE_TASK:
T-DOC-STATE-002

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
RESUME_GOVERNANCE_PREPARATION

CURRENT_TASK:
T-DOC-001

TASK_OBJECTIVE:
Prepare the existing documentation pack for safe resumable execution before the actual documentation re-architecture begins.

TASK_STATUS:
PLANNED

ALLOWED_SCOPE:
- modify existing resume/handoff sections
- add or align state-control pointers
- align resume protocols with PROJECT_EXECUTION_STATE.md
- establish local-only progress / auto-upload boundary
- establish task and phase verification gates
- keep Phase 2 implementation locked until Phase 1 completion
- add/update centralized project state control
- remove or reconcile conflicting resume instructions

FORBIDDEN_SCOPE:
- rewrite product or architecture documentation
- change product requirements
- change architecture decisions
- redesign API/domain/provider/security/evaluation contracts
- implement product code
- perform the actual documentation re-architecture

TASK_COMPLETION_CRITERIA:
- PROJECT_EXECUTION_STATE.md accurately describes current project phase/task control.
- README points Agents to PROJECT_EXECUTION_STATE.md and the lightweight resume protocol.
- Resume/Handoff rules consistently use the single authoritative project state.
- Local-only progress / auto-upload boundary is explicit.
- Task/Phase completion gates are explicit.
- Phase 2 implementation remains locked until Phase 1 documentation is verified.
- The actual documentation rewrite is explicitly delegated to the next authorized task.
- No product/architecture specs are rewritten except resume/governance references if needed.
- Git diff is reviewed.
- Local commit is created and verified.

VERIFICATION_EVIDENCE:
To be recorded when T-DOC-001 is completed.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-DOC-STATE-002

LAST_VERIFIED_TASK_COMMIT:
bd98595e797bb4ce0eb9c62e0efa2d46fe6058ce

NEXT_TASK:
T-DOC-001

NEXT_TASK_OBJECTIVE:
Resume/State Governance Preparation.

NEXT_TASK_AUTHORIZED:
YES

AFTER_T_DOC_001_VERIFIED_SET:
TASK_STATUS = VERIFIED
LAST_VERIFIED_TASK = T-DOC-001
LAST_TRUSTED_COMMIT = <local commit hash>
CURRENT_WORKSTREAM = DOCUMENTATION_REARCHITECTURE
NEXT_TASK = T-DOC-002
NEXT_TASK_OBJECTIVE = Perform the actual documentation re-architecture according to the established governance, authority order, and project decisions.
NEXT_TASK_AUTHORIZED = YES

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

## STOP CONDITION

```text
Complete one authorized task only.
Verify locally.
Update this state only at a verified checkpoint.
Create local commit.
Report commit hash and next task.
Stop.
```
