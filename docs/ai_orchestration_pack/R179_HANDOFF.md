# R179 HANDOFF — instructions (Part B §9)

Branch `genspark_ai_developer_r179`; gate clone d747b158 (3533/0/0/64), gateway 194, live r178 59 + r179 5.
Read `R179_READINESS.md` for analysis; this file only says what to do next.

## A. Ordered items

| # | item | where | do |
|---|---|---|---|
| 1 | Merge R179 PR after review | GitHub | squash-merge; keep `evidence/r179/*` |
| 2 | Production 0020 procedure | `docs/OPERATIONS.md` §8.1 | stop ALL old writers BEFORE `alembic upgrade head`; never restart pre-0020 binaries (F-R179-05) |
| 3 | Retention sweeps | external timer | call `POST /v1/admin/learning/custody/sweep` with an admin session (D2=(a)) |
| 4 | Operator visibility | `GET /v1/admin/learning/custody/holds` | use before any release; read the `outcome` on release |
| 5 | Intake retries | `POST /v1/admin/learning/intake` | on 503 re-send the SAME batch `idempotency_key`; landed rows dedup |

## B. Decision queue (operator rulings needed)

| id | question | default if silent |
|---|---|---|
| Q1 (DEC-B) | bind durable audit + usage repositories in the durable profile (same seam pattern as 4.5)? | stays deferred; measured limit documented |
| Q2 (F-R179-05) | authorize a NEW migration adding a schema-level guard (trigger/constraint refusing custody inserts while a hold row exists)? | procedure-only mitigation |
| Q3 (F-R179-02) | add `GraderType.SECURITY` to `FINAL_ACTIVE_GRADER_TYPES` or relax strict evidence for the governed runtime? | promote stays unreachable over HTTP (409) |
| Q4 (DEC-A) | expose the payload-schema half of action discovery (requires declarative schemas in `core/admin`)? | design only |
| Q5 (ui/ thaw) | let the console consume `/capabilities/actions` and drop the `ADMIN_ACTIONS` hand-list? | frozen |

## C. Disposition of every finding

| id | severity | disposition |
|---|---|---|
| F-R179-01 execute+conversation_id 500 (durable) | S1 | CLOSED by 4.5 (after-measure 200/200/200) |
| F-R179-02 promote unreachable over HTTP | S2 | OPEN → Q3 |
| F-R179-03 memory dies with process | S1 | CLOSED by 4.5 (memory_blocks 1→1) |
| F-R179-04 audit/usage reset on restart | S2 | OPEN by design (DEC-B) → Q1; documented §13 |
| F-R179-05 old writer not refused by 0020 schema | S2 | OPEN → Q2; procedure in §8.1 |

## D. Resume mechanism (unchanged)
Remote branch head is the checkpoint; rebuild `.venv` (`pip install -e '.[dev]'`) and the workspace PostgreSQL binaries
(`tests_live/r179/run_local_postgres.sh` prints the exact commands). Authentication is supplied by the operator per
session and is never written into the workspace or the home directory. Do not invent alternate paths.
