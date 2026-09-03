# Evidence — Phase 0 + Phase 1 baseline (QEVION capability-evolution round)

Every claim is tagged per §12. Untagged = invalid.

## Phase 0 — preconditions

| item | value |
|---|---|
| stack | Python 3.13, FastAPI; entrypoint `python3 -m apps.main`; composition `apps/composition/runtime.py::build_runtime_profile` [OBSERVED code:apps/main.py, apps/composition/runtime.py] |
| tests | `env -u GSK_API_KEY -u GROQ_API_KEY python3 -m pytest -p no:cacheprovider -o addopts="" -q -W ignore` → **2683 passed, 64 skipped, 36.0 s** [VERIFIED cmd exit:0] |
| gate | `bash engineering/verification/check_repo.sh` → RESULT: PASS on 4072348 [VERIFIED exit:0] |
| git | branch `main`, HEAD `4072348` == `origin/main`, tree clean at start [VERIFIED cmd:`git status --short | wc -l` → 0] |
| runtime startable | yes — started in a prior session with GROQ bound, `/healthz` alive, `providers: ["groq"]`, real `POST /v1/execute` → `succeeded` [VERIFIED, prior session log] |
| web access | yes (`curl https://pypi.org` → 200) [VERIFIED] |
| sandbox | reset between sessions wipes deps/servers/tmp, NOT the repo (§1A applied: verified HEAD, restored env only) [VERIFIED] |
| abort conditions | none. Workspace artifacts outside scope: none. |

## Phase 1 — forensics (capability-affecting surfaces only)

| surface | finding | tag |
|---|---|---|
| Agent loop | `core/execution/loop.py` bounded plan→act→observe; closed stop reasons; repeated-failure refusal; invalid-proposal repair (2); deadline; verifier-before-final with correction loop; evidence ledger of succeeded steps | [OBSERVED code:core/execution/loop.py:L81-102, L204-434] |
| Runtime | `core/agent/runtime.py` one `reason()` seam → router → `execute_single`; default `evidence_verifier` rejects invented evidence + empty answers; per-tool `verify_result` semantic rule (ws_run exit code) | [OBSERVED core/agent/runtime.py:L253-283, core/engineering/tools.py:L123-129] |
| Provider failure inside a run | a provider error on ONE reasoning step becomes `propose_failed` and **ends the whole run**; completed tool work is kept in the record but the run is dead. Under AUTO policy `fallback_candidates` is empty (`_resolve_fallback_scope` returns None) so a registered backup provider is **never tried** | [MEASURED rows 5–7 below] [OBSERVED core/routing/router.py:L433-443, core/agent/runtime.py:L495-503] |
| Resume | no primitive to seed a new run from a prior record's evidence/observations; `hasattr(runtime,"resume")` False; partial work preserved on disk only | [MEASURED row 10] [VERIFIED grep resume/continue_from → 0 hits in core/apps] |
| Tool gate / authz | every tool act passes `ToolExecutor` → `ToolCallGate` → `CapabilityFirewall`; ungranted permission ⇒ refused observation, handler never runs | [MEASURED row 11 `handler_ran: False`] |
| Capability metadata | `apps/api/capabilities.py` closed 16-id set, 3 states, `evidence` string only. No inputs/outputs/permissions/cost/verification-method fields — insufficient for §9 metadata-driven Admin (L1/L2/L3) | [OBSERVED apps/api/capabilities.py:L58-77, L82-92] |
| Admin hardcode | exercise handlers keyed by id in `create_app` (`"execute.sync": _exercise_execute_sync`) — data mapping, not `if capability ==` branches in UI; UI badges derive from server enums | [OBSERVED apps/api/app.py:L1823-1861] |
| Learning seams | `core/learning/{lifecycle,gates,sanitizer}.py` exist; not exercised here | [OBSERVED] not [VERIFIED] this round |

## Measured baseline — `python3 evidence/baseline_tasks.py` → `evidence/baseline_before.json`

Scripted model over the REAL router/execution/gate chain (`tests/agent/world.py`). Numbers measure the runtime, not a provider.

| # | task | expected | stop_reason | outcome | note |
|---|---|---|---|---|---|
| 1 | simple | success | final | PASS | verified |
| 2 | multi_step (2 reads, cited final) | success | final | PASS | verified |
| 3 | multi_tool_coding (read/run/fix/run/final) | success | final | PASS | file_fixed=True |
| 4 | artifact production | success | final | PASS | artifact_present=True |
| 5 | provider transient (one retryable 503 mid-run) | success | **propose_failed** | **FAIL** | run dies; retries=0 in world (prod default `PROVIDER_MAX_RETRIES=1`) |
| 6 | provider hard 400 mid-run, backup provider exists | success | **propose_failed** | **FAIL** | backup_used=False; bad_request is request-indicting by design — expected NOT to failover; the failure is that the RUN dies rather than the step |
| 7 | persistent provider outage, backup provider exists | success | **propose_failed** | **FAIL** | backup_used=False — AUTO policy yields no fallback candidates |
| 8 | tool failure → recovery | success | final | PASS | |
| 9 | verification failure (invented evidence ×3) | bounded failure | verification_failed | PASS | never reported success |
| 10 | partial success (budget exhausted after real fix) | bounded failure | max_steps_exceeded | PASS | work_preserved=True, **resumable_primitive_exists=False** |
| 11 | authz denial (write not granted) | success (honest answer) | final | PASS | handler_ran=False |

Summary [MEASURED]: **pass 8 / fail 3**; verified completions 6/6 (0 unverified successes); model calls 28; prompt chars 34 139.

Weakest measured link: **RECOVER at the reasoning seam** (rows 5–7). Second: **partial-success resumability** (row 10). Verification is already stronger than it looks (row 9 + `verify_result`).

## Not executed this round (honest)
- Phase 2 domain discovery + competitor benchmark, Phase 3 gap matrix, Phase 4 selection, Phase 5 implementation, Phase 6 §11 logs, §15 transcript — session budget exhausted at the checkpoint below. Nothing was fabricated to fill them.
