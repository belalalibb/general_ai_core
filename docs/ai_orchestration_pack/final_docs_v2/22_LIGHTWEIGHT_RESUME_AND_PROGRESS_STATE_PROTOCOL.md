# 22 — Lightweight Resume & Progress State Protocol
## Low-Token Resume With Strict Recovery Guarantees

---

## 1. Purpose

This protocol defines a **simple, low-token, strict resume system** for any chat/session executing the project or rewriting the documentation.

The goal is:

```text
minimum resume tokens
+
maximum protection against lost progress
+
no conflict with real project state
+
no model drift after session interruption
```

The resume prompt must be short, but the rules behind it are strict.

---

## 2. Core Rule

```text
Git committed state is the only trusted progress.
Progress state files are navigation aids, not proof.
Uncommitted work is Recovery Candidate only.
```

A future Agent must never trust:

```text
previous conversation
memory
state file alone
handoff note alone
previous AI claim
unverified generated file
```

as proof of completion.

---

## 3. Upload / Push Assumption

In this project workflow, remote upload/push may be handled automatically by the surrounding system or by an external process.

Therefore, unless explicitly instructed otherwise:

```text
The Agent should not focus on push/upload mechanics.
The Agent's responsibility is to keep local verified progress state accurate.
```

The Agent may update progress/state files directly, but must not treat a progress update as completion unless implementation and verification are real.

If explicit push is requested by the user, follow the secure credential handling rules. Otherwise, assume upload is external/automatic.

---

## 4. What the Agent Must Maintain

At minimum, the project should maintain compact state files such as:

```text
engineering/STATE.md
engineering/ACTIVE_TASK.md
engineering/NEXT_PLAN.md
engineering/HANDOFF.md
engineering/VERIFY.md
```

For documentation rewrite work, use:

```text
docs/ai_orchestration_pack/DOC_REWRITE_STATE.md
docs/ai_orchestration_pack/DOC_REWRITE_NEXT_PLAN.md
docs/ai_orchestration_pack/DOC_REWRITE_HANDOFF.md
```

These files should be short and structured.

---

## 5. Minimal Progress State Format

Use a compact format to reduce token usage:

```md
# STATE
Last trusted commit: <hash>
Mode: build | docs-rewrite | audit | recovery
Phase: <phase>
Active task: <task-id + one-line objective>
Status: not_started | in_progress | verified | blocked | recovery_needed
Verified evidence: <tests/commands/artifacts/commit>
Changed files: <short list>
Uncommitted work: none | present | unknown
Next step: <one smallest task>
Risks/blockers: <short list>
Updated at: <timestamp>
```

Do not write long narratives in state files.

---

## 6. Lightweight Resume Prompt

Use this at the start of a new execution session:

```text
RESUME PROJECT — LOW TOKEN

Git commit is the only trusted progress.
State files are navigation only.
Do not trust previous chat claims.
Do not delete/reset uncommitted work blindly.

Steps:
1. git status
2. git rev-parse HEAD
3. git diff --stat
4. read README.md
5. read the relevant STATE / ACTIVE_TASK / NEXT_PLAN files if present
6. compare state files with real filesystem and Git
7. classify uncommitted work: none / belongs to active task / unknown / unsafe
8. verify the smallest relevant evidence
9. continue only from verified reality
10. choose one smallest next task

If state files are missing or stale, reconstruct from Git + files + tests, then update state.
No DONE without verification + commit.
```

---

## 7. Lightweight Documentation Rewrite Resume Prompt

Use this when resuming documentation rewriting, not product implementation:

```text
RESUME DOCS REWRITE — LOW TOKEN

Goal: improve docs only; do not build product code.
Git commit is trusted progress.
State files are navigation only.
Do not trust previous chat claims.

Steps:
1. git status
2. git rev-parse HEAD
3. git diff --stat
4. read README.md
5. read docs/ai_orchestration_pack/README.md
6. read final_docs_v2/00_INDEX.md
7. read DOC_REWRITE_STATE / NEXT_PLAN if present
8. inspect changed/new docs before editing
9. continue one smallest docs task
10. update rewrite state and commit

Keep resume short. Preserve recovery rules. Do not add complexity without execution value.
```

---

## 8. If Files Were Created But Not Reviewed

If the Agent finds new files created before interruption:

```text
1. Do not trust them.
2. Do not delete them blindly.
3. Inspect file names and content.
4. Classify each file:
   - intended and useful
   - duplicate
   - incomplete placeholder
   - unsafe/unrelated
   - unknown
5. Verify whether they match the active task.
6. Complete, repair, or remove only with explicit evidence.
7. Update state with the decision.
```

A file existing on disk is not proof that the task is complete.

---

## 9. If the Agent Did Not Update Progress Before Interruption

This is expected and must not break recovery.

On the next session:

```text
1. Treat state files as possibly stale.
2. Use Git HEAD as last trusted baseline.
3. Inspect git diff and untracked files.
4. Determine whether the work belongs to the last known active task.
5. Run targeted verification if possible.
6. If valid and complete: update progress state and commit.
7. If valid but incomplete: finish the smallest coherent unit, verify, update state, commit.
8. If unsafe/unrelated: preserve or discard only after explicit inspection.
```

Never continue based only on the old NEXT_PLAN if the filesystem shows different reality.

---

## 10. If Progress State Says Done But Git Does Not

If a state/handoff file says a task is done but there is no verified commit:

```text
Task is NOT trusted as done.
```

The Agent must:

