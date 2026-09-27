# ui_recon_shell — state ledger

| # | when | step | result |
|---|---|---|---|
| 0 | 2026-09-27 | branch ui_recon_shell from main ffb97453; DESIGN FREEZE approved (OD-1 = B, OD-2 = APPROVED, OD-3 = CONFIRMED) | this commit |
| 1 | 2026-09-27 | records: UI-RECON-DEC-01; manifest round_ui_recon_shell (ceiling 0) + ui_shell_static_check guard frame declared BEFORE code | this commit |
| 2 | 2026-09-27 | FIRST RED: tests/ui/test_shell_recon_guard.py fails CLOSED (shell absent) | 935eb33c (red_guard.txt) |
| 3 | 2026-09-27 | M1 skeleton: api.js (ONE transport, CSRF header), router.js (hash, pushState/hashchange), context.js (sessionStorage non-secret ctx), components.js, shell.js, index.html | 057510ac |
| 4 | 2026-09-27 | pages: auth, command (OD-1 = B: no user topology), work (model-first picker, Models, context, memory, webhooks, usage) | aaf0df13, 13a517fc |
| 5 | 2026-09-27 | pages: runs (SSE timeline, agent trace, admin evaluations/capture), build (plan-only App Factory) | 89ee6e51 |
| 6 | 2026-09-27 | pages: intelligence (skills+imports, learning dashboard/samples/promote with evidence_refs, scenarios, evaluation, context lab) | f18e92a0 |
| 7 | 2026-09-27 | pages: control (capabilities 1:1, catalog search-first, provider detail with NOT AVAILABLE accounts/RPM, generated Changes forms from served actions, plans, routing, usage, audit, notifications, system, self-review, source, engineering) | c4e06fc8 |
| 8 | 2026-09-27 | shell.css design system (desktop/tablet/390px) | f111f507 |
| 9 | 2026-09-27 | guard suite GREEN 34/34 on the 14 declared files (green_guard_static.txt) | b468ab67 |
| 10 | 2026-09-27 | FINDING (real browser): header overflowed at 390px (closed session menu still contributed width) → CSS fix; K_no_horizontal_overflow false → true | ccdee09b |
| 11 | 2026-09-27 | REAL Chromium proof tests/ui/test_shell_recon_browser.py 3/3 (fail-closed) + journey facts.json + 13 PNGs (A–L); live-provider plan refusal rendered verbatim as entitlement_exceeded (D0_live_provider_refusal.png, honest failure — live success NOT VERIFIED) | 3c66bdd4, 4b763ee0 |
| 12 | 2026-09-27 | OD-3: api.js /v1/ ceiling frozen at measured 32 (down-only); tests strict-typed | 7e137bb5 |
| 13 | 2026-09-27 | canonical gate (first run): pytest 4047/0/0/64 PASS (+31 = 34 guard + 3 browser − 6 parametrize collapse… see gate txt); mypy/ruff FAIL on the two new test files only → fixed in 7e137bb5; re-gate recorded in row 14 | /tmp → gate_first_run.txt |
| 14 | 2026-09-27 | ENV FINDING: fresh venv resolved SQLAlchemy 2.1.1 → mypy --strict flags infrastructure/db/learning.py:392 (var-annotated) — reproduced on main ffb97453 unchanged ⇒ pre-existing/environmental, not this round; with sqlalchemy 2.0.54 (declared >=2.0) mypy clean | gate_worktree_d62edb21.txt |
| 15 | 2026-09-27 | GATE OF RECORD (worktree d62edb21): RESULT: PASS passed=4047 failed=0 errors=0 skipped=64; mypy/ruff/import-linter/secret scan PASS; round_ui_recon_shell 0/0; ratchet min_passed 4016 → 4047 | this commit |
| 16 | 2026-09-27 | UI-RECON-DEC-02 recorded; origin/main still ffb97453 (branch is a fast-forward, no rebase); PR opened | this commit |
