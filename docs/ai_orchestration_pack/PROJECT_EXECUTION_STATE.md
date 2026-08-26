# PROJECT EXECUTION STATE

This file is the single project-level control point for documentation rewrite and later implementation phases.

It is not a replacement for Git. Git + verified filesystem reality remain the factual source of truth.
This file controls phase/task progression and prevents Agents from drifting, skipping, or reopening decisions.

Important proof rule:

```text
PROJECT_EXECUTION_STATE.md alone is not proof of completion.
Trusted proof = this state file + local Git commit exists + filesystem reality matches the verified task.
```

---

## STATE HEADER

```text
STATE_VERSION: 1
STATE_REVISION: R045

RESUME_TOKEN:
PROJECT|R045|PHASE_2_IMPLEMENTATION|MVP_PHASE_6_IN_PROGRESS|T_IMPL_025_VERIFIED|NEXT_T_IMPL_026_ROLE_SKILL_CONTRACTS

LAST_VERIFIED_LOCAL_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (R045 session: the R044 session recorded the Phase 6 slicing decision + authored the conversation/memory CONTRACTS (core/contracts/{conversation,memory}.py, committed by the auto-uploader) and the ports/errors modules, but was interrupted mid-write of core/memory/memory.py. THIS session applied the recovery rule — verified filesystem state first (found __init__/errors/ports present, memory.py MISSING), recreated the missing binding, authored the full test suites (tests/memory/ + tests/contract/test_conversation_memory_contract.py), reinstalled the full pinned dep set after another sandbox reset (same flat-layout editable-install breakage — deps installed directly), untracked re-tracked tool caches again, and ran ALL gates green (527 tests; check_repo.sh PASS). NOTE: the checkpoint WRITE itself was interrupted once mid-edit; the state file was verified unmodified (still R043) before this successful re-application. Trust HEAD + filesystem + green gates over old hashes.)

LAST_VERIFIED_STATE_TASK:
T-IMPL-025 — MVP Phase 6 slice 1: conversation + memory contracts (03 §3 verbatim + 13 §3 sensitivity), ConversationStorePort/MemoryStorePort, in-memory bindings with tenant isolation (20 §6 anti-enumeration), append-only history, upsert-with-evidence memory identity, 13 §9 retrieval filters (scope/recency/confidence/expiry), 13 §7 secret-like rejection at the port boundary, 13 §8 deletion — completed + VERIFIED with green gates at this checkpoint (R045).

LAST_TRUSTED_COMMIT_RULE:
Run `git rev-parse HEAD`. The current committed HEAD is the trusted progress point after verification.

WORKTREE_STATUS_AT_LAST_UPDATE:
CLEAN_AFTER_COMMIT_REQUIRED
```

---

## DOCUMENTATION BASELINE / TARGET

```text
DOCUMENTATION_BASELINE:
V2

DOCUMENTATION_TARGET:
V3

V2_STATUS:
ARCHIVED_BASELINE (read-only historical source; never authority — T-DOC-013)

V2_STRUCTURE_AUTHORITY:
NONE

V3_STATUS:
COMPLETE_AUTHORITATIVE (all 20 documents; QA gate passed at T-DOC-013)

V3_BLUEPRINT:
docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md

V3_AUTHORITY_RULE:
Each V2 document remains authoritative until the V3 index marks its successor complete and verified. The V3 index MIGRATION STATUS table is the single authority switch.

V3_OBJECTIVE:
Create the best verified documentation architecture for the project, independent of the V2 file structure.

V3_SUCCESS:
The final documentation architecture is authoritative, traceable, internally consistent, implementation-ready, recoverable, and verified. Its file count and document boundaries may differ from V2.
```

V2 documents are source material and current baseline. They are not a mandatory final structure for V3.
V3 may merge, split, rename, reorder, move, create, or remove documents when this improves execution value.
Product decisions, ADR decisions, requirements, contracts, architecture invariants, security constraints, and critical decisions must be preserved unless explicitly changed through the proper decision process.

---

## PROJECT PHASE CONTROL

```text
PROJECT:
General AI Core / AI Orchestration Platform

PROJECT_STATUS:
PHASE_2_PRODUCT_IMPLEMENTATION_IN_PROGRESS

CURRENT_PHASE:
PHASE_2_PRODUCT_IMPLEMENTATION (MVP roadmap: final_docs_v3/41 Part II)

PHASE_1_STATUS:
VERIFIED (T-DOC-013: DOCUMENTATION_PHASE_EXIT_CHECKS = PASS, recorded in docs/ai_orchestration_pack/DOC_REWRITE_REPORT.md)

PHASE_2_STATUS:
UNLOCKED (T-IMPL-000, this revision: unlock condition re-verified in a NEW session per PHASE_2_START_RULE — PHASE_1_STATUS = VERIFIED confirmed from filesystem; DOCUMENTATION_PHASE_EXIT_CHECKS = PASS per DOC_REWRITE_REPORT.md §7; FINAL_DOCUMENTATION_COMMIT_VERIFIED: T-DOC-013 checkpoint content committed at HEAD (synced as per-file commits ending fcb8aae) and worktree clean/matching)

PHASE_2_NAME:
PRODUCT_IMPLEMENTATION

PHASE_2_UNLOCK_CONDITION (MET at T-IMPL-000):
PHASE_1_STATUS = VERIFIED
+
DOCUMENTATION_PHASE_EXIT_CHECKS = PASS
+
FINAL_DOCUMENTATION_COMMIT_VERIFIED

PHASE_2_START_RULE (SATISFIED):
Do not begin product implementation in the same cycle that verifies Phase 1.
A new session must resume from this state after Phase 2 is explicitly unlocked.
(Phase 1 was verified in the prior session; this unlock ran in a new session.)

PHASE_2_GOVERNANCE:
- Roadmap authority: final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md Part II (MVP Phases 0-8, in order).
- Engineering rules: final_docs_v3/40_ENGINEERING_PROTOCOL.md.
- Build prompt: final_docs_v3/50_AGENT_EXECUTION_PROMPT.md; cognition: 51; resume: 52.
- Task IDs: T-IMPL-NNN, each mapped to a 41 Part II phase task; micro-task protocol per 41 §28; output contract per 41 §29.
- Scope-control recording target: final_docs_v3/60_DECISION_LOG.md (append-only).
- Significant architecture choices (e.g. language/stack) require an ADR; stack selection additionally requires explicit user approval before Phase 1 (Contracts) code is written.
```

---

## CURRENT TASK CONTROL

