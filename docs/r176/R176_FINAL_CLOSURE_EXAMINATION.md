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

## 19. Defect ledger (R176)
| id | sev | area | reproduction | expected | actual | root cause | impact | evidence | status |
|---|---|---|---|---|---|---|---|---|---|
| F-R176-01 | **S1** (doc/secret) | governance | `apps.cli check` at 521d885 | secret scan clean; prompt §0.6 "placeholders only" | FAIL on prompt line 132; three literal secrets committed, AssemblyAI one **live (200)** | operator committed real values in the prompt | repo gate red; live key public in history | `evidence/r176/00_session_start/` | OPEN → FIX-01 + ROTATE |
| F-R176-02 | S4 | ops | `pip install -e gateway-service[dev]` in fresh venv | installs | build fails | no `[build-system]` in gateway pyproject; suite runs from its dir | doc only | A0, A9 | OPEN (doc) |
| F-R176-03 | S3 | docs/resume | read `PROJECT_EXECUTION_STATE.md` | current | frozen at R168, `CURRENT_TASK: STATE_RECOVERY` | ledgers became the checkpoint | fresh agent misled | A1 | OPEN → FIX-02 |
| F-R176-04 | S4 | docs | README/§52 push rule | matches practice | says "never push" | wording | none | A1 | OPEN (doc) |
| F-R176-05 | S3 | contract | `execution_policy.strategy=debate` (or any string) | 422 | 200 silent single-stage | field typed `BoundedStr`; API branches only on `agent` | contract lie for SDK consumers | A4 P-15/16/17/23 | OPEN → FIX-03 |
| F-R176-06 | S4 | contract | `webhook_url` on execute | validated or absent | accepted, never consumed | dead field | none today | A5 O-02 | OPEN (fold into FIX-03) |
| F-R176-07 | S3 | admin/credential hygiene | `register_provider` draft with `api_key` | refused | stored 201, echoed on read-back; rejected only structurally | no credential-key deny-list at draft | secret at rest in change table (durable) | A6 L-14 | OPEN → FIX-04 |
| F-R176-08 | S3 | idempotency | same key, different body | 409 | 202 replays old execution | no body hash in idempotency record | lost work looks like success | A7 R-03 | OPEN → FIX-05 |
| F-R176-09 | S3 | learning/memory screen | sample with `gsk_` value | scan finding | `clean:true` | `_VALUE_PATTERNS` lacks Groq/Anthropic/Google/… shapes | bounded by eligibility gate | A8 | OPEN → FIX-06 |
| F-R176-10 | S3 (product gap) | external consumption | headless consumer | app credential | only user sessions | FINAL-plan item not built | friction, not defect | A10 | OPEN (POST-RELEASE or FIX-08 if prioritised) |
| F-R176-11 | **S2-latent** / S3 now | SSRF admission | webhook url `http://127.1/x`, `0x7f000001`, `2130706433` | 422 | 201 | `ipaddress.ip_address` ValueError → treated as named host | becomes S1 when a sender is composed | A12 F5 | OPEN → FIX-07 |
Also recorded: O-01 trace route admin-only vs OPERATIONS wording (S4 doc). Prior-round open items unchanged: F-R175-04 (bare `python3` in check_repo).

## 20. Unverified / not probed
Browser UI live suite (dependency absent); webhook delivery (relay not composed); multi-instance operation; admin publish during an
in-flight job; async retry with foreign ambient tenant on the wire; skills import from an allowed source E2E; `not_poisoned`
heuristic characterisation; gateway streaming; user-owned provider credentials; Groq live this round; execution strategies other than
single/agent; evaluation graders beyond unit tests; engineering workspace tools at runtime.

## 21. Limitations
Sandbox: no Postgres this round (durable profile relies on R175 D-01, 3197/0); no browser; 10 sandbox resets; GitHub token invalid for
three turns (bundles used). Provider: Groq key org-restricted; AssemblyAI live spend capped at 1 call. Prompt/repo mismatches:
`tests_live/` does not exist; `RUN.md` is a pointer to OPERATIONS.

## 22. Closure classification
| class | items |
|---|---|
| MUST FIX FOR CLOSURE | F-R176-01 (gate is red; rotate + redact) |
| SHOULD FIX BEFORE EXTERNAL CONSUMPTION | F-R176-05, -07, -08, -09, -11, -10(product) |
| DOCUMENTATION / CONTRACT ONLY | F-R176-02, -03, -04, -06, O-01 |
| POST-RELEASE | multi-instance (Redis queue/limits/usage ledger), device identity, multi-AZ, SDK, webhook delivery relay |
| RESEARCH ONLY | learned routing, automatic training promotion |
| NOT A REAL GAP | client runtime / device trust (FUTURE), payments, `/docs` UI disabled |

