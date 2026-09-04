# R169 CLOSURE REPORT — development-agent surface (PARTIAL CLOSURE)

Repository `belalalibb/general_ai_core`, branch `main`. Round baseline `199b1cf` (2026-09-04);
closure gate measured at `5268ef3`, recorded in `82d93ce`. Every verdict below points at a
fail-first artifact, a test file and a commit; anything without evidence is NOT EVALUATED (INV-4).

## 1. Items

| Item | Verdict | Fail-first artifact | Evidence / tests | Commit(s) |
|---|---|---|---|---|
| §0/§2 baseline, ledgers, manifest `round_r169`, verifier per-round budget loop + guard | DONE | guard test added to `tests/verification/test_green_manifest_guards.py` (+1) | `evidence/r169/check_repo_baseline.txt` (2777/0/0/64, EXIT=0); `evidence/r169_state_ledger.md`; `evidence/r169_conflict_ledger.md`; IMPL-013 | 199b1cf |
| A1 capability map | DONE (docs) | n/a (documentation) | `docs/r169/CAPABILITY_MAP.md` — 16 ids, derivation rule quoted from `create_app`, publish-mode list for the UI round | d3a5ca4 |
| A2 bounded source WRITE primitive | PASS | `evidence/r169/A2/fail_first.txt` (collection error before module) | `core/contracts/source_write.py`; `core/tools/source_writer.py`; `tests/tools/test_source_writer.py` 42 passed; `evidence/r169/A2/after_fix.txt`; IMPL-014 | 2ff8bda |
| A3 dev-agent composition root (`apps/agent_dev/`) | PASS | `evidence/r169/A3/fail_first.txt` | `apps/agent_dev/{__init__,surface}.py`; `tests/agent_dev/test_dev_surface.py` 28 passed; IMPL-015 | 631970f, 080c534, 0eb51c3 |
| A4 INV-7 admin boundary | PASS | same A3 artifact | `tests/agent_dev/test_admin_boundary.py` 9 passed — admin registry/permission classes asserted unchanged | 080c534 |
| A5 GitHub connectivity (contracts, git tools, surface wiring) | PASS at contract/fake-transport level; **live transport NOT EVALUATED** | `evidence/r169/A5/fail_first.txt` (EXIT=2) | `core/contracts/{repo_binding,publish_mode}.py` + `tests/agent_dev/test_contracts_r169.py` 15; `apps/agent_dev/git_tools.py`; `apps/agent_dev/surface.py`; `tests/agent_dev/test_git_tools.py` 38 passed (`evidence/r169/A5/after_fix.txt`); IMPL-016 | d381489, 796b0dd, 833a6ce, 1dd565c, d626099 |
| A6 PublishMode + read endpoint | PASS (backend router); **not mounted in `apps/api/app.py`**; UI OUT OF SCOPE | `evidence/r169/A6/fail_first.txt` (`ModuleNotFoundError: apps.agent_dev.http`, EXIT=2) | `apps/agent_dev/http.py`; `tests/agent_dev/test_publish_modes_http.py` 10 passed (`evidence/r169/A6/after_fix.txt`, EXIT=0); `evidence/r169/A6/notes.md`; IMPL-017 | 4ae4e09, 7831b69, 667bfb5 |
| B1 sandbox options | DONE (design only) | n/a — no code by mandate §5 | `docs/r169/SANDBOX_OPTIONS.md` (6 options, threat model, recommendation O3/O4, inert-never-degraded) | 5268ef3 |
| Closure gate | PASS | n/a | `evidence/r169/check_repo_final.txt` EXIT=0; manifest floor 2777→2920 | 82d93ce |
| UI (dropdown, IDE integration) | OUT OF SCOPE | — | binding surface documented in `docs/r169/CAPABILITY_MAP.md` §Publish modes | — |

## 2. Budget ledger — 5/6 production changes used

Source of truth: `engineering/verification/green_manifest.json` → `change_budget.round_r169`
(verified by `check_repo`: `round_r169=5/6`).

| # | Item | File | LOC | Commit |
|---|---|---|---|---|
| 1 | A2 | `core/tools/source_writer.py` | +226/-0 | 2ff8bda |
| 2 | A3 | `apps/agent_dev/surface.py` | +236/-0 | 631970f |
| 3 | A5 | `apps/agent_dev/git_tools.py` | +559/-0 | 796b0dd |
| 4 | A5 | `apps/agent_dev/surface.py` | +32/-13 | 833a6ce |
| 5 | A6 | `apps/agent_dev/http.py` | +99/-0 | 4ae4e09 |
| 6 | — | **unused** (reserved; mounting the dev router in `apps/api/app.py` would consume it) | — | — |

