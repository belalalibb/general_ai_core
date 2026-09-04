# C4 — atomic source writes + deny-check path normalisation

## What changed (budget 1 change / one commit, two files → total 4/8)
Two coherent production edits, each charged as one change (the directive counts per file under core/ apps/):
- **`core/tools/source_reader.py`** — NEW module-level `normalize_deny_path(rel_posix)` and `is_denied(rel_posix, patterns)`;
  `SourceReader._denied` now delegates to `is_denied`. Module functions (not methods) keep the `SourceReader` public-surface pin
  `test_public_surface_is_read_only` byte-identical. `DEFAULT_DENIED_PATTERNS` unchanged (13 globs — the LIST is C1's business, C4 changes the CHECK).
- **`core/tools/source_writer.py`** — NEW `_atomic_write(target, blob)`; both `target.write_bytes(blob)` call sites (create, overwrite) replaced;
  `_denied` delegates to the shared `is_denied` so reader and writer cannot drift. `fnmatch` import dropped (no longer used).
- **Budget-free:** `core/tools/denied_paths.py` comment-only edit — the C1 case variants are now described as "belt and braces alongside the
  C4 normaliser" instead of "patch only". No code change.

## Normalisation (per path segment, idempotent, pure)
NFKC → drop Unicode categories Cf/Cc/Mn/Me (zero-width joiner/space, BOM, soft hyphen, controls, combining marks) → cut at first `:`
(NTFS alternate data stream `name:stream`, `name::$DATA`) → `rstrip(". ")` → `casefold()`. Empty segments dropped.
`is_denied` matches the RAW path first, then the normalised one only if it differs — so no existing match can be lost, only gained.
Verified variants (default 13-glob list, no C1 list): `.ENV`, `.Env.local`, `.env::$DATA`, `.env:hidden`, `.env.`, `.env `, `.env. . `,
`.e<ZWJ>nv`, `<ZWSP>.env<BOM>`, `.e<SHY>nv`, `nested/.ENV.production`, `Server.KEY`. Non-denied stay readable: `pkg/mod.py`, `environment.py`.
Reader `read_file` refuses, `list_files` hides, `search` hides; writer `create` refuses with `path_denied`, nothing created, no op consumed.

## Atomic write
Same-directory temp `.<name>.<uuid>.tmp` opened `O_EXCL` → write → flush → fsync → (chmod to the pre-existing mode for overwrite) →
`os.replace` → best-effort directory fsync. On any `OSError` the temp is unlinked and the error propagates to `write()` which already
maps it to the `io_error` refusal (data). Proven: interrupted `os.replace` ⇒ original bytes intact, no `.*.tmp` left, `ops_used` unchanged,
and the NEXT CAS overwrite against the ORIGINAL digest succeeds (the failure did not poison the precondition). Create interrupted ⇒ target absent.
Mode: overwrite preserves 0o755; create honours umask (0o644 under 0o022) — identical to the previous `write_bytes` behaviour.

## Trade-off noted
`normalize_deny_path` cuts at the first `:` in a segment. A legitimate POSIX filename containing `:` is normalised to its prefix for the
DENY CHECK only — it may become denied if the prefix matches a pattern (e.g. `.env:notes`). It is never renamed or otherwise affected.
This errs toward refusal, consistent with fail-closed. Documented here and in IMPL-021.

## Fail-first
`fail_first.txt`: `ImportError: cannot import name 'is_denied' from 'core.tools.source_reader'` at `9598239`.

## Tests
`tests/tools/test_source_hardening_r172.py` — 39 passed. Suites `tests/agent_dev tests/tools tests/verification`: 358 passed, 1 xfailed
(319+1 at C3). Pre-existing `test_source_reader.py`/`test_source_writer.py`/`test_denied_paths_r172.py`: 122 passed 1 xfailed, files unmodified.
`tests/admin_agent` (SourceReader consumer, frozen tree): 130 passed. ruff + mypy clean.
