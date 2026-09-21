# V1 ACCEPTANCE REGISTER — QEVION (R198, operator D1: accepted **as measured**)

**Posture:** v1 is accepted *as measured* by the recorded gates and evidence below. It is **not** claimed to be
production-ready: that claim is withheld while the D-03 row is `OPERATOR-OWNED-OPEN` (operator D1, R198-DEC-01).
Nothing in this register converts a deferred item into work; every row carries a status from the closed set and an
evidence path. Guard: `tests/verification/test_v1_acceptance_register_r198.py` (no silent loss).

**Status closed set:** `ACCEPTED-AS-MEASURED` · `DEFERRED-BY-RULING` · `OPERATOR-OWNED-OPEN` · `NOT-EVALUATED` · `DECLARED-UNCONSUMED`

**Baseline of this register:** `main fbdd1f0b` (post-R197). Gate: fresh clone `8ced2242` PASS 3914/0/0/64, gateway 194;
contract freeze 15 modules · 46 served routes, `--check` MATCHES; 18 regression roots 3123 / 14 / 0.

## A. Audit decisions (operator rulings "APPROVE THE AUDIT RECOMMENDATIONS" and later)

| id | subject | status | where it lives / evidence | owner |
|---|---|---|---|---|
| AD-1 | governed binding registration + remote trust via the admin change lifecycle (no `/v1/dev` write routes) | ACCEPTED-AS-MEASURED | R195 (PR #48 → `16048078`): `AdminAction` +3 → `AdminArea.TOOLS`; `tests/admin/test_r195_governed_dev_bindings.py` (16); `evidence/r195/` | engineering |
| AD-2 | existing durable `SecretManagerPort` (Vault) for dev credentials | ACCEPTED-AS-MEASURED | R195 `secret_custody_from_env` (`apps/composition/runtime.py`); `tests/composition/test_r195_secret_custody.py` (4); live Vault round-trip NOT part of the gate | engineering |
| AD-3 | read-only `/v1/templates` + `/v1/templates/{ref}`, built-in registry composed; workspace ownership = later direction | ACCEPTED-AS-MEASURED | R196 (PR #50 → `e08b04f6`), 44→46 routes re-derived in-round; R197 Workbench picker (PR #52 → `8ced2242`); `evidence/r196/`, `evidence/r197/` | engineering |
| AD-4 | `SkillManifest` DATA-only semantics for v1 | ACCEPTED-AS-MEASURED | contract frozen (15 modules); no executable-skill path exists; `tests/skills/` | engineering |
| AD-5 | v1 topology = durable single-server, single API process, external Postgres; multi-replica future | ACCEPTED-AS-MEASURED | `docs/architecture/ADR-0014_V1_PRODUCTION_TOPOLOGY.md` (R198-A); live re-measure on current main `evidence/r198/live_durability_measured_*.json` + `evidence/r198/live_r179_postgres_*.txt` (R198-B, disposable local PostgreSQL 17.11 + pgvector 0.8.0, real alembic, SIGKILL P1–P4; "single node; no production claim") | engineering |
| AD-6 / DEC-03 | application-scoped credentials deferred beyond user testing | DEFERRED-BY-RULING | R178 DEC-03; OPERATIONS §8.1 | operator |
| AD-7 | tenant-code sandbox / App Factory code execution deferred until a sandbox architecture is approved | DEFERRED-BY-RULING | R191–R196 records; `ws_run` is a scrubbed subprocess, not a sandbox (OPERATIONS §13) | operator |
| D-03 | credential rotation + history purge before public deployment; never claimed without evidence | OPERATOR-OWNED-OPEN | `evidence/r198/D03_CREDENTIAL_ROTATION_AND_PURGE.md` (measured state + operator checklist). Measured: leak commit `521d8850` (tree-redacted by `28989b04` only); GitHub secret-scanning alert #1 Groq **open, publicly_leaked**; alert #2 PAT dismissed `used_in_tests` (not a rotation proof); repository **PUBLIC**; legacy branches carry the blobs. No rewrite by engineering without the operator-controlled procedure (D4). | operator |
| N-5 | tenant dev surface path — explicit operator decision, never chosen silently | DEFERRED-BY-RULING | R194-F1 / R194-DEC-02; unchanged through R198 | operator |
| N-9 | branch / PR hygiene: five legacy branches (`feature/platform-capability-assessment`, `genspark_ai_developer`, `r178_decisions_verified_units`, `r178_p01_subject_verified_units`, `r178_verified_units`) all diverged and carrying the D-03 blobs | OPERATOR-OWNED-OPEN | bound to the D-03 purge procedure (operator D5): removed only after the historical record is preserved through that procedure; open PRs = 0; round branches deleted per compare rule since R186 | operator |

## B. Deferred blocks carried from the freeze records (NO SILENT LOSS)

| id | subject | status | where it lives / evidence | owner |
|---|---|---|---|---|
| R189 §6.1 | Modality limits enforcement (`PlanLimits.modality_limits` declared, unenforced on the execute path) | DEFERRED-BY-RULING | `evidence/r189/CONTRACT_FREEZE_RECORD.md` §6.1 | operator |
| R189 §6.2 | Admin fallback source (`admin_fallback_chain` producer + wiring) | DEFERRED-BY-RULING | §6.2 | operator |
| R189 §6.3 | D-03 — credential unavailable (live two-account failover) — see row D-03 and `not_evaluated` #1 | NOT-EVALUATED | §6.3; manifest `not_evaluated[0]` | operator |
| R189 §6.4 | Account pool lease / fencing consumer (OPTIONAL in v1) | DEFERRED-BY-RULING | §6.4; Disposition C | operator |
| R189 §6.5 | Async execution strategy (P-R188-03 NO) | DEFERRED-BY-RULING | §6.5 | operator |
| R189 §6.6 | Durable / shared resource signals (P-R188-04 NO) — the multi-replica dependency named in ADR-0014 | DEFERRED-BY-RULING | §6.6 | operator |
| R189 §6.7 | Training consumer | DEFERRED-BY-RULING | §6.7 | operator |
| R189 §6.8 | Feedback intake | DEFERRED-BY-RULING | §6.8 | operator |
| R189 §6.9 | Strategy-output evaluation | DEFERRED-BY-RULING | §6.9 | operator |
| R189 §6.10 | P-R189-01 — model identity across providers (RECOMMENDED, not decided) | DEFERRED-BY-RULING | §6.10 | operator |
| P-R191-01 | served templates — write half ("register user template") | DEFERRED-BY-RULING | `evidence/r196/CONTRACT_FREEZE_RECORD_R196_UPDATE.md` (read half EXECUTED R196; UI consumer R197) | operator |
| P-R192-03 | template ownership / durability (workspace ownership = recorded later direction) | DEFERRED-BY-RULING | `evidence/r196/CONTRACT_FREEZE_RECORD_R196_UPDATE.md` | operator |
| not_evaluated #1 — real two-account provider round-trip (D-03 Class-A failover against live providers) | credential unavailable (closed-set reason) | NOT-EVALUATED | `green_manifest.json` `not_evaluated` (count 1, ceiling 2); printed by every gate as NOT EVALUATED, never green, never FAIL | operator |

## C. UI ↔ backend integration (operator D6: recorded, no extra UI round)

46 served `/v1` paths; the three guarded UI trees (`ui/admin` 73 = N0, `ui/app/command` 12, `ui/app` 22) consume 41
(9 of them through `${step}` interpolation of the change / source-change lifecycle). The remaining served paths:

| route | reason it has no UI consumer | status | evidence |
|---|---|---|---|
| `GET /v1/admin/evaluations/{id}` | evaluation detail read; the Command Center renders `evaluation_status` from the execution record (R185), not this route | DECLARED-UNCONSUMED | `tests/ui/test_command_center_experience_r185.py`; freeze baseline |
| `GET /v1/admin/learning/dashboard` | declared INERT surface (R182_HANDOFF §11 row 16) — honest placeholder only | DECLARED-UNCONSUMED | `docs/ai_orchestration_pack/R182_HANDOFF.md` §11 |
| `GET /v1/templates/{ref}` | R197 operator D4: picker consumes the list only; detail view not in R197 | DECLARED-UNCONSUMED | R197-DEC-01 D4; `evidence/r197/` |
| `GET /v1/webhooks/{id}`, `DELETE /v1/webhooks/{id}` | console lists webhooks (`GET /v1/webhooks`) and registers them; per-id read/delete not surfaced | DECLARED-UNCONSUMED | `ui/admin/app.js` (webhooks table); `docs/architecture/ADMIN_UI_BACKEND_COVERAGE.md` P6 |

## D. Cross-cutting acceptance facts (measured at the baseline)

| area | fact | evidence |
|---|---|---|
| Security | hardening headers on every response; CSP + `X-Frame-Options: DENY`; admin-gated OpenAPI on the durable profile; per-tenant/IP rate limits; replay protection; IDOR + log-secret-leakage suites; pre-commit secret scanner 5/5 declared exceptions; gate = mypy strict + ruff + import-linter + secret scan + no `.env` | `tests/security/` (8 modules); `evidence/r197/gate_merge_8ced2242.txt` |
| Tenancy | shared multi-tenant architecture unchanged R195–R198 (production diff EMPTY in R197/R198); 29 cross-tenant / isolation tests; capability firewall | `tests/security/test_execution_idor.py`, `test_capability_firewall.py`; `tests/api/` |
| Contracts | 15 frozen modules · 46 served routes; every additive change re-derived in a declared round with a freeze record | `engineering/verification/contract_freeze_baseline.json`; `evidence/r189/`, `r191/`, `r192/`, `r196/`, `r197/` |
| Regression | 3914/0/0/64 (gate), 18 roots 3123 / 14 / 0 | `evidence/r197/` |
| Durable profile | R181 measured (`7a41caff`) and R198 re-measured on current main with real PostgreSQL 17 + pgvector, real alembic 0001→0022, SIGKILL P1–P4 | `evidence/r181/`, `evidence/r198/` |
| Deployment artefacts | none in the repository (no Dockerfile / compose / process unit / CI workflow); ADR-0014 records the topology deployers must realise | ADR-0014 §1, §2.2 |
