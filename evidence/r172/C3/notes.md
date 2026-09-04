# C3 — explicit remote trust, refused before credential resolve

## What changed (budget 1 → total 3/8)
- **Charged:** `apps/agent_dev/git_tools.py` (+29/-0): `RemoteTrustPort` Protocol (`is_trusted(tenant_id, remote_url) -> bool`);
  `GitToolset.trust: RemoteTrustPort | None = None` (placed after `secrets`, before the defaulted `trace`); `_require_trust(binding)`
  raising `BindingLookupRefused(GitRefusalCode.REMOTE_NOT_TRUSTED, ...)`; called in `fetch()` immediately after `_binding()` and
  **before** `_token()`, and in `publish()` immediately after `_binding()` (inside the same try/except, so the refusal carries `mode`
  in the trace) and before the `mode_allowed` check. `status()` / `commit()` untouched.
  Registry exceptions inside `_require_trust` are caught and treated as *untrusted* — a faulty registry can never become a 500 or a bypass.
- **Budget-free (contract, INV-1):** `core/contracts/repo_binding.py` +1 line: `GitRefusalCode.REMOTE_NOT_TRUSTED = "remote_not_trusted"`
  (snake-case invariant test `test_refusal_codes_are_snake_case_values` still passes). NEW `core/contracts/remote_trust.py` (75 lines):
  `RemoteTrustGrant(tenant_id: UUID, remote_url: RemoteUrl, trusted: StrictBool, granted_by, granted_at, revoked_by?, revoked_at?, note?)`,
  `.effective` = trusted is True and not revoked; `TrustStoreDocument` v1; `TrustSkippedRecord`; `TrustStoreLoadReport`.
- **Budget-free (new leaf modules):** NEW `core/tools/remote_trust.py` (178 lines): `RemoteTrustRegistry(store=None)` with
  `is_trusted/get/grant/revoke` + `load_report`; `JsonRemoteTrustStore(path, outside_of=())`; `TrustStorePort`; `RemoteTrustRefused`.
  NEW `core/tools/atomic_json.py` (150 lines): the C2 durability primitives extracted (`resolve_outside`, `write_document`,
  `read_document`, `AtomicJsonRefused`) so C2 and C3 share ONE implementation. `core/tools/binding_store.py` was rebuilt on it —
  pure refactor, public API unchanged, C2's 14 tests re-run green before and after (`d24a213`).
  Transparency: if the owner counts the binding_store refactor as a change, the round total is 4/8 — still inside the ceiling.

## Semantics (as mandated)
- **Default untrusted.** No grant ⇒ `is_trusted` is `False`. `GitToolset(trust=None)` ⇒ R169 behaviour byte-for-byte (53 R169 tests unmodified, green).
- **`"true"` string ⇒ untrusted, never an exception into the tool path.** `trusted: StrictBool` — the contract rejects it; a stored record
  with `"trusted": "true"` is skipped on load (`source_state="partial"`), reported, and yields no trust.
- **Revoked ⇒ untrusted.** `revoke()` stamps `revoked_by`/`revoked_at`; `.effective` becomes False. Revoking an unknown pair records an
  explicit `trusted=False` grant so the decision is auditable rather than silently absent.
- **Per remote, per tenant.** Key = `(tenant_id, remote_url.strip())`. Only surrounding whitespace is normalised; host case, missing `.git`,
  or scheme variants are DIFFERENT remotes and stay untrusted (conservative on purpose — over-normalising would widen trust).
- **Enforced only in `GitToolset`, only for `git.fetch` and `git.publish`.** All publish modes incl. `dry_run` are refused for an
  untrusted remote (a whole-act refusal; no partial acts). `git.status`/`git.commit` do not consult trust.
- **Refuse before resolve.** `CountingSecrets.resolve_calls == 0` on every untrusted path (fetch, publish×3 modes, foreign-tenant grant, post-revoke).
  Trusted path resolves exactly once per network act.
- **Refusal is data (INV-2).** Executor `record.status == "succeeded"`, `record.result == {"ok": False, "code": "remote_not_trusted", "binding_id": …}`;
  trace entry `code is REMOTE_NOT_TRUSTED, ok False`. Token bytes absent from the refusal payload.

## Persistence (C2 durability reused)
Directory 0o700, file 0o600, same-dir temp → flush → fsync → `os.replace`; `outside_of` refusal with "inside a protected working tree".
Load fail-closed: malformed document ⇒ nothing trusted (`malformed`), bad record ⇒ skipped (`partial`), restart ⇒ trust survives (`ok`).

## Fail-first
`fail_first.txt`: `ModuleNotFoundError: No module named 'core.contracts.remote_trust'` at `d04dd7d`.
Spec bug found during implementation: helper `call()` treated `ToolCallRecord` as a dict — fixed in the test to unwrap `record.result`
AND assert `record.status == "succeeded"` (stronger: proves the gate admitted and the refusal is handler data).

## Tests
`tests/agent_dev/test_remote_trust_r172.py` — 19 passed. Suites `tests/agent_dev tests/tools tests/verification`: 319 passed, 1 xfailed
(300+1 at C2). ruff + mypy clean. Pre-existing starlette/httpx deprecation warning only.

## Open (honest)
- No composition wires a `RemoteTrustRegistry` into `GitToolset` yet (same status as the C2 binding store): every production
  `GitToolset` today has `trust=None` ⇒ R169 behaviour. Wiring + the operator act that *grants* trust (CLI/endpoint) are owner decisions.
  Until then C3 is an enforced-when-wired invariant, not a live gate. Flagged for `BACKEND_STATE_OF_TRUTH.md` Sections C/E.
- C8 live GitHub run will construct a registry explicitly and prove the untrusted-binding refusal against a real remote.
