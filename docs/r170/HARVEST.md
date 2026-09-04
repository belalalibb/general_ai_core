# R170 — Reference Harvest (READ-ONLY round, production budget = 0)

**Repo:** `belalalibb/general_ai_core` @ `main` (HEAD at start `4e6b44a` == `origin/main`, tree clean).
**Reference:** `https://github.com/pijsal1-tech/Claude-Fable-5`, shallow clone at `/tmp/ref`, HEAD `9c3738275ede8f51400bd083cf5ed4dcd7d1a667`. Cloned once, read only, deleted at the end of the round (proof: `evidence/r170/scrub.txt`). Never added as remote / submodule / subtree. **Ideas were harvested, not files.**

**Budget discipline:** this round created only `docs/r170/HARVEST.md` and `evidence/r170/**`. No file under `core/**`, `apps/**`, `ui/**`, `infrastructure/**`, `tests/**`, `engineering/verification/**` or `green_manifest.json` was touched. No tests were run or added; no manifest edits. **Nothing in this document is implemented** — R171 implements only rows the owner approves.

**Do-not-read list respected:** `DEVELOPMENT_TASKS_V_1.md`, `chat_dispatch.py`, `config.yaml`, `desktop.py`, `desktop.spec`, `provider_keys.py`, `.coverage`, build/dist artifacts were not opened.

---

## 0. Reading log (what was actually read)

| Reference path | Lines | Depth |
|---|---|---|
| `core/workspace_trust.py` | 1-77 (whole) | full |
| `core/ignore_rules.py` | 1-36 (whole) | full |
| `core/hooks.py` | 1-209 (whole) | full |
| `core/index_snapshot.py` | 1-127 (whole) | full |
| `actions/command_runner.py` | 1-290 (whole) | full |
| `actions/file_manager.py` | 1-317 (whole) | full |
| `chain/path_policy.py` | 1-272 (whole) | full |
| `core/approval.py` | 1-135 | partial |
| `core/checkpoint.py` | 1-66 (header + layout) | partial |
| `core/permissions_overrides.py` | 1-76 | partial |
| `core/lease.py` | 1-34 | partial |
| `core/network_guard.py` | 1-37 | partial |
| `server.py` | 321-333, 370-395, 2750-2768 | targeted (trust enforcement) |
| `routes/meta.py` | 343-364 | targeted (trust write path) |
| QA docs: `COMMAND_EXECUTION_TESTS.md`, `FILE_OPERATION_TESTS.md`, `SENSITIVE_DATA_TESTS.md`, `ACTION_SCOPE_VIOLATION_TESTS.md` (under `TesT_-_2_ToOoOo_-_Marena_-_ResultS/qa_logs/`) | whole | full |
| Remaining `core/*.py`, `actions/*.py` | AST outline (classes/functions/docstrings) | skim |

