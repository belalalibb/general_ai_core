# C5 — checkpoint / undo for the dev-surface `source.write` apply path

## What changed (budget 1 change / one commit → total 5/8)
- **`apps/agent_dev/surface.py`** (+14/-1, the charged edit) — `build_dev_surface(..., checkpoints: CheckpointManager | None = None)`,
  `DevAgentSurface.checkpoints` field, and handler selection: `checkpointed_write_handler(writer, checkpoints)` when a manager is
  supplied, otherwise the unchanged `source_write_handler(writer)`. Absent manager ⇒ result keys exactly
  `{ok, op, path, bytes_written, sha256, previous_sha256, ops_remaining}` (pinned by test; `test_dev_surface.py` untouched, green).
- **`core/contracts/checkpoint.py`** NEW (98 lines, budget-free INV-1) — `Checkpoint` (id, tenant_id, path, op, pre_sha256|None,
  post_sha256|None, state open/sealed/partial/restored, timestamps), `CheckpointIndexDocument` v1, `CheckpointLoadReport`
  (source_state missing/ok/partial/malformed/unreadable), `RestoreResult`, `CheckpointRefusal`, `CheckpointRefusalCode`
  (checkpoint_unknown, checkpoint_conflict, object_store_corrupt, path_refused, io_error).
- **`core/tools/checkpoint.py`** NEW (466 lines) — `CheckpointStore`, `CheckpointManager`, `checkpointed_write_handler`.
  New modules under `core/` are counted as part of the C5 item (one row) per the R172 manifest guard, as C2/C3 were.

## Store
`CheckpointStore(dir, outside_of=(repo_root,))` — refuses a directory inside any protected tree (`resolve_outside`, message
"inside a protected working tree"). Blobs are content-addressed at `objects/<sha256>`, written via same-dir temp `O_EXCL` 0o600 →
flush → fsync → `os.replace` → dir fsync; index `checkpoints.json` through `atomic_json.write_document`. Every directory 0o700 and every
file 0o600 (test walks `rglob`). `get_blob` re-hashes on read; mismatch ⇒ `None` ⇒ `object_store_corrupt`. `load` is fail-closed:
malformed/unreadable index ⇒ zero checkpoints with `source_state` reported; invalid or duplicate records skipped ⇒ `partial`.

## Manager
- `begin(rel_path, op, denied_patterns=None)` — admission mirrors the writer (relative, no `..`, inside root, not denied, regular file);
  the handler passes `writer.denied_patterns` so the two can never disagree. Snapshots the current bytes (missing ⇒ `pre_sha256=None`),
  persists the `open` record, returns the `Checkpoint`. Snapshot/index failure ⇒ `CheckpointRefused(io_error)` and nothing recorded.
- `seal(id, post_sha256)` / `mark_partial(id)` — typed transitions, persisted; index failure rolls the in-memory record back.
- `restore(id)` → data: `cur == pre` ⇒ `outcome="noop"`; `cur == post` and state not `partial` ⇒ `outcome="reverted"` (delete when
  `pre is None`, else atomic write of the verified blob preserving the existing mode); else `checkpoint_conflict` — file untouched.
  Unknown id ⇒ `checkpoint_unknown`.

## Handler ordering (fail closed)
validate → `begin` → write → `seal` (success, `+checkpoint_id`) | `mark_partial` (writer refusal, refusal returned unchanged).
`begin` **path_refused** falls through to the writer (its own `path_denied` refusal; no blob, no checkpoint, no `checkpoint_id`).
Any other `begin` failure returns `CheckpointRefusal` data and the write is **not attempted** — never write without a snapshot.

## Not wired into production composition
`apps/composition/runtime.py` does not construct a `CheckpointManager`; the store directory location per deployment is an owner
decision (§9 open items). The seam is the `checkpoints=` parameter.

## Fail-first
`fail_first.txt`: `ModuleNotFoundError: No module named 'core.contracts.checkpoint'` at `73766ab`.

## Tests
`tests/agent_dev/test_checkpoint_r172.py` — 16 passed (spec was written before implementation; the WIP plan said "17" — the file
has 16 tests, the plan wording was wrong, no test removed). Suites `tests/agent_dev tests/tools tests/verification`: 374 passed,
1 xfailed (358+1 at C4). `tests/admin_agent`: 130 passed. ruff format/check + mypy clean. See `after_fix.txt`.

## Resets
Reset #8 (clean, nothing lost) and reset #9 (wiped the uncommitted contract + tools module). Both recreated from the recorded
design; from then on each file was committed as WIP immediately (`5974b39`, `b4e84f8`, `6e62d01`) before the next step.
