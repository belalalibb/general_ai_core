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