```text
CURRENT_WORKSTREAM:
PRODUCT_IMPLEMENTATION_MVP

CURRENT_TASK:
DONE — T-IMPL-017 implementation part (ADR-0004 observability wiring) + MVP Phase 3 exit evaluation. Phase 3 is CLOSED. The next task control lives in PROGRESS CHECKPOINT below.

TASK_OBJECTIVE:
PostgreSQL migrations groundwork (41 §42, 40 §5.1): write ADR-0002 selecting the persistence toolchain BEFORE any DB dependency lands. Proposal: SQLAlchemy 2.x async + asyncpg + Alembic + pgvector, all confined to infrastructure/ with a new import-linter contract keeping core free of persistence imports. Dependency pins, alembic environment under infrastructure/db/, and the first identity/tenancy migration follow ONLY after the ADR is ACCEPTED by the operator.

TASK_STATUS:
ADR-0002 IMPLEMENTED_AND_VERIFIED; ADR-0003 IMPLEMENTED_AND_VERIFIED; ADR-0004 IMPLEMENTED_AND_VERIFIED (T-IMPL-017, commit 6ba586b). MVP_PHASE_3_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED (R035).

ALLOWED_SCOPE (part 1):
- create engineering/adr/ADR-0002-persistence-toolchain.md (full §8.1 format)
- register it in engineering/adr/README.md index
- update this state file at the verified checkpoint

FORBIDDEN_SCOPE:
- adding sqlalchemy/alembic/asyncpg/pgvector to pyproject.toml before ADR-0002 is ACCEPTED
- any migration code, any real DB/network binding, any secret material (20 §5)

TASK_COMPLETION_CRITERIA (part 1):
- ADR-0002 has all §8.1 sections (Context/Alternatives/Decision/Reason/Consequences/Status), >=2 alternatives analyzed, STATUS: PROPOSED, explicit no-dependency-until-accepted gate stated inside the ADR.
- ADR index updated. check_repo.sh => RESULT: PASS. Focused local commit; state updated.

VERIFICATION_EVIDENCE (T-IMPL-017 + Phase 3 exit, R035):
- apps/observability/ = config.py (ObservabilityConfig: service resource attrs, exporter mode closed set console|none — OTLP intentionally NOT a valid value until a collector exists per ADR-0004; sampler thresholds), sampler.py (AdaptiveSampler per 40 §5.3: normal→reduced ratio, error/slow/high-value/debug→ALWAYS_ON, composed under ParentBased(root) so child spans follow the parent decision), logs.py (structlog JSON pipeline; secret-scrubbing processor at the PIPELINE HEAD per 20 §5 — recursive over dicts/lists, key-pattern + value-pattern based; trace_id/span_id correlation processor injecting active span context), setup.py (composition root: TracerProvider wiring ONLY here; console/no-op exporters; idempotent init guard).
- Dependencies pinned in the SAME commit as the 7th import-linter contract ("Core must not import the telemetry stack": core/* forbidden from opentelemetry*, structlog): opentelemetry-api>=1.25, opentelemetry-sdk>=1.25, structlog>=24.
- tests/observability/test_observability_setup.py: 18 hermetic tests — sampler policy matrix (normal sampled at reduced ratio, error/slow/high-value/debug always sampled, parent decision honored), scrubbing (nested dicts/lists, key patterns, value patterns, pipeline-head position asserted), correlation (trace_id/span_id present inside span, absent outside), config validation (OTLP rejected), boundary (core imports clean of telemetry).
- Audit port untouched: telemetry references audit ids only (ADR-0004 consequence honored).
- Gates at R035: 269 tests PASS; mypy --strict (core/) clean; ruff clean; ALL 7 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- MVP PHASE 3 EXIT EVALUATION (41 §42) — all six deliverables verified from filesystem: (1) PostgreSQL migrations: infrastructure/db/{alembic.ini,engine.py,tables.py,migrations/versions/0001_identity_tenancy.py} + parity gates in tests/db/. (2) Redis setup: core/runtime/{ports,errors,memory}.py + infrastructure/redis/binding.py + hermetic gates in tests/runtime/. (3) Object storage abstraction: core/storage/{ports,errors,memory}.py. (4) Secret manager abstraction: core/secrets/{ports,errors,memory}.py (opaque refs only, no secret material). (5) Basic audit logs: core/audit/{ports,errors,memory}.py. (6) OpenTelemetry setup: apps/observability/ (this task). => MVP_PHASE_3_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED.
- Session maintenance (R035): sandbox reset wiped dev tools AGAIN — reinstalled all pinned deps before gates; auto-uploader had re-tracked tool caches — untracked again (3d5383f).

VERIFICATION_EVIDENCE (R034 reconciliation — filesystem + gates, per recovery rule; the executing session's checkpoint was lost to an interruption):
- ADR-0002/0003/0004 all read STATUS: ACCEPTED with the operator decision quoted verbatim ("ADR-000N = ACCEPTED", 2026-08-25); ADR index rows updated to ACCEPTED. All three are append-only from acceptance.
- ADR-0002 implementation (T-IMPL-015 part 2) present and verified: deps pinned (sqlalchemy>=2.0, alembic>=1.13, asyncpg>=0.29, pgvector>=0.2) WITH the 5th import-linter contract ("Core must not import the persistence toolchain"); infrastructure/db/ = alembic.ini + engine.py + tables.py (identity contracts mapped field-for-field) + migrations/versions/0001_identity_tenancy.py (hand-written, full downgrade per 40 §8.2); hermetic gates in tests/db/test_schema_contract_parity.py (contract/schema parity, offline postgresql DDL compile, migration/metadata parity incl. downgrade reversal).
- ADR-0003 implementation (T-IMPL-016 part 2) present and verified: redis>=5 pinned WITH the 6th import-linter contract ("Core must not import the Redis client"); core/runtime/{ports,errors,memory}.py define Queue/Lease/Cache/RateLimiter ports + in-memory fakes; infrastructure/redis/binding.py implements RedisQueue (Streams consumer groups + DLQ stream), RedisLeaseManager (SET NX PX + INCR fencing + Lua compare-and-delete release), RedisCache (tenant-scoped, PX TTL), RedisRateLimiter (fixed window); hermetic gates in tests/runtime/test_runtime_ports.py run against fakes.
- Full suite green; check_repo.sh RESULT: PASS (all 6 import-linter contracts kept, secret scan clean).
- EXTRA (sandbox-only, not a repo artifact): the redis binding was smoke-tested against a real throwaway Redis server — queue publish/consume/ack/claim-stale/dead-letter, lease acquire/renew/release/fencing-monotonicity/TTL-expiry, cache tenant-isolation/TTL, rate-limit window — ALL PASS. Script intentionally not in the repo (hermetic gates keep fakes; ADR-0003 Testing note).
- Session maintenance (R034): sandbox reset wiped dev tools again — reinstalled all pinned deps; tool caches the auto-uploader had re-tracked were untracked again (36bc126).

VERIFICATION_EVIDENCE (T-IMPL-016/017 ADR parts, earlier session, R033):
- engineering/adr/ADR-0003-redis-binding.md: PROPOSED. 3 alternatives (A: redis-py asyncio under core ports — chosen; B: task frameworks arq/taskiq/celery — rejected: impose competing job/retry semantics vs 40 §4's outbox/retry-taxonomy/DLQ/leases-with-fencing design; C: aioredis deprecated / valkey-glide immature). Decision: infrastructure/redis/ implements queue (Streams consumer groups), lock/lease (SET NX PX + fencing token + Lua release), cache, rate-limit ports; DLQ terminal record in PostgreSQL (Redis never truth, 40 §5.1); 6th import-linter contract lands with the dep; hermetic gates keep fakes.
- engineering/adr/ADR-0004-observability-setup.md: PROPOSED. 3 alternatives (A: opentelemetry-python API/SDK split + OTLP + structlog — chosen; B: vendor SDK first — rejected: violates 40 §5.3 standard=OTel; C: DIY-then-retrofit — rejected: retrofit cost on execution/provider tracing). Decision: SDK wiring ONLY at apps/ composition root; dev/test = console/no-op exporters (hermetic); custom AdaptiveSampler per 40 §5.3; structlog JSON w/ trace-id correlation + secret-scrubbing processor (20 §5); audit port (T-IMPL-014) untouched — telemetry references audit ids only; core must not import opentelemetry/structlog (contract lands with dep).
- engineering/adr/README.md index rows added for both. check_repo.sh RESULT: PASS.
- Session maintenance: sandbox reset had wiped dev tools — reinstalled (pydantic/pytest/mypy/ruff/import-linter); tracked tool caches untracked (ced1e20), .gitignore already covered them.

VERIFICATION_EVIDENCE (T-IMPL-015 part 1, this session):
- engineering/adr/ADR-0002-persistence-toolchain.md: 3 alternatives (A: SQLAlchemy 2.x async + asyncpg + Alembic + pgvector — chosen; B: raw asyncpg + hand-rolled migration runner — rejected: owning a migration runner on the source of truth, stringly-typed rows vs mypy --strict; C: SQLModel/Tortoise/Piccolo — rejected: SQLModel pushes table defs into contracts, breaking the core-purity import-linter contract; others lack Alembic-grade migrations). Decision confines ALL persistence to infrastructure/, mandates a 5th import-linter contract (core must not import sqlalchemy/alembic/asyncpg) landing WITH the dependency, requires downgrade paths per 40 §8.2, treats autogenerate output as reviewed draft. Consistent with the ACCEPTED ADR-0001 stack sketch (confirmation-with-analysis, not reversal).
- engineering/adr/README.md index row added (PROPOSED; no DB dependency until ACCEPTED).
- check_repo.sh RESULT: PASS after edits.

MVP_PHASE_2_EXIT (recorded R028, unchanged): MVP_PHASE_2_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED — full 41 §41 evaluation preserved in git history at the R028 checkpoint commit (d88a876 pre-rewrite).

MVP_PHASE_3_EXIT (recorded R035): MVP_PHASE_3_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED — full 41 §42 evaluation in the R035 evidence block above.
```

---

## PROGRESS CHECKPOINT

