# Backend State of Truth — R172 closure (2026-09-04)

Repository `belalalibb/general_ai_core` @ `main`. Round start `67824d0`; C8 closure commit `e43ca80`.
Every status below is one of **LIVE** (enforced in the production composition today), **WIRED-OPT-IN**
(built, tested, reachable only when a composition root injects it — production does not), **BUILT-UNWIRED**
(module + tests exist, nothing constructs it in `apps/composition/**`), **DESIGN-ONLY**, or **NOT EVALUATED**.
Nothing below is claimed beyond what `evidence/r172/**` shows.

## A. What R172 changed (budget 8/8, `green_manifest.json::change_budget.round_r172`)

| # | IMPL | Change | Status in production composition |
|---|------|--------|----------------------------------|
| C1 | IMPL-018 | `core/tools/denied_paths.py` — 64 unique fail-closed deny globs; `build_dev_surface` default reader/writer use them | **LIVE for any `build_dev_surface` caller** (the default path). No production root calls `build_dev_surface` today → see Section C. |
| C2 | IMPL-019 | `core/tools/binding_store.py` JSON store (atomic write, tenant-scoped load report) behind `RepoBindingRegistry(store=)` | **BUILT-UNWIRED** — `RepoBindingRegistry()` in `apps/api/app.py` stays in-memory. |
| C3 | IMPL-020 | `core/tools/remote_trust.py` registry + `GitRefusalCode.REMOTE_NOT_TRUSTED`; `GitToolset._require_trust` runs before `_token` | **WIRED-OPT-IN** — every production `GitToolset` would have `trust=None` ⇒ R169 behaviour; proven live in C8 with an explicit registry. |
| C4 | IMPL-021 | `source_reader.normalize_deny_path/is_denied` (NFKC, zero-width, `::$DATA`, trailing dot/space) + `source_writer` atomic tmp+fsync+replace | **LIVE** wherever `SourceReader`/`SourceWriter` are used (both default and injected). |
| C5 | IMPL-022 | `core/tools/checkpoint.py` `CheckpointManager` + `checkpointed_write_handler`; `build_dev_surface(checkpoints=)` | **WIRED-OPT-IN** — absent manager ⇒ unchanged `source_write_handler`. |
| C6 | IMPL-023 | `core/tools/payload_binding.py` — approval bound to sha256 of the tool payload for `PAYLOAD_BOUND_PERMISSIONS`; `ApprovalBindingRefusal` | **WIRED-OPT-IN** — surface-level opt-in; approval-issuing UI does not emit payload hashes (UI frozen). |
| C7 | IMPL-024 | `apps/api/app.py::create_app(dev_bindings=)` mounts `/v1/dev` read router (composition-time import to break the `apps.agent_dev.http → apps.api.errors → apps.api.app` cycle); `dev.publish_modes` added to closed `CAPABILITY_IDS` (16 → 17) | **WIRED-OPT-IN** — `apps/composition/runtime.py` passes no `dev_bindings`; route absent from the table; capability INERT. |
| C8 | IMPL-025 | `apps/agent_dev/github_transport.py` `GitHubRestTransport` — REST-only `GitTransportPort` (no subprocess/shell/hooks); `tests_live/r172` env-gated live suite | **BUILT-UNWIRED** — no production root constructs a `GitToolset`; live-proven 13/13 against a throwaway repo. |

Non-budget: `evidence/r172/**` (discovery, C1–C8 fail-first/after-fix/notes, `secret_scan.txt`, `live_transport.txt`),
`docs/r169/SANDBOX_OPTIONS.md §8` (D8 docs-only), `docs/r169/CAPABILITY_MAP.md`, `60_DECISION_LOG.md` IMPL-018..025,
`evidence/r172_state_ledger.md`. `ui/**` and `apps/admin_agent/**`: `git diff --stat 67824d0..HEAD` empty.

## B. Live proof — what was actually exercised against real services (`evidence/r172/live_transport.txt`)

GitHub (throwaway `belalalibb/r172-live-transport-throwaway-48b263`, `main` protected PR-only, enforce_admins; never `general_ai_core`):

| Scenario | Result | Typed outcome |
|----------|--------|---------------|
| fetch + status | remote head `f69adaf`, 380 ms | `ok` |
| commit + publish `pull_request` | real PR `…/pull/2` (and `/pull/1` from first run), 3.4 s | `pushed=true`, `pull_request_url` |
| publish `direct_push`, mode not in `allowed_modes` | refused, remote head unchanged | `publish_mode_not_allowed` + `suggested_mode=pull_request` |
| publish `direct_push`, mode allowed, branch protected | GitHub 422 "Changes must be made through a pull request.", remote head unchanged | `remote_rejected_protected_branch` + `suggested_mode=pull_request` |
| untrusted binding (registry present, no grant) | fetch and publish refused; `secrets.resolve` called **0** times | `remote_not_trusted` |
| credential in artifacts | absent from trace / `repr` / binding dumps / evidence | — |

Groq (`llama-3.1-8b-instant`, via `InMemorySecretManager` credential_ref):

| Scenario | Result | Typed outcome |
|----------|--------|---------------|
| completion, keys 1–4 | **all four keys HTTP 400 `organization_restricted`** (account-level block) | `invalid_credential`, `retryable=false` (route-indicting, never `bad_request`) |
| bogus key | HTTP 401 `invalid_api_key` | `invalid_credential` |
| `timeout_ms=1` | client timeout | `timeout`, `retryable=true` |
| 6-call burst | 429 **not observed** (restriction short-circuits first) | adapter performs **no** retry/backoff — retries live in `ExecutionService.max_retries_per_candidate` |

