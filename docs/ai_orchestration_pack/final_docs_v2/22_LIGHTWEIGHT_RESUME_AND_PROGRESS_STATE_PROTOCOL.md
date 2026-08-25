# 22 — Lightweight Resume & Progress State Protocol
## Low-Token Resume With Strict Recovery Guarantees

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-012)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md
(CARRY: all recovery guarantees, prompts, and boundaries carried verbatim;
v2 17's still-valid session-discipline rules absorbed as successor §17;
resume prompts repointed to the v3 index)
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

---

## 1. Purpose

This protocol defines **how to resume** work after a lost or interrupted session without wasting tokens and without drifting from the authorized task.

It applies to:

```text
documentation governance preparation
documentation re-architecture
future product implementation
recovery after interruption
```

It does not define product architecture. It defines recovery behavior.

---

## 2. Separation of Responsibilities

```text
README.md
= permanent operating contract

PROJECT_EXECUTION_STATE.md
= where the project is, current phase, current task, and next authorized task

22_LIGHTWEIGHT_RESUME_AND_PROGRESS_STATE_PROTOCOL.md
= how to resume safely

final_docs_v2/*
= product/documentation specifications and decisions

DOC_REWRITE_REPORT.md, if created
= audit/report artifact only, not task-control state
```

There must be only one mutable project-level state file:

```text
docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
```

Do not create any additional mutable state file unless explicitly instructed.

---

## 3. Core Rule

```text
Git committed state is the only trusted progress.
PROJECT_EXECUTION_STATE.md controls progression, but is not proof by itself.
Uncommitted work is Recovery Candidate only.
```

Trusted proof requires:

```text
PROJECT_EXECUTION_STATE.md
+
local Git commit exists
+
filesystem reality matches the verified task
```

A future Agent must never trust:

```text
previous conversation
memory
state file alone
previous AI claim
unverified generated file
```

as proof of completion.

---

## 4. Local-Only Progress / Auto-Uploader Boundary

The Agent is responsible for local execution only unless explicitly instructed otherwise.

The Agent may:

```text
edit files required by the current authorized task
update PROJECT_EXECUTION_STATE.md
update required static resume/handoff pointers
run verification
review git diff
create a local commit
```

The Agent must not:

```text
git push
upload files to GitHub
trigger remote synchronization
spend context on push/upload mechanics
```

Remote synchronization is handled externally by the project's auto-uploader unless the user explicitly requests a push.

A task may become `VERIFIED` after:

```text
local verification
+
successful local commit
```

even if remote upload has not occurred yet.

---

## 5. Low-Token Project Resume Prompt

Use this at the start of a new session:

```text
RESUME PROJECT — LOW TOKEN

Git commit is trusted progress.
PROJECT_EXECUTION_STATE.md controls authorized task progression but is not proof alone.
Previous chat claims are not proof.
Uncommitted work = Recovery Candidate.
Do not delete/reset blindly.
Do not push unless explicitly instructed.
No DONE without verification + local commit.

Steps:
1. git status
2. git rev-parse HEAD
3. git log --oneline -5
4. git diff --stat
5. read README.md
6. read docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
7. read docs/ai_orchestration_pack/final_docs_v2/00_INDEX.md only if needed
8. inspect uncommitted/new files
9. compare state with Git + filesystem reality
10. continue only the authorized CURRENT_TASK

If PROJECT_EXECUTION_STATE.md is missing/invalid, enter STATE_RECOVERY first.
```

---

## 6. Low-Token Documentation Resume Prompt

Use this when resuming documentation work, not product implementation:

```text
RESUME DOCUMENTATION WORK — LOW TOKEN

Documentation only unless PROJECT_EXECUTION_STATE.md explicitly unlocks implementation.
Git + filesystem reality verify progress.
PROJECT_EXECUTION_STATE.md authorizes the current task.
Do not trust previous chat claims.
Do not create extra state files.
Do not push unless explicitly instructed.

Steps:
1. git status
2. git rev-parse HEAD
3. git log --oneline -5
4. git diff --stat
5. read README.md
6. read docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
7. inspect changed/new files
8. verify whether CURRENT_TASK is PLANNED / IN_PROGRESS / VERIFIED / RECOVERY_REQUIRED
9. continue only CURRENT_TASK
10. update PROJECT_EXECUTION_STATE.md only at a verified checkpoint

Complete one micro-task only, then stop.
```

---

## 7. If Files Were Created But Not Reviewed

If new or modified files exist after interruption:

