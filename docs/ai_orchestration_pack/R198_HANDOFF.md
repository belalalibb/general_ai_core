# R198 HANDOFF — final acceptance "as measured"

Status: OPEN (declaration committed; RED next). Base: `main fbdd1f0b`. Branch: `genspark_ai_developer_r198`.

## 1. Authority (operator, verbatim anchors)
"APPROVE R198" — D1 YES (accept v1 as measured; D-03 OPEN; **no Production Ready claim while unresolved**); D2 YES (ADR-0014); D3 YES (live PostgreSQL 17 + pgvector re-measure on current main, else honest NOT EVALUATED); D4 YES (history-purge path; **no rewrite by engineering without the operator-controlled procedure/evidence**; rewritten SHAs invalidate prior references — acknowledged); D5 (legacy branches removed only via the approved purge procedure; no public refs to leaked commits afterwards); D6 YES (DECLARED-UNCONSUMED; no extra UI round).

## 2. Allowed / frozen
- MAY add/change: `docs/architecture/ADR-0014_V1_PRODUCTION_TOPOLOGY.md`, `docs/ai_orchestration_pack/V1_ACCEPTANCE_REGISTER.md`, `evidence/r198/*`, `tests/verification/test_ad5_topology_artefact_r198.py`, `tests/verification/test_v1_acceptance_register_r198.py`, manifest (`round_r198`, `not_evaluated` only if R198-B cannot run), OPERATIONS §1 cross-link, records.
- FROZEN: `core/ apps/ infrastructure/` (0); `ui/*` (73 / 12 / 22); contracts + freeze baseline (46).

## 3. Steps
1. Declaration (this commit). 2. RED (two static guards). 3. R198-A ADR-0014, R198-C register, R198-D D-03 slot → GREEN. 4. R198-B live re-measure (`.venv/pg_root` PostgreSQL 17.11 + pgvector 0.8.0; `tests_live/r179/run_local_postgres.sh`; `tests_live/r178`). 5. Verify (guards, freeze `--check`, regression 18 roots). 6. Fresh-clone gate. 7. PR (merge commit). 8. Post-merge gate. 9. Records-only closure. 10. STOP.

## 4. Resume
After a reset: `git fetch`; `git checkout -B genspark_ai_developer_r198 origin/genspark_ai_developer_r198`; read the last row of `evidence/r198_state_ledger.md`; redo only the missing step. PostgreSQL binaries live under `.venv/pg_root` (ignored; rebuilt via `apt-get download postgresql-17 postgresql-client-17 postgresql-17-pgvector libpq5` + `dpkg-deb -x`).
