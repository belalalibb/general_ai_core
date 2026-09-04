# R168 — Conflict Ledger (INV-6)

Format per entry: both texts, touched files, stricter reading, disposition (APPLIED-STRICTER / OPEN).

## C-01 — "NOT EVALUATED (deferred)" vs the closed reason set

- **Text A (mandate §6.7):** "apps/admin_agent is deferred to R169 and recorded NOT EVALUATED (deferred)."
- **Text B (mandate §6.4):** "the reason must come from the closed set of missing dependency, credential unavailable, environment unavailable — any other reason is a FAIL".
- **Touched files:** `engineering/verification/green_manifest.json`, `engineering/verification/check_repo.sh`.
- **Stricter reading:** §6.4. A NOT EVALUATED line with reason "deferred" would turn the gate red by the mandate's own rule.
- **Disposition:** APPLIED-STRICTER. The item is recorded in the manifest under `deferred_out_of_gate` (not a gate line, not green, listed verbatim in §11 as OUT OF SCOPE (R168): deferred to R169 — mypy strict apps/admin_agent). The `not_evaluated` list carries only closed-set reasons.

## C-02 — pytest `addopts="-q"` hides the summary line the gate must parse

- **Text A (repo `pyproject.toml` L78):** `addopts = "-q"`.
- **Text B (mandate §6.1):** the script must "distinguish failed from skipped and … report counters".
- **Touched files:** `engineering/verification/check_repo.sh` (reads the summary line), `pyproject.toml` (NOT edited).
- **Stricter reading:** measure counters without changing the repo's pytest defaults for developers.
- **Disposition:** APPLIED-STRICTER. The script passes `-o addopts="" -q` per slice so exactly one `-q` applies and the summary line is emitted; `pyproject.toml` is untouched. Recorded here because a second `-q` from the script would silently produce zero counters (observed during baseline capture).

## C-03 — pytest counters depend on provider credentials present in the shell

- **Text A (mandate §6.1):** the gate records a single measured `passed` count in the manifest and in `PROJECT_EXECUTION_STATE.md`.
- **Text B (repo tests):** 15 tests are env-gated on credentials (`GSK_API_KEY` 8, `GROQ_API_KEY` 6, `GW_GROQ_API_KEY` 1) and flip skipped→passed when the sandbox shell exports those variables — the number is not a property of the tree alone.
- **Touched files:** `engineering/verification/green_manifest.json` (`pytest.last_measured`), `engineering/verification/green_manifest.md`, `evidence/r168/check_repo_v01_hermetic.txt`.
- **Stricter reading:** INV-5 (no invented green). A count inflated by ambient credentials is not reproducible by a reviewer without them.
- **Disposition:** APPLIED-STRICTER. The canonical `last_measured` is taken from a hermetic run: `env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY bash engineering/verification/check_repo.sh`. The floor gate (`min_passed`) is set from the hermetic count; a credentialed run can only exceed it, never fall below it. The 15 credential-gated skips stay classified as "credential unavailable" in the skip classification.