```text
LAST_VERIFIED_TASK:
T-IMPL-025 — conversation + memory stores: contracts, ports, in-memory bindings, hermetic tests (MVP Phase 6 slice 1, R045)

LAST_VERIFIED_TASK_COMMIT:
VERIFY_WITH_GIT_REV_PARSE_HEAD (auto-uploader history rewrites make stored hashes unreliable; content verified against filesystem + green gates at R045)

T_IMPL_025_VERIFICATION_EVIDENCE (R045):
- core/contracts/conversation.py (86 lines, authored R044, committed): ConversationStatus (active|archived) + MessageRole (user|assistant|system|tool) closed sets 03 §3 verbatim; Conversation (id/tenant_id/user_id/project_id?/title/status) + Message (id/conversation_id/role/content/attachments/created_at) field-for-field. Recorded decisions: Message.role is the CHAT-TURN role, distinct from the 03 §6 Role entity (name collision comes from the spec); content max 200k chars with structured payloads on attachments (JSON objects, 03 §3); no secret-bearing field on any contract (20 §5).
- core/contracts/memory.py (105 lines, authored R044, committed): MemoryScope (global|tenant|workspace|project|conversation|role) 03 §3 verbatim + MemorySensitivity (low|medium|high) from 13 §3; MemoryItem = 03 §3 entity PLUS 13 §3 sensitivity (field reconciliation recorded in the docstring — both authorities honored, nothing dropped/invented); confidence bounded [0,1]; user_id=None means tenant-shared. SCOPE_PRIORITY encodes 13 §4 verbatim (Conversation > Project > Workspace > Tenant > Global) with TWO recorded decisions: ROLE is absent from the conflict chain (role-scoped memory selects by role relevance 13 §9, never scope comparison) and the 13 §4 "User" rank is encoded via user_id ownership, not a scope value (03 §3 has no user scope).
- core/memory/ports.py (127 lines): ConversationStorePort + MemoryStorePort Protocols — tenant_id explicit on EVERY method (20 §6, the core/storage pattern verbatim). Recorded port decisions: history is APPEND-ONLY in MVP (no edit/delete — audit-grade record of what the model saw); get_history(limit) keeps the NEWEST tail (context windows want the tail); memory writes are UPSERTS keyed by (tenant, user, scope, key) with evidence_count accumulation (13 §6 needs the count); secret-like keys/values REJECTED at this boundary (13 §7, the R044 slicing decision duty (e)); NO semantic-similarity retrieval on the port — MVP retrieval = scope/recency/confidence per R044 boundary (c), pgvector binds later behind the same surface.
- core/memory/errors.py (61 lines): MemoryStoreError base (renamed from MemoryError — Python builtin shadow caught in-session) + ConversationNotFound / MemoryItemNotFound (BOTH deliberately raised for foreign-tenant probes — anti-enumeration, 20 §6) + EmptyMessage + SecretLikeMemoryRejected (carries the matched INDICATOR only, never the offending value — no secrets in logs, 20 §5).
- core/memory/memory.py (232 lines): InMemoryConversationStore (physical keying (tenant_id, id); duplicate-create rejected; set_status active|archived; list newest-first per user; append-only message log; EmptyMessage when neither content nor attachments; attachment-only tool turns allowed) + InMemoryMemoryStore (upsert keeps original item id, bumps evidence_count, refreshes value/confidence/last_seen; query filters tenant + user-visibility (shared user_id=None OR the caller's own — NEVER another user's, 13 §7) + scope + key + min_confidence + expiry (excluded unless include_expired), ordered most-recently-seen first (13 §9 recency); delete frees the logical slot so re-upsert starts fresh at evidence_count=1). Secret screening: key-indicator list (password/secret/api_key/access_token/private_key/credential/...) + value patterns (Bearer, PEM private key, AKIA, JWT-like, sk-/ghp-/xoxb- opaque tokens) — a boundary GUARD, not a scanner.
- tests/contract/test_conversation_memory_contract.py: 20 hermetic contract tests — closed sets verbatim (incl. SCOPE_PRIORITY chain + ROLE absence), 13 §3 example validates (preferred_language="ar", 0.92, low default), structured JSON values, unknown fields/values rejected (deny-by-default), confidence/evidence bounds, no secret-bearing fields (20 §5), frozen instances.
- tests/memory/test_memory_stores.py: 36 hermetic tests — conversation lifecycle (create/get/duplicate-rejected/archive/list-newest-first-per-user), append-only history (ordering, tail-limit, missing-conversation raise, empty-message rejected, attachment-only allowed), tenant isolation (cross-tenant get/history/append/list — same NotFound as absent, 20 §6), memory upsert identity ((tenant,user,scope,key) logical key, evidence accumulation, id stability, distinct users distinct identities), retrieval filters (recency ordering, scope+key, min_confidence, expiry default-exclusion, tenant-shared visible + other-user invisible per 13 §7, cross-tenant empty), deletion (13 §8, logical-slot freeing, cross-tenant delete anti-enumeration), secret rejection (5 key indicators + 5 value patterns parametrized; error message carries indicator NOT the value; benign preference accepted).
- 41 §49 NOT-CLAIMED rule intact: stores are in-memory; durable persistence (ADR-0002 toolchain) binds behind the same ports in a later phase; context composer + roles/skills are LATER slices (T-IMPL-026/027), not claimed here.
- Gates at R045: 527 tests PASS (56 new: 20 contract + 36 store; up from 471 at R043); mypy --strict (core/) clean across 56 files; ruff check clean; ALL 8 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R045): recovery-first session — verified interrupted R044 artifacts from filesystem BEFORE writing anything (memory.py was the only missing piece); sandbox reset had wiped all deps again (reinstalled pinned set directly; editable install still broken by flat-layout); auto-uploader had re-tracked tool caches again (untracked with git rm -r --cached); one ruff I001 auto-fix + format normalization of the new files only.

T_IMPL_024_VERIFICATION_EVIDENCE (R043):
- core/usage/ports.py (79 lines): UsageAccountingPort Protocol — the reserve-BEFORE/settle-AFTER seam (03 §7 UsageLedger lifecycle; 41 §43 "units estimate/reserve/settle"; same port+in-memory-fake posture as core/storage, core/secrets, core/runtime — durable billing binds at the composition root in a later phase, no payments integration in MVP). Lifecycle contract recorded in the module docstring: (1) reserve(tenant_id, execution_id, units) holds units against the tenant task-unit budget (21 §5) BEFORE any provider work — insufficient budget or missing entitlement raises BEFORE execution starts; (2) exactly ONE resolution per reservation — settle (success, finalize from ACTUAL usage) / refund (nothing consumed, release full hold) / fail (failed execution, record failed settlement with policy-decided units, may be 0); (3) double resolution raises ReservationAlreadyResolved — ledger entries are append-once accounting facts. Settled units MAY exceed the reservation: overage is charged honestly, never clamped (hiding real consumption would corrupt the 10 §8 usage summary).
- core/usage/memory.py (214 lines): InMemoryUsageAccounting — hermetic MVP binding + test double. Budget semantics recorded once: used = resolved consumption (settled + failed-settlement units) PLUS active holds (a reservation consumes budget the moment it is granted, so parallel requests cannot jointly overdraw); remaining = limit - used floored at 0 for the summary view. Deny-by-default is an EXPLICIT decision per the task note: tenants get a budget ONLY via configure_tenant (the 21 §5 plan seam); reserving for an unconfigured tenant raises EntitlementNotConfigured — never a silent default allowance. summary() returns the 10 §8 UsageSummary (task_units limit/used/remaining).
- core/usage/errors.py (80 lines): UsageAccountingError base + EntitlementNotConfigured + BudgetExceeded (carries requested/remaining as data) + ReservationNotFound + ReservationAlreadyResolved. core/usage/__init__.py exports the surface.
- core/execution/service.py wiring (599 lines, up from ~540): optional UsageAccountingPort seam + units_per_stage MVP metric (units reserved per stage, settled per SUCCEEDED stage). reserve(units_per_stage × stage-count) runs BEFORE any provider work — a denied reservation raises before any adapter is called (20 §4 posture: work the tenant cannot pay for never reaches a provider). Exactly-once resolution AFTER: settle on success / fail on failed execution (failed settlement charges only SUCCEEDED-stage units; raw provider-reported usage rides along as modality_costs data per 03 §7); a BaseException mid-execution resolves the reservation as failed with 0 settled units BEFORE the fault propagates — a reservation must never leak. Unbound (usage=None) keeps pre-T-IMPL-024 behavior verbatim: cost_snapshot.settlement = pending_usage_service and nothing is charged (the R041 marker honored exactly as recorded). ExecutionReport gained usage: UsageLedger | None; cost_snapshot.settlement carries the resolved ledger facts when accounting is bound.
- apps/api/app.py wiring (354 lines, up from 312): optional UsageAccountingPort injection at create_app; BudgetExceeded/EntitlementNotConfigured map to the 10 §9 entitlement_exceeded code (HTTP 403) with requested/remaining as details — denial happens BEFORE provider work and the test asserts zero adapter calls. Successful responses surface the settled ledger as the 10 §3 usage block (units_reserved/units_settled/details.status); a service without accounting keeps usage absent — never faked. Failure keeps the unified error envelope (no usage key) while the ledger is still resolved and the hold released.
- tests/usage/test_usage_accounting.py: 29 hermetic tests (317 lines) — reservation (grants hold, consumes budget immediately, multiple holds accumulate, exact-remaining boundary allowed), deny-by-default (unconfigured tenant => EntitlementNotConfigured; BudgetExceeded carries requested/remaining; denied reservation leaves no ledger entry), settlement (actual replaces hold incl. under/over-reservation overage charged honestly, modality_costs recorded), refund (full release), fail (policy units charged, 0 allowed), exactly-once (all double-resolution pairs raise ReservationAlreadyResolved; unknown execution => ReservationNotFound), summary (limit/used/remaining arithmetic, floor-at-0, per-tenant isolation), ledger record shape (03 §7 fields, status enum verbatim, tenant/execution ids carried).
- tests/execution/test_execution_service.py: +7 usage-wiring tests (39 total) — reserve-before-provider-work ordering (denied budget => provider NEVER called), single success settles stage units, pipeline settles per-succeeded-stage, failed execution resolves via fail with only-succeeded-stage units, crash resolves reservation before propagating, usage=None keeps pending_usage_service verbatim, provider raw usage lands in modality_costs.
- tests/api/test_execute_api.py: +5 usage tests (26 total, 550 lines) — success surfaces the settled 10 §3 usage block; empty budget => entitlement_exceeded 403 with requested/remaining details and ZERO adapter requests; bound-but-unconfigured tenant denied (deny-by-default); budget depletes across requests then denies (third request never reaches the provider); failed execution keeps the unified envelope with no usage key while the hold is released (summary remaining restored).
- 41 §49 NOT-CLAIMED rule intact: accounting is in-memory; real billing/payments stay out of MVP scope per 41 §43; end-to-end AI execution stays PENDING_REAL_PROVIDERS.
- Gates at R043: 471 tests PASS (29 usage + 26 api + 39 execution; up from 430 at R042); mypy --strict (core/) clean across 50 files; ruff check clean; ALL 8 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R043): the executing session was interrupted at the final gate-confirmation step; THIS session re-verified everything from filesystem, reinstalled the full pinned dep set after another sandbox reset (editable install still broken by setuptools flat-layout — deps installed directly, same pins), untracked 49 re-tracked tool-cache files, fixed one ruff I001 import-order finding in apps/api/app.py (auto-fix, cosmetic), re-ran all gates green, then recorded this evidence.

MVP_PHASE_5_EXIT_EVALUATION (41 §44, R043) — all six deliverables verified from filesystem:
(1) POST /v1/execute: apps/api/app.py:185 (T-IMPL-023; full contract validation, idempotency, unified errors). (2) router simple scoring: core/routing/router.py SimpleScoringRouter (T-IMPL-021; deterministic weighted scoring, explainable exclusions, fallback scopes). (3) single execution: core/execution/service.py execute_single (T-IMPL-022; bounded retries, error-aware failover). (4) pipeline execution: execute_pipeline (T-IMPL-022; sequential stages, output chaining, partial-failure honesty). (5) execution status endpoint: GET /v1/executions/{id} apps/api/app.py:311 (T-IMPL-023; stage progress + result/error detail). (6) usage reservation/settlement: core/usage/ + ExecutionService/API wiring (T-IMPL-024, this checkpoint).
=> MVP_PHASE_5_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED (scaffold-state qualifications recorded: all execution runs against fakes per 41 §49; real providers + durable billing bind in later phases).

T_IMPL_023_VERIFICATION_EVIDENCE (R042):
- apps/api/app.py (312 lines): create_app() — pure composition of already-verified core services: ExecuteRequest (10 §2) → SimpleScoringRouter (T-IMPL-021) → ExecutionService (T-IMPL-022) → ExecuteSyncResponse / unified error (10 §3/§9). FastAPI lives ONLY in apps/ per ADR-0001; the dependency pin (fastapi>=0.111, httpx>=0.27 dev) landed WITH the 8th import-linter contract ("Core and providers must not import the web framework": core/*, providers/* forbidden from fastapi/starlette). Injected seams: router, execution_service, store, Principal (fixed dev tenant/user — the auth phase plugs in here without touching handlers). Loud scope rejections (never silent degradation): execution_policy.async=true and stream=true => validation_error (durable async runtime / streaming are later phases per 12 §9 / 10 §11, not faked); non-UUID conversation_id => validation_error. Idempotency (10 §10): (tenant_id, Idempotency-Key) index replays the SAME execution instead of creating a duplicate. request_hash = sha256 of canonical JSON dump (03 §5). Routing failures map explainably: UnsupportedPolicyType => validation_error 422; NoEligibleCandidates => model_unavailable 503 CARRYING the router's ExclusionRecords in details (11 §14 fail-clearly); FallbackNotConfigured => model_unavailable. Failed executions return the unified envelope with the execution id so GET stays usable for diagnosis. Global exception handler => internal_error 500 generic message (20 §4: internals never leak). GET /v1/executions/{id}: full ExecutionStatusResponse (10 §5) with stage progress, result on success, unified error detail on failure; malformed id => 422; unknown id => 404.
- apps/api/errors.py (109 lines): the ONLY mapping from internal failure shapes to the unified {"error": {...}} envelope (10 §9 closed 11-code set carried verbatim from core.contracts.errors). HTTP_STATUS_BY_CODE covers all 11 codes. Provider error categories map to MORE SPECIFIC codes (rate_limited/quota=>entitlement_exceeded/model_unavailable/provider_unavailable), else execution_failed 502. Mapping DECISION recorded in the module docstring: the closed set has no not_found code — unknown execution id = validation_error body with HTTP 404 (honest closest category, not a contract change). Provider-internal raw payloads never cross into responses.
- apps/api/store.py (43 lines): InMemoryExecutionStore + ExecutionNotFound — process-local ExecutionReport store keyed by execution id (slice decision: durable persistence is an infrastructure concern already covered by ports/ADR-0002; the composition root swaps in a repository-backed store without handler changes).
- tests/api/test_execute_api.py: 21 hermetic tests (473 lines) via FastAPI TestClient/ASGI transport over the T-IMPL-022 FakeAdapter pattern — NO network, NO real providers: sync success shape (+non-content output serialized verbatim, format hint echoed), opaque credential_ref + bound model name reach the adapter (and the credential never appears in any response body), contract validation (missing ask, unknown fields rejected, bad conversation_id, valid conversation_id passthrough), loud rejections (async, streaming, unsupported policy types), router failure mapping (no-eligible-candidates carries exclusion records), provider failure mapping (category=>specific code; generic=>execution_failed; raw provider internals asserted ABSENT), idempotency (same key replays same execution id; different keys distinct; no key never replays), status endpoint (succeeded, failed-with-unified-error, unknown=404, malformed=422).
- 41 §49 NOT-CLAIMED rule intact: the API is tested against fakes; end-to-end AI execution stays PENDING_REAL_PROVIDERS.
- Gates at R042: 430 tests PASS (21 api; up from 409 at R041); mypy --strict (core/) clean across 45 files; ruff check clean; ALL 8 import-linter contracts kept (new: web-framework contract); secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R042): the executing session was interrupted at the checkpoint step; THIS session re-verified everything from filesystem, reinstalled the full pinned dep set after another sandbox reset, untracked 49 re-tracked tool-cache files (gitignore already covers them), re-ran all gates green, then recorded this evidence.

T_IMPL_022_VERIFICATION_EVIDENCE (R041):
- core/execution/service.py (~540 lines): ExecutionService — consumes RoutingDecisions and drives the ProviderAdapter port (T-IMPL-018), the ONLY provider seam. Router-decides/Execution-executes boundary honored (02 invariant 5): candidate traversal is STRICTLY Router order (selected then fallback_candidates), never re-scored. execute_single (03 §5 strategy=single) + execute_pipeline (strategy=pipeline; sequential stages, each with ITS OWN RoutingDecision; stage N>1 receives the previous stage's output under PREVIOUS_OUTPUT_KEY="previous_output"; a failed stage fails the execution and marks remaining stages SKIPPED — partial failure recorded, never hidden). Error-aware failure routing (40 §4.6/§4.7): retryable errors get a BOUNDED same-candidate retry budget (max_retries_per_candidate, default 1; retry_after_ms honored via injected sleeper); non-retryable errors fail over to the next candidate; REQUEST-INDICTING categories (bad_request, content_rejected) fail the node immediately with NO retry and NO failover — malformed requests and safety rejections are never shopped across providers. Boundary defense: any exception RAISED by an adapter is passed through that adapter's normalize_error (30 §14) and becomes error DATA, never re-raised; a failed response missing its normalized error is normalized as a contract breach. Records: Execution (status trail QUEUED→RUNNING→SUCCEEDED/FAILED, request_hash/idempotency_key/conversation_id passthrough, completed_at, cost_snapshot carrying RAW provider usage per node + settlement=pending_usage_service — reservation/settlement explicitly NOT claimed, it is the T-IMPL-024 slice) + ExecutionNode per stage (input_ref/output_ref, retry_count=attempts-1, LAST normalized error preserved on failure) + AttemptRecord trail (candidate + attempt number + error + latency) for full traversal explainability. Composition fail-fast: EVERY candidate of EVERY stage validated (adapter bound, credential ref configured, binding present) BEFORE any provider work — AdapterNotBound / CredentialNotConfigured / BindingNotFound(T-IMPL-019) raise loudly; InvalidPipeline for empty stage list or duplicate node_keys. Credentials stay opaque references (20 §5): the ref crosses ONLY on ProviderGenerateRequest; no execution/node record carries it. Injected seams (adapters map, credential_refs map, BindingRegistry, sleeper, id_factory, clock) keep it hermetic — no I/O of its own.
- core/execution/errors.py: ExecutionServiceError base + AdapterNotBound + CredentialNotConfigured + InvalidPipeline. core/execution/__init__.py exports the service surface incl. PipelineStage/AttemptRecord/NodeReport/ExecutionReport.
- tests/execution/test_execution_service.py: 32 hermetic tests (~640 lines) against a scripted FakeAdapter (replays ProviderError / raised-Exception / success-dict outcomes) — the 12 §12 execution items applicable to this in-process slice: single success (+status history, node record fields, metadata passthrough, cost snapshot), node retry (retryable retries same candidate then succeeds; budget BOUNDED — never infinite; retry_after_ms honored; zero budget fails over immediately), pipeline success (stage order, output chaining, first stage has no previous_output key, per-node usage aggregation), partial failure with fallback (failover in Router order across 3 providers; all-fail preserves LAST error; non-retryable fails over without retry; bad_request/content_rejected never shopped; pipeline mid-failure marks later stages SKIPPED and never calls their providers; stage-level fallback recovery continues the pipeline). Plus: raised-exception normalization + contract-breach normalization, composition fail-fast for all three error types (validated BEFORE any provider work, incl. all-stages-before-any-runs), InvalidPipeline (empty/duplicate keys), negative retry budget rejected, core.execution boundary guard, credential-ref never appears in any dumped record.
- 41 §49 NOT-CLAIMED rule intact: everything runs against fakes; end-to-end AI execution stays PENDING_REAL_PROVIDERS.
- Gates at R041: 409 tests PASS (32 execution; up from 377 at R040); mypy --strict (core/) clean; ruff check clean; ALL 7 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R041): sandbox reset wiped ALL deps again (even opentelemetry/sqlalchemy runtime deps) — reinstalled the full pinned set before gates; auto-uploader had re-tracked .mypy_cache/.import_linter_cache/.pytest_cache/.ruff_cache — untracked again (gitignore already covers them). One ruff I001 import-order fix in the new test file, auto-fixed. A second reset mid-commit reverted the state-file edit; re-applied and re-verified.

T_IMPL_021_VERIFICATION_EVIDENCE (R040):
- core/contracts/routing.py (143 lines): TaskAnalysis (11 §3 field-for-field; complexity/risk_level open bounded strings — doc declares no closed set), ScoringWeights (11 §6 initial values verbatim as defaults: 0.35/0.20/0.15/0.15/0.10/0.05; versioned — weights are policy-driven), CandidateScore (11 §7: model/provider/account ids + score + human-readable reasons/risks; account_id nullable — account selection is a later pipeline stage, accounts optional per 30 §10.1), ExclusionRecord (explainable deny paths: which filter excluded which candidate), RoutingRequest (operation enum + capability/modality lists + optional policy/task_analysis/context hint/weights; explicit lists win over task_analysis, empty lists derive from it per 11 §2), RoutingDecision (selected + full ranked list + fallback_candidates + excluded + policy_snapshot per 11 §16 + fallback_policy + weights + decided_at). All exported from core.contracts.
- core/routing/router.py (457 lines): SimpleScoringRouter — deterministic, explainable selection. Scope = AUTO / TIER / EXPLICIT_MODEL policies (10 §13); EXPLICIT_MODELS + AGENT_NODE_MAPPING are execution-graph-slice concerns and are REJECTED loudly (UnsupportedPolicyType), never guessed. Candidate sourcing EXCLUSIVELY from T-IMPL-019 registries: ProviderRegistry.routing_candidates excludes templates/non-functional/undeclared-operation by construction (31 §10), only ACTIVE models (03 §4), per-binding availability facts (UNAVAILABLE excluded; DEGRADED acceptable-but-recorded-as-risk per 11 §5/§7). Hard filters deny-by-default: declared-capability only (11 §5 + 30 §7 unknown=ineligible), modality, context-window vs hint. Explicit-model honors user choice over Router preference but never over availability/eligibility (11 §13); explicit provider_id narrows bindings (11 §14). Scoring = configurable weighted sum (11 §6) with unknown-score posture: undeclared component scores contribute 0.0 and surface as risks (never invented); deterministic tie-break by model/provider key. Fallback (11 §8/§14): allow_fallback=false => scope NONE + fail-clearly behavior; explicit-model default = same_model_different_provider; same_tier / lower_cost_same_capability / max_escalation / admin_defined_chain implemented (chain requires admin configuration or FallbackNotConfigured). Filters deferred to their own phases (never faked): tenant/plan entitlement, rate-limit budget, data boundary, tool permissions — recorded in module docstring; pipeline ordered so they slot in without contract changes.
- core/routing/errors.py (33 lines): RoutingError, NoEligibleCandidates (carries ExclusionRecord list — diagnosable without re-running), FallbackNotConfigured. UnsupportedPolicyType lives beside the router.
- core/contracts/model_policy.py gained FallbackScope usage for router fallback resolution (contract was already present from Phase 2).
- tests/routing/test_router_scoring.py: 38 hermetic tests (658 lines) — 11 §11 required set (auto selection, explicit model selection, same-model-provider fallback, same-tier fallback, provider unavailable, unknown capability denied) plus: deterministic ties, default-policy=auto snapshotted, auto tier-hint boost, tier hard-filter + empty-tier fail-clearly, explicit unknown-model / provider narrowing / unavailable-with-fallback-disabled, modality + context-window + inactive-model + template + unbound-model exclusions, degraded-as-risk, undeclared-scores-as-risk with exact score arithmetic, all five fallback scopes incl. admin chain ordering, §6 default weights verbatim, custom weights change ranking + version recorded, weighted-sum arithmetic, reasons/exclusions explainability, frozen policy snapshot, out-of-slice policy rejection (both types), registry non-mutation, core.routing boundary guard, operation-enum + UUID typing.
- Completion work done in THIS session: authored the full test suite (was missing after interruption); implemented the two missing RoutingRequest-derivation helpers on the router (explicit lists win, task_analysis fallback — exactly the documented contract semantics); typed-locals fix for mypy strict in _resolve_fallback_scope. No contract or behavior invention beyond the documented spec anchors.
- Gates at R040: 377 tests PASS (38 routing; up from 339 at R039); mypy --strict (core/) clean across 42 files; ruff check clean; ALL 7 import-linter contracts kept (incl. core-must-not-import-providers/infra); secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R040): sandbox reset wiped dev tools AGAIN — reinstalled all pinned deps (runtime + dev) before gates. Pre-existing cosmetic note unchanged: ruff format --check would reformat files repo-wide; the ENFORCED gate is ruff check (lint), which is clean.

T_IMPL_020_VERIFICATION_EVIDENCE (R039):
- providers/templates/: 12 disabled diverse template packages covering the 31 §6 categories in order (chat_text, reasoning, coding, image_generation, audio_tts, audio_stt, vision, multimodal, embeddings, rerank, moderation_safety, provider_agent). Each exposes MANIFEST + build_adapter(); every manifest carries the FULL 31 §7 marker set (status=template_disabled, is_template=true, is_functional=false, real_provider_required=true, auth.types=[] verbatim, models.discovery=not_implemented, verbatim scaffold notes). Auth-shape diversity per 31 §12 recorded as INTENT-ONLY in notes (7 api_key, 2 oauth, 1 session_cookie, 2 no-auth local/internal), never functional auth. provider_agent template carries the 31 §8 agent_module + security blocks (agent posture) verbatim.
- providers/common/manifest_builder.py (84 lines): single builder guaranteeing the marker set on every template; unsupported modules marked not_implemented per 31 §12 (never TODOs implying mandatory work).
- providers/common/template_adapter.py (125 lines): TemplateProviderAdapter — structurally satisfies the ProviderAdapter port (T-IMPL-018) but is NON-FUNCTIONAL: generate/discovery ALWAYS raise (normalized to unsupported-capability taxonomy), credential check reports CredentialStatus.INVALID (canonical import from core.contracts.domain), health_check returns UNAVAILABLE for both scopes; constructor REJECTS non-template manifests (defense against accidental real-provider reuse).
- providers/_pending_real_providers.md: NOT-CLAIMED ledger per 31 §9 / 41 §49 — records that end-to-end AI execution is explicitly NOT-CLAIMED and lists the activation requirements for any future real provider.
- tests/providers/test_scaffold_templates.py: 21 hermetic tests (354 lines) = the 31 §11 suite — every template loads + validates against core contract schema, category coverage in order, full marker-set matrix, no secret material scan, loadable-but-never-routable, execution-eligibility exclusion, generate-raises for every declared operation, discovery-raises + credential-invalid, taxonomy normalization, health UNAVAILABLE (adapter + aggregation regardless of signals), capability diversity, auth-shape diversity intent-only, account-pool diversity not forced, 31 §8 agent posture, structural port satisfaction, non-template-manifest rejection, core-does-not-import-providers boundary, ledger content, builder marker invariance.
- Gates at R039: 339 tests PASS (21 scaffold; up from 314 at R038: +21 scaffold suite, +4 from adapter-port test fixes in the same slice); mypy --strict (core/) clean; ruff check clean; ALL 7 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R039): sandbox reset wiped dev tools AGAIN — reinstalled all pinned deps before gates. Pre-existing cosmetic note unchanged: ruff format --check would reformat 17 files repo-wide; the ENFORCED gate is ruff check (lint), which is clean.

MVP_PHASE_4_EXIT_EVALUATION (41 §43, R039) — all six deliverables verified from filesystem:
(1) provider registry: core/providers/registry.py ProviderRegistry (register/replace, template exclusion, deny-by-default capability, ensure_eligible, routing_candidates). (2) one provider adapter: ProviderAdapter behavioral port (T-IMPL-018, 30 §8) + TemplateProviderAdapter proving the contract shape; a REAL functional adapter is PENDING_REAL_PROVIDERS per 41 §49 (scaffold-state explicitly allowed; never faked). (3) model registry: ModelRegistry (active pool, declared-capability filter). (4) provider-model binding: BindingRegistry (multi-provider per model, per-binding availability). (5) credential reference: opaque credential_ref plumbing through registry + adapter port + templates; zero secret material (20 §5). (6) health checks: adapter health_check + aggregate_provider_health (30 §11 matrix; templates always UNAVAILABLE).
=> MVP_PHASE_4_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED (scaffold-state qualifications recorded, per 41 §49 and the R036 directive interpretation).

T_IMPL_019_VERIFICATION_EVIDENCE (R038):
- core/providers/registry.py (335 lines): RegisteredProvider (immutable provider+manifest pairing; is_template = ANY 31 §7 marker: is_template OR status=template_disabled OR real_provider_required — defense in depth), ProviderRegistry (register rejects duplicates, replace = explicit re-registration; templates ARE loadable per 31 §10 but never eligible; supports_operation per 30 §5; supports_capability deny-by-default via getattr-False per 30 §7/20 §4; ensure_eligible gate ordered existence→template→functional→status→operation; routing_candidates applies all 31 §10 exclusions), ModelRegistry (03 §4: active_models pool, models_with_capability declared-only per 11 §5), BindingRegistry (ProviderModelBinding; multi-provider per model; availability is per-binding fact), aggregate_provider_health (30 §11: templates/non-functional => UNAVAILABLE always; explicit provider-scope signal wins; account failures only ever DEGRADE — even ALL accounts failing is account-scope evidence, never provider death; no accounts + no signal => HEALTHY since account pools are optional per 30 §10.1).
- core/providers/errors.py extended: DuplicateRegistration, ProviderNotRegistered, ModelNotRegistered, BindingNotFound, ProviderNotEligible.
- tests/providers/test_provider_registries.py: 31 hermetic tests, ZERO type-ignore comments — registration/duplicate/replace, template exclusion matrix (all 3 markers), eligibility gate ordering, deny-by-default capability (unknown key => False), routing candidate filtering by operation, model/binding registries, health aggregation matrix (template=>UNAVAILABLE, provider signal precedence, all-accounts-down=>DEGRADED-not-UNAVAILABLE, empty accounts=>HEALTHY).
- Credential plumbing stayed opaque: registry surfaces touch credential_ref only, no secret material anywhere (20 §5).
- Gates at R038: 314 tests PASS (31 provider-registry); mypy --strict (core/) clean across 38 files; ruff clean; ALL 7 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- Session maintenance (R038): sandbox reset wiped dev tools AGAIN — reinstalled all pinned deps (ruff/mypy/import-linter + runtime deps) before gates. Known pre-existing cosmetic note: `ruff format --check` would reformat 15 files repo-wide (long-standing, includes pre-T-IMPL-018 files); the ENFORCED gate is `ruff check` (lint), which is clean — formatting normalization is deliberately NOT bundled into this focused task commit.

CURRENT_WORKSTREAM_AFTER_THIS_COMMIT:
MVP Phase 6 — Context / Roles / Skills MVP (41 §45): slice 1 of 4 DONE and VERIFIED at this R045 checkpoint (T-IMPL-025 evidence above). Remaining slices per the R044 MVP PHASE 6 SLICING DECISION: T-IMPL-026 role + skill contracts + registries → T-IMPL-027 context composer → T-IMPL-028 API surface. MVP_PHASE_6_STATUS: IN_PROGRESS (1/4).

NEXT_TASK:
T-IMPL-026 — MVP Phase 6 slice 2 (per the R044 slicing decision, binding): role + skill contracts (03 §6 Role/Skill entities verbatim; 14 §2 skill manifest; 14 §3 import lifecycle states as a closed enum) + registries with the LOADABLE-NOT-EXECUTABLE posture: only status=active system roles / local skills are selectable; 03 §8 relationship rules bind (Role can request capabilities but cannot GRANT permissions; Skill can require Tools but cannot BYPASS tool policy). Scope boundaries (a)/(b) of R044 apply: LOCAL skills only, tools representable but not executable, no import machinery.

NEXT_TASK_OBJECTIVE:
Continue MVP Phase 6 within the same slicing decision: contracts first (core/contracts/), then registry module(s) mirroring the port + in-memory pattern, then hermetic tests (contract-layer + registry-layer).

NEXT_TASK_NOTE:
Constraints carried forward: hermetic gates only (no network), credential handling stays opaque-reference-only (20 §5), unknown capability => DENY (30 §7), templates never routable/executable (31 §4/§10), 41 §49 NOT-CLAIMED rule still binds. Session-start ritual (recurring reality): expect the sandbox reset to have wiped ALL deps — reinstall the full pinned set from pyproject.toml directly (editable install broken by flat-layout) and untrack any auto-uploader-re-tracked tool caches BEFORE running gates.

NEXT_TASK_AUTHORIZED:
YES (USER DIRECTIVE 2026-08-26 R036 continuous-execution directive: "as many authorized micro-tasks as safely possible"). Slice 2 is within the SAME phase — no session boundary applies until the Phase 6 exit evaluation.

DO_NOT_START:
- MVP Phase 7+ code until Phase 6 exit is verified
- Tool execution / Capability Firewall / client runtime / GitHub tools (R044 boundary (a) — NOT Phase 6)
- Skill import machinery (R044 boundary (b) — representable as data only)
- Semantic-similarity retrieval (R044 boundary (c) — arrives with pgvector binding)
- Memory learning/inference loop (R044 boundary (d) — Phase 7 evaluation)
- real KMS/vault/network bindings; real secret material anywhere (20 §5)
- no OTLP exporter dependency until a collector exists (ADR-0004)
- do not re-open Phase 1/2 contract or service decisions or ACCEPTED ADRs (superseding ADR required)
```