## 23. Dependency-aware closure map
```
CURRENT (gate FAIL on committed secret)
  → FIX-01 redact + operator rotates keys            → gate PASS                       [no code]
  → FIX-07 SSRF numeric-host refusal                 → independent                     [core/events/webhooks.py]
  → FIX-04 credential deny-list in admin drafts      → independent                     [core/contracts/admin.py or apps/api/admin.py]
  → FIX-06 sanitizer/memory patterns                 → independent                     [core/learning/sanitizer.py (+ memory screen)]
  → FIX-03 execution_policy.strategy enum + 422      → check ui/app for literal strings [core/contracts/execute.py, apps/api/app.py]
  → FIX-05 idempotency body hash → 409               → durable needs migration 0019    [core/runtime/worker.py, apps/api/app.py, infra/db]
  → FIX-02 state-file pointer + §52 note             → after all, one doc commit
  → VERIFY: apps.cli check (hermetic) + durable pytest + gateway suite + rerun a4/a5/a6/a7/a8/a12 probes
  → FREEZE
```
No fix depends on another except FIX-02 (docs last). None touches architecture or ADR scope.

## 24. Exact fix plan (PROPOSED — none approved)
Common: one defect → one focused change → failing-first regression test captured on the parent commit → fix → same test passes →
affected suite → `apps.cli check` → one commit. Rollback for every fix = `git revert <sha>`.

| FIX | WHY (finding) | PROPOSED CHANGE | FILES | RISK | TEST PLAN | EXPECTED RESULT |
|---|---|---|---|---|---|---|
| FIX-01 | F-R176-01 | replace the three literal values at prompt lines 132–134 with `<REDACTED>`; operator ROTATES AssemblyAI key + old GitHub tokens (history keeps them) | `docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md` | none (doc) | `apps.cli check` secret scan | gate RESULT PASS |
| FIX-02 | F-R176-03/-04, O-01 | header pointer in `PROJECT_EXECUTION_STATE.md` → per-round ledgers; one line in §52 §2; OPERATIONS §4 note "trace is admin-only"; push-rule wording | 3 doc files | none | `apps.cli check` (docs untested) | fresh agent finds the ledger |
| FIX-03 | F-R176-05 (+F-R176-06) | `ExecutionPolicy.strategy: ExecutionStrategy \| None`; `/v1/execute` refuses strategies the composed slice cannot run with 422 `validation_error` field `execution_policy.strategy` (accept `single`, `agent`; `pipeline` only if wired); drop or validate `webhook_url` | `core/contracts/execute.py`, `apps/api/app.py`, `tests/api/test_execute_api.py` (+ `ui/app/app.js` audit for literals) | UI may send a literal → check first | failing-first: `debate`/`nonsense` → 422 on fix, 200 on parent | silent single-shot gone |
| FIX-04 | F-R176-07 | validator on `AdminDraftRequest.payload`: any key matching `(api_key\|apikey\|secret\|token\|password\|private_key\|credential)` at any depth → 422 field `payload` | `core/contracts/admin.py` (or draft route), `tests/admin/` | admin UI onboarding form must not send raw keys — audit `ui/admin` | failing-first L-14 shape | secret never stored/echoed |
| FIX-05 | F-R176-08 | idempotency record stores `body_sha256`; mismatch → 409 `idempotency_conflict`; durable: migration 0019 adds column | `core/runtime/worker.py`, `apps/api/app.py`, `infrastructure/db/migrations/versions/0019_*.py`, tests | migration on durable profile | failing-first R-03; durable pytest | conflict is loud |
| FIX-06 | F-R176-09 | add `gsk_`, `sk-ant-`, `AIza`, `xox[abpr]-`, generic `api[_-]?key\s*[:=]\s*\S{16,}` to `_VALUE_PATTERNS`; make memory screen import the same table | `core/learning/sanitizer.py`, `core/memory/memory.py`, `tests/learning/test_sanitizer_r161.py` | `SECRET_LABELS` grows (UI enumerates) | failing-first `gsk_` case | scan flags Groq-shaped secret |
| FIX-07 | F-R176-11 | in `validate_webhook_url`: if hostname matches `^[0-9a-fA-Fx.]+$` and is not a valid dotted-quad → refuse "ambiguous numeric host"; also refuse when `socket.inet_aton`-style parsing yields a non-public address | `core/events/webhooks.py`, `tests/events/` | none (stricter) | failing-first for `127.1`, `0x7f000001`, `2130706433` | 422 for all three |

