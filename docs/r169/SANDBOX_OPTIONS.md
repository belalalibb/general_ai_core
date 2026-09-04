# SANDBOX OPTIONS — design note for a future dev-agent command surface (R169 B1)

**Status:** DESIGN ONLY. This document adds no code, no tool id, no permission and no route.
The development-agent surface (`apps/agent_dev/`) has NO command-execution capability after
R169; any `command.*` tool is a decision for a later round and for the operator (INV-5, INV-7).

Verified against HEAD `667bfb5` (2026-09-04). Every claim about the repository points at code.

## 1. What already exists (do not rebuild)

| Layer | Location | What it guarantees today |
|---|---|---|
| Contract | `core/contracts/engineering.py` L67–83 (`CommandRequest{argv ≤64, cwd, timeout_ms ≤120_000}`, `CommandResult{exit_code, timed_out, stdout/stderr + *_truncated}`), `MAX_COMMAND_OUTPUT_BYTES=65_536` | Typed request/result; truncation is loud data, not silent loss |
| Admission (core, pure) | `core/engineering/command.py` `CommandPolicy.admit()` | argv[0] basename must be in the composition ALLOWLIST (`python3`, `pytest`, `ruff` by default); relative executable paths refused; `-c`/`--command` denied; cwd must resolve inside the workspace jail; timeout capped by contract AND policy; only `env_allowlist` variables pass (`PATH HOME LANG LC_ALL TMPDIR`) |
| Port | `core/engineering/command.py` `CommandRunnerPort.run(AdmittedCommand) -> CommandResult` | Core never spawns; the adapter is injected |
| Adapter | `infrastructure/engineering/subprocess_runner.py` `SubprocessCommandRunner` | `create_subprocess_exec` (no shell), scrubbed env + `PYTHONDONTWRITEBYTECODE`, own session, hard kill on timeout, capped output |
| Composition | `apps/composition/engineering.py::build_engineering` | Bundle exists ONLY for the platform's own checkout (engineering admin), granted through `grant_engineering_*` on the admin path |
| Layer rule | `pyproject.toml` import-linter (13 contracts) | `core` never imports `infrastructure`; `apps.admin_agent` / `apps.api.admin` / `apps.api.engineering_admin` never import `infrastructure.engineering` |

Consequence: a dev-agent command tool would be **one more handler behind the same port**, admitted by
the same `CommandPolicy`, executed through the existing `ToolExecutor` (gate → usage reserve → handler →
single `TOOL_CALL` audit event). The open question is *where the process runs*, not how it is admitted.

## 2. Threat model the sandbox must answer

The dev agent writes source into a per-binding jail (`source.write`, A2) and can publish it (`git.publish`,
A5). Running commands on that source adds four risks the write/publish tools do not have:

1. **Arbitrary code execution by construction** — `pytest` executes the tenant's own `conftest.py`; the
   allowlist limits the *launcher*, not the *code*. Every option below must assume hostile code runs.
2. **Credential exfiltration** — the process must never see `GH_TOKEN`, `GSK_API_KEY`, `GROQ_API_KEY`,
   `DATABASE_URL`, `~/.git-credentials`, or any `credential_ref` resolution (INV-3). The env allowlist
   covers variables; the filesystem view must cover files.
3. **Cross-tenant reach** — one tenant's command must not read another binding's `local_root`, the
   platform checkout, or the API process's memory/sockets.
4. **Resource abuse** — CPU, memory, disk, fork bombs, outbound network (crypto-mining, data egress),
   and long-lived daemons that outlive `timeout_ms`.

Scoring below is against these four, plus operability in the target deployments (single container on
Cloudflare-fronted VM / plain Linux host; no Kubernetes assumed).

## 3. Options

### O1 — In-process `SubprocessCommandRunner` (status quo, reused as-is)

- **Mechanism:** the API process spawns the child directly in the binding's `local_root`.
- **Isolation:** env scrub, no shell, timeout, own session. **No filesystem, network, or resource isolation.**
  The child runs as the API user and can read `/home/user/.git-credentials`, other bindings, `/proc`.
- **Verdict:** acceptable ONLY for the platform's own checkout under admin authority (what it does today).
  **Refused for tenant code.** Threats 1–3 unmitigated.
- **Cost to adopt:** 0 production changes (already exists) — which is exactly why it is tempting and why
  this note exists.

### O2 — Hardened subprocess: dedicated unprivileged UID + `prlimit` + private tmp

- **Mechanism:** new adapter `infrastructure/engineering/hardened_runner.py` implementing
  `CommandRunnerPort`; spawns via `preexec_fn`/`start_new_session` with `setresuid` to a per-tenant or
  shared `dev-runner` UID, `RLIMIT_AS/CPU/NPROC/FSIZE/NOFILE`, `TMPDIR` inside the jail, cwd chdir'd
  before exec. Bindings' `local_root` chowned so only that UID (and the API) can read them.
- **Isolation:** credentials (owned by API UID, mode 0600) unreadable; resource caps enforced by kernel;
  cross-tenant reads blocked by ownership **if** each tenant has its own UID (UID pool management
  becomes an operator task). No network isolation; `/proc` and shared libraries readable.
