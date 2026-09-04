# C1 — hardened denylist wired at dev-surface composition

**Round-start:** `67824d0` · **prep HEAD:** `e8772f6` · **budget:** 1/8 (`apps/agent_dev/surface.py`; `core/tools/denied_paths.py` is a NEW file, counted inside the same C1 change)

## What changed
- NEW `core/tools/denied_paths.py` — `DENIED_PATH_PATTERNS` (superset of `SourceReader.DEFAULT_DENIED_PATTERNS`, 13 → 73 unique globs) + `is_denied_path(rel_posix)`. Same `fnmatch` semantics as `SourceReader._denied` / `SourceWriter._denied`; no new matching engine.
- `apps/agent_dev/surface.py::build_dev_surface` — default reader/writer now constructed with `denied_patterns=DENIED_PATH_PATTERNS`. Injected reader/writer are untouched. **Not edited:** `source_reader.py`, `source_writer.py` (C4 targets), `core/tools/gate.py`.
- Comment in module: case-variant enumeration (`.ENV*`/`.Env*`) is a patch; the proper fix is normalisation (C4).

## Fail-first
`fail_first.txt`: `ModuleNotFoundError: No module named 'core.tools.denied_paths'` (1 collection error) at `e8772f6`.
`after_fix.txt`: 61 passed, 1 xfailed; `tests/tools tests/agent_dev tests/verification` 286 passed 1 xfailed (existing suites unmodified); ruff/mypy clean.

## Probe table consumption
Test parses `evidence/r170/denylist_probe.txt` directly: 27 `EXPECT_DENIED` rows → all deny except `acco33unts.txt` (xfail, reason exactly: "obfuscated name — needs content-based detection, out of scope"); 3 `expect_allowed` rows stay allowed.

## Decision — `session_dump.txt` (probe: `expect_allowed?`)
**ALLOWED.** The name has no credential semantics by itself; a `*dump*`/`*session*` glob would deny legitimate fixtures/logs (`tests/**/session_*.py`, `*_dump.json`). If session artefacts must be protected that is content-based detection — same bucket as `acco33unts.txt`, out of scope. Recorded as an open item for Section E.

## Collateral finding (directive pattern vs. tracked sources)
Directive-mandated `*accounts*` / `*password*` globs match **tracked source files**:
- `core/providers/accounts.py` → DENIED to the dev agent (read + write)
- `infrastructure/security/password.py` → DENIED
- `tests/infrastructure/test_argon2_password_hasher.py`, `engineering/adr/ADR-0005-password-hashing-binding.md` → DENIED
- any future `tests/**/test_accounts*.py`, `docs/**/tokens.md` → DENIED

Decision: **keep the patterns exactly as mandated** (fail-closed; the operator asked for them) and document rather than silently narrow. Consequence: the dev agent cannot self-edit those files; a human does. If the owner wants them reachable, the fix is an explicit allow-list exception (a new, separate change) — not a weaker glob. Flagged in `BACKEND_STATE_OF_TRUTH.md` Section C.

## Not covered by C1 (by design)
- Unicode/zero-width/`::$DATA`/trailing-dot/space bypasses — C4 normalisation.
- Content-based detection (obfuscated names, high-entropy strings) — out of scope for R172.
- `ui/**`, `apps/admin_agent/**` untouched (sizes verified at closure).