Dependency blast radius (every fix): direct deps = listed files; indirect = OpenAPI document changes for FIX-03/04/05 (additive
error cases only); runtime impact = stricter refusals only; admin impact = FIX-04 payload rule; external-app impact = FIX-03/05 error
codes (documented); provider impact = none; learning impact = FIX-06 label set; test impact = +7 regression tests; rollback = revert.

Effect explanation template is satisfied per row: current behaviour (§19 "actual"), new behaviour ("expected"), what it enables
(closure of the finding), what it does not change (architecture, ADRs, routes), what could break (RISK column), how verified (TEST
PLAN), rollback (revert).

## 25. Probe coverage
```
P0 executed: 8/8
P1 executed: 44/46
P2 executed: 0/6
NOT PROBED: multi-instance run · config publish mid-flight · retry w/ foreign ambient tenant (wire) · skills import E2E from allowed
            source · not_poisoned heuristic · gateway streaming · browser UI live suite · webhook delivery
BLOCKED:    user-owned provider credential path (no key) · Groq live this round (org-restricted key — external)
```

## 26. Astra self-assessment
| area | rating | why |
|---|---|---|
| repository understanding | STRONG | entrypoints, composition root, gate, 79 routes executed |
| architecture understanding | STRONG | invariants checked by execution; ADR vs plan reconciled |
| security reasoning | STRONG | two-tenant concurrent + falsification; one real bypass found (F-R176-11) |
| dependency reasoning | ADEQUATE | blast radius listed; UI literal audits deferred to Phase B |
| agent reasoning | ADEQUATE | loop behaviour from tests + honest-stop runtime; no real-model run this round |
| learning reasoning | STRONG | poisoning chain executed end-to-end with control sample |
| provider reasoning | STRONG | live via gateway; failure taxonomy mapped; spend bounded (1 call) |
| external-app reasoning | STRONG | two independent consumers + repo example executed |
| evidence discipline | STRONG | every claim labelled; one false claim (RUN.md) corrected in a fixup commit |
| scope discipline | STRONG | zero product files touched; no fix executed |
| resume/recovery discipline | STRONG (learned) | 10 resets recovered; drafts lost 6× before adopting commit-before-run |
| change safety | UNVERIFIED | no change was made to verify against |

## 27. Approval matrix (updated after Phase B)
Operator approval (ledger row B0): "ابدأ من FIX-02 حتي النهايه" ⇒ `APPROVED: FIX-02..07`; FIX-01 NOT approved.

| FIX ID | Status | Approved? | Implemented? | Verified? | Git action | Result |
|---|---|---|---|---|---|---|
| FIX-01 | PROPOSED | **NO** | NO | NO | none | prompt file untouched; gate secret scan still FAIL (operator action: redact + rotate) |
| FIX-02 | DONE | YES | YES | docs (gate header fields intact) | 1 commit, 4 doc files | state file carries a resume pointer to `evidence/rNNN_state_ledger.md`; §52/README push wording; OPERATIONS trace admin-only |
| FIX-03 | DONE | YES | YES | YES | test eb83e77 → fix 005aa45 (+2 style) | 7 non-runnable strategies → 422 (fail-first 7/7 on parent); tests/api+events 560 passed |
| FIX-04 | DONE | YES | YES | YES | test 323dd79/66031cb → fix ff38b07/21460f2 | admin draft payload with credential-like key → 422 (fail-first 8/13); 578 passed; live L-14 rerun 422 |
| FIX-05 | DONE | YES | YES | YES | tests → fix (app.py + core/agent/runtime.py) | same key + different body → **409** `idempotency_conflict` (fail-first 3/3); 646 passed; live R-03 rerun 409, usage 1.0; **no migration needed** (request_hash durable since 0008) |
| FIX-06 | DONE | YES | YES | YES | test a84b422 → fix bd4bdd9/eb44553/804048b | Groq/Anthropic/Google/GitHub shapes flagged (fail-first 9/16); 120 passed; live A8 rerun `clean:false, label groq_api_key` |
| FIX-07 | DONE | YES | YES | YES | test 9788ff7 → fix bf5d0f9 (+ leading-digit tightening found by tests/api during FIX-03) | `127.1`/`0x7f000001`/`2130706433`/octal → 422 (fail-first 6/6); named hosts incl. bare `https://x` still 201; live F5 rerun all 422 |