- **Verdict:** meaningful improvement over O1 at low operational cost; still not a security boundary
  against kernel-level or network exfiltration. Suitable for **trusted internal tenants** only.
- **Cost:** 1 production change (adapter) + composition (`apps/agent_dev` runner factory). Requires the
  API to run with `CAP_SETUID` or as root-then-drop — an operator decision with its own risk.

### O3 — Linux namespaces via `bwrap` (bubblewrap) or `unshare`, unprivileged

- **Mechanism:** adapter wraps argv as `bwrap --unshare-all --die-with-parent --new-session
  --ro-bind /usr /usr --ro-bind /lib /lib … --bind <local_root> /work --tmpfs /tmp --proc /proc
  --dev /dev --chdir /work --clearenv --setenv PATH … -- argv…`; `--unshare-net` removes network
  entirely; cgroup limits via `systemd-run --scope -p MemoryMax= -p CPUQuota=` when systemd is present,
  else fall back to `prlimit` from O2.
- **Isolation:** the child sees ONLY the bound `local_root`, a read-only toolchain, and a private
  `/tmp`; no network; no other bindings; no credential files (never bound). PID namespace kills
  orphans with the parent. User namespaces mean no root needed on most distributions
  (`kernel.unprivileged_userns_clone=1`, default on Debian ≥11/Ubuntu; some hardened hosts disable it).
- **Verdict:** **recommended default** for tenant code on a plain Linux host. Answers threats 1–4 with
  standard kernel primitives and a single well-audited binary (`bwrap`, used by Flatpak).
- **Cost:** 1 production change (adapter, ~150 lines) + composition; `bwrap` becomes a deploy
  dependency (verify at startup, else the tool is **inert**, never a silent fall-through to O1 — same
  posture as `models.listing` when a seam is missing).
- **Caveats:** Python venv inside the jail must be bind-mounted read-only or provisioned per binding;
  `pip install` (network) is impossible by design — dependency installation becomes a separate,
  operator-approved step, which is the correct posture for INV-5.

### O4 — Per-command container (Docker/Podman `run --rm`)

- **Mechanism:** adapter shells out to `podman run --rm --network none --read-only --tmpfs /tmp
  --memory 512m --cpus 1 --pids-limit 256 --user 65534 -v <local_root>:/work:rw -w /work
  <pinned-image> argv…` with the image containing the toolchain.
- **Isolation:** equivalent to O3 plus image-level reproducibility (pinned toolchain versions); rootless
  Podman avoids the Docker socket (which is root-equivalent and must never be reachable from the
  API process).
- **Verdict:** strong and familiar to operators; **the recommended choice when the API itself already
  runs in a container** (nested namespaces via `bwrap` inside Docker often need `--privileged` or
  seccomp changes, so O3 degrades there while O4 with a sibling-container pattern works).
- **Cost:** 1 production change (adapter) + image build pipeline + registry hygiene (image pinning by
  digest, rebuild cadence). Cold start 300–800 ms per command; acceptable for `pytest`/`ruff`,
  noticeable for a chatty agent.
- **Caveats:** the bind-mount of `local_root` must be the ONLY writable path; the container runtime
  daemon is new attack surface; Docker (non-rootless) is rejected outright.

### O5 — MicroVM (Firecracker / gVisor `runsc`)

- **Mechanism:** O4 with a stronger runtime (`--runtime=runsc`) or a Firecracker pool with a snapshot
  per toolchain image and the binding synced in/out (rsync or 9p).
- **Isolation:** kernel boundary; the strongest option; standard for multi-tenant public code execution.
- **Verdict:** **over-scoped for the current deployment** (single host, private tenants). Record it as the
  target if the dev agent ever runs untrusted third-party tenants at scale.
- **Cost:** infrastructure project (VM images, pool warmers, host with KVM), not a 6-change round.

### O6 — Remote execution provider (external sandbox API)

- **Mechanism:** the adapter POSTs `{files, argv, timeout}` to a hosted sandbox service and receives
  the result; the binding's tree is uploaded per call or kept in a provider workspace.
- **Isolation:** the provider's; the platform gains nothing it can verify (INV-4: claims about the
  provider's isolation would be NOT EVALUATED here).
- **Verdict:** rejected for this codebase's posture: it moves tenant source and results across a
  network boundary to a third party, introduces a new credential class (provider API key) and makes
  `CommandResult` provenance unverifiable. Also violates the hermetic `check_repo` stance.

## 4. Comparison

