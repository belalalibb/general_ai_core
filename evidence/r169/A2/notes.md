# R169 A2 — bounded SourceWriter

## Artifacts
- `core/contracts/source_write.py` (contract; budget-free)
- `core/tools/source_writer.py` (+226/-0; budget change #1 of 6)
- `tests/tools/test_source_writer.py` (42 tests)
- `fail_first.txt` — `ModuleNotFoundError: No module named 'core.tools.source_writer'`, EXIT=2
- `after_fix.txt` — 42 passed, EXIT=0

## Discipline mirrored from SourceReader
- `_admit`: relative-only, no `..` parts, `resolve()` then parent check (defeats symlink escapes), fnmatch against the SAME `DEFAULT_DENIED_PATTERNS`.
- Denylist covers `.git/**`, `.env*`, `*.pem`, `*.key`, `*.p12`, `*credentials*`.

## Refusal-as-data (INV-2)
12 codes: path_not_relative, path_outside_root, path_denied, file_exists, file_missing,
not_a_file, precondition_required, precondition_mismatch, write_too_large,
op_cap_exceeded, content_required, io_error. Handler adds `validation_error` for
malformed arguments. Refusals do not consume the op cap.

## Executor / audit proofs
- admitted write → status succeeded, 1 TOOL_CALL event
- handler refusal (`.git/hooks/pre-commit`) → status succeeded, result.ok False, code path_denied, no file, 1 event
- invalid op → code validation_error, ops_used 0
- gate refusal (tool lacks permission) → status refused, no file, 1 event status refused

## Caps
`max_write_bytes` default 65_536 (UTF-8 byte count), `max_ops` default 50 per writer instance.

## Not done by design
- No registration anywhere; `core/tools/__init__.py` untouched; admin registry unchanged (A3/A4 prove it).

## Lint / type
ruff check + format clean; `mypy --strict` clean (2 files); lint-imports 13 kept / 0 broken.

## Note
First A2 pass was lost to a sandbox reset before commit; recreated identically from the state ledger design.
