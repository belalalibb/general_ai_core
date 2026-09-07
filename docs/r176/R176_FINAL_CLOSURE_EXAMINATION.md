# R176 — QEVION FINAL CLOSURE EXAMINATION (Phase A report)

Contract: `docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md` (521d885). Round ledger:
`evidence/r176_state_ledger.md`. Raw evidence: `evidence/r176/00..12`. Labels per prompt §0.5
(`VERIFIED|INFERRED|FAILED|BLOCKED|MISSING` × `STATIC|TEST|RUNTIME|LIVE|MEASURED`).
**Phase A was read-only on the product tree: zero product files changed. No FIX has been approved, implemented or verified.**

---

## 1. Executive verdict — what QEVION actually is today

A **working, tenant-isolated, provider-agnostic AI execution platform** (FastAPI + framework-free `core/`): real identity
(register/verify/login, admin by allow-list); sync/async execution over a routed provider layer (in-process adapters + a separate
remote **provider gateway**, Groq and AssemblyAI live-proven); a shared agent runtime with tool/skill admission; an admin control
plane driven by ONE config lifecycle (draft→validate→preview→publish→rollback) with immediate runtime effect and audit; a gated
learning pipeline (scan → reviewer act → evaluate → eligibility → GOLD) that refused a secret-bearing sample; usage accounting;
workspaces/projects; webhook registration; OpenAPI 3.1; two static UIs.

**Honest envelope**: single-instance durable (Postgres 17 + pgvector; queue / rate-limit / usage ledger are process-local);
user-session consumers only (no application credential); console-delivered verification tokens; no webhook delivery relay composed;
browser UI not re-verified in this sandbox.

**ZERO KNOWN DEFECTS WITHIN THE DECLARED TESTED ENVELOPE** for tenant isolation, authorization composition, credential containment
and learning trust — after executed two-tenant, concurrent and falsification probes. **Eleven findings** open (§19): one S1 that is
*documentary* (live third-party secrets committed inside the examination prompt, breaking the repo's own gate), one S2-latent (SSRF
admission bypass on a path not yet dereferenced), seven S3 contract/hygiene defects, two S4.

Closure decision (§29): **BOUNDED FIX SET** — 7 small fixes, each with a failing-first test; none architectural.

