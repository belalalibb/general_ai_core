# R179 READINESS — analysis (operator directive Part A §4.8)

Round: R179 on `genspark_ai_developer_r179` (base `main` f5cbe48c = R178 merge). Gate clone: d747b158, `env -i`
(`evidence/r179/final_gate_d747b158.txt`). Everything below is derived from committed evidence; nothing is claimed
that a test or a measurement did not show.

## Part 1 — What R179 changed and how it was proven

| Mandate | Outcome | Proof |
|---|---|---|
| 4.1 operational truth | `docs/OPERATIONS.md` §8.1 (custody/retention/holds/release runnable from docs), §10 (B6 governance truth), §13 (measured durability limits); `RUN.md` identity binding corrected (auth-only vs `DEV_DEMO_PRINCIPAL=1` hybrid); `60_DECISION_LOG.md` R178-ACK + R179-DEC-01..06 (append only) | commits f8faebba, 445e1aee, 9b934708 |
| 4.2 self-description | ONE widening `learning.custody_governance` (22→23), row derived from the mount condition; every mounted `/v1/admin` family owned by a specific shelf row | `tests/api/test_capability_shelf_coverage_r179.py` (4), pin test updated with justification |
| 4.3 action discovery | `GET /v1/admin/capabilities/actions` = pure function of `ACTION_AREA` + `FINAL_ACTIVE_ADMIN_AREAS`; no hand-maintained names; frozen consumers untouched; payload half NOT exposed (DEC-A) | `tests/api/test_action_discovery_r179.py` (5); route pins 73→74 conscious |
| 4.4 durability measured | real `python -m apps.main` + SIGKILL −9 between phases | `evidence/r179/durability_measured_before.json`; F-R179-01..04 |
| 4.5 durability corrected | composition seam only (`apps/composition/memory.py` + runtime binding) — P1 memory 1→1, P2 conversation 200/200/200 | `evidence/r179/durability_measured.json`; `tests/composition/test_durable_memory_r179.py` (13) |
| 4.6 deploy truth | real alembic base→0020→base→0020 + populated-downgrade refusal (2); rolling pair MEASURED (F-R179-05); crash DURING a write → zero orphans, same-key retry 201 | `tests_live/r179` 5 passed; `evidence/r179/deploy_truth_rolling_crash.json` |
| 4.7 operator visibility | (a) `GET …/custody/holds` read-only; (b) release `outcome` tri-state + 409 on contradiction; (c) intake row-refused vs layer-unavailable (503 + partial report) | `tests/api/test_operator_visibility_r179.py` (7); r178 live 59 passed after 1 conscious pin update |
| 4.9 exit numbers | gate 3533/0/0/64 (floor 3504 recorded); gateway 194; live r178 59 + r179 5; mypy/ruff/import-linter/secret scan clean; no `.env`; frozen trees zero diff | `evidence/r179/final_gate_d747b158.txt`, `gateway_final.txt` |

### diff == log table (production files under core/ apps/ infrastructure/, base f5cbe48c)

| file | git diff (+/−) | manifest `round_r179.log` entry | item |
|---|---|---|---|
| apps/composition/memory.py | +123/−0 (new) | yes | R179-DC |
| apps/composition/runtime.py | +13/−4 | yes | R179-DC |
| apps/api/capabilities.py | +48/−0 | yes (two edits, one slot) | R179-SD |
| apps/api/app.py | +13/−0 | yes | R179-SD |
| apps/api/admin.py | +80/−4 | yes (two edits, one slot) | R179-SD / OV |
| infrastructure/db/learning.py | +31/−0 | yes | R179-OV |
| apps/composition/learning.py | +27/−0 | yes | R179-OV |
| core/learning/lifecycle.py | +40/−1 | yes | R179-OV |
| apps/api/intake.py | +45/−11 | yes | R179-OV |
| **total** | **9 files, +413/−22** | **9 entries = changes_used 9 ≤ ceiling 9** | — |

