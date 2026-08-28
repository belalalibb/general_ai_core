# Backup Configuration — FINAL Phase 3 Required Item (41 §6)

```text
STATUS: CONFIGURATION SPECIFICATION (Lane C closed — no production
        database exists; no live backup job can run or be verified.
        This document is the deployable configuration contract, recorded
        so the 41 §6 "backup configuration" Required item is closed
        HONESTLY as specification, not as a falsely-claimed running
        system. 41 §49 honesty rule.)
TASK:   T-IMPL-053
```

Spec authority (verbatim):

- 41 §6 Required list: `backup configuration`
- 02 §6 Production Baseline: `HA PostgreSQL + backups + PITR`
- 40 §5.4 Production Architecture: `Database = primary + HA standby +
  backups + PITR`

---

## 1. What must be configured at deployment (Lane C)

```text
Postgres:
  - Continuous archiving (WAL): archive_mode = on,
    archive_command → object storage (per ADR-0006 backend when ACCEPTED)
  - PITR: base backups + WAL retention window ≥ the recovery-point
    objective the operator sets (spec fixes the MECHANISM — PITR — not
    the RPO number; the number is operator configuration, never invented
    here)
  - HA standby: streaming replication, primary + ≥1 standby (40 §5.4)
  - Backup verification: every base backup must be restore-tested on a
    scratch instance before it counts as a backup (an unverified backup
    is a hope, not a backup)

Object storage (blobs, per 40 §5.1 role):
  - Bucket versioning ON (point-in-time object recovery)
  - Lifecycle rules = operator retention policy

Secret Manager:
  - Custody backend's OWN backup/unseal material handled per the
    ADR-0007-accepted backend's documented procedure — NEVER exported
    through the SecretManagerPort (the port deliberately has no
    dump/export operation; 20 §5)

Redis (ADR-0003 roles: cache/queues/rate-limit/sessions):
  - RDB/AOF persistence per deployment profile; Redis is NOT a source
    of truth (40 §5.1) — its loss is a degradation, not data loss;
    backup priority is Postgres first, object storage second.
```

## 2. What is deliberately NOT here

```text
- No backup cron/job code: nothing can run against a database that does
  not exist (Lane C closed). Fabricating an unrunnable job would violate
  the 41 §49 honesty rule.
- No RPO/RTO numbers: the specs mandate mechanisms (backups, PITR, HA
  standby, DR region readiness) — the recovery objectives are operator
  policy, recorded as configuration when Lane C opens.
- No provider selection: the WAL archive target depends on ADR-0006's
  accepted backend.
```

## 3. Verification obligations when Lane C opens

```text
1. archive_command ships WAL to the configured bucket (observe a WAL
   segment land).
2. Base backup + PITR restore drill to a scratch instance succeeds and
   is REPEATED on a schedule (restore-tested backups only).
3. Standby promotion drill (40 §5.4 HA requirement).
4. All four checks recorded in the state file with dates — same
   checkpoint protocol as every other verified claim in this repo.
```
