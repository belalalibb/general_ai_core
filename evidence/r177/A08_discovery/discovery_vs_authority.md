# R177-A08 — Repository discovery vs execution authority (§11) at HEAD b58432a0

## 1. Real primitives (KNOWN)
| concern | code | behaviour observed |
|---|---|---|
| Read jail | `core/tools/source_reader.py` `SourceReader` (root.resolve(); `_admit` :124-133: relative-only, resolved candidate must stay under root else `SourceReadRefused("path escapes the source root")`, denylist check after normalisation of invisible/format chars :63-90) | bounded: `DEFAULT_MAX_FILE_BYTES=65_536`, `DEFAULT_MAX_ENTRIES=500` |
| Denylist | `core/tools/denied_paths.py` `DENIED_PATH_PATTERNS` = `DEFAULT_DENIED_PATTERNS` ∪ `HARDENED_PATTERNS` (27 EXPECT_DENIED rows from R170 probe); `is_denied_path` fnmatch | applied by both `SourceReader._denied` and `SourceWriter._denied` |
| Write path | `core/tools/source_writer.py` + `core/tools/checkpoint.py` (checkpoint index outside the jail; seal with post-apply hash; revert only when `cur == post`, else typed `checkpoint_conflict`) | writes are hash-sealed and revertible |
| Tool gate / executor | `core/tools/gate.py` (frozen) + `core/tools/executor.py` | A05: manifest → firewall → approval_policy (default ALWAYS) → execute; refusals typed |
| Payload binding | `core/tools/payload_binding.py` (R172 C6) | approval tied to sha256 of canonical arguments |
| Remote trust | `core/tools/remote_trust.py` per-(tenant, remote_url) grants in an atomic JSON store outside the jail | git remotes are allow-listed per tenant |
| Engineering tools | `core/engineering/tools.py` ws_read / ws_list / ws_write / ws_run / git_commit / git_push; permissions vocabulary = `source.read`, `workspace.read`, `workspace.write`, `workspace.exec`, `git.read`, `git.write` | ws_write/ws_run: "policy FIRST, ticket SECOND" (:186) — jail/denylist refusal precedes the AuthorizationLedger ticket check |
| Command policy | `core/engineering/command.py` `CommandPolicy(allowlist=DEFAULT_COMMAND_ALLOWLIST, env_allowlist=…)`; allowlist = python3, pytest, ruff (+ `-c/--command` shapes) | only allow-listed env vars pass ("credentials never leak" :10) |
| Tenant policy | `apps/composition/agent.py:56 READ_ONLY_AGENT_POLICY` = {source.read} + entitlement agent.tools; `apps/composition/engineering.py grant_engineering_reads / grant_engineering_writes(subset)` (unknown names refused) | default = READ ONLY; every write permission is an explicit admin grant + a one-use ticket |
| Tool selection | `apps/api/agent.py:77-93 select()`: absent/empty allow-list AND no skills ⇒ **NO tools**; unknown names ⇒ `AgentToolsRejected` (loud); `denied` overrides everything | deny-by-default at selection time, before the gate |

## 2. §11 requirement-by-requirement
| requirement | class | evidence |
|---|---|---|
| Progressive, need-driven discovery (read/list bounded, not whole-repo slurp) | **ALREADY COVERED** (primitive level) | 64 KiB / 500-entry bounds; glob-scoped `list_files`; R165 live 32-stage run (R176 A11 readiness) exercised read → fix → test → commit → push end to end |
| Reliable **project map / model** artefact (stack, entry points, modules, APIs, schemas, config, infra, tests, deps) | **MISSING** | grep `project map|repo map|repository_map|project_model|discover` over core/apps → no such artefact/contract; understanding exists only transiently inside an agent run's steps/trace |
| Distinguish understood vs not established; expose confidence; ask for deeper analysis | **PARTIALLY COVERED** | agent trace records every step + evidence ledger (`/v1/agent/executions/{id}/trace`, R165 verify-with-evidence); no persisted confidence per repository fact |
| Never pretend to understand un-inspected code | **COVERED BUT NEEDS STRONGER EVIDENCE** | verify_with_evidence loop refuses unevidenced "done" (R165); no direct probe in R176/R177 for hallucinated file claims |
| Reading ≠ execution authority (least privilege, scoped permissions, approvals) | **ALREADY COVERED** | read-only default policy; write/exec = separate permissions + admin grant + ticket + firewall + approval_policy ALWAYS + payload binding; command allowlist; remote-trust allowlist |
| Capability laundering / confused deputy not regressed | **ALREADY COVERED** (R176 A5 probed: role/skill/project/model laundering refused) | R176 report §… "role/skill/project/model laundering refused"; A08 adds: a discovered path can never widen the jail (resolve-then-relative_to) |
| Scalability of discovery on LARGE repositories | **COVERED BUT NEEDS STRONGER EVIDENCE** | bounds exist; no executed probe on a large (10k+ file) tree; `list_files` truncates at 500 entries without a continuation token (KNOWN from :169) — a large-repo agent must recurse by directory |

## 3. Findings
- **F-R177-05 (S3, capability)**: no persisted, tenant/project-scoped **repository model** — discovery is re-done per run and is not
  a first-class artefact the planner can cite. Minimum compatible addition (if approved later): a `MemoryItem` convention
  `scope=project, source="repo.map"` written by an OPTIONAL discovery tool through the existing memory port (no new store, no new
  contract), with confidence/evidence_count already present on MemoryItem, and the composer already ranking project scope.
- **F-R177-06 (S4, ergonomics)**: `list_files` hard-truncates at `max_entries` with no continuation cursor; fine for bounded reads,
  weak for large trees. Composition data (`max_entries`) mitigates; not a security issue.

Separation verdict: **understanding never implies permission** is structurally true today — the same tool that reads cannot write;
writes need three independent consents (grant, ticket, approval state) and are hash-sealed.
