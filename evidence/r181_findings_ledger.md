# R181 findings ledger (every measurement that FAILED or contradicted the brief; a finding gets an entry, never an off-books fix)

Precedent: `evidence/r180_findings_ledger.md`. Severities: S1 release-blocking … S4 cosmetic.

| id | finding | evidence | severity | disposition |
|---|---|---|---|---|
| F-R181-01 | After formatting, the 0022 `op.drop_constraint(` call wraps onto three lines and the parity test `test_each_downgrade_drops_everything_its_upgrade_creates` (regex `op\.drop_constraint\("(fk_\w+)"` — no `\s*` unlike its `create_foreign_key` twin) failed to see the dropped FK: `created_fk={'fk_usage_ledger_execution_id_executions'} != dropped_fk=set()`. | targeted run on the first Q6 landing (`1 failed, 169 passed`) | S3 (test-only) | FIXED test-only: the drop pattern now tolerates the same wrap as the create pattern (`tests/db/test_schema_contract_parity.py`); no production file touched, budget unaffected |

Closed carry-overs from earlier ledgers (dispositions written at their source rows):
- **F-R179-06** (r179 ledger) → CLOSED by Q6 / migration 0022 (R181-DEC-01); live: `evidence/r181/q6_live_fk_verification_7a41caff.txt`, `evidence/r181/durability_measured_7a41caff.json` (P4 6.0 → 8.0 across SIGKILL).
- **F-R179-04** usage half (r179 ledger) → CLOSED with F-R179-06 (audit half was closed in R179 Q1).
- **F-R175-04** (r175 ledger) → CLOSED: `check_repo.sh` step 1b interpreter guard; `tests/engineering/test_check_repo_interpreter_guard_r181.py`.
- manifest `deferred_out_of_gate` mypy `apps.admin_agent` → CLOSED: admitted to the gate (215 files clean).

Formally UNDEFINED / DEFERRED (not worked, not invented): Q7, Provider slice. Feature-scope (record-only): D-11 residue (`CREDENTIAL_*`, `PROVIDER_ACCOUNT_USED`), in-process engineering tickets/grants.

Severity totals: S1 0 · S2 0 · S3 1 found / 1 fixed (test-only) · S4 0.
