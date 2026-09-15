# R184 findings ledger (every measurement that FAILED or contradicted the brief; a finding gets an entry, never an off-books fix)

Precedent: `evidence/r183_findings_ledger.md`. Round budget: `round_r184` ceiling **2** (spent) — no further finding may be fixed inside `core/ apps/ infrastructure/` under this round id.

| id | finding | evidence | severity | disposition | owning round |
|---|---|---|---|---|---|
| F-R184-01 | Test-fixture only: `_seed_execution` (tests/api/test_aa1_api_seams.py) inserts a SUCCEEDED report with `nodes=()`; the user read `GET /v1/executions/{id}` then raises `IndexError` in `ExecutionReport.final_output` (`core/execution/service.py:201`) because SUCCEEDED implies a last node. Pre-existing property of the seeding helper, surfaced by the new user-read assertion; the R184 test seeds RUNNING instead. Whether a node-less SUCCEEDED report should be representable is a `core/` question outside this round's budget. | first GREEN attempt of `test_evaluation_list_route_and_user_read_are_unchanged` | S4 (test fixture; no served behaviour affected) | RECORDED; test adjusted; not fixed in production (frozen, budget spent) | unassigned (record only) |

Carried forward, recorded, NOT worked: Provider slice / provider verification, App Factory, API keys, webhook delivery (UNDEFINED — operator contract first); F-R182-03 baseline drift (operator chose "leave"); F-R182I-03/04/06 standing rules.
