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

## C-04 — §6.6 "ExerciseSurface rewire to an isolated test tenant" vs the frozen caller-scoped derivation and INV-2

- **Text A (mandate §6.6):** isolated test tenant via `configure_tenant` + ExerciseSurface rewire.
- **Text B (repo `apps/api/exercise.py` header, frozen V7 derivation; mandate INV-2):** probes are "CALLER-SCOPED — the exerciser receives the admitted Principal — probes bill and record against the caller's tenant like any real request (no service account, no invented identity)"; INV-2 allows non-additive production changes only for D-01 settlement and D-08 project_id.
- **Touched files:** `tests/api/test_exercise_tenant_isolation.py` (new), `apps/api/exercise.py` (NOT edited), `apps/api/app.py` (NOT edited).
- **Stricter reading:** Text B. A composition-owned "test tenant" is exactly the invented identity the frozen derivation forbids, and rewiring the surface is a non-additive production change outside the INV-2 exceptions. The isolation property the rewire was meant to buy can be proven on the existing seam.
- **Disposition:** APPLIED-STRICTER. No production change. `tests/api/test_exercise_tenant_isolation.py` builds a dedicated probe tenant through the SAME `configure_tenant` admin seam and proves: probe bills the caller only; a bystander tenant on the same accounting instance keeps used == 0.0 and an empty store view; the probe record resolves only under the caller (foreign lookup → ExecutionNotFound); a finite probe budget is enforced and exhaustion stays on the probe tenant. If the operator still wants a composition-owned probe tenant, it is a scheduled R169 design item, not an R168 silent change.

## C-05 — D-01 "CONTENT_REJECTED / credential-indicting" vs the frozen failover posture and "failover-permitting"

- **Text A (mandate §5 D-01):** in-band HTTP-200 refusal "classified CONTENT_REJECTED / credential-indicting, run FAILED, 0 units; failover-permitting".
- **Text B (repo `core/execution/service.py` `_REQUEST_INDICTING`, frozen):** `CONTENT_REJECTED` is REQUEST-indicting — the node fails immediately and the router NEVER fails over ("would launder a refusal"). Account/plan-indicting categories (`quota_exceeded`, `invalid_credential`, `auth_expired`) with `retryable=False` are route-indicting ⇒ immediate failover.
- **Touched files:** `providers/real/genspark_llm/adapter.py` (fix), `tests/providers/test_d01_refusal_contract.py`, `tests/certification/test_r167a_routing_matrix.py`; `core/execution/service.py` NOT edited.
- **Stricter reading:** Text A is self-contradictory under Text B (CONTENT_REJECTED cannot be failover-permitting). The refusal indicts the account's plan, not the prompt; the mandate's operative requirements are FAILED / 0 units / failover-permitting / no leak. `QUOTA_EXCEEDED` satisfies all four without changing the frozen core; `CONTENT_REJECTED` would satisfy three and would need a core change (budget 5/5) to relax a safety posture.
- **Disposition:** APPLIED-STRICTER. Classified `quota_exceeded`, `retryable=False`, `provider_code="plan_refusal_200"`, generic `safe_message`; core untouched (round A stays 4/5). Recorded as IMPL-009. If the operator insists on the literal `content_rejected` label it is a scheduled R169 decision requiring a core posture change, not an R168 silent change.