```text
inspect files
run verification
commit if truly complete
or mark as recovery_needed
```

---

## 11. If Git Is Ahead But State Is Stale

If Git contains committed work but state files are outdated:

```text
Git wins.
```

The Agent must update state files to match Git reality.

---

## 12. If Uncommitted Work Exists

Classify it:

```text
none
belongs_to_active_task
useful_but_out_of_scope
unknown
unsafe
```

Rules:

```text
belongs_to_active_task → verify/complete smallest unit
useful_but_out_of_scope → move to future note or ask
unknown → inspect before action
unsafe → preserve evidence, ask or isolate
```

Forbidden:

```text
git reset --hard
git clean -fd
rm untracked files
checkout overwrite
```

unless explicitly instructed and after inspection.

---

## 13. Strict Anti-Drift Conditions

A resuming Agent must not:

```text
change architecture because it seems better
start a new module while recovery is unresolved
rewrite large docs before reading index/state
ignore active task
skip verification
expand scope during recovery
trust old chat context over Git
```

If architecture/docs direction is unclear, create a small audit note first rather than rewriting everything.

---

## 14. State Update Timing

The Agent should update progress state:

```text
1. after selecting the active micro-task
2. after meaningful file changes
3. after verification
4. after commit
5. before ending voluntarily
```

But if interruption happens before this, the next session recovers from Git/diff reality.

---

## 15. Compact Handoff Format

At voluntary stop, write:

```md
# HANDOFF
Last trusted commit: <hash>
Current task: <id/objective>
Status: <verified|in_progress|blocked>
Files changed: <short list>
Verification: <commands/results>
Uncommitted work: <none/list>
Next task: <one task>
Warnings: <short list>
```

Keep it short. Do not duplicate full documentation.

---

## 16. Build vs Documentation Rewrite Separation

Two modes must not be confused:

```text
build mode: implementing product code
```

```text
docs-rewrite mode: improving documentation only
```

Resume must identify mode before continuing.

If mode is docs-rewrite:

```text
Do not implement product code.
Do not create runtime modules.
Only edit docs, prompts, protocols, indexes, and decision logs.
```

If mode is build:

```text
Do not rewrite documentation broadly unless required by active task.
```

---

## 17. Final Rule

The resume system should be short enough to paste cheaply, but strict enough to prevent damage.

```text
Short prompt.
Strict reality checks.
Git wins.
State guides.
Evidence closes.
Commit confirms.
```

---

## 18. Project Execution State Control Point

The project-level state file is:

```text
docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
```

This file defines where the project is now:

```text
current phase
phase lock/unlock status
current task
task status
last verified task
next authorized task
resume token
local progress checkpoint
```

The protocol in this document defines **how to resume**.
`PROJECT_EXECUTION_STATE.md` defines **where to resume from**.

---

## 19. Local-Only Progress / Auto-Uploader Boundary

The Agent is responsible for local execution only unless explicitly instructed otherwise.

The Agent may:

```text
edit files required by the current authorized task
update PROJECT_EXECUTION_STATE.md
update compact resume/handoff metadata
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

Remote synchronization is handled externally by the project's auto-uploader.

A task may become VERIFIED after:

```text
local verification
+
successful local commit
```

even if remote upload has not occurred yet.

---

## 20. Current Progress State vs Resume Checkpoint

Do not write long narratives into the state file.

At a verified checkpoint, update only compact state such as:

```text
CURRENT_TASK
TASK_STATUS
LAST_VERIFIED_TASK
NEXT_TASK
NEXT_TASK_AUTHORIZED
LAST_TRUSTED_COMMIT_RULE
RESUME_TOKEN
```

If interruption happens during a task:

```text
CURRENT_TASK = active task
TASK_STATUS = IN_PROGRESS or recovery-needed
LAST_VERIFIED_TASK = previous verified task
NEXT_TASK = current task or last authorized task
```

The next Agent must not advance to a later task until the current task is verified.

---

## 21. Static Document Resume Pointer

Individual specification documents should not store live progress state.

They may contain a static pointer like:

```text
Resume / Handoff:
Project execution state is controlled by docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md.
Do not infer project progress from this document.
Resume only from the authorized task recorded in the project state file.
```

This avoids duplicating progress state across many documents and saves tokens.


---

## 22. State Is Not Proof By Itself

Project state controls progression, but it is not proof alone.

Trusted proof requires:

```text
PROJECT_EXECUTION_STATE.md
+
local Git commit exists
+
filesystem reality matches the verified task
```

On resume, if the state references a commit or task, verify it locally before trusting it.

---

## 23. Do Not Add More Mutable State Files

The project-level mutable state should remain centralized in:

```text
docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
```

Reports such as `DOC_REWRITE_REPORT.md` may exist as audit artifacts, but they do not control task progression.

Individual documents should keep only static resume pointers, not live progress state.

---

## 24. Remote Read Operations

Fetching remote state for recovery or synchronization checks is allowed when useful.

But it must not become repeated per-task overhead.

The local-only boundary forbids push/upload by default; it does not forbid occasional read-only remote inspection when needed for recovery.


---

## 25. Current Documentation Phase Task Boundary

```text
T-DOC-001 is governance preparation only.
It prepares PROJECT_EXECUTION_STATE.md, resume/handoff pointers, local-only progress boundary, and phase/task gates.
It must not perform the actual documentation rewrite.

T-DOC-002 is the first task allowed to begin actual documentation re-architecture, and only after T-DOC-001 is VERIFIED.
```
