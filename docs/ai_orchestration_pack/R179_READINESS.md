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
