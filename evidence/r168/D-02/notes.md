# D-02 — Groq normaliser misclassifies `detail`-only 400 model-not-allowed (S2, MISCLASS)

- Defect: proxy answers HTTP 400 `{"detail": "Model '<x>' is not allowed. See GET /v1/models…"}` (no `error.code`); `_normalize_http_response` only read `error.code`/`error.param` → `bad_request` (request-indicting ⇒ no retry, no failover). Captured shape: `tests/certification/shapes/genspark_llm_unknown_model.json`.
- FAIL FIRST (2f310a65): `tests/providers/test_d02_groq_detail_only_400.py` — `GroqAdapter` + `httpx.MockTransport`; 1 failed (`bad_request / http_400`), 3 guards passed (`fail_first.txt`).
- FIX (9118f4d7, `providers/real/groq/adapter.py` +32/−0, budget-free): `_is_model_not_allowed(response)` structural predicate (mirrors genspark_llm); new branch before the generic 400/413/422 branch → `MODEL_UNAVAILABLE`, `retryable=False`, `provider_code="model_not_allowed"`, safe message "requested model is not available at the provider". Detail text never crosses (asserted on the dumped `ProviderError`).
- Decision (INV-4, IMPL-012): other `detail`-only 400s stay `bad_request` — no captured evidence they are non-indicting. `error.code` paths unchanged (guard test).
- Certification row flipped: `test_shape_unknown_model_400_detail_only_is_model_unavailable`, prints `MAP|400_detail_model_not_allowed|model_unavailable|retryable=False|D-02 FIXED R168`.
- PASS: D-02 4 passed (`after_fix.txt`); `tests/providers/test_groq_adapter.py` + `tests/certification` 67 passed / 0 failed; ruff + `mypy --strict providers/real/groq/adapter.py` clean.
- NOT EVALUATED: live proxy round-trip of the disallowed model (credential unavailable / plan-exhausted key; hermetic gate is canonical, C-03).
- Docs: defect ledger D-02 FIXED + summary; `evidence/error_classification_map.md` row + gap note; IMPL-012.