```text
1. Do not trust them.
2. Do not delete them blindly.
3. Inspect file names and content.
4. Classify each file:
   - belongs_to_current_task
   - useful_but_out_of_scope
   - duplicate
   - incomplete_placeholder
   - unsafe_or_unrelated
   - unknown
5. Verify whether they match CURRENT_TASK in PROJECT_EXECUTION_STATE.md.
6. Complete, repair, preserve, or discard only with explicit evidence.
7. Update PROJECT_EXECUTION_STATE.md only after verified reconstruction or verified task completion.
```

A file existing on disk is not proof that the task is complete.

---

## 8. If the Agent Did Not Update State Before Interruption

This is expected and must not break recovery.

On the next session:

```text
1. Treat PROJECT_EXECUTION_STATE.md as possibly stale.
2. Use Git HEAD as the last factual baseline.
3. Inspect git diff and untracked files.
4. Determine whether work belongs to CURRENT_TASK.
5. Run targeted verification if possible.
6. If valid and complete: update PROJECT_EXECUTION_STATE.md and commit.
7. If valid but incomplete: finish the smallest coherent unit, verify, update state, commit.
8. If unsafe/unrelated: preserve or discard only after explicit inspection.
```

Never continue based only on an old task note if filesystem reality shows a different state.

---

## 9. If State Says Verified But Git Does Not

If `PROJECT_EXECUTION_STATE.md` says a task is verified but there is no local verified commit:

```text
Task is NOT trusted as verified.
```

The Agent must:

```text
inspect files
verify referenced commit/task evidence
run targeted checks
commit if truly complete
or mark PROJECT_EXECUTION_STATE.md as RECOVERY_REQUIRED
```

---

## 10. If Git Is Ahead But State Is Stale

If Git contains committed work but `PROJECT_EXECUTION_STATE.md` is outdated:

```text
Git/filesystem reality wins for facts.
```

The Agent must reconcile `PROJECT_EXECUTION_STATE.md` before advancing tasks.

---

## 11. If Uncommitted Work Exists

Classify it:

```text
none
belongs_to_current_task
useful_but_out_of_scope
unknown
unsafe
```

Rules:

```text
belongs_to_current_task → verify/complete smallest unit
useful_but_out_of_scope → preserve as note or ask
unknown → inspect before action
unsafe → preserve evidence, ask or isolate
```

Forbidden unless explicitly instructed and after inspection:

```text
git reset --hard
git clean -fd
rm untracked files
checkout overwrite
```

---

## 12. State-Missing Recovery

If `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md` is missing, unreadable, empty, or invalid:

```text
treat project progress as UNKNOWN
do not advance phases
do not start product implementation
do not invent task completion
do not create a new task plan
enter STATE_RECOVERY first
reconstruct state only from Git + filesystem + existing repository documentation
recreate PROJECT_EXECUTION_STATE.md only after verified reconstruction
mark reconstructed state explicitly as VERIFIED or RECOVERY_REQUIRED
commit reconstructed state before continuing
```

A missing state file is a recovery condition, not permission to continue.

Do not create any additional mutable state file.

---

## 13. Current Documentation Phase Task Boundary

```text
T-DOC-001 is governance preparation only.
It prepares PROJECT_EXECUTION_STATE.md, resume/handoff pointers, local-only progress boundary, and phase/task gates.
It must not perform the actual documentation rewrite.

T-DOC-002 is the first task allowed to begin actual documentation re-architecture, and only after T-DOC-001 is VERIFIED.
```

---

## 14. Static Resume Pointer in Individual Documents

Individual specification documents should not store live progress state.

They may contain only a static pointer like:

```text
Resume / Handoff:
Project execution state is controlled by docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md.
Do not infer project progress from this document.
Resume only from the authorized task recorded in the project state file.
```

This avoids duplicated progress state and saves tokens.

---

## 15. Build vs Documentation Work Separation

Two modes must not be confused:

```text
documentation mode
product implementation mode
```

If current phase is documentation:

```text
do not implement product code
do not create runtime modules
only edit the authorized documentation/governance scope
```

If product implementation is locked:

```text
PHASE_2_STATUS = LOCKED
```

must be respected.

---

## 16. Remote Read Operations

Read-only remote inspection, such as fetch/rebase, may be used for recovery or synchronization checks when useful.

But it must not become repeated per-task overhead.

The local-only boundary forbids push/upload by default; it does not forbid occasional read-only remote inspection when needed for recovery.

---

## 17. Final Rule

```text
Short prompt.
One mutable project state file.
Strict reality checks.
Git/filesystem verify facts.
Project state controls task progression.
Evidence closes.
Local commit confirms.
Push only if explicitly instructed.
```