Our side (read-only, for filter #3): `core/tools/source_reader.py`, `core/tools/source_writer.py`, `apps/agent_dev/surface.py`, `apps/agent_dev/git_tools.py`, `core/contracts/repo_binding.py`, `core/engineering/command.py`, `docs/r169/SANDBOX_OPTIONS.md`, test names under `tests/tools/` and `tests/agent_dev/`.

---

## 1. Seed verification (§6) — verdicts first

| Seed | Claim | Verdict | Evidence |
|---|---|---|---|
| (a) | Reference `workspace_trust` is untrusted-by-default; our `RepoBinding` has no stored human trust decision | **CONFIRMED (gap is real)** | Ref `core/workspace_trust.py` L32-51: record must literally be `{"trusted": true}` (bool) else `is_trusted()` returns `False`; never raises. Enforced at `server.py` L321-333 (`_workspace_trusted()`), L382 (untrusted ⇒ force approval), L2755-2762 (`ApprovalGate(interactive_override=lambda: not _workspace_trusted())`). Ours: `core/contracts/repo_binding.py` L52-62 `RepoBinding(id, tenant_id, remote_url, branch, local_root, allowed_modes, credential_ref, label)` — **no trust field, no trust record anywhere**. |
| (b) | QA docs are a portable attack catalogue for `source_writer` / `git_tools` tests | **MOSTLY WRONG** | The four docs are chat-routing / UX findings against an LLM assistant (BUG-CMD-001 command-echo inconsistency, BUG-ROUTE-001, BUG-ACT-001/002 "review-only turned into execute", OUTPUT-MD-001 markdown rendering). Only two things port: (i) name-based sensitive-file cases (SEC-004: auto-analysis read `acco33unts.txt` despite prohibition; proposed names `accounts/credentials/cookies/tokens/password/session`) → feed row 2; (ii) the meta-lesson "no SAFE claim without an audit" → already our INV-4 posture. |
| (c) | `command_runner.py` demonstrates same-process execution is unsafe | **CONFIRMED** | `SAFE_COMMANDS` L28-33 includes `node`, `python`, `python3`, `py`; `_is_safe` L251-265 matches on **first word only** so `python -c "<anything>"` is "safe"; `self.cwd = os.path.abspath(cwd)` L49 — no jail, no containment; `_ask_approval` L279-291 uses blocking `input()`; `subprocess.run(args, shell=False, cwd=self.cwd, env=env)` L157-167 inherits the parent env (redaction L135-148 is by key-name substring only). This is exactly the failure mode `docs/r169/SANDBOX_OPTIONS.md` O1 (L44-53) refuses. |
| (d) | Our `DEFAULT_DENIED_PATTERNS` does not cover `engineering/verification/**` or `green_manifest.json` | **CONFIRMED OPEN — 17 gaps of 27 probes** | `evidence/r170/denylist_probe.txt` (fnmatch exactly as `SourceReader._denied` L93-94). Uncovered: `engineering/verification/green_manifest.json`, `engineering/verification/check_repo.sh`, `green_manifest.json`, `.ENV`, `.Env.local` (fnmatch is case-sensitive on POSIX), `keys/id_rsa`, `.ssh/id_ed25519`, `.aws/config`, `.kube/config`, `cert.pfx`, `cert.pkcs12`, `key.asc`, `passwd`, `shadow`, `accounts.txt`, `acco33unts.txt`, `cookies.txt`. Covered correctly: `.env*`, `*.pem`, `*.key`, `*.p12`, `*credentials*`, `.git/**`. Proposed fix is binding-level configuration (row 2). |

---

## 2. Ranked harvest table (HIGHEST VALUE FIRST)

Legend — **INV**: 1 contracts-first · 2 typed refusals · 3 provider isolation (opaque `credential_ref`) · 4 evidence or NOT EVALUATED · 5 human authority for publish · 6 green stays green · 7 admin agent not widened · 8 HEAD == origin/main. **cost** = estimated number of production files that must change (new files count as additive).

| rank | idea | reference path (+ line range) | what we have today (exact path or "nothing") | verdict | INV check (which, pass/fail) | additive? | cost (est. production changes) | plain-language gain |
|---|---|---|---|---|---|---|---|---|
| 1 | **Stored, fail-closed human trust decision per repo binding.** A side record `{version, trusted: bool, decided_at (ISO-UTC), decided_by}` written atomically (tmp + fsync + `os.replace`); reader treats anything that is not literally `trusted: true` as untrusted; untrusted binding ⇒ every commit/publish/write requires explicit approval regardless of mode. | `core/workspace_trust.py` L27-29 (`trust_path`), L32-45 (`read_trust_record`, strict `isinstance(..., bool)`), L48-51 (`is_trusted`), L54-77 (`set_trust`, atomic). Enforcement pattern: `server.py` L321-333, L382, L2755-2762; write path `routes/meta.py` L343-364 (`decided_by="user"`). | **nothing.** `core/contracts/repo_binding.py` L52-62 has no trust field; `apps/agent_dev/git_tools.py` L302-306 already marks commit/publish `ApprovalRequirement.BEFORE_ACTION`, but there is no persisted human decision that survives a process restart, and no "who trusted this remote, when". | **TAKE** | INV-1 pass (new contract `BindingTrustRecord` + `GitRefusalCode` addition if needed); INV-2 pass (typed refusal `binding_untrusted`); INV-3 pass (no credential involved); INV-5 **pass — strengthens it**; INV-7 pass (narrows, never widens). | **yes** as a new module `core/contracts/binding_trust.py` + `core/tools/binding_trust_store.py` and composition wiring in `apps/agent_dev/surface.py::build_dev_surface` (L200-222). Making `GitToolset` consult it is a **needs edit: `apps/agent_dev/git_tools.py` L302-306 (approval decision) and/or L350-356 (`_token` — refuse token resolution for untrusted bindings)**. | 2 new files + 1 composition edit (+1 optional `git_tools.py` edit) ≈ **1–2** | A remote we cloned is not automatically a remote we are allowed to push to; a human must say "trusted" once, it is recorded with a timestamp and author, and the record can be revoked. Directly serves the OPEN item "binding provisioning / persistence unbuilt". |
| 2 | **Denylist hardening as binding-level configuration** (names, extensions, directories), plus a note on case/normalization. Reference keeps three explicit sets — names (`id_rsa id_dsa id_ecdsa id_ed25519 credentials passwd shadow keys.txt provider_keys.json`), extensions (`.pem .key .pkcs12 .pfx .p12 .asc`), dirs (`.aws .ssh .git .gcloud .kube`) — and normalizes the name before matching (strip invisible chars, cut NTFS ADS `:stream`, strip trailing dots/whitespace, lower-case). | `chain/path_policy.py` L18-24 (`SECRETS_DENYLIST_NAMES`), L25-27 (`_EXTENSIONS`), L28-30 (`_DIRS`), L35-43 (`_INVISIBLE_CHARS`), L77-98 (`_classify_name`, `.env.example` exempt), L116-157 (`normalize_secret_name`), L158-190 (`is_secret_file`). QA input: `SENSITIVE_DATA_TESTS.md` SEC-004 (`acco33unts.txt`). | `core/tools/source_reader.py` L32-46 `DEFAULT_DENIED_PATTERNS` (13 fnmatch globs), `_denied` L93-94; `source_writer.py` L36 imports the same tuple. Probe (`evidence/r170/denylist_probe.txt`): **17/27 expected-denied paths admitted**, including the two gate files. Both `SourceReader` and `SourceWriter` accept `denied_patterns=` and `build_dev_surface` accepts pre-built `reader`/`writer` (`apps/agent_dev/surface.py` L219-220), so the denylist is already injectable. | **TAKE** (config-only part now; matcher change deferred) | INV-6 **pass — protects the gate** (`engineering/verification/*`, `green_manifest.json` become unwritable/unreadable by the dev agent); INV-7 pass; INV-2 pass (existing `SourceReadRefused`/write refusal codes reused); INV-4 pass (probe is the evidence). | **config-only** for the pattern set: build `SourceReader(root, denied_patterns=DEFAULT + R170_EXTRA)` / `SourceWriter(...)` at the composition root and pass them to `build_dev_surface`. Proposed extra globs: `engineering/verification/*`, `engineering/verification/**`, `green_manifest.json`, `*/green_manifest.json`, `id_rsa* id_dsa* id_ecdsa* id_ed25519*`, `*/id_rsa*` (etc.), `.ssh .ssh/* */.ssh/*`, `.aws .aws/* */.aws/*`, `.kube/* .gcloud/*`, `*.pfx *.pkcs12 *.asc`, `passwd shadow */passwd */shadow`, `*accounts* *cookies* *token* *password* *session*` (case variants `.ENV .Env* ...` as extra globs, since fnmatch is case-sensitive). Case-insensitive / normalized matching itself would be **needs edit: `core/tools/source_reader.py` L81-94 (`_admit`/`_denied`)** — defer. | **0 production edits** for the config-only variant (composition root config) + 1 new test file in R171; matcher normalization would be 1 file | The agent that edits source can no longer read or rewrite the green-gate files or common private-key/credential files, and the widened list lives in configuration, not in the tool. Closes seed (d). |
| 3 | **Content-addressed pre-write checkpoint with external-modification-guarded restore.** Before each mutating op, store the current blob under `objects/<sha256>` and append a snapshot record; on restore, verify the on-disk hash still equals the pre-image (or the sealed post-image) — otherwise refuse with a conflict report and a partial-status result. | `core/checkpoint.py` L1-56 (design + store layout), L57-66 (record fields). | `core/tools/source_writer.py` L112-127 (`_existing_file_digest`) + CAS `expected_sha256` precondition in `_perform` L161-198. We refuse **stale** writes but cannot **undo** an applied write; there is no snapshot store. | **TAKE** | INV-1 pass (new `Checkpoint` contract); INV-2 pass (typed `restore_conflict` refusal); INV-6 pass (no gate impact); INV-7 pass. | **yes** — new module `core/tools/checkpoint_store.py` wrapping `SourceWriter` (compose in `build_dev_surface` by passing a wrapped `writer=`). No edit to `source_writer.py` required if implemented as a decorator around `apply()`. | 1 new file + composition config ≈ **1** | Every agent write gets an automatic "undo" whose restore refuses to clobber changes a human made in the meantime. |
| 4 | **Evidence for `SANDBOX_OPTIONS.md` O1 refusal — same-process/`subprocess` execution is not a safe surface.** Concrete anti-pattern: interpreter names in a SAFE list, first-word matching, unjailed cwd, inherited env, blocking `input()` approval. | `actions/command_runner.py` L28-33 (`SAFE_COMMANDS`), L49 (`cwd`), L93-100 (operator substring check), L135-148 (env redaction by key name), L157-167 (`subprocess.run`), L251-265 (`_is_safe`), L279-291 (`input()`). | `core/engineering/command.py` `CommandPolicy` — allowlist `python3/pytest/ruff`, `-c/--command` denied, cwd jail: **ALREADY BETTER on admission**. Sandboxing itself remains design-only (`docs/r169/SANDBOX_OPTIONS.md` O1 L44-53, recommendation L139-150). | **TAKE (as evidence only, cost 0)** | INV-4 pass (this row *is* the evidence); INV-7 pass (no surface added). | **yes** — docs only (a cited paragraph appended to `SANDBOX_OPTIONS.md` in R171, or this row referenced from it). | **0** | Gives the owner a concrete, line-cited example of why "just run subprocess with a SAFE list" is rejected, so O1 stays refused with evidence rather than opinion. |
| 5 | **Atomic file writes (tmp + fsync + `os.replace`)** for CREATE/OVERWRITE. | `actions/file_manager.py` L103-113 (also `core/workspace_trust.py` L68-74, `core/index_snapshot.py` L60-88 use the same NF-19 pattern). | `core/tools/source_writer.py` `_perform` — CREATE `target.write_bytes(blob)` L178, OVERWRITE L183: **non-atomic**; a crash mid-write leaves a truncated file that the CAS digest will then treat as "externally modified". | **TAKE (low)** | INV-6 pass; INV-2 pass (no refusal semantics change); INV-7 pass. | **needs edit: `core/tools/source_writer.py` L178 and L183** (replace two `write_bytes` calls with a small `_atomic_write(target, blob)` helper). An additive subclass is possible but strictly worse than a 2-line edit. | **1** file, ~10 lines + 1 test | A power loss or kill during an agent write can never leave a half-written source file behind. |
| 6 | **Approval bound to a payload hash.** Approval request carries `payload_hash = sha256(canonical JSON of actions)`; a verdict for a different hash is rejected as `hash_mismatch`; timeout/deny-mode are distinct typed reasons. | `core/approval.py` L58-70 (`compute_actions_hash`), L77-92 (`ProposedAction`), L94-116 (`ApprovalRequest.payload_hash`), L118-135 (`Verdict` reasons: `hash_mismatch`, `timeout`, `deny_mode`). | `apps/agent_dev/git_tools.py` L302-306 marks commit/publish `ApprovalRequirement.BEFORE_ACTION` via the shared `ToolCallGate`. **Whether the gate binds the approval to the exact arguments (TOCTOU-safe) was NOT EVALUATED this round** — the gate module was not read. | **VERIFY in R171** (TAKE only if the gate does not already hash the payload) | INV-5 **pass — strengthens it** if missing; INV-1 pass (typed field on the approval contract); INV-4: currently NOT EVALUATED. | Unknown until the gate is read; likely **needs edit** to the approval contract + gate. | **0–2** | A human who approved "commit these 3 files" cannot have that approval silently reused for a different set of files. |
| 7 | **Tighten-only, fail-closed hook runner** (pre-command hooks may only deny; post hooks are warnings; timeouts capped). | `core/hooks.py` L71-95 (`_parse_specs`, timeout ≤ 60 s), L137-166 (`_run_one`, `shell=False`), L168-183 (`pre_command` fail-closed), L185-209 (post hooks warn only). | `ToolCallGate` is our single policy seam; no subprocess hook mechanism. | **SKIP** | INV-7 **fail risk**: owner-configured subprocess hooks add an execution surface while sandboxing is design-only. | would be additive, but contradicts SANDBOX posture | — | (Recorded for completeness; the "deny-only pre-hook" idea is already expressible as a gate policy.) |

### Combined R171 proposal for owner approval (not implemented here)

- **Row 2 (config-only)** — zero production edits, closes seed (d), protects the gate. Safest first step.
- **Row 1** — new contract + store, serves the "binding provisioning / persistence" open item; the one-line consult in `git_tools.py` is the only non-additive touch.
- **Row 3** — additive wrapper.
- **Row 5** — 2-line edit, pairs naturally with row 3.
- **Row 4** — documentation citation only.
- **Row 6** — read `ToolCallGate` first; decide after.

None of the rows touches the open item **"live git transport NOT EVALUATED"** — the reference has no git transport layer to learn from (confirmed by AST skim: no `git` module under `core/` or `actions/`). That item stays NOT EVALUATED.

---

## 3. Rejected (one line each)

- `core/hooks.py` — owner-defined subprocess hooks add an execution surface while sandboxing is design-only (INV-7); our gate is the seam (see row 7).
- `core/index_snapshot.py` — performance cache for a workspace index; we have no such index; skeptical-loading pattern noted but nothing to apply it to.
- `core/lease.py` — Redis `SET NX PX` + Lua lease; infrastructure-specific, no matching need in the dev surface.
- `core/network_guard.py` — loopback-only bind guard for a local desktop server; we authenticate with bearer tokens at the HTTP layer instead.
- `core/permissions_overrides.py` — strict whitelist of override keys, fail-closed whole-file; we already have an admin config lifecycle with typed refusals.
- `core/ignore_rules.py` — a 36-line `IGNORED_DIRS` frozenset; trivial and already covered by our reader's admission.
- `actions/file_manager.py::create_backup` (`.webdev_backups`, L197-211) — superseded by the content-addressed checkpoint idea (row 3).
- `actions/file_manager.py` `WEB_EXTENSIONS` including `.env` (L23) — reference treats `.env` as an editable "web" file; ours denies it, which is correct.
- `actions/command_runner.py` env redaction by key-name substring (L135-148) — weaker than passing a constructed minimal env; nothing to take beyond the evidence in row 4.
- `core/response_parser.py`, `core/session_manager.py`, `core/session_context.py`, `core/app_context.py`, `core/strategy.py`, `core/project_memory.py`, `core/run_metrics.py`, `core/events.py`, `core/execution.py`, `core/runner.py`, `core/backends.py` — chat/assistant layer or runtime plumbing of a different product shape; nothing INV-relevant on AST skim.
- QA docs `COMMAND_EXECUTION_TESTS.md`, `ACTION_SCOPE_VIOLATION_TESTS.md`, `FILE_OPERATION_TESTS.md` (bulk) — LLM routing / rendering bugs of the reference product; not path-level or transport-level attacks; seed (b) largely wrong. Only SEC-004 name cases were kept (row 2).
- Reference `.env.example` exemption (`chain/path_policy.py` L77-98) — convenience over safety; we keep `.env.*` denied.

---

## 4. Evidence index

- `evidence/r170/denylist_probe.txt` — seed (d) probe: 30 paths against `DEFAULT_DENIED_PATTERNS`, 17 gaps.
- `evidence/r170/scrub.txt` — §7 scrub proofs (`git status --porcelain` empty; `git ls-files` has no reference paths; `grep -rIl "Claude-Fable"` matches only this file; `rm -rf /tmp/ref`; `ls /tmp/ref` → No such file).

## 5. Round close

- Production budget used: **0**. Files created: this document + `evidence/r170/**`.
- Reference clone deleted; no remote/submodule/subtree added; no reference file copied.
- Credential store (`~/.git-credentials`, `credential.helper store`) left in place per mandate; no token appears in any tracked file, commit message, or evidence (staged-file secret scan recorded in the commit step).
- **STOP.** R171 implements only owner-approved rows.
