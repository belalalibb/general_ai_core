# A1 — Resume / memory system audit (prompt §1.2, §1.3, §1.5)

Session: R176 A1 · HEAD at start 46c163c (restored from bundle 4moz9qRH after sandbox reset #19) · tree clean.

## 1. Discovery (repo search: resume / checkpoint / state / handoff / recovery)

| artifact | role | authority | last mutated | survives sandbox loss? |
|---|---|---|---|---|
| `docs/ai_orchestration_pack/final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md` | the written protocol (how to resume) | AUTHORITATIVE (V3, T-DOC-012) | doc-rewrite era | yes (committed) |
| `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md` | "the ONLY mutable state file" per §52; project-level phase/task control | AUTHORITATIVE by declaration | **R168** (commit 2046622); 571 lines; header says STATE_REVISION R168; line 539 `CURRENT_TASK: STATE_RECOVERY` | yes |
| `evidence/rNNN_state_ledger.md` (R168, R169, R172, R173, R174, R175, R176) | per-round checkpoint: one row appended BEFORE each item, HEAD-at-start column | AUTHORITATIVE **in practice** since R168 (OPERATIONS.md §12 row "Execution state (R-series ledger)") | every round; R175 = 21 rows through reset #17 | yes |
| `README.md` §"RESUME / INTERRUPTION RULE" + §"LOCAL-ONLY PROGRESS" | 3–5-line pointers | pointer only | doc-rewrite era | yes |
| off-sandbox git bundles (R175 §2-A′/§6′/§0-d, R176 A0) | surviving copy when push is blocked | operational | per event | yes (external URL recorded in ledger) |

## 2. Findings

**F-R176-03 (S3, DOCUMENTATION DRIFT — two state artifacts, one stale).**
§52 declares `PROJECT_EXECUTION_STATE.md` the *only* mutable state file, but it has not been updated since R168
(`CURRENT_TASK: STATE_RECOVERY`, `NEXT_TASK_AUTHORIZED: NO_UNTIL_STATE_RECONSTRUCTED_AND_COMMITTED`), while seven
rounds of real continuity (R168→R176) live in `evidence/rNNN_state_ledger.md`. A fresh agent following §52 §5
literally (step 6) reads a file that says "state recovery required", contradicting the ledgers and
`docs/r175/R175_FINAL_BACKEND_CERTIFICATION.md`. OPERATIONS.md §12 already points to the ledger — so the *operational*
doc is right and the *protocol* doc + state file are stale. Classification: DOCUMENTATION DRIFT, not a blocker.
Proposed (not executed): **FIX-02** — one pointer row in `PROJECT_EXECUTION_STATE.md` header
(`STATE_REVISION: R176 — see evidence/r176_state_ledger.md; per-round ledgers are the checkpoint since R168`) and a
one-line note in §52 §2. No product change.

**F-R176-04 (S4, DOCUMENTATION DRIFT — push rule).** README/§52 §4: "Agent must not git push … unless the user
explicitly requests a push". Practice R168–R176: operator hands a token each turn and says "continue" → agent pushes
after each ledger row. Reconciled as: the handed token + standing instruction *is* the explicit request; but the doc
should say so. The examination prompt §1.3/§4.1 is stricter (push needs explicit authorization per Git op); the repo's
existing rule wins per the operator's instruction to keep the current resume protocol. Recorded, no action.

## 3. Recovery evidence (EXECUTED, not described)

```text
RESUME ARTIFACT:  evidence/r176_state_ledger.md (last row) ; project pointer docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
RESUME COMMAND:   git fetch origin main && git status -sb && tail -3 evidence/r176_state_ledger.md
                  && pip install -e ".[dev]" && env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY -u DATABASE_URL python3 -m apps.cli check
RESUME TEST:      sandbox reset #19 (between turns) reverted the working tree to 521d885 (A0 commit 46c163c lost locally,
                  venv + credentials wiped). Recovery: ledger-recorded bundle 4moz9qRH → `git bundle verify` OK →
                  `git fetch <bundle> HEAD && git merge --ff-only FETCH_HEAD` → HEAD 46c163c byte-identical; ledger last row
                  says "Next: A1" → this file. Venv rebuilt with the documented command.
RESULT:           PASS (state fully reconstructed from repository + recorded bundle; zero chat memory needed)
EVIDENCE:         evidence/r176/00_session_start/*, this file, ledger rows A0/A1
GitHub auth:      FAILED again (push dry-run "Authentication failed"); read via public ls-remote OK. PUSH BLOCKED → bundle continues.
```

Interruption classification of last action (A0): **COMPLETE** (row + commit + bundle all present; nothing uncommitted).

## 4. Answers to §1.2 questions

1. Authoritative for continuity: per-round ledger (`evidence/r176_state_ledger.md`) — by practice and OPERATIONS.md; §52 says PROJECT_EXECUTION_STATE.md — DRIFT (F-R176-03).
2. Persistent checkpoint exists: YES (committed; 7 rounds of proof).
3. Completed / in-progress / failed recorded: YES — ledger rows + checklist table (R176 adds explicit PENDING/DONE/WAIT column).
4. Evidence referenced: by path under `evidence/rNNN/**`, tracked; `raw_*` gitignored.
5. Fresh session reconstruction: read last ledger row → HEAD column → evidence dir. Verified this session.
6. Survives model/chat/sandbox/process interruption: YES — 19 resets across R174–R176 recovered with zero loss of committed work; uncommitted-at-reset work was lost once (R175 §0-d driver edit survived by luck) → rule already in force: commit before ending a turn.
7. Survives GitHub loss: YES via bundles (URL in ledger) — but bundles depend on an external file host; a PUSHED commit is the durable form. Current blocker: token invalid.
