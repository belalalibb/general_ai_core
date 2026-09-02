> **Reconciliation note (R162, 2026-09-02):** this document records the V1–V9 closure at R135 (2121 tests). Subsequent R136–R162 work on branch `feature/model-provider-skill-orchestration` (PR #12) ADDED, without regressing it: shared agent runtime (`core/agent`, `strategy=agent`), verification-before-finalization, external skill acquisition pipeline, provider onboarding via gateway discovery (refs only), measured learning lifecycle (scan/sanitize/derived admission signals/GOLD-after-write/context_provenance/capability re-test with production reach), two-lane self-evolution statement (§14 gate untouched), hybrid identity mode, unified CLI, S2 pooled provider clients (all three real adapters + shutdown release), S3 bounded fan-out. Gates at R162: 2586 passed / 64 skipped, ruff clean, mypy --strict clean (core+apps/api+apps/admin_agent), 12/0 import contracts. Operations: `docs/OPERATIONS.md`. The §6 honest exclusions still standing: email delivery, OS jail, token streaming, distributed deployment composition; durable stores for usage/audit/learning samples remain in-process.

# MASTER VISION v2 — FINAL DOCUMENTATION (V9, one doc)

```text
STATUS: FINAL (V9 chunk 2 deliverable — the roadmap's "Final Documentation (one doc, §13)")
DATE: 2026-08-31
STATE_REVISION: R135
BRANCH: feature/platform-agent-vision
VALIDATION_AT_WRITING: engineering/verification/V9_FULL_VALIDATION.md — PASS
  (2121 passed + 60 skipped hermetic; ruff repo-wide clean; mypy --strict core
  127 files + recorded apps scopes 20 files clean; import-linter 12 kept /
  0 broken; secret scan clean; 222 adversarial/security tests; check_repo.sh PASS)
```

Honesty rule (41 §49): every claim below is reproducible from the repository
at the commit carrying this file. This document COMPOSES recorded facts —
phase records, committed evidence files, executable tests — and makes zero
new claims. Where something does NOT exist, it is named in §6.

---

## 1. What this platform is

A multi-tenant AI orchestration platform built as a **modular monolith**:

- **`core/`** — framework-free domain logic (22 packages: admin, audit,
  context, contracts, evaluation, events, execution, identity, learning,
  memory, providers, roles, routing, runtime, secrets, security, skills,
  sourcechange, storage, tools, usage, workspace). Every I/O concern is a
  `Protocol` port; no web framework, no DB driver, no telemetry stack may
  be imported here — enforced by tooling, not convention.
- **`apps/`** — composition layer: `apps/api` (FastAPI composition root
  `create_app`, every collaborator injected, absent seam = absent routes),
  `apps/admin_agent` (governed admin-agent tool surface), `apps/composition`,
  `apps/observability` (the ONLY OTel/structlog configuration site).
- **`infrastructure/`** — bindings behind accepted ADRs: PostgreSQL/
  SQLAlchemy/Alembic (ADR-0002), Redis (ADR-0003), S3 object storage
  (ADR-0006), Vault secret manager (ADR-0007), Argon2id (ADR-0005).
- **`providers/`** — provider adapters behind `ProviderAdapterPort`;
  remote gateway per ADR-0008.

## 2. The frozen invariants (tooling-enforced)

| Invariant | Enforcement | Evidence |
|---|---|---|
| 12 import-linter contracts (core pure; contracts import no implementation; providers/infrastructure/apps layering; ADR-confined toolchains) | `lint-imports` on every `check_repo.sh` run | **12 kept / 0 broken** (249 files, 1269 deps) at V9 validation |
| Closed enums / closed route surfaces / closed error sets | contract suites + guard pins (aa1 openapi pin, t033 closed-surface pin, aa2 total-op pin = **63 ops**) | `tests/contract/`, `tests/api/test_aa1_api_seams.py`, `tests/security/test_hardening_t033.py`, `tests/admin_agent/test_aa2_admin_agent.py` |
| Tool risk ladder: `NEVER_REGISTRABLE_CLASSES == {R3_SOURCE_CHANGE, R4_FORBIDDEN}` refused UNCONDITIONALLY at `ToolRegistry` construction — no parameter can widen past it | adversarial construction tests | `tests/api/test_source_changes_v8.py::TestAdversarialAgentBoundary` |
| §14 activation gate: `AuthoritativeApplierPort` has ZERO implementations in the repo; `authoritative_applier=None` in composition; every source-change HTTP response carries `authoritative_apply: {available: False, gate: "S14_OPERATOR_GATE"}` | subclass scans at core AND app layer + per-response posture assertions | `tests/sourcechange/test_workflow_v8.py`, `tests/api/test_source_changes_v8.py` |
| Secret boundary: file bytes NEVER cross the admin surface (operation metadata `{kind, path, content_sha256, size_bytes}` only); scrub at the agent boundary | synthetic-secret sweep raw + base64 over the full lifecycle | `TestAdversarialSecretBoundary` (V8 chunk 6) |
| Anti-enumeration: absent/foreign/malformed ids answer identically | dedicated trios per surface | 20 §6 suites across admin/API tests |
| Hermetic gates: full suite runs with provider keys stripped | `env -u GSK_API_KEY -u GROQ_API_KEY python -m pytest` | 2121 + 60 at V9 |

Change control: **9 ACCEPTED ADRs** (`engineering/adr/ADR-0001..0009`);
any frozen-component/topology/dependency change is a roadmap-§6 STOP.

## 3. What was built — Vision phases V1→V8 (ledger, all pushed + remote-verified)

| Phase | Delivered | Closure | Key commits |
|---|---|---|---|
| **V1 — Repository layer** | 7 repositories + 4 catalogs over the 20-table schema; migrations 0013+0014; PRV-4 hydration/write-through design; live-Postgres verification 53/53 | R110 | `4436e13..eab5664`, `caa045a` |
| **V2 — Async durable execution** | durable transactional outbox binding; async execute path flip; worker handler; durable async chain live gate — zero core contract changes | R111 | `8478f44`, `71bce10`, `caa3783`, `50b1754`, `40acc5d` |
| **V3 — Tool execution runtime** | `ToolExecutor`: the SINGLE gated tool execution path (X²-2), admission through the pre-existing pure gate | R112 | `c3712b6`, `9394bfd` |
| **V4 — Agent loop + structured output** | R095 structured-output validator; bounded agent loop over the V3 gated runtime | R113 | `c47cfcf`, `bc08d44`, `e013095` |
| **V5 — Workspace + Projects** | workspace primitive (files/listing/manifests over `ObjectStoragePort`); durable workspace/project repositories | R114 | `d72c5fe`, `6fb121f`, `d06eae5` |
| **V6 — Events / scheduler / webhooks + SSE** | webhook delivery over the V2 chain + scheduler + SSRF validator; SSE progress surface; producer wiring (registration admission, queued + terminal event staging) | R116 | `0340787`, `a2d0168`, `7f2629e` |
| **V7 — Platform surfaces** (6 chunks) | Capability Catalog (honest closed-set from composition facts) · Exercise Surface (real probes, real evidence) · Test Scenarios → Regression Center · Context Validation Lab · Learning observability · Self-Review + Change Impact Simulator (evidence-backed proposals, NEVER auto-apply) — each as apps-layer service + admin routes + agent tools + guard pins + hermetic tests | R123 | `381d831`, `45b424d`+`3f7a796`, `e6b428b..76869bd`, `f4bb31e`+`db2af66`, `5ec2236`+`6afc9f5`, `e8e370c`+`3a58578` |
| **V8 — R3 source-change workflow** (7 chunks; **activation §14-GATED**) | ADR-0009; content-addressed snapshots + patch algebra; closed 7-state proposal lifecycle (`FAILED_VERIFICATION` has zero exits); hermetic sandbox (zero-parameter constructor) + differential verifier (verify-twice determinism); `SourceChangeWorkflow` with §14 absent-applier seam; 9 human-only admin routes; 84 dedicated tests; 12/12 acceptance criteria proven | R132 | `0f012f6..445c1c4` (8 commits) |

Test-count trajectory: 1712+23 (V-start, R108) → 2037+60 (V7 close) →
**2121+60** (V8 close = current). Per-phase acceptance evidence for V8:
`engineering/verification/V8_R3_ACCEPTANCE_EVIDENCE.md` (12 criteria,
citations machine-validated against the suite).

## 4. Governance surfaces (how the platform is operated)

- **Admin control plane**: 63 pinned admin operations (config lifecycle
  draft→validate→preview→publish→rollback; scenarios; context lab;
  learning review; self-review proposals; source-change proposals) — all
  under one `_admit` gate; non-admin = 403 across the full sweep.
- **Admin agent**: governed tool registry (R0 read / R1 probe / R2
  config-change with approval machinery / R3+R4 never-registrable);
  secrecy scrubbing (`scrub_text`: gwsecret_/AKIA/URLs/JWT/private-key)
  at the agent boundary.
- **Source changes (V8)**: propose → differential-verify (regression can
  never be approved — structural) → exact-hash approve (`ApprovalHashMismatch`
  names both hashes, persists nothing) → apply within snapshot-store space
  with recorded inverse + post-apply re-verification → rollback replays
  the recorded inverse through the SAME apply machinery. Every act audited
  with hashes/reports, never file bytes.
- **State discipline**: single mutable state file
  (`docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md`, currently R135);
  commit+push per chunk (standing R107 directive); 15 sandbox resets
  absorbed with zero completed-work loss.

## 5. Verification architecture (how truth is proven)

- `engineering/verification/check_repo.sh` — the single local/CI gate
  entry point (governance structure, state schema, pytest, mypy strict,
  ruff, import-linter, secret scan). **RESULT: PASS** at V9.
- `engineering/verification/FINAL_VALIDATION.md` — the 41 §27 17-area
  production-readiness proof (R098, MVP baseline).
- `engineering/verification/V8_R3_ACCEPTANCE_EVIDENCE.md` — V8's 12-criteria
  evidence + the activation-boundary STOP report.
- `engineering/verification/V9_FULL_VALIDATION.md` — this phase's full gate
  run (all green, post-remediation).
- Guard-pin discipline: every route/op addition is a conscious pin bump in
  three independent suites — drift is structurally loud.

## 6. Honest exclusions and open items (named, not hidden)

**Not built (by design or pending authorization):**
1. **R3 real activation** — `AuthoritativeApplierPort` has no implementation;
   activation requires the 5 credential items resolved + a new ADR for the
   write path + OS-isolation review (2 composition edits, zero workflow
   edits, when authorized). The applier's pre-authorization existence would
   itself be the §14 violation.
2. **Durable bindings for V7/V8 stores** — scenario/proposal/snapshot stores
   are in-memory per the recorded posture; repository bindings follow the
   established V1 patterns when scheduled.
3. **OS-level sandbox jailing** — the V8 sandbox is hermetic-by-construction
   (zero-parameter constructor, no os/subprocess/socket in module namespace),
   not OS-jailed; recorded in ADR-0009.
4. **Token streaming** — `execute.token_streaming` is honestly UNAVAILABLE
   in the capability catalog (V6-2 record).
5. **Deployment composition** — production wiring of subscriptions/agent
   tool surfaces is deployment territory; the seams exist and are pinned.

**Open operator items (gate any future R3 activation, per §14):**
revoke the R060 temporary PAT · rotate the R058 key · rotate the in-chat
Groq keys · Lane C deployment items (×2).

## 7. Where to look (index)

| Concern | Location |
|---|---|
| Frozen roadmap + governing interpretation | `docs/architecture/MASTER_VISION_V2_ROADMAP.md` |
| Execution state (single control point) | `docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md` |
| Authoritative doc pack (20 docs) | `docs/ai_orchestration_pack/final_docs_v3/` |
| ADRs (9 accepted) | `engineering/adr/` |
| Verification records + CI gate | `engineering/verification/` |
| Capability assessment (corroborating) | `docs/architecture/PLATFORM_CAPABILITY_ASSESSMENT.md` |
| Completion report (V9 chunk 3 deliverable, lands after this doc) | `engineering/verification/V9_FINAL_COMPLETION_REPORT.md` |
