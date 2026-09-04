# R172 §1 — Discovery (round-start SHA 67824d0, HEAD == origin/main)

R171 did **not** land: no `docs/r171/`, no `evidence/r171/`, no `round_r171` budget
block, no commit message mentioning R171 on `origin/main`. Latest round on origin
is R170 (harvest only, `docs/r170/HARVEST.md`, `evidence/r170/denylist_probe.txt`).

| Item | Probe | Result | Verdict |
|---|---|---|---|
| D1 denylist module | `ls core/tools/denied_paths.py` | no such file; `DEFAULT_DENIED_PATTERNS` lives only in `core/tools/source_reader.py` L32-46; `build_dev_surface` L219-220 passes no patterns | **ABSENT** |
| D2 persistent binding store | `grep -rn "BindingStore\|binding_store" core apps` | 0 hits; `RepoBindingRegistry` (`apps/agent_dev/git_tools.py` L135-165) is a dict | **ABSENT** |
| D3 explicit remote trust | `grep -rn "trusted" core/contracts/repo_binding.py apps/agent_dev` | 0 hits; `GitRefusalCode` L36-49 has no trust code | **ABSENT** |
| D4 atomic write | `core/tools/source_writer.py` L178, L183 | `path.write_bytes(...)` direct, no temp/fsync/replace | **DEFECT (in scope, C4)** |
| D5 checkpoint/undo for dev writer | `grep -rn "checkpoint\|Checkpoint" apps/agent_dev core/tools` | 0 hits. `core/sourcechange/snapshot.py` has `SourceSnapshot`/`file_content_hash` but serves the admin source-change workflow (`apps/api/admin.py`, `source_changes.py`) — nothing wraps the dev surface apply path | **ABSENT for dev surface** |
| D6 approval payload binding | `core/tools/gate.py` L149 | `request.approval_state != "approved"` — string state only, no payload hash | **DEFECT (boundary; C6 layer above gate)** |
| D7 publish-modes route | `grep -rn "create_dev_router" apps` | defined `apps/agent_dev/http.py:7,68,69`; never imported in `apps/api/app.py` or `apps/composition/runtime.py` | **PRESENT, UNMOUNTED** |
| D8 sandbox options R170 citation | `grep -n "R170\|r170" docs/r169/SANDBOX_OPTIONS.md` | 0 hits | **ABSENT (docs-only fix)** |

Baseline gate (R169 last measured): PASS 2920 passed / 0 failed / 0 errors / 64 skipped.