---

## CONFIRMED DECISIONS

```text
- USER DIRECTIVE (2026-08-25, supersedes one-task-per-session stop rule): the Agent must execute as many authorized tasks as possible in the same session, in migration order, provided each task still gets its own focused commit, its own verification, and a state-file update at each verified checkpoint. Phase boundaries still hold: Phase 2 must not start in the same session that verifies Phase 1.
- USER DIRECTIVE (2026-08-26, R036 — continuous execution to project completion): the operator instructed "execute the next task and continue until full project completion". Interpretation under governance: continue executing authorized tasks in migration order across MVP phases within this session, keeping per-task commits, per-task verification, and state checkpoints. The R024 phase-boundary decision is SATISFIED for Phase 4 (this is a new session that first re-verified R035). For SUBSEQUENT phase boundaries this directive is read as explicit operator authorization to verify a phase's exit criteria and continue into the next phase within the same session — the R024 rule's purpose (no unverified phase rollover) is preserved because each phase exit still gets an explicit verified checkpoint commit before the next phase starts. "Full project completion" for this workstream = MVP DoD (41 §48) EXCEPT items impossible without real provider credentials/network (41 §49 explicitly authorizes scaffold-state and forbids faking them); those are recorded as PENDING_REAL_PROVIDERS, never claimed.
- MVP PHASE 4 SLICING DECISION (R036): 41 §43 deliverables are executed contracts-first, mirroring R025: T-IMPL-018 ProviderAdapter behavioral port (30 §8) + missing operation contracts → T-IMPL-019 provider/model/binding registries + health aggregation + template-exclusion (31 §10) → T-IMPL-020 providers/ scaffold tree (31 §5–§7: 12 disabled diverse templates, manifest schema validation, _pending_real_providers.md, 31 §11 test suite). 'Credential reference' deliverable = opaque credential_ref plumbing through registry + adapter port (20 §5), never secret material. 41 §49 scaffold-state rules bind the whole phase.
- MVP PHASE 5 SLICING DECISION (R040, recorded as required by the R039 NEXT_TASK_NOTE): 41 §44 deliverables execute contracts-first in four slices — T-IMPL-021 routing contracts + SimpleScoringRouter (DONE R040) → T-IMPL-022 execution service (single-node first, then pipeline; fakes per 41 §49) → T-IMPL-023 API surface (POST /v1/execute + status endpoint; FastAPI pin + import-linter contract land in the SAME commit per ADR-0001) → T-IMPL-024 usage reservation/settlement. Router scope boundary: EXPLICIT_MODELS + AGENT_NODE_MAPPING policy resolution belongs to the execution-graph slice; the simple-scoring router REJECTS them loudly (UnsupportedPolicyType) — recorded so the boundary is a decision, not an accident. Deferred router filters (tenant/plan entitlement, rate-limit budget, data boundary, tool permissions) slot into the eligibility pipeline in their own phases without contract changes.
- MVP PHASE 6 SLICING DECISION (R044, recorded as required by the R043 NEXT_TASK directive BEFORE any Phase 6 code): 41 §45 deliverables (conversation history, basic user preferences, system roles, local skills, context composer) execute contracts-first in four slices, mirroring R025/R036/R040 discipline — T-IMPL-025 conversation + memory contracts (03 §3 Conversation/Message/MemoryItem verbatim; 13 §3 memory-item contract fields incl. sensitivity) + ConversationStorePort/MemoryStorePort + in-memory bindings (tenant-scoped every call, 20 §6 anti-enumeration NotFound posture mirroring core/storage) → T-IMPL-026 role + skill contracts (03 §6 Role/Skill entities verbatim; 14 §2 skill manifest; 14 §3 import lifecycle states as a closed enum) + registries with the LOADABLE-NOT-EXECUTABLE posture: only status=active system roles/local skills are selectable, and 03 §8 relationship rules bind (Role can request capabilities but cannot GRANT permissions; Skill can require Tools but cannot BYPASS tool policy) → T-IMPL-027 context composer service (13 §5 inputs/output contract; 13 §4 scope priority Conversation > Project > Workspace > User > Tenant > Global with more-specific-wins-unless-low-confidence; 13 §9 retrieval rules; context budget respected; EXCLUDED list is explainable data like router exclusions) → T-IMPL-028 API surface (GET /v1/skills per 10 §7; conversation history persisted through POST /v1/execute's existing conversation_id; role selection honored from the existing request contract). SCOPE BOUNDARIES recorded as decisions, not accidents: (a) Tool execution, Capability Firewall enforcement, client runtime, and GitHub tools (14 §4–§8) are NOT Phase 6 — 41 §45 delivers LOCAL skills only; skills that require tools are representable but not executable (mirrors 31 template posture). (b) Skill IMPORT pipeline (scanned/validated/reviewed states) is representable as data but no import machinery is built — local source only. (c) Semantic-similarity retrieval (13 §9) is deferred with the pgvector binding; MVP retrieval = scope + recency + confidence + relevance-tag filtering, recorded honestly. (d) Memory learning/inference (13 §6) is NOT Phase 6 — preferences are explicitly written in MVP; the learning loop belongs to Phase 7 evaluation. (e) 13 §7 memory safety binds NOW: secrets must never be stored as memory (deny at the port on secret-looking keys is an explicit design duty of T-IMPL-025). Port + in-memory fake pattern throughout; hermetic tests; 41 §49 NOT-CLAIMED rule binds the whole phase.
- Agent performs local work only unless explicit push instruction is given.
- Auto-uploader/external system owns remote synchronization.
- Local commit + verification is enough to mark a task VERIFIED.
- Remote push is not required for task verification.
- PROJECT_EXECUTION_STATE.md controls project phase/task progression.
- 22_LIGHTWEIGHT_RESUME_AND_PROGRESS_STATE_PROTOCOL.md defines how to resume.
- final_docs_v2 documents are specifications, not progress-state files.
- Resume/Handoff inside documents should be static pointers, not live progress data.
- Phase 2 implementation remains LOCKED until Phase 1 documentation is VERIFIED.
- Project state alone is not proof; it must be verified against local Git and filesystem reality.
- Do not add more mutable state files unless explicitly approved.
- Reports such as DOC_REWRITE_REPORT.md are audit artifacts, not task-control state.
- Fetch/rebase may be used for recovery/synchronization checks, but it should not become repeated per-task overhead.
- T-DOC-001 is resume/state governance preparation only, not actual documentation rewrite.
- Actual documentation re-architecture begins at T-DOC-002 after T-DOC-001 is VERIFIED.
- T-DOC-001 cleaned legacy resume/state instructions and centralized them on PROJECT_EXECUTION_STATE.md.
- V2 structure is not authoritative; V3 documentation architecture may differ from V2.
- V3 must preserve decisions/contracts/invariants, not V2 file boundaries.
- T-DOC-002 approved the V3 blueprint: final_docs_v3/00_INDEX.md is the live migration index and single authority switch.
- V3 target = 20 documents in 7 layers; merges: 05+24, 23+25, 07+21, 14+15, 16+20; superseded: 17 (by 22 + project state).
- Migration proceeds one cluster per session (T-DOC-003 … T-DOC-013); a V2 doc stays authoritative until its V3 successor is verified and marked in the V3 index.
- T-DOC-003 completed the first content migration: final_docs_v3/30 is authoritative for the Provider subsystem; v2 24 and v2 05 are SUPERSEDED baseline material.
- R006 reconciliation: external auto-uploader commits after f10ea536 (scaffold file removals, README carry) were verified as unrelated to documentation tasks; f10ea536 confirmed as ancestor of HEAD.
- R007 reconciliation: the T-DOC-003 local commit (a43b7281) was re-synchronized by the external auto-uploader as per-file sync commits ending at 26c83ad4; filesystem verification confirmed all T-DOC-003 artifacts intact (v3 doc 30 present, banners present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-004 completed the second content migration: final_docs_v3/31 is authoritative for provider scaffolding + real provider onboarding; v2 23 and v2 25 are SUPERSEDED baseline material.
- R008 reconciliation: the T-DOC-004 local commit (88965f5) was re-synchronized by the external auto-uploader as per-file sync commits ending at 1c26bda; filesystem verification confirmed all T-DOC-004 artifacts intact (v3 doc 31 present at 1304 lines, banners on v2 23/25 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-005 completed the third content migration: final_docs_v3/12 is authoritative for Execution Graph, Agent Mode, and provider-agent orchestration; v2 07 and v2 21 are SUPERSEDED baseline material. Critical rule preserved: Provider Agent Capability != Platform Agent Runtime; platform remains the commander.
- R009 reconciliation: the T-DOC-005 local commit (2b08b04) was re-synchronized by the external auto-uploader as per-file sync commits ending at bf421c8; filesystem verification confirmed all T-DOC-005 artifacts intact (v3 doc 12 present at 887 lines, banners on v2 07/21 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-006 completed the first carry cluster: final_docs_v3/01, 02, 03 are authoritative for product requirements, architecture baseline/invariants, and domain model; v2 01/02/03 are SUPERSEDED baseline material. All 15 architecture invariants and FR-001..FR-015 carried verbatim; no decision changed.
- R010 reconciliation: the T-DOC-006 local commit (542cb4d) was re-synchronized by the external auto-uploader as per-file sync commits ending at 1f5967a; filesystem verification confirmed all T-DOC-006 artifacts intact (v3 docs 01/02/03 present, banners on v2 01/02/03 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-007 completed the second carry cluster: final_docs_v3/10 and 11 are authoritative for API contracts and model routing/model control; v2 04/06 are SUPERSEDED baseline material. All 5 model policy types and all 5 router selection modes carried verbatim; no decision changed.
- T-DOC-008 completed the third carry cluster: final_docs_v3/13 and 14 are authoritative for memory/context and skills/tools; v2 08/09 are SUPERSEDED baseline material. Capability Firewall check and unknown-tools-default-to-DENY carried verbatim; no decision changed.
- T-DOC-009 completed the fourth carry cluster: final_docs_v3/20, 21, 22 are authoritative for security threat model, admin control plane, and evaluation/learning; v2 10/11/12 are SUPERSEDED baseline material. Capability Firewall, deny-by-default, tenant isolation, verification levels, and promotion gates carried verbatim; no decision changed.
- R012 reconciliation: the T-DOC-009 local commit (62b02fb) was re-synchronized by the external auto-uploader as per-file sync commits ending at aa2c0bd; filesystem verification confirmed all T-DOC-009 artifacts intact (v3 docs 20/21/22 present, banners on v2 10/11/12 present, index flipped). Facts from filesystem, not commit hashes.
- T-DOC-010 completed the rewrite-compress of v2 13 into final_docs_v3/40_ENGINEERING_PROTOCOL.md (2385 -> 659 lines). All engineering rules with execution value preserved (verified mechanically: 22 invariants, 17 test types, 6 boundary tests, 10 principles, phase gates, DoD, ADR, Git safety, recovery). Only v2 13 SS39/SS40/SS41/SS50 (legacy STATE.md/PROGRESS.md/HANDOFF scheme + resume command) are superseded — explicitly, by D10/D11, recorded in the successor's SS11, its traceability ledger, and the v2 banner. Architecture duplication replaced with an authority map to owning v3 docs.
- R013 reconciliation: the T-DOC-010 local commit (71484af) was re-synchronized by the external auto-uploader as per-file sync commits ending at da22183; filesystem verification confirmed all T-DOC-010 artifacts intact. Facts from filesystem, not commit hashes.
- T-DOC-011 completed the merge of v2 14 + 15 into final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md (Part I FINAL plan / Part II MVP roadmap / Part III FINAL-MVP-FUTURE map). All 24 FINAL phases, 15 rules, micro-task protocol, MVP scope and DoD preserved (verified mechanically). Explicit D10/D11 supersessions only: v2 14 SS32/SS33/SS35/SS37/SS39/SS42 (multi-file resume, NEXT_PLAN.md, FUTURE_IMPROVEMENTS/ARCHITECTURE_GAPS ledgers, handoff files, static resume prompt) and v2 15 legacy state-file wording — recorded in the successor SS51 ledger and both v2 banners. Commit/recovery detail now points to 40 SS9-SS10 (single authority). Arabic narrative normalized to English; decision blocks verbatim.
- New rule made explicit in 41 SS31 (D10/D11 application, not a new decision): scope-control recording target = 60_DECISION_LOG.md once it exists (until then the state-file SESSION NOTES), replacing the superseded FUTURE_IMPROVEMENTS.md/ARCHITECTURE_GAPS.md ledger files.
- R015 reconciliation: the T-DOC-012 content work was synced by the external auto-uploader as per-file commits ending at 76d3415 before this state checkpoint was written (an interrupted state update in the prior session did not apply). Filesystem verification confirmed all T-DOC-012 artifacts intact and content-verified; this checkpoint was then recorded and committed. Facts from filesystem, not commit hashes.
- T-DOC-012 completed the agent-operation cluster: final_docs_v3/50 (build prompt: v2 20 Ultra base + v2 16 as subordinate Standard Profile — single build-prompt authority), 51 (cognitive protocol, carried verbatim), 52 (resume protocol: v2 22 carried + v2 17 retired/absorbed as SS17), 60 (decision log: all 25 Q&A carried verbatim + append-only rules + migration records MR-001..MR-004) are authoritative; v2 16/17/18/19/20/22 are SUPERSEDED baseline material. Explicit D10/D11 supersessions only (legacy state/handoff files, FUTURE_IMPROVEMENTS.md target, NEXT_PLAN scheme, v2 17 dead paths) — recorded in successor ledgers and v2 banners; never silent.
- 60_DECISION_LOG.md is now the live scope-control recording target per 41 SS31. It is append-only: existing entries are never edited; superseded decisions get a new entry referencing the old one.
- R016 reconciliation: a prior session began T-DOC-013 and was interrupted mid-audit; its partial artifacts (v3 index QA-gate marks, v2 00_INDEX ARCHIVED_BASELINE block, 41 authoritative header, README repointing to v3) were synced by the external auto-uploader as per-file commits ending at 8967f06. This session verified each artifact from the filesystem (facts from filesystem, not commit hashes), completed the remaining audit items, and recorded the checkpoint.
- T-DOC-013 completed the V3 finalization QA gate: index/filesystem consistency (20/20), banner audit (26/26 v2 files, 0 dead successor paths), authority audit (no v2 doc cited as authority in v3), dead-path audit (0 after creating DOC_REWRITE_REPORT.md), ARCHIVED_BASELINE marks verified, secret scan pass, build-agent readiness mapping recorded. DOCUMENTATION_PHASE_EXIT_CHECKS = PASS (full scorecard in DOC_REWRITE_REPORT.md). PHASE_1_STATUS = VERIFIED. PHASE_2 remains LOCKED; unlock requires a new session (T-IMPL-000 gate).
- DOC_REWRITE_REPORT.md is an audit artifact only (README DOC_REWRITE_REPORT rule); it carries no task-control authority.
- R017 reconciliation: the T-DOC-013 checkpoint local commit (457ed3f) was re-synchronized by the external auto-uploader as per-file sync commits ending at fcb8aae; filesystem verification in this new session confirmed all checkpoint artifacts intact. Facts from filesystem, not commit hashes.
- T-IMPL-000 (this new session) re-verified the full Phase 2 unlock condition and flipped PHASE_2_STATUS to UNLOCKED. PHASE_2_START_RULE satisfied: verification session (R016) and unlock session (R017) are distinct.
- Phase 2 task numbering: T-IMPL-NNN; governance per PHASE_2_GOVERNANCE block above.
- OPEN DECISION (blocks MVP Phase 1 code): implementation language/stack is not specified anywhere in the v3 pack. Stack selection is a significant architecture decision => requires an ADR and explicit user approval before contracts code is written. Governance scaffolding (T-IMPL-001) is stack-neutral and may proceed.
- T-IMPL-001 completed MVP Phase 0 governance scaffolding: engineering/adr (template + index), engineering/gates (template), engineering/verification (conventions + check_repo.sh), engineering/decisions (pointer to 60_DECISION_LOG.md), .github/workflows/ci.yml (runs the same script as local). Verification: check_repo.sh => RESULT: PASS. Gate G0 exit criteria met (41 §39). CI-mirrors-local rule established: repo checks run via one entry point in both places.
- Stack ADR flow decided: T-IMPL-002 writes ADR-0001 as PROPOSED; it becomes ACCEPTED only on explicit user approval recorded in this state file; contracts code stays blocked until then.
- T-IMPL-002 committed ADR-0001 (PROPOSED): TypeScript/Node LTS monorepo (zod contracts, Fastify, Postgres+drizzle, Redis Streams, outbox-first workflows — Temporal deferred to its own ADR, OTel+pino, vitest, dependency-cruiser boundary tests). 3 alternatives analyzed. USER DECISION PENDING: approve / amend / reject. While PROPOSED, the ADR file may be edited freely; once ACCEPTED it becomes append-only per ADR rules.
- Session R017-R019 note: T-IMPL-000, T-IMPL-001, T-IMPL-002 were executed in the same session (allowed within Phase 2 by the USER DIRECTIVE; the PHASE_2_START_RULE only separated Phase-1-verification from Phase-2-start, which was honored).
- R020 reconciliation: the T-IMPL-002 checkpoint local commit was re-synchronized by the external auto-uploader as per-file sync commits ending at debde5f; filesystem verification in this new session confirmed all T-IMPL-002 artifacts intact (ADR-0001 present as PROPOSED, index row present, check_repo.sh PASS 18/18). Facts from filesystem, not commit hashes.
- USER DECISION (2026-08-25, T-IMPL-003): implementation stack = Python / FastAPI / Pydantic (user selected Alternative B, superseding the proposed TypeScript stack before acceptance). ADR-0001 Decision/Reason rewritten to the Python stack and flipped to ACCEPTED; recorded as IMPL-001 in 60_DECISION_LOG.md. ADR-0001 is append-only from this point; stack changes require a superseding ADR.
- Stack facts now binding (ADR-0001): Python 3.12+, Pydantic v2 contracts with JSON Schema export, FastAPI, SQLAlchemy 2.x async + Alembic + pgvector, redis-py Streams, outbox-first workflows (Temporal Python via future ADR), OTel + structlog, pytest, mypy --strict on core/, ruff, import-linter boundary tests, single pyproject monorepo per 41 §2. Admin UI / client-runtime stack deferred to a future ADR.
- T-IMPL-004 started MVP Phase 1 (Contracts): workspace layout per 41 §2 created as Python packages; pyproject.toml is the single tool-config source; contract layer posture fixed in core/contracts/base.py (ContractModel = extra:forbid + frozen — deny-by-default at the contract boundary, immutable value objects); unified error contract implemented verbatim from 10 §9 (11 categories, closed StrEnum); 9 contract tests pass; import-linter enforces the 4 boundary contracts and was negative-tested.
- check_repo.sh remains the single verification entry point: it now additionally runs pytest/mypy/ruff/import-linter when pyproject.toml exists (CI-mirrors-local preserved).
- R021 note: .github/workflows/ci.yml (created at T-IMPL-001) was found missing from the worktree — evidently dropped during the external auto-uploader's history re-sync of dot-directories. Recreated at T-IMPL-004, upgraded for the Python stack (setup-python 3.12 + dev deps + same check_repo.sh entry point). If the uploader drops it again, restoring it is maintenance, not a decision change.
- T-IMPL-005 completed the execute API + model policy contracts: core/contracts/execute.py (ExecuteRequest per 10 §2 with wire aliases async/schema; ExecuteSyncResponse §3; ExecuteAsyncAccepted §4 pinned to status=queued; ExecutionStatusResponse §5 with 6-state closed ExecutionStatus per 03; discriminated StreamEvent union §11; WebhookPayload + 6 WebhookEventType values §12) and core/contracts/model_policy.py (discriminated union of all 5 policy types per 10 §13; SelectionStrategy 5 values §13.4; FallbackScope 6 values per 11 §8; AgentPolicy request carrier §13.5; node policies exclude recursive agent_node_mapping). 41 contract tests validate every documented example verbatim (incl. byte-for-byte wire round-trip of the §2 request) and reject unknown fields/enum values/missing required fields. Maintenance in same commit: python cache dirs untracked + gitignored (uploader had synced .mypy_cache etc. as commits).
- R022 session interruption note: T-IMPL-005 content work (contracts + tests) was authored in a prior interrupted session; this session verified all artifacts from the filesystem (facts from filesystem), fixed one test round-trip assertion (exclude_unset for the optional agent_policy field), removed one stale type-ignore, formatted 2 files, ran all gates green, and committed. Content commit: 0a07f3d.
- T-IMPL-006 completed the provider contract + model contract + core domain types: core/contracts/domain.py (03 §4 entities verbatim — Model as the Router's model contract with tier/modalities/capabilities/scores, Provider, ProviderModelBinding, Credential with opaque credential_ref never raw secrets, ProviderAccount with 7-value lifecycle + 4-value health; 03 §9 agent extensions with undeclared-by-default capability flags) and core/contracts/provider.py (30 §5 operations closed set of 11; §7 manifest with deny-by-default closed capability keys; §11 provider health 4 states vs account check states 4 — provider health ≠ account health preserved; §12 normalized rate-limit states 4; §14 error normalization 12 categories + documented shape — Core sees normalized errors only). 53 new contract tests; 94 total pass; all gates green. ProviderAdapter behavioral interface (30 §8) deliberately deferred to the port-layer task. Content commit: dab4216.
- R023 session interruption note: a prior session authored domain.py/provider.py for T-IMPL-006 and was interrupted before exports/tests; this session verified filesystem reality first (recovery rule), found the export edit unapplied and tests absent, completed them, verified content against 03/30 line-by-line, ran all gates green, and committed. Facts from filesystem, not chat history.
- T-IMPL-007 completed the execution contract (core/contracts/execution.py: Execution + ExecutionNode per 03 §5 verbatim; strategy set 8, node types 7, node states 6; status reuses shared ExecutionStatus; 12 §5/§6 graph-runtime supersets deliberately deferred to the Execution Graph task). 18 new tests; 112 total green; all gates PASS. MVP Phase 1 exit criteria (41 §40) evaluated and VERIFIED at R024. Content commit: b95af2d.
- R024 environment note: this session recovered from a sandbox reset + auto-uploader history rewrite. All previously recorded short commit hashes are invalid in the rewritten history; the trusted progress anchor is HEAD + filesystem + green gates, per the state file's own proof rule. Dev tooling (mypy/ruff/import-linter) had to be reinstalled; pre-task gates re-run PASS before new work began.
- MVP-PHASE BOUNDARY DECISION (R024): applying the same discipline as the documentation PHASE_2_START_RULE and the USER DIRECTIVE's phase-boundary clause, MVP Phase 2 (T-IMPL-008) must start in a NEW session that first re-verifies the R024 checkpoint from filesystem + git. This session verified Phase 1 exit and therefore stops here.
- MVP PHASE 2 SLICING DECISION (R025): 41 §41 deliverables are executed contracts-first, mirroring Phase 1 discipline: T-IMPL-008 identity/tenancy contracts (03 §2) → T-IMPL-009 RBAC/entitlement + capability-firewall decision contracts (20 §4) → T-IMPL-010 in-memory identity service skeleton (registration + personal tenant + email-verification port with fake + session) with auth/tenant-isolation tests. No network, no real email, no secrets in code anywhere in Phase 2.
- T-IMPL-017 completed the ADR-0004 observability implementation (R035, commit 6ba586b): opentelemetry-api/sdk + structlog pinned WITH the 7th import-linter contract (core must not import the telemetry stack) in the same commit; apps/observability/ composition root (TracerProvider wiring ONLY there; console/no-op exporters — OTLP rejected by config until a collector exists, per ADR); AdaptiveSampler per 40 §5.3 under ParentBased(root); structlog JSON pipeline with head-of-pipeline secret scrubbing (20 §5) + trace_id/span_id correlation; audit port untouched (telemetry references audit ids only). 18 hermetic tests; 269 total green; all 7 contracts kept; check_repo.sh PASS.
- MVP PHASE 3 EXIT (R035): all six 41 §42 deliverables verified from filesystem (migrations / redis / object storage / secret manager / audit logs / OTel) — MVP_PHASE_3_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED. Applying the MVP-PHASE BOUNDARY DECISION (R024): MVP Phase 4 (T-IMPL-018) must start in a NEW session that first re-verifies the R035 checkpoint. This session stops here.
- T-IMPL-018 completed MVP Phase 4 slice 1 (R037): core/providers/ports.py — ProviderAdapterPort Protocol mapping 30 §8.1 1:1 (get_manifest / validate_credential / discover_models / get_capabilities / generate / health_check / normalize_error; async posture matching runtime ports; generate = normalized entry dispatching to 30 §5 operations, undeclared operation => unsupported_capability), plus the 30 §8.2 OPTIONAL interfaces as SEPARATE protocols (ProviderAccountLifecyclePort, ProviderAssetsPort). core/contracts/provider.py extended with the missing operation contracts: HealthScope (provider|account), CredentialHealth (opaque credential_ref only — secret-material fields rejected by test), DiscoveredModel (provider declaration, NOT a registry binding — binding fields rejected by test), ProviderGenerateRequest (documented-operation-only, positive timeout, inline-secret fields rejected), ProviderGenerateResponse (success shape XOR normalized ProviderError — raw provider error shapes rejected, non-negative latency). core/providers/errors.py: Core-side boundary errors (ProviderNotRegistered/NotEligible, ModelNotRegistered, BindingNotFound, DuplicateRegistration) for the T-IMPL-019 registries. 22 new hermetic tests (14 contract + 8 port-behavior against an in-memory fake adapter: manifest-as-single-source, declared op succeeds, undeclared op => unsupported_capability, opaque credential handling, discovery-not-binding, provider/account health separation, error normalization incl. rate-limit retry hint and no-raw-payload-leak). Gates at R037: 291 tests PASS; mypy --strict clean; ruff clean; ALL 7 import-linter contracts kept; secret scan clean; check_repo.sh RESULT: PASS.
- R037 reconciliation: the R036 session was interrupted mid-T-IMPL-018 after authoring artifacts; the auto-uploader synced them as per-file commits (ending near HEAD). This session verified every artifact from the filesystem per the recovery rule, reinstalled deps after another sandbox reset (editable install broken — deps installed directly, same pins), untracked re-tracked tool caches again, ran full gates green, and recorded this checkpoint. Facts from filesystem, not chat history.
- T-IMPL-024 completed MVP Phase 5 slice 4 (R043): core/usage/ UsageAccountingPort + InMemoryUsageAccounting (reserve BEFORE provider work; exactly-once settle/refund/fail resolution; deny-by-default EntitlementNotConfigured; overage charged honestly), wired into ExecutionService (denied reservation never reaches an adapter; crash resolves the hold before propagating; usage=None keeps pending_usage_service verbatim) and the API (10 §3 usage block on success; BudgetExceeded/EntitlementNotConfigured => entitlement_exceeded 403 with requested/remaining details). 41 new hermetic tests (29 usage + 7 execution-wiring + 5 api); 471 total green; all 8 contracts kept; check_repo.sh PASS.
- MVP PHASE 5 EXIT (R043): all six 41 §44 deliverables verified from filesystem (POST /v1/execute / router simple scoring / single execution / pipeline execution / status endpoint / usage reservation-settlement) — MVP_PHASE_5_STATUS: EXIT_CRITERIA_MET_AND_VERIFIED. Applying the MVP-PHASE BOUNDARY DECISION (R024): MVP Phase 6 (T-IMPL-025) must start in a NEW session that first re-verifies the R043 checkpoint. This session stops here.
```

