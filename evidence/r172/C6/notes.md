# C6 — Approval ↔ payload binding (opt-in, dev-surface layer) — IMPL-023

## What changed (budget row 6/8)
- `apps/agent_dev/surface.py` (+142/-4, the charged edit): `PAYLOAD_BOUND_PERMISSIONS`
  = {`source.write`, `git.commit`, `git.publish`}; `DevAgentSurface.payload_binding: bool = False`
  and `audit: AuditLogPort | None`; `call(..., approved_payload_hash=None)` runs a pre-gate
  check when binding is on, the permission is write-class and `approval_state == "approved"`;
  `_refuse_payload_binding` produces an executor-shaped `ToolCallRecord(status="refused",
  error=TOOL_APPROVAL_REQUIRED, error_detail=<ApprovalBindingRefusal JSON>)` and one
  `TOOL_CALL` audit event with the same detail keys the executor emits.
  `build_dev_surface(..., payload_binding=False)` threads the flag.
- NEW `core/contracts/approval_binding.py` (50 lines): `ApprovalBindingRefusalCode`
  (approval_hash_required / approval_payload_mismatch / payload_not_canonicalisable),
  `ApprovalBindingRefusal` ContractModel.
- NEW `core/tools/payload_binding.py` (94 lines): `NonCanonicalPayload`, `canonical_json`
  (recursive type check, floats rejected, sort_keys, `(",", ":")`, UTF-8, allow_nan=False),
  `payload_hash` (sha256 hex), `check_payload_binding` (canonicalise → missing hash → compare
  with `hmac.compare_digest`).
- NEW `tests/agent_dev/test_payload_binding_r172.py` (17 tests).
- `ErrorCode` NOT widened (closed 11 values; `TOOL_APPROVAL_REQUIRED` reused).

## Boundary / owner decision
- `core/tools/gate.py` NOT modified (directive). The gate stays string-state approval only;
  pinned by `test_gate_admit_has_no_payload_parameter_pin` (`admit` signature has no payload
  parameter).
- Binding is opt-in (`payload_binding=True`), default off. Default surface behaviour pinned by
  `test_default_surface_admits_any_payload_under_approved_state` so the 23 existing approved
  call sites stay green (INV-6).
- Binding is NOT enabled in the production composition. Enabling it requires the
  approval-issuing side (UI/admin — frozen under INV-7 this round) to carry the payload hash.
  Recorded as an open item for §9.

## Behaviour pinned (17 tests)
canonical form (sorted/compact/UTF-8, key-order independent, floats rejected recursively,
non-JSON types rejected); verdict table; gate pin; default surface non-binding; scope exactly
three permissions; missing hash on write refused before gate (transport never called);
mismatched hash → `approval_payload_mismatch`; correct hash admits; argument key order
irrelevant; float payload → `payload_not_canonicalisable`; non-write-class unaffected when
enabled; unapproved write still falls through to gate (gate ordering preserved); `git.commit`
and `git.publish` bound; refusal detail is JSON data and does not echo arguments.

## Not done / open
- Not wired into `apps/composition/runtime.py` (owner decision above).
- Approval-issuing UI does not produce payload hashes (INV-7 freeze).
- Hash algorithm fixed to sha256 hex; no versioning field (acceptable while opt-in).

## Verification
- fail-first: `evidence/r172/C6/fail_first.txt` (ImportError `PAYLOAD_BOUND_PERMISSIONS` at cc04872).
- after-fix: `evidence/r172/C6/after_fix.txt` (spec 17; slice 391 passed/1 xfailed; admin 130;
  ruff/mypy/import-linter clean; gate diff empty).