Final gate after all approved fixes (`evidence/r176/B_fixes/final_gate/`): `apps.cli check` → pytest **3196 passed / 0 failed / 64 skipped** (floor 3127), ruff/format/mypy/import-linter green, **RESULT FAIL solely on the secret scan of the unapproved FIX-01 line** (prompt :132). Gateway suite 194 passed. Probe reruns a6/a7/a8/a10/a12 against a hermetic server: all previously-open runtime findings now refuse loudly; isolation/401/403/usage invariants unchanged.

## 28. Evidence matrix
| Area | Static | Hermetic | Real Runtime | Real Provider | Final Status |
|---|---|---|---|---|---|
| Auth | ✓ | ✓ (identity/security suites) | ✓ A4/A5/A12 | n/a | VERIFIED |
| Tenant Isolation | ✓ | ✓ | ✓ concurrent 2-tenant | n/a | VERIFIED |
| Authorization | ✓ | ✓ 385 | ✓ direct/async/tool/skill/role | R165 (agent w/ real model, prior) | VERIFIED |
| Credential Isolation | ✓ | ✓ | ✓ 0 leaks | ✓ A9 gateway (mode-only envelope) | VERIFIED (user-owned path BLOCKED) |
| Agent | ✓ | ✓ 585 | ✓ honest stop, tool refusal | R165/R175 prior | VERIFIED (platform) / LIVE (prior) |
| Skills / Tools | ✓ | ✓ | ✓ gates | — | VERIFIED at gates; E2E import NOT PROBED |
| Learning | ✓ | ✓ | ✓ poisoning chain | — | VERIFIED; pattern gap F-R176-09 |
| Admin Control | ✓ | ✓ | ✓ lifecycle + stale-config + audit | — | VERIFIED; F-R176-07 |
| Provider Routing | ✓ | ✓ 752+194 | ✓ 503/refusals | ✓ AssemblyAI (R176), Groq (R175) | VERIFIED |
| External Consumer | ✓ OpenAPI | — | ✓ 3 consumers | — | VERIFIED; F-R176-10 friction |
| Recovery / Resume | ✓ | ✓ fabric/chaos | ✓ 10 resets, bundle restores | — | VERIFIED |
No tier is implied where it was not run: durable-DB runtime this round = R175 evidence only; browser = prior round only.

## 29. Closure decision — exactly one
**BOUNDED FIX SET — EXECUTED (6 of 7).** FIX-02..07 are approved, implemented, verified and on `origin/main`; every product change
is guarded by a failing-first regression test and the full gate is green except the secret scan. **FREEZE is blocked by exactly one
operator-owned item**: FIX-01 (redact the three literal values at prompt lines 132–134 and rotate the AssemblyAI key + GitHub tokens
that appear in history). Once FIX-01 lands, `apps.cli check` is expected to report RESULT PASS with no further code change.

## 30. Resume command
```bash
GITHUB_TOKEN=<PASTE_GITHUB_TOKEN_HERE> bash -c '
git fetch origin main && git status -sb && tail -3 evidence/r176_state_ledger.md \
&& python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]" \
&& env -u GSK_API_KEY -u GROQ_API_KEY -u GW_GROQ_API_KEY -u DATABASE_URL .venv/bin/python -m apps.cli check'
```
```
RESUME ARTIFACT:   evidence/r176_state_ledger.md  (last row = where to continue; checklist table = what is DONE/PENDING/WAIT)
RESUME COMMAND:    above (token goes to the git credential store only — never into the tree)
RESUME TEST:       executed 10× this round (resets #18–#27); bundle restore path executed 2×
RESULT:            PASS
EVIDENCE:          evidence/r176/00_session_start/, evidence/r176/01_resume_memory_audit/, ledger rows A0/A1/A3′/A5–A12
```

## 31. Execution instruction
No FIX may be executed now. Phase B opens only on an explicit operator message of the form `APPROVED: FIX-01, FIX-07 …`.
Recommended order if all are approved: FIX-01 → FIX-07 → FIX-04 → FIX-06 → FIX-03 → FIX-05 → FIX-02 → final gate → FREEZE.
Independently of approval: **rotate the AssemblyAI key and every GitHub token that appeared in chat or in the committed prompt.**
