# C2 — persistent, fail-closed, tenant-scoped binding store

## What changed (budget 1 → total 2/8)
- **Charged:** `apps/agent_dev/git_tools.py` (+26/-2): `BindingStorePort` Protocol; `RepoBindingRegistry.__init__(self, store=None)`;
  `load_report: BindingStoreLoadReport | None`; registry loads valid records at construction and re-saves the full
  valid set on every `register()`. Without a store the behaviour is unchanged (38 `test_git_tools.py` tests, file unmodified since `67824d0`).
- **Budget-free (contract, INV-1):** NEW `core/contracts/binding_store.py` (66 lines): `BindingStoreDocument` (version=1 envelope),
  `SkippedRecord(index, reason)`, `BindingStoreLoadReport(bindings, skipped, source_state)`; `SourceState` = missing|ok|partial|malformed|unreadable.
- **Budget-free (new module, no existing behaviour changed):** NEW `core/tools/binding_store.py` (193 lines): `JsonBindingStore(path, outside_of=())`, `BindingStoreRefused`.
  Note: the directive's budget counts "one coherent edit to a file under core/ apps/"; a brand-new leaf module that nothing imports until wired
  is reported here for transparency. If the owner counts new modules, C2 costs 2 and the total is 3/8 — still inside the ceiling.

## Durability (D4 closed for bindings)
same-dir temp `.bindings.json.<uuid>.tmp` opened `O_EXCL` 0o600 → write → flush → fsync → `os.chmod 0o600` → `os.replace` → best-effort dir fsync.
Directory created/forced 0o700. On any `OSError` the temp file is unlinked and `BindingStoreRefused` is raised; prior bytes intact
(`test_save_is_atomic_on_interrupted_write` monkeypatches `os.replace`). No `*.tmp*` leftovers (`test_save_creates_dir_0700_and_file_0600`).

## Location
Constructor refuses a path inside any `outside_of` root ("inside a protected working tree"). Callers are expected to pass the bound
`local_root`s (wiring into composition is NOT done here — see Open).

## Fail-closed load
- missing file → `source_state="missing"`, empty (not an error)
- unreadable (PermissionError) → `"unreadable"`, empty, reported — test skips under root (uid 0 ignores modes); this sandbox runs uid 1000 so it executed
- malformed JSON / non-object / wrong version / `bindings` not a list → `"malformed"`, nothing loaded, `skipped[0].reason` startswith `malformed`
- per-record `ValidationError` or duplicate id → skipped with index, others kept, `"partial"`
- Nothing raises into the tool path; the registry exposes `load_report` for operators.
- Never partial resurrection: `test_registry_never_resurrects_partial_store` — garbage record absent from registry and dropped from disk on next save.

## INV-3
Only `credential_ref` is serialised. `test_serialised_bytes_contain_ref_never_token` stores a synthetic `ghp_ZZZ…` in `InMemorySecretManager`,
saves the binding with the returned ref, and byte-greps the file: ref present, token absent, `b"ghp_"` absent.

## Tenant scoping
`test_tenant_scoping_survives_round_trip`: after a "restart" (new registry over same file) a foreign tenant gets `binding_tenant_mismatch`
(not `binding_unknown`); unknown id under foreign tenant → `binding_unknown`; `list_for_tenant` filtered.

## Tests
`tests/agent_dev/test_binding_store_r172.py` — 14 passed. Fail-first: `ModuleNotFoundError: core.contracts.binding_store` (fail_first.txt).
Suites `tests/agent_dev tests/tools tests/verification`: 300 passed, 1 xfailed (was 286+1 before C2). ruff + mypy clean.
The single warning is the pre-existing starlette/httpx deprecation from `fastapi.testclient`, filtered by the verifier.

## Open (not done in C2, honest)
- Composition does not yet construct a `JsonBindingStore`; `RepoBindingRegistry()` in `apps/composition/**` stays in-memory. Wiring is a
  separate owner decision (default state path + `outside_of` roots) and would consume budget in `apps/composition/runtime.py`.
