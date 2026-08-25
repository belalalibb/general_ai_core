# STATIC RESUME PROMPT

استخدم هذا النص في بداية كل جلسة جديدة لاستكمال المشروع بعد انقطاع أو انتقال إلى Agent/مهندس آخر.

```text
RESUME ENGINEERED PROJECT

You are continuing an existing production-oriented codebase.

SOURCE OF TRUTH:
The Git repository is the only authoritative source of trusted project progress.

Trusted progress requires:
VERIFIED IMPLEMENTATION + SUCCESSFUL COMMIT.

Do NOT treat:
- previous conversation
- STATE.md
- PROGRESS.md
- HANDOFF.md
- previous AI claims
- previous plans

as proof of completion.

STEP 1 — READ
Read:
- final_docs/01_FINAL_ARCHITECTURE_BASELINE.md
- final_docs/02_MASTER_ENGINEERING_PROTOCOL.md
- final_docs/03_MASTER_IMPLEMENTATION_PLAN.md
- engineering/state/* if present
- current phase/gate if present
- relevant ADRs if present

STEP 2 — VERIFY REALITY
Inspect:
- git HEAD
- git status
- git diff
- current files
- relevant tests
- latest verified commit

STEP 3 — RECOVER
Determine:
- last trusted commit
- current phase
- current gate
- current task
- uncommitted work
- whether uncommitted work belongs to the active task

Never delete or reset uncommitted work blindly.

STEP 4 — RECONCILE
If documentation conflicts with Git:
Git wins.

If uncommitted work exists:
treat it as untrusted recovery material until verified.

STEP 5 — CONTINUE
Resume only from the last verified project state.

Choose the smallest valid next micro-task.

Do not expand scope.

Do not silently change architecture.

If a new architectural decision is required:
STOP → analyze → create/update ADR → verify impact → then continue.

STEP 6 — AFTER EACH MICRO-TASK
- implement
- run targeted tests
- verify result
- commit the completed logical unit
- verify the commit
- update state
- update handoff
- generate the next micro-task plan

STEP 7 — SESSION END
Before voluntarily ending:
- leave no unexplained working-tree changes
- record exact last trusted commit
- record current task status
- generate NEXT_PLAN
- update HANDOFF

Never claim DONE without a verified commit.
Never assume interrupted work succeeded.
Never use conversation memory as project truth.
```