**No real Groq completion was obtained in R172.** The completion path remains proven only by the hermetic
`httpx.MockTransport` suite (`tests/providers/test_groq_adapter.py`) and by earlier rounds' `tests/providers/test_groq_live.py`
(9 skipped here). A live completion needs an unblocked key.

## C. Contradictions and corrections (where the directive / HARVEST / earlier docs were wrong or imprecise)

1. **C1 collateral** — the mandated `*accounts*` / `*password*` globs deny tracked sources to the dev agent:
   `core/providers/accounts.py`, `infrastructure/security/password.py`, `tests/infrastructure/test_argon2_password_hasher.py`,
   `engineering/adr/ADR-0005-password-hashing-binding.md`. Kept exactly as mandated (fail-closed); a human edits those files.
   Reopening them needs an explicit allow-list exception, not a weaker glob.
2. **Deny-pattern count** — the deduplicated `DENIED_PATH_PATTERNS` set is **64** unique globs, not the 73 cited in the directive
   text; 73 is the unrelated UI `/v1/` ceiling `N0` in `green_manifest.json::ui_static_check`.
3. **"live git transport NOT EVALUATED" (R169/R170)** — now EVALUATED for GitHub over REST (Section B). Still NOT EVALUATED:
   GitHub Enterprise base URLs, non-GitHub remotes, `git` CLI transports (refused by the no-subprocess rule).
4. **R170 HARVEST L71** said no row touched the transport item — correct at the time; C8 closed it without harvesting anything
   from the reference (it has no transport layer).
5. **`docs/r169/SANDBOX_OPTIONS.md`** had 0 references to R170 evidence (discovery D8); §8 now cites HARVEST row 4 line-by-line.
6. **Import cycle** (C7 finding): `apps.agent_dev.http → apps.api.errors → apps.api.__init__ → apps.api.app` — a module-level import
   of `create_dev_router` in `app.py` breaks one import order; resolved with a composition-time import at the seam.
7. **Groq keys** supplied for R172 are organization-restricted; any plan that assumed "4 working keys" is wrong for this round.
8. **GitHub protected-branch signal** is HTTP **422** with a message string, not 403 — mapped by message markers
   (`"pull request"`, `"protected branch"`, `"protected"`).

## D. UI readiness — honest verdict

`ui/admin/{app.js 79351, index.html 32385, styles.css 16392}` and `ui/app/{app.js 28395, index.html 11686, styles.css 19604}`
are byte-identical to round start (frozen by mandate). Consequences:

- The UI cannot issue payload-bound approvals (C6) — the binding is opt-in and inert until the UI emits hashes.
- The UI has no `/v1/dev` client; `dev.publish_modes` is a capability id only (C7).
- No trust-grant or binding-provisioning UI exists (C2/C3); those acts would be CLI/endpoint work in a later round.
- The `ui_static_check` ceiling (`N0 = 73`, may only move down) is unchanged; `tests/ui` 14 passed.

**Verdict:** the UI is *unchanged and green*, not *ready for the R172 features*. Nothing in R172 is user-visible.

## E. Open items (owner decisions; none consumes R172 budget)

| Item | What is missing | Where |
|------|-----------------|-------|
| C2 binding store | construct `JsonBindingStore(path, outside_of=…)` in `apps/composition/runtime.py`; choose default state path | `core/tools/binding_store.py` |
| C3 trust registry | wire `RemoteTrustRegistry` into the production `GitToolset`; operator act that *grants* trust (CLI/endpoint) | `core/tools/remote_trust.py` |
| C5 checkpoints | pass a `CheckpointManager` to `build_dev_surface`; retention/GC policy | `core/tools/checkpoint.py` |
| C6 payload binding | UI/approval issuer must emit `payload_sha256`; hash versioning field | `core/tools/payload_binding.py` |
| C7 dev seam | inject `dev_bindings` in `runtime.py` (depends on C2 + C3); write routes deliberately absent | `apps/api/app.py` |
| C8 transport | construct `GitHubRestTransport` + `GitToolset` in a production root; GHE `base_url` plumbing; branch/PR cleanup primitive | `apps/agent_dev/github_transport.py` |
| Groq live completion | an unblocked key; then `tests_live/r172` and `tests/providers/test_groq_live.py` run green end-to-end | env only |
| Session-artefact denial | `*dump*`/`*session*` deliberately NOT denied (would hit fixtures); content-based detection out of scope | C1 notes |
| Sandboxing | still design-only (O1 refused with evidence, §8) | `docs/r169/SANDBOX_OPTIONS.md` |
| Throwaway repo | `r172-live-transport-throwaway-48b263` keeps PR #1/#2 as evidence; delete when no longer needed | GitHub |

How to run the live suite (keys exported in-shell only, never persisted):

```
GROQ_API_KEY_1=… GITHUB_TOKEN=… R172_LIVE_GITHUB_REPO=https://github.com/<owner>/<throwaway>.git \
python -m pytest tests_live/r172 -q -p no:cacheprovider -o addopts="" -rs
```

`tests_live/` is outside `pyproject::testpaths` and every manifest slice; `check_repo.sh` never collects it.