| | O1 subprocess | O2 UID+rlimit | O3 bwrap/unshare | O4 rootless container | O5 microVM | O6 remote |
|---|---|---|---|---|---|---|
| Hostile code contained (T1) | no | partial | yes | yes | yes | provider |
| Credential files unreadable (T2) | no | yes (ownership) | yes (never mounted) | yes | yes | n/a (uploaded source instead) |
| Cross-tenant FS (T3) | no | with per-tenant UID | yes | yes | yes | provider |
| Network egress blocked (T4) | no | no | yes (`--unshare-net`) | yes (`--network none`) | yes | no (by design) |
| CPU/mem/pids caps (T4) | timeout only | rlimit | rlimit / cgroup | cgroup | VM | provider |
| Root / caps needed | none | `CAP_SETUID` | none (userns) | none (rootless) | KVM | none |
| Works inside a container host | yes | yes | often NOT | yes (sibling) | rarely | yes |
| New deploy dependency | none | none | `bwrap` | podman + image | heavy | vendor |
| Production changes (est.) | 0 | 1 + comp | 1 + comp | 1 + comp + image | many | 1 + comp + secret |
| Per-call overhead | ~0 | ~0 | ~10 ms | 300–800 ms | seconds | network |

## 5. Recommendation (for the operator to accept or reject — INV-5)

1. **Do not expose `command.*` on the dev surface in any round that reuses O1.** The existing adapter
   is correct for the engineering-admin path (platform's own checkout, admin authority) and wrong for
   tenant code.
2. **Default: O3 (`bwrap`) on a plain Linux host; O4 (rootless Podman, `--network none`) when the API
   runs containerised.** Both keep `CommandPolicy` and `CommandRunnerPort` unchanged — the round adds
   one adapter under `infrastructure/engineering/` and composes it in `apps/agent_dev`. Import-linter
   already forbids `apps.admin_agent` from touching it (INV-7).
3. **Inert, never degraded.** At startup the adapter probes its dependency (`bwrap --version` / `podman
   info`). If absent, `command.run` is NOT registered on the dev surface and the capability is reported
   inert with the probe output as evidence. There is no fall-through to O1.
4. **Contract additions (budget-free) before the adapter:** `CommandRefusalCode` in
   `core/contracts/engineering.py` (`executable_not_allowlisted`, `argument_denied`,
   `cwd_outside_binding`, `timeout_exceeds_policy`, `sandbox_unavailable`, `network_requested`), and a
   `SandboxProfile{kind: bwrap|podman, network: false, mem_bytes, cpu_quota, pids}` stored on
   `RepoBinding` (like `allowed_modes`), so the sandbox is per-binding data, not a global.
5. **Allowlist stays tiny and per-binding**: `python3 pytest ruff` (+ `mypy`) — no `pip`, no `git`
   (git is A5's job with its own refusals), no `sh`. `-c/--command` denial stays.
6. **Audit**: keep the single `TOOL_CALL` event per attempt; enrich details with `sandbox_kind`,
   `exit_code`, `timed_out`, `stdout_truncated` — same pattern as `ModeRecordingAudit` (A5), no new
   `AuditEventType` (closed set of 13).
7. **Dependency installation is a separate human-approved act**, not a command the agent may run
   (network is off inside the sandbox by design).

## 6. Open questions recorded for the operator

- Host shape: plain VM (→ O3) or containerised API (→ O4)? Decides which adapter is written first.
- Is `kernel.unprivileged_userns_clone` enabled on the target host? If not, O3 needs setuid `bwrap`
  (acceptable, Flatpak's model) or the answer is O4.
- Per-tenant UID pool (O2 hardening) is unnecessary under O3/O4 — confirm it is dropped rather than
  layered.
- Budget: the adapter + composition is 1–2 production changes; a UI trigger for "run tests" is OUT OF
  SCOPE until the backend surface exists and is evidenced.

## 7. What this note does NOT do

- No code, tool id, permission, route, or manifest budget entry — B1 is design only (§5 of the R169
  mandate).
- No claim that any option has been exercised in this repository: every "yes" in §4 is a property of the
  named mechanism, NOT EVALUATED here (INV-4). The round that adopts an option must produce fail-first
  evidence (e.g. a test proving `~/.git-credentials` is unreadable and `curl` fails inside the sandbox).

## 8. Evidence for the O1 refusal (R170 harvest row 4; cited by R172 D8)

O1 ("run tools in the same process / plain `subprocess` with a SAFE list") stays **refused**, and since
R170 the refusal rests on a line-cited external anti-pattern rather than on opinion. `docs/r170/HARVEST.md`
row 4 (and confirmation (c) in its seed table) records, from the reference project's `actions/command_runner.py`:

- interpreter names (`node`, `python`, `python3`, `py`) inside the SAFE list (L28-33);
- `_is_safe` matches on the **first word only** (L251-265), so `python -c "<anything>"` is admitted;
- `cwd = os.path.abspath(cwd)` with no jail or containment (L49);
- `subprocess.run(..., env=env)` inheriting the parent environment, with redaction by key-name
  substring only (L135-148, L157-167);
- approval through a blocking `input()` (L279-291).

Our admission layer (`core/engineering/command.py::CommandPolicy` — `python3/pytest/ruff` allowlist,
`-c/--command` denied, cwd jail) is already stricter on admission; sandboxing itself remains design-only
here (§4 O1, §6). R172 C8 additionally shows the transport side can avoid subprocesses entirely
(`apps/agent_dev/github_transport.py` speaks the GitHub REST API; see IMPL-025). This section is
docs-only: no code, tool id, permission or route changed (R172 discovery D8 was "0 hits for R170 in
this note").