Ceiling history 6 → 8 (4.5 triggered) → 9 (design note 60d09d95 committed BEFORE production commit ccfa9a7d).
Frozen: `ui/`, `apps/admin_agent/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`, `final_docs_v3` (20 files; only
`60_DECISION_LOG.md` appended) — `git diff f5cbe48c HEAD` empty for each tree except the append.

## Part 2 — Vision audit (PRESENT / WIRED / INERT / ABSENT)

| Vision element | State | Evidence |
|---|---|---|
| Durable memory & conversations (13 §5, 03 §3) | WIRED (durable profile) | 4.5 after-measure |
| Durable audit / usage | PRESENT, INERT in runtime (repositories exist, in-memory composed) | F-R179-04, DEC-B deferred |
| Custody governance (revoke/sweep/release/holds) | WIRED | shelf row AVAILABLE iff mounted; live 59 |
| Schema-level protection against stale writers | ABSENT | F-R179-05 (procedure only) |
| Promotion over HTTP in governed runtime | PRESENT, INERT | F-R179-02 (SECURITY grader not in active set → 409) |
| Capability shelf + exercise + action discovery | WIRED | 23 ids; actions route |
| Payload-schema discovery (DEC-A) | ABSENT (design only) | R179-DEC-03 |
| Scheduler for retention sweeps | ABSENT by decision (D2=(a) external timer) | OPERATIONS.md §8.1 |
| Live vendor / browser paths | not exercised this round | not_evaluated=2 unchanged |

## Part 3 — UI readiness per screen family (ui/ frozen; backend-first)

| Screen family | Backend surface | UI state |
|---|---|---|
| Capabilities shelf | `/v1/admin/capabilities` (+ `/actions`, `/exercisable`) | renders 23 rows; actions route NOT yet consumed (frozen) |
| Admin changes (ADMIN_ACTIONS) | `/v1/admin/changes/*` | hand-list pinned == enum − {capability_proposal}; discovery route ready to replace it after thaw |
| Learning lifecycle | `/v1/admin/learning/*` | intake report gains `layer_fault`/`not_attempted` (additive; UI ignores) |
| Custody governance | `/v1/admin/learning/custody/{holds,revoke,sweep,release-legacy-hold}` | no screen (API/agent only) |
| System / audit / usage | unchanged | unchanged |

## Part 4 — Factory readiness + external-consumer contract

- Readiness: deploy from docs (`OPERATIONS.md` §1 alembic, §8.1 custody procedure incl. "stop ALL old writers"); recovery
  after crash proven (zero orphans, idempotent retry); durable memory/conversations survive restart; audit/usage do NOT
  (documented). Rolling upgrades are NOT safe with old writers running (F-R179-05).
- External-consumer contract (stable this round): shelf rows `{id,state,evidence}` (23 ids, closed); actions read model
  `{scope, capability, vocabulary, actions[{action, area}], areas[{area, active, actions[]}]}`; release outcome
  `{released, outcome, reconciliation_ref}`; intake report additive fields `layer_fault`, `not_attempted`; 503 retryable with
  `details.report` on a layer fault; holds view `{tenant_id, legacy_hold, holds[{scope, policy_id, reason, recorded_at}]}`.

## Part 4 — Operator rulings round (`round_r179_rulings`, base dbddf4ca)

Rulings Q1–Q5 received after the R179 close (verbatim: `evidence/r179_state_ledger.md` "RULINGS Q1–Q5 received"). Order executed: Q1 → Q3 → Q4 → Q2; each tests-first, logged in the manifest before/at its production commit.

