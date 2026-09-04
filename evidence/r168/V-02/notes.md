# V-02 — §6.7 mypy widen (verification track, outside the change budget)

- FAIL FIRST (measure): `mypy --strict -p apps.api` → 0 errors / 22 files; `-p apps.composition` → 0 errors / 15 files; `-p apps.admin_agent` → 0 errors / 7 files (fail_first.txt = apps.api measurement).
- FIX: `pyproject.toml [tool.mypy].packages` widened `["core"]` → `["core", "apps.api", "apps.composition"]` (Round A + Round B scopes together, since both measured zero). `apps.admin_agent` stays out of the gate per mandate (R169) — listed in manifest `deferred_out_of_gate`.
- PASS: `python3 -m mypy` (gate call) → see after_fix.txt.
- Guard: `tests/verification/test_green_manifest_guards.py::test_mypy_gate_scope_never_shrinks`.
- Docs: OPERATIONS §10 — types row now points at the gate scope; boto3 stubs naming corrected (`boto3-stubs[s3]`, installs `mypy_boto3_s3`; not `types-boto3`).
- No production code changed (budget untouched: 0/5, 0/5).
