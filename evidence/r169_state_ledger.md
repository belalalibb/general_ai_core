# R169 — state ledger (observed state, checkpoints, resumption points)

Repository `belalalibb/general_ai_core`, branch `main`. Every row is verbatim observed output at the stated HEAD.

## §2 facts re-verified at 9876678c (2026-09-04)

| # | Fact | Observed |
|---|---|---|
| 1 | `git rev-parse HEAD` / `origin/main` / `git status --porcelain` | `9876678cfdab552b3ee6dc1d823ea6b329e3e1e4` / `9876678cfdab552b3ee6dc1d823ea6b329e3e1e4` / clean (0 lines) |
| 2 | `check_repo.sh` (hermetic, `env -u GSK_API_KEY -u GENSPARK_TOKEN -u GSK_TOKEN`) | `RESULT: PASS (all repo governance checks)`, `EXIT=0` — full output `evidence/r169/check_repo_baseline.txt` |
| 3 | pytest summary (from the verifier's 5 slices) | `passed=2777 failed=0 errors=0 skipped=64` |
| 4 | `/v1/` literal count in `ui/admin/app.js` | 73 |
| 5 | byte sizes app.js / index.html / styles.css | 79351 / 32385 / 16392 (matches mandate; delta 0) |
| 6 | `.md` under `docs/ai_orchestration_pack/final_docs_v3/` | 20 (matches) |
| 7 | `core/tools/` | `__init__.py errors.py executor.py gate.py registry.py source_reader.py` (+`__pycache__`); NO write-capable tool: `source_reader.py` docstring "READ ONLY — this module contains no write, delete, or execute path"; grep for write/unlink/remove/mkdir finds none |
| 8 | `green_manifest.json` | `pytest.gate = {failed:0, errors:0, max_skipped:64, min_passed:2777}`; `pytest.last_measured = {passed:2762, at_head:0ef7820a, …}` — STALE (last hermetic measurement 2777 at c25f586f, `evidence/r168/D-02/check_repo_after.txt`); NOT lowered; will be updated upward only. `change_budget` has `counts_production_code_under=[core/, apps/, infrastructure/]`, `round_a` 4/5, `round_b` 4/5 (R168 rounds; both closed) |
| 9 | `apps/api/capabilities.py` `CAPABILITY_IDS` (16) | execute.sync, execute.async, execute.token_streaming, executions.progress_sse, conversations.persistence, context.composition, models.listing, skills.listing, usage.reporting, webhooks.registration, webhooks.delivery_staging, admin.control_plane, learning.lifecycle, rate_limits.execute, auth.sessions, health.liveness — states are DERIVED at `create_app` composition time (module is pure data; no static state list) |

Recovery this session: sandbox had been reset (deps absent, credential store absent). Restored: `pip install -e ".[dev]"`, git identity, GitHub credential via `git credential.helper store` (`~/.git-credentials`, mode 600, outside the repo; raw token never written anywhere tracked). `origin/main` fetched and equals HEAD.

## Checkpoints

| When | Item | Note | HEAD | Status |
|---|---|---|---|---|
| 2026-09-04 | §0/§2 | VERIFY → RESTORE → baseline verifier PASS 2777/0/0/64; ledgers created; manifest gains `round_r169` (ceiling 6, roots core/ apps/ ui/) + verifier/guard extended ADDITIVELY | see commit | done |
| 2026-09-04 | A1 | `docs/r169/CAPABILITY_MAP.md` — read/write/git surface map + design commitments | d3a5ca4 | done |
| 2026-09-04 | A2 | contract `core/contracts/source_write.py`; engine `core/tools/source_writer.py` (budget 1/6); tests `tests/tools/test_source_writer.py` 42 passed; evidence `evidence/r169/A2/`; IMPL-014. Sandbox reset wiped the first uncommitted A2 pass — recreated from ledgered design, committed immediately | see commit | done |
| 2026-09-04 | A3/A4 | `apps/agent_dev/{__init__,surface}.py` composition root (budget 2/6; committed 631970f before tests to survive resets); tests `tests/agent_dev/` 37 passed (28 surface + 9 INV-7 admin boundary) committed 080c534; evidence `evidence/r169/A3/`; manifest rest slice += tests/agent_dev; IMPL-015. Resets #8 and #9 wiped uncommitted tests — recreated twice from ledgered design | see commit | done |
| 2026-09-04 | A5 | contracts `core/contracts/{repo_binding,publish_mode}.py` + 15 tests (d381489); `apps/agent_dev/git_tools.py` (budget 3/6, 796b0dd); surface wiring (budget 4/6, 833a6ce); tests `tests/agent_dev/test_git_tools.py` 38 passed (1dd565c); evidence `evidence/r169/A5/`; IMPL-016. Live GitHub transport NOT EVALUATED (fake transport only; token never used/logged). Reset #11 hit mid-edit — no loss | see commit | done |
| 2026-09-04 | A6 | `apps/agent_dev/http.py` dev router `GET /v1/dev/bindings/{binding_id}/publish-modes` (budget 5/6, 4ae4e09); tests `tests/agent_dev/test_publish_modes_http.py` 10 passed (7831b69); evidence `evidence/r169/A6/`; IMPL-017. Router NOT mounted in `apps/api/app.py` (operator decision, would be change #6). UI OUT OF SCOPE. Reset #12 wiped the uncommitted test file once — recreated | see commit | done |
| 2026-09-04 | B1 | `docs/r169/SANDBOX_OPTIONS.md` — design-only comparison of six sandbox options (in-process subprocess, UID+rlimit, bwrap/unshare, rootless container, microVM, remote provider) against the existing `CommandPolicy`/`CommandRunnerPort` seam; recommendation O3/O4, inert-never-degraded, contract additions listed. NO command execution surface added; budget unchanged 5/6 | see commit | done |