Budget-free: contracts under `core/contracts/` (`source_write`, `repo_binding`, `publish_mode`),
tests, docs, evidence, manifest, decision log. `apps/admin_agent/*` untouched (INV-7).

## 3. pytest before / after

| | passed | failed | errors | skipped | head | evidence |
|---|---|---|---|---|---|---|
| Before (R169 baseline) | 2777 | 0 | 0 | 64 | 199b1cf | `evidence/r169/check_repo_baseline.txt` |
| After (closure) | 2920 | 0 | 0 | 64 | 5268ef3 | `evidence/r169/check_repo_final.txt` |
| Delta | **+143** | 0 | 0 | 0 | | |

Delta reasons (all additive; no test removed, weakened or skipped):
- `tests/tools/test_source_writer.py` +42 (A2)
- `tests/agent_dev/test_dev_surface.py` +28, `test_admin_boundary.py` +9 (A3/A4)
- `tests/agent_dev/test_contracts_r169.py` +15, `test_git_tools.py` +38 (A5)
- `tests/agent_dev/test_publish_modes_http.py` +10 (A6)
- `tests/verification/test_green_manifest_guards.py` +1 (per-round budget guard, §0)

Manifest counters moved **upward only**: `pytest.gate.min_passed` 2777→2920;
`last_measured` {passed 2920, at_head 5268ef3, evidence `evidence/r169/check_repo_final.txt`};
`max_skipped` unchanged at 64. The `rest` slice selection gained `tests/agent_dev` (0eb51c3).

## 4. check_repo — final hermetic run (verbatim)

Command: `env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY bash engineering/verification/check_repo.sh`
Run at HEAD `5268ef3`; captured to `evidence/r169/check_repo_final.txt`.

```
PASS: exists: engineering/adr/ADR-TEMPLATE.md
PASS: exists: engineering/adr/README.md
PASS: exists: engineering/gates/GATE-TEMPLATE.md
PASS: exists: engineering/decisions/README.md
PASS: exists: engineering/verification/README.md
PASS: exists: engineering/verification/green_manifest.json
PASS: exists: docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md
PASS: exists: docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
PASS: no legacy state files (D10/D11)
PASS: v3 pack complete: 20 documents
PASS: state field present: STATE_REVISION
PASS: state field present: RESUME_TOKEN
PASS: state field present: CURRENT_TASK
PASS: state field present: NEXT_TASK
PASS: state field present: PHASE_2_STATUS
pytest slice api: passed=462 failed=0 errors=0 skipped=0
pytest slice contract-providers: passed=633 failed=0 errors=0 skipped=15
pytest slice execution-composition-infra: passed=380 failed=0 errors=0 skipped=49
pytest slice admin-security-evaluation: passed=417 failed=0 errors=0 skipped=0
pytest slice rest: passed=1028 failed=0 errors=0 skipped=0
pytest coverage: slices ran = 5; passed=2920 failed=0 errors=0 skipped=64
PASS: pytest: passed=2920 (>= 2777) failed=0 errors=0 skipped=64 (<= 64)
PASS: mypy --strict (scope: pyproject.toml [tool.mypy].packages): clean
PASS: ruff: clean
PASS: import-linter: architecture boundaries kept (40 §6.2)
PASS: secret scan clean (declared exceptions: 5/5)
PASS: no .env tracked
PASS: change budget within ceilings: round_a=4/5; round_b=4/5; round_r169=5/6
NOT EVALUATED: live-suite: browser automation against the real server and real UI — missing dependency
NOT EVALUATED: real two-account provider round-trip (D-03 Class-A failover against live providers) — credential unavailable
SUMMARY: not_evaluated=2 (counted separately; never green, never FAIL)
RESULT: PASS (all repo governance checks)
EXIT=0
```

Exit code: **0**. Also at 4ae4e09/7831b69: `mypy --strict apps/agent_dev` → "Success: no issues found in 4
source files" (package not in the pyproject mypy scope; checked manually); `lint-imports` → "Contracts: 13
kept, 0 broken."

## 5. Capability deltas vs A1

A1 (`docs/r169/CAPABILITY_MAP.md`) recorded 16 capability ids with states derived in `create_app`. R169
did NOT extend that closed set (extending it is a budgeted edit to `apps/api/capabilities.py`). What
changed is the **separately composed development-agent surface**, invisible to the shipped catalog:

