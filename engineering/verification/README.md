# Verification Conventions

Authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md`
(§2.9 Evidence Before Confidence, §6 Quality Gates, §9 Git Safety).

## Conventions

```text
1. Every micro-task declares its verification command BEFORE implementation
   (41 §28). A task without a runnable verification command is not a task.
2. Verification output is evidence; assertions are not. "It should work" is
   forbidden; run the command and read the result.
3. No DONE before: verification passed + focused local commit exists +
   worktree clean + state file updated (41 §29, §34).
4. Repo-level checks live in this directory and must be runnable locally and
   in CI with the same entry point:
       ./engineering/verification/check_repo.sh
5. CI (.github/workflows/ci.yml) runs the same script — CI is a mirror of the
   local gate, never a different gate.
6. Never assume an interrupted command succeeded (40 §10): re-verify from
   filesystem/Git reality after any interruption.
```

## Current checks (stack-neutral, Phase 0)

```text
check_repo.sh
  - governance-structure check: required engineering/ files exist
  - single-state-file check: exactly one mutable state file
    (PROJECT_EXECUTION_STATE.md); no legacy STATE.md/PROGRESS.md/HANDOFF.md
  - docs-integrity check: v3 pack complete (20 files), authoritative index
    present, state file parseable header fields present
  - secret scan: no obvious credentials committed
```

Stack-specific checks (lint, typecheck, unit/contract tests) are added when
the stack ADR is accepted (see engineering/adr/README.md).
