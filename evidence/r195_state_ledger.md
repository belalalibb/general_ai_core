# R195 state ledger

| # | When | State | Evidence |
|---|------|-------|----------|
| 1 | 2026-09-20 | R195 proposal delivered read-only (findings F1–F6); operator "APPROVE R195" with D1–D4 accepted | chat; R195-DEC-01 |
| 2 | 2026-09-20 | Declaration committed BEFORE code: R195-DEC-01, manifest `round_r195` (ceiling 4, used 0), handoff, this ledger | this commit |
| 3 | 2026-09-20 | RED recorded at c9b7f754 (both modules fail collection: missing `AdminAction` members / `secret_custody_from_env`) | `evidence/r195/red_r195.txt` |
| 4 | 2026-09-20 | Production 4/4 files at 1f55d782 (+ ruff import-order 01a93151); GREEN 20/20; mypy strict 4 files clean; ruff clean; freeze `--check` MATCHES; guards 33/33; pinned suites (tests/admin, action discovery R179, R193 composition, tests/agent_dev) 54/54 | `evidence/r195/green_r195.txt` |
| 5 | 2026-09-20 | Records: OPERATIONS §2 Vault rows TRUE + seeding; STATE_OF_TRUTH C3/C7 → DONE (G-BIND/G-TRUST/G-CRED); CAPABILITY_MAP `dev.governed_bindings`; ADMIN_UI coverage note (fd31a8cd) | commit fd31a8cd |
| 6 | 2026-09-20 | Regression 18 roots at fd31a8cd: 3107 passed / 14 skipped-xfail / 0 failed (EXIT=0). **Gate of record** fresh clone `2a636b50`: `RESULT: PASS` pytest 3872/0/0/64 (≥ 3852), gateway 194. D-6 ratchet `min_passed` 3852 → 3872; `ceiling_history` gate entry | `evidence/r195/{regression_fd31a8cd.txt, gate_head_2a636b50.txt, gateway_head_2a636b50.txt}` |