---

## DO NOT CHANGE WITHOUT ADR / EXPLICIT USER DECISION

```text
- Architecture invariants in README and final_docs_v2.
- Provider-agnostic and model-agnostic Core.
- Model != Provider != Account.
- Router decides; Execution executes.
- LLM is not a security authority.
- Unknown capability/permission => DENY.
- Provider templates are non-functional until real providers are implemented and verified.
- Agent must not push unless explicitly instructed.
```

---

## RECOVERY RULE

On a new session:

```text
1. Read this file.
2. Run git status.
3. Run git rev-parse HEAD.
4. Run git diff --stat.
5. Compare this state with Git/filesystem reality.
6. Verify referenced commits exist locally when used as evidence.
7. If conflict exists, Git/filesystem reality wins for facts.
7. Reconcile this file before advancing tasks.
8. Continue only the authorized NEXT_TASK.
9. Do not infer progress from chat history.
10. Do not push unless explicitly instructed.
```

---

## STATE FAILURE MODE

If this file is missing, unreadable, empty, or invalid, the recovery state is:

```text
STATE_STATUS: RECOVERY_REQUIRED
PROJECT_PROGRESS: UNKNOWN
CURRENT_TASK: STATE_RECOVERY
PHASE_2_STATUS: LOCKED
NEXT_TASK_AUTHORIZED: NO_UNTIL_STATE_RECONSTRUCTED_AND_COMMITTED
```

Recovery must be reconstructed only from:

```text
local Git history
filesystem reality
existing repository documentation
verified commits
```

Do not infer progress from chat history or previous AI claims.
Do not create additional mutable state files.
Recreate this file only after verified reconstruction, then commit before continuing.

---

## STOP CONDITION

```text
Per USER DIRECTIVE (2026-08-25): execute as many authorized tasks as possible
in the same session, in migration order.
For EACH task:
  Verify locally.
  Update this state only at a verified checkpoint.
  Create one focused local commit.
Then continue to the next authorized task in the same session.
At session end: report all commit hashes and the next task. Stop.
Phase boundaries still hold: do not start Phase 2 in the session that verifies Phase 1.
```