## 2. Repository state
| item | value |
|---|---|
| repo / branch | `belalalibb/general_ai_core` · `main`; origin/main == HEAD after every item |
| worktree | clean at every checkpoint; 10 sandbox resets (#18–#27) during the round, all recovered from repo/bundles |
| runtime / CLI | `python3 -m apps.cli serve` (= `apps.main`) · `apps.cli {serve,check,test,routes,describe}` |
| verification gate | `apps.cli check` = `engineering/verification/check_repo.sh` + `green_manifest.json` (5 slices, floor 3127, max_skipped 64) |
| gate at A0 | **FAIL** — only the secret scan (prompt line 132); pytest 3150/0/0/64, mypy, ruff, import-linter, budgets all PASS |
| composition | env → profile: hermetic (in-memory, `local_echo`, auth-only) / durable (`DATABASE_URL`) / demo / gateway (`GATEWAY_*`) / engineering (`AGENT_WORKSPACE_ROOT`) |
| route surface | 79 paths / 88 method-routes (59 under `/v1/admin`) — `evidence/r176/02_repo_state/routes_hermetic.txt` |

## 3. Authoritative documents — what wins
Prompt §0.4 order applied. Conflicts found and resolved (A3): ADR-0008 remote gateway supersedes 41's in-process plugin plan
(REQUIREMENT CHANGE, accepted); §52 names `PROJECT_EXECUTION_STATE.md` the only state file while reality since R168 is
`evidence/rNNN_state_ledger.md` and OPERATIONS §12 already says so (DOCUMENTATION DRIFT, F-R176-03); prompt §0.6 "placeholders
only" vs literal live values committed → security invariant wins (F-R176-01).

## 4. Operational memory / resume
| | |
|---|---|
| RESUME ARTIFACT | `evidence/r176_state_ledger.md` (checklist + one row per item, HEAD-at-start column) |
| PROTOCOL | `final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md` + OPERATIONS §12 |
| RECOVERY EVIDENCE | 10 resets recovered; 2 byte-identical bundle restores while push was blocked; uncommitted drafts lost 6× → rule adopted mid-round: **commit + push the probe script BEFORE running it** |
| RESULT | PASS — every resumption reconstructed state from the repository alone |

## 5. Platform architecture map (actual)
```
apps/api  (auth, execute, executions, models, usage, webhooks, workspaces, projects, skills, agent-tools, admin/*)
  └ apps/composition/runtime.py — the ONE place adapters/stores/queues are chosen per profile
core/ (framework-free; import-linter 13 contracts kept): identity security roles context memory execution agent routing
      providers runtime(outbox worker queue admission) usage evaluation learning(lifecycle sanitizer) skills tools admin audit
      events(webhooks) workspace sourcechange engineering secrets storage
providers/real (platform adapters incl. RemoteGatewayAdapter)   gateway-service/ (own package: groq, assemblyai, fixture_echo)
infrastructure/ (alembic 0018, redis, Vault, S3)                 ui/app, ui/admin (static)
```

## 6. Trust-boundary map (executed, A5/A6)
| edge | identity propagation | authorization | failure behaviour | bypass found |
|---|---|---|---|---|
| External app → Core API | Bearer session → principal (tenant, user, is_admin) | middleware before body parse: anon 401 (one constant body), non-admin on `/v1/admin` 403 | closed shapes → 422 | none (F1/F2/F3 falsifiers held) |
| Core → Admin | same principal, `is_admin` from `ADMIN_EMAILS` | admin routes tenant-scoped; admin **cannot** read tenant data through user routes (404) | 409 on bad lifecycle transitions | none |
| Core → async queue → worker | `tenant_id` **serialized into the message payload** (app.py:1179) | worker re-derives from payload; no ambient state | dedup / stale-claim / dead-letter (96 tests) | none (20/20 interleave) |
| Core → Agent → Tool/Skill | tools resolved against composition catalog before the loop | unknown ⇒ 422; Capability Firewall per call | honest 502 with `stop_reason` | none |
| Core → Routing → Credential → Provider | envelope carries `credential.mode`, never the key | ACTIVE-model filter; failover only for account-indicting classes | 503 `model_unavailable`, no silent fallback | none; key 0 hits in evidence/logs |
| Core → Learning | tenant-scoped samples; two independent gates | reviewer act refused over findings; eligibility refused secret | never GOLD | none (pattern gap F-R176-09 bounded) |
| Core → Webhook registration | tenant-scoped | SSRF admission | 422 | **partial** — non-canonical IPv4 literals admitted (F-R176-11) |

## 7. Capability coverage (A4 matrix, condensed)
VERIFIED·RUNTIME: identity chain, execute sync/async, executions read model, models, usage, skills/tools surfaces, contract strictness,
admin surface + lifecycle, context provenance artefact, recovery/resume. VERIFIED·LIVE (this or prior rounds): execute through Groq
(R175), through gateway→AssemblyAI (R176 A9), agent multi-step coding run (R165). INFERRED/UNVERIFIED: browser UI (not evaluable here),
engineering workspace tools (needs `AGENT_WORKSPACE_ROOT`), evaluation graders beyond tests. MISSING vs FINAL plan (not blockers):
device identity, multi-AZ, application credentials, SDK, execution strategies other than single/agent (F-R176-05).

## 8. Agent assessment
Strengths (executed): real plan→act→observe→verify loop with proposals validated per step; honest terminal stops (`invalid_proposal`,
max_steps cap operator-owned); tool admission before any step; trace endpoint (admin) with observable artefacts only; live 32-stage
coding run committed and pushed real code (R165). Weaknesses: no pause/resume primitive (benchmark row 10); trace is admin-only while
OPERATIONS lists it under API (O-01); agent strategy runs sync only; no real-model run re-executed this round (by design, no spend).

## 9. Skills / tools assessment
Skills: import lifecycle `import → scan → validate → review → approve → activate`, 3-source allow-list, unapproved never user-visible,
unknown skill 422. Tools: catalog-resolved allow-list, 0 offered hermetic, `git_push` refused loudly for a consumer. External skills
are not trusted on import (RUNTIME). E2E import from an allowed source: NOT PROBED (P2).

## 10. Evaluation / learning
Trust chain executed on a poisoned sample: RAW → scan (`clean:true`, gap) → sanitize passed → evaluate VALIDATED → **admit refused**
(`sensitive_data_handled`, `not_poisoned`) → promote refused → GOLD empty → `learning/ask` not found → execute `gold_blocks 0` →
other tenant sees nothing → secret never echoed. Control `sk-` sample: scan finding (fingerprint only), reviewer `passed=true`
**refused**. Dashboard is an honest placeholder. Finding: sanitizer pattern gap (F-R176-09).

## 11. Provider / model / routing
Tier 1: 752 + 194 (gateway) pass. Tier 3 this round: AssemblyAI via gateway 10/10 (1 paid call); prompt's Groq key
`organization_restricted` (BLOCKED, external). Router: disable-only-model → 503 with reasons; unknown model → 503 echoing only
caller's key. 12-class failure taxonomy; parity fix from R175 in place. Credential graph: mode-only in envelope; 0 leaks.

## 12. Admin control plane
No direct mutation routes (PUT weights 405). One lifecycle for 13 actions/7 areas; tenant+actor from principal; publish → next request
sees it (strong, process-local); rollback restores; 409 state machine; audit event with versions. **Runtime enforcement does not
consult the admin surface** (absent seam = absent routes; enforcement stays) — CONTROL-PLANE AUTHORITY ≠ RUNTIME ENFORCEMENT.
Finding: credential material accepted+echoed in a draft payload (F-R176-07). Multi-instance propagation = restart-only (A7).

## 13. External application — actual consumability
Repo example client exit 0; two hand-built consumers from the HTTP contract only succeeded end-to-end (discovery, scoping, sync,
async 5/5, usage, webhook registration, loud refusals, isolation 404/403, OpenAPI 3.1). Platform provides identity, isolation,
execution, usage, admin; app must provide email delivery, UI, webhook receiver.

## 14. One-line app challenge
"Slack bot that summarises a pasted incident report and files it under the team's project" — buildable today; no hard blocker.
Frictions: no application credential (F-R176-10), console-only verification token, no SDK, `/docs` 404 (OpenAPI JSON served),
no capability-version discovery. No second platform needed.

## 15. Compromised-app security (direct-Core bypass)
28 probes with a valid non-admin token: cross-tenant reads 404 byte-identical to unknown ids; admin 403 before validation; forged /
empty / junk tokens 401; role/skill/project/model laundering refused; SSRF gate refuses canonical private/loopback/link-local;
**bypass found only in SSRF admission for non-canonical IPv4 literals** on a stored-but-never-dereferenced URL (F-R176-11).

## 16. Tenant / auth / credential — isolation evidence
20 concurrent async jobs from 2 tenants: 20/20 correct attribution, 0 cross-reads; usage exact per tenant (11.0/11.0); idempotency
keys namespaced per tenant (F7); no key material in any response, log or evidence file (grep 0). Async retry with foreign ambient
tenant: PARTIALLY VERIFIED (unit only).

## 17. Reliability / recovery / concurrency — actual guarantees
Durable profile: stores/outbox/idempotency/identity SHARED; queue/rate-limit/usage-ledger/leases PROCESS LOCAL (Redis impls exist,
not composed) ⇒ **single-instance durable** is the guarantee. Crash matrix (Tier 1): relay crash → dedup RECOVER; worker crash → peer
reclaim RECOVER; permanent → dead-letter SAFE FAIL; floods refused SAFE FAIL; usage reservation on process death LOSE (bounded).
Wire: idempotent replay same id; burst 40 → 40×202 all succeeded. Finding: key reuse with different body silently replays (F-R176-08).

## 18. Market readiness (ceiling rule: no executed head-to-head ⇒ max COMPETITIVE)
| domain | evidence | class |
|---|---|---|
| coding / repo engineering agent | R165 live 32-stage run, real commit+push, target `7 passed` | COMPETITIVE |
| provider-agnostic execution + failover | Groq 7/0/0 (R175), AssemblyAI gateway 10/10 (R176) | COMPETITIVE |
| multi-tenant API platform + admin + learning gates | A5/A6/A8 runtime probes | COMPETITIVE |
| admin UI | prior 32/32 browser proof; not re-run here | ADEQUATE |
| retrieval Q&A | no index | UNVERIFIED |
Technical readiness ≠ commercial success.