| ruling | outcome | proof |
|---|---|---|
| Q1 (DEC-B / F-R179-04) | AUDIT bound durably in the `DATABASE_URL` profile (4.5 seam pattern, `apps/composition/audit_usage.py`) — P3 audit **1→1→1** across SIGKILL. USAGE: binding the durable ledger was MEASURED to break every `/v1/execute` (F-R179-06, `usage_ledger.execution_id` NOT NULL FK vs reserve-before-row) → adapter composed, consciously NOT bound; usage still resets (5.0→2.0) → **Q6** | `evidence/r179/durability_measured_after_q1.json`, `F06_usage_ledger_fk_violation.txt`; `tests/composition/test_durable_audit_usage_r179.py` |
| Q3 (F-R179-02) | RESOLVED BY CAPABILITY: `SecretMaterialGrader` = first real `GraderType.SECURITY` (13 §7 credential scan, non-vacuous), activated through `active_types` + injectable `output_graders` on the ONE lifecycle policy service; `evaluate` returns `evaluation_id`; promote **201** on creation, **409** governed refusal for a credential-bearing sample. Live: promote 201, GOLD survives SIGKILL (`learned_keys` 1→1, `gold_blocks` 1→1) | `evidence/r179/durability_measured_after_q3.json`; `tests/api/test_security_grader_q3_r179.py` (18) |
| Q4 (DEC-A) | `PAYLOAD_FIELD_RULES` in `core/admin/service.py` = the ONE declared source; validator derives presence/shape from it (inline checks removed), action discovery publishes it as `fields` per action | `tests/api/test_payload_field_rules_q4_r179.py` (30) |
| Q2 (F-R179-05) | Smallest STRUCTURAL guard, no trigger, no policy in DDL: migration 0021 `custody_schema_generation SMALLINT NOT NULL` (backfill 1, server default dropped; metadata client default 2). Live rolling pair: OLD writer capture **500** `NotNullViolationError`, 0 rows landed; new writer 404 → release → 201 | `evidence/r179/deploy_truth_rolling_crash_after_q2.json`, `F05_old_writer_refused_by_0021.txt`; `tests/infrastructure/test_custody_schema_guard_q2_r179.py` (9) |
| Q5 (ui/ thaw) | NOT in this budget — next round's opening commit (N0=73 arithmetic binding) | — |
| Token | not a blocker; no credential material lands in the workspace or home directory (env-only push helper); rotation is the operator's action after merge | `R179_HANDOFF.md` §D |

### diff == log table (production files under core/ apps/ infrastructure/, base dbddf4ca)

| file | git diff (+/−) | manifest `round_r179_rulings.log` entry | item |
|---|---|---|---|
| apps/composition/audit_usage.py | +175/−0 (new) | yes | Q1 |
| apps/composition/runtime.py | +42/−14 | yes | Q1 |
| core/evaluation/graders.py | +59/−14 | yes | Q3 |
| core/evaluation/policy.py | +36/−0 | yes | Q3 |
| apps/api/app.py | +12/−1 | yes | Q3 |
| apps/api/admin.py | +32/−2 | yes | Q3 |
| core/admin/service.py | +163/−60 | yes | Q4 |
| apps/api/capabilities.py | +14/−5 | yes | Q4 |
| infrastructure/db/migrations/versions/0021_custody_schema_generation.py | +45/−0 (new) | yes | Q2 |
| infrastructure/db/tables.py | +15/−0 | yes | Q2 |
| **total** | **10 files, +593/−96** | **10 entries = changes_used 10 ≤ ceiling 10** (declared 8 → 10 with the Q3 design note BEFORE the Q3 production commit) | — |

Frozen trees (`ui/`, `apps/admin_agent/`, `core/tools/gate.py`, `PROJECT_EXECUTION_STATE.md`, `final_docs_v3` except the append-only decision log): zero diff vs dbddf4ca.

### Vision audit deltas after the rulings

| Vision element | was | now |
|---|---|---|
| Durable audit | INERT | **WIRED** (durable profile; P3 stable) |
| Durable usage | INERT | INERT — decision-gated (F-R179-06 → Q6), adapter composed |
| Schema-level protection against stale writers | ABSENT | **WIRED** (0021 structural guard, measured live) |
| Promotion over HTTP in governed runtime | INERT | **WIRED** (SECURITY grader; 201/409 measured) |
| Payload-schema discovery (DEC-A) | ABSENT | **WIRED** (`fields` from `PAYLOAD_FIELD_RULES`) |
