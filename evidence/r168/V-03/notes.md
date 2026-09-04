# V-03 — §6.6 isolated test tenant (verification track)

- Conflict: C-04 (mandate rewire vs frozen caller-scoped derivation + INV-2). Disposition APPLIED-STRICTER: no production change.
- Proof: `tests/api/test_exercise_tenant_isolation.py` (4 tests) — dedicated probe tenant via `configure_tenant`; bystander untouched (used 0.0, store empty); record foreign lookup → ExecutionNotFound; probe budget exhaustion enforced on the probe tenant only.
- FAIL FIRST: not applicable as a red→green fix (no defect fixed); `fail_first.txt` records the negative control (a test asserting the bystander WAS charged fails).
- Budget: 0 production changes.