| Surface | A1 (199b1cf) | Closure (82d93ce) |
|---|---|---|
| Bounded source WRITE | did not exist | `source.write` tool (`core/tools/source_writer.py`) — jail, denylist, byte/op caps, sha256 precondition; typed `SourceWriteRefusalCode` |
| Dev-agent composition root | did not exist | `apps/agent_dev/surface.py::build_dev_surface` — own `ToolRegistry`, `dev_tenant_policy(write, git)`, admin registry untouched |
| Repository binding + git tools | did not exist | `git.fetch/status/commit/publish` behind `GitTransportPort`; `RepoBindingRegistry` tenant-scoped; token only via `SecretManagerPort.resolve(credential_ref)`; `GitRefusalCode` (11) |
| Publish mode | did not exist | `PublishMode` (4), default `pull_request`, `direct_push` opt-in per binding, mode recorded in the single `TOOL_CALL` audit event |
| Publish-mode read endpoint | did not exist | `GET /v1/dev/bindings/{binding_id}/publish-modes` router — **exists, tested, NOT mounted** |
| Command execution for tenant code | did not exist | still does not exist; design note only (`docs/r169/SANDBOX_OPTIONS.md`) |
| Catalog `GET /v1/admin/capabilities` | 16 ids | 16 ids, unchanged |

Invariants: INV-1 contracts landed before consumers in every item (d381489 before 796b0dd; source_write
contract in 2ff8bda alongside the engine with tests); INV-2 every refusal is typed data; INV-3 no
provider/transport credential appears outside `SecretManagerPort.resolve`; INV-5 nothing was published or
promoted by an agent — `direct_push` is off by default; INV-6 green stayed green at every commit
(check_repo PASS before and after); INV-7 asserted by `tests/agent_dev/test_admin_boundary.py`;
INV-8 verified below.

## 6. Open operator decisions

1. **Live GitHub transport — NOT EVALUATED.** Only `FakeTransport` was exercised. A real transport
   (`git` CLI and/or PR API) is a future production change requiring its own fail-first evidence against
   a throwaway repository. The temporary token supplied for R169 was used exclusively for `git push` of
   this repository by the operator's agent session; it was never wired into any code path, test, or
   evidence file.
2. **Composition of the dev router into `apps/api/app.py`.** `create_dev_router(bindings, resolve=…)`
   is ready to mount next to the admin router using the existing `_principal` resolver
   (`apps/api/app.py` L631–655). Doing so is production change #6, touches the composition root, and
   requires the operator to decide (a) which `RepoBindingRegistry` instance backs it, (b) whether the
   route is env-gated like `EXECUTE_RATE_LIMIT`/`DEV_DEMO_PRINCIPAL`, and (c) whether a `dev.*`
   capability id row is added to the closed catalog set.
3. **Sandbox for command execution.** `docs/r169/SANDBOX_OPTIONS.md` recommends O3 (`bwrap`) on a plain
   host or O4 (rootless Podman, `--network none`) when containerised; both keep `CommandPolicy` /
   `CommandRunnerPort` unchanged and add one adapter. Host shape and `unprivileged_userns_clone`
   availability decide which is written first. Until adopted, `command.*` stays off the dev surface;
   the existing `SubprocessCommandRunner` is refused for tenant code.
4. **UI** for publish-mode selection and the IDE integration — OUT OF SCOPE; the binding surface is the
   A6 endpoint plus the table in `docs/r169/CAPABILITY_MAP.md`.
5. **Binding provisioning.** `RepoBindingRegistry` is in-memory; a persistent store, and the admin act
   that creates a binding (INV-5), are not designed.

## 7. Credential hygiene — confirmation

- Repository secret scan in `check_repo`: **PASS** ("secret scan clean (declared exceptions: 5/5)").
- Pre-commit staged-file scan (`git diff --cached --name-only | xargs grep -lE 'ghp_[0-9A-Za-z]{36}'`)
  returned 123 (no match) before every R169 commit.
- `evidence/r169/check_repo_final.txt` grep for the token pattern: 0 matches.
- Test fixtures use `ghp_FAKE_TOKEN_NEVER_LEAKS_0123456789abcdef` (does not match the 36-char pattern)
  and assert its absence from `ToolCallRecord`, audit and trace.
- The operator's temporary token lived only in `~/.git-credentials` (mode 0600) for pushes; it is
  removed from the sandbox at the end of this round (`rm -f ~/.git-credentials; git config --unset
  credential.helper`). The operator revokes it on GitHub.

## 8. INV-8 / completion gate

At the final commit: `HEAD == origin/main`, working tree clean (recorded in the state ledger closure
row). No R170 is started by this report.

This is a PARTIAL CLOSURE. Items marked NOT EVALUATED or OUT OF SCOPE are open. The backend is not closed to further repair.
