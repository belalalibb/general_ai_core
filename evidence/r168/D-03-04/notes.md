# D-03 / D-04 — multi-account routing absent; no per-call account attribution (S3, ABSENT / AUDIT-GAP)

- Defect: `AccountPoolManager`/`ResourceSelector` had no call sites; `CandidateScore.account_id` was always None; a second credential for the same provider overwrote the first (matrix row `two_credentials_same_provider` = NOT SUPPORTED); `PROVIDER_ACCOUNT_USED` had zero emitters.
- FAIL FIRST (76913e5a): `tests/routing/test_d03_d04_two_account_failover.py` — hermetic World with ONE provider, an `AccountPool` of two accounts (secret-manager refs), first account's adapter answers `INVALID_CREDENTIAL`; 7 tests failed at construction (`RoutingRequest` extra_forbidden: `credential_policy`) — `fail_first.txt`.
- FIX (Round B, 3 changes, all `core/`):
  | Link | File | LOC |
  |---|---|---|
  | (ii) policy travels with the request | `core/contracts/routing.py` — `RoutingRequest.credential_policy: CredentialPolicy \| None = None` | +5/−1 |
  | (iii) account-complete route | `core/routing/resources.py` — `ResourceSelector.complete()`: pooled candidates → one per eligible account (LRU, policy-filtered); pool-less pass-through; exclusions recorded; `NoEligibleAccount` when empty | +60/−0 |
  | (i) per-account credential + audit | `core/execution/service.py` — `account_credentials`, `audit` seams; `_credential_ref_for` (account ref wins), `_has_credential` precheck, `_audit_account_used` → `PROVIDER_ACCOUNT_USED` per attempt (no secrets) | +66/−3 |
- Test correction: the original test 2 mixed PLATFORM and USER accounts in one pool; 30 §10.5 makes a pool single-sided (`PoolOwnershipViolation`), so the policy filter is proven on a USER pool (USER_ONLY admits, PLATFORM_ONLY → `NoEligibleAccount`). Contract respected, not bent.
- PASS (824dce8a): 7 passed — `after_fix.txt`. ruff clean; `mypy --strict` clean on the 3 files; `tests/verification tests/certification/test_r167a_routing_matrix.py tests/routing` 102 passed.
- Scope: contract level FIXED. Composition wiring (`apps/composition/runtime.py` building `ExecutionService` with the seams and calling `complete()`): OUT OF SCOPE (R168): budget — scheduled for R169. Live 2-account run: NOT EVALUATED (single credential envelope).
- Budget: Round B 3/5 (`changes_used == len(log)`, items D-04/D-03/D-03 all scheduled; guard test passes).
- Docs: matrix row `two_credentials_same_provider` → SUPPORTED VIA ACCOUNT POOL (assertions unchanged); `evidence/credential_binding_boundary.md` R168 re-evaluation; `evidence/defect_ledger.md` D-03/D-04 FIXED (contract level); IMPL-010 in `60_DECISION_LOG.md`.
