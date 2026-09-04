# D-10 — admin gate ordering: 422 schema hints to non-admins (S3, ORDER)

- FAIL FIRST: `tests/composition/test_d10_admin_gate_order.py` run against the pre-fix production tree (39e89322 `apps/api/app.py` + `runtime.py` swapped in, then restored): non-admin session ⇒ 14 of 59 admin operations answered 422 `validation_error` (the ledger's "16/64" was measured live at R167-A; hermetic OpenAPI enumeration at R168 has 59 admin operations, 14 typed-body POSTs); anonymous ⇒ 403 instead of 401 everywhere — `fail_first.txt`.
- FIX: the SAME middleware as D-07 (`apps/api/app.py`, counted once as Round A change #2): admin admission (401 anonymous, 403 non-admin) runs before FastAPI body validation on every `/v1/admin/*` path. Route handlers keep their `_admit(request)` (defence in depth; no signature refactor — the ledger's "route-signature refactor" concern did not materialise).
- PASS: `after_fix.txt` — 3 passed: non-admin ⇒ 59/59 constant 403 `unauthorized`; anonymous ⇒ 59/59 constant 401 `unauthenticated`; an ADMIN posting `{}` still reaches validation (422) — schema hints are admin-only.
- Budget: no additional production file beyond D-07's two.
