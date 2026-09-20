# R191 HANDOFF — General Agent + Template/Skill foundation + App Factory first slice

## 1. Authority
Operator directive "QEVION — R191 EXECUTION DIRECTIVE". Declared in `final_docs_v3/60_DECISION_LOG.md` R191-DEC-01 BEFORE any production commit. Baseline `main dc1c62de`.

## 2. Boundaries
Additive-only. ONE router, ONE execution service, ONE strategy engine (`StrategyExecutor`), ONE skill registry. No AppFactory engine/router/registry. Templates are data. No provider-name branching. Frozen contract SHAPE unchanged (`--check` MATCHES). No served route added (P-R191-01 proposal). App Factory generation NOT in this round.

## 3. Slice
`round_r191` ceiling 6: `core/contracts/agent_template.py`, `core/execution/templates.py`, `core/agent/general.py`, `core/agent/app_factory.py`, `apps/agent_dev/project_inspector.py` (+1 headroom `apps/composition/runtime.py`).

## 4. Proof plan
RED tests A–F/K–O/Q + App Factory slice → implement → GREEN → G–J re-verified on unchanged router/executor → regression → fresh-clone gate + gateway → ratchet → PR → post-merge gate → closure.

## 5. Stop conditions
Seventh production file → STOP. Served route / frozen-shape change → PROPOSAL. Tenant-owned templates needing a new ownership rule → PROPOSAL (use `origin=workspace` only as a label over existing tenancy).

## 6. Ledger
`evidence/r191_state_ledger.md`.
