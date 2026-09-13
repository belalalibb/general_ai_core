# R180 HANDOFF — instructions

Branch `genspark_ai_developer_r180`; base `main` 5b78f467. Read `R180_READINESS.md` for analysis; this file only says what to do next.

## A. Ordered items

| # | item | where | do |
|---|---|---|---|
| 1 | Merge R180 PR (rulings 1+2 ratified, R180-DEC-02) | GitHub | merge COMMIT (no squash) once exit conditions hold; re-run the canonical gate on the merge commit |
| 2 | Rotate the in-session GitHub token | GitHub settings | operator action after merge (no credential lands in the workspace) |
| 3 | Q6, Q7, Provider slice | `R180_READINESS.md` Part 4 | DEFERRED by ruling; no reordering; usage stays process-local (OPERATIONS §13) |

R181 status of item 3: **Q6 CLOSED** (migration 0022, R181-DEC-01, usage durable on the `DATABASE_URL` profile — OPERATIONS §13 updated); **Q7 and the Provider slice remain UNDEFINED** (no repository definition; recorded, not worked). Item 1 done (gate on ed61f7e6: `evidence/r181/gate_merge_ed61f7e6.txt`). See `R181_HANDOFF.md`.

## B. Resume mechanism (unchanged)
Remote branch head is the checkpoint; rebuild `.venv` (`pip install -e '.[dev]'`). Two sandbox resets during R180 lost only
uncommitted work — publish the branch FIRST, commit after every landed item. Live console check recipe: `RUN.md` "Zero-config
admin walkthrough" + `evidence/r180/q5_live_dom_probe.txt` header.
