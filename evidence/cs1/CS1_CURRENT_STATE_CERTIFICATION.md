# CS1 — CURRENT-STATE CERTIFICATION of QEVION (main `a99e2545`, 2026-09-16)

New validation task (NOT R186; R186 stays closed at `r186-close-records`). Everything below was measured on the
actual repository and the actual runtime (`python3 -m apps.main` + `gateway-service/app.py`, both processes
stripped of ambient provider variables) behind a sandbox-lifetime public URL. Evidence:
`evidence/cs1_state_ledger.md` rows 1–9, `evidence/cs1/api_probe.json`, `evidence/cs1/browser/*`.
Nothing is called READY unless demonstrated.

## A. VERIFIED (real runtime evidence)

**Security / correctness — 54 live probes, 0 FAILED (three independent runs; first run 58/0)**
- Authentication: register 201 → console-delivered verification token (by design: real e-mail forbidden) →
  login 200 with opaque `secrets.token_urlsafe(32)` token; Argon2id password hashing
  (`infrastructure/security/password.py`); wrong password / unknown e-mail / garbage bearer / wrong auth scheme →
  ONE constant 401 body (no user enumeration, no scheme oracle); duplicate registration → generic 422;
  logout 204 revokes (session → 401); logout of a revoked token → 204 (no liveness oracle).
- Authorization / tenancy: anonymous admin → 401; non-admin on 6 admin routes → 403; cross-tenant execution
  read / SSE events → 404 (anti-enumeration), cross-tenant admin evaluations → 403; list isolation; `tenant_id`
  query cannot re-scope.
- API hygiene: malformed JSON / unknown field (`extra=forbid`) / oversized body / non-UUID → 422 envelopes, no
  traceback; unknown route 404; global `Exception` handler → constant "Internal error."; `/docs` off; no CORS
  allow for foreign origins; static path traversal refused.
- Provider boundary: `/v1/admin/system` exposes provider **names** only; disabled provider → 503 with no upstream
  call; unknown model → 503; unresolvable `route_token_ref` → 409 refusal (R174 F-3 fix holds); gateway rejects
  missing / wrong shared secret with 401; the provider key exists ONLY in the gateway process environment.
- Engineering runtime (hermetic): `tests/engineering tests/security tests/identity tests/secrets` → 208 passed
  (jail, symlink escape, denylist, command allow-list, ticket ledger); manifest/state guards 27 passed.

**AssemblyAI — real, paid, 3 successful calls**
- Support boundary (inspected first): AssemblyAI is a **gateway-service** provider
  (`gateway-service/providers/assemblyai`, operation `generate_text` — an LLM text gateway, **not** speech),
  NOT a direct platform adapter. Reached only via `GATEWAY_BASE_URL/SECRET/SECRET_VERSION/ROUTE_TOKENS` →
  `POST /v1/admin/providers/onboard` (refs only) → change lifecycle enable → `POST /v1/execute`.
- Live: onboard 201 (registered DISABLED) → draft/validate/preview/publish 200 → `/v1/models` lists
  `assemblyai/qwen3.5-4b-32k-fast` → `POST /v1/execute explicit_model` → **200 `succeeded`, 358–539 ms, content
  exactly "chain verified"**, usage reserved 1 / settled 1; execution record, usage row
  (`evaluation_status = NEVER_EVALUATED`), admin evaluations and audit all readable.

**Command Center in a real browser — 31 items VERIFIED (public URL, Chromium)**
- Login view → wrong-password error → login → 23 capability nodes, 2 orbit dots, 10 running animations;
  Core `Enter` → overview dialog (server facts) → focus moves in → `Escape` → focus returns to Core;
  node `Enter` → record dialog → `Escape` → focus returns to node; pointer click + close button;
  cursor/focus-visible feedback; orbit dot `Enter` → execution record; execute success path (`succeeded`,
  stage single 100 %, evaluation badge `NEVER_EVALUATED`, graph 5 nodes, 4 stream frames);
  820 / 600 / 390 px → 0 px horizontal overflow, Core centred; 390 px after a converse turn → no `undefined`,
  0 px overflow; reduced motion → 0 running animations; Core `data-state` in the closed set; no secret shapes
  in DOM / web storage; logout → login view; zero page exceptions.

## B. FIXED DURING THIS TASK
**None.** Every real defect found lives in a tree the executor may not change without an operator-declared round
(`ui/app/command/` frozen; `apps/` composition) or is operator-owned (key rotation). No production, UI, manifest
or contract file was touched: `git diff origin/main..HEAD` = `evidence/` only.

## C. FAILED (measured, reproducible, root-caused)
- **F-CS1-01** — session does not survive a page reload: `command.js` keeps the bearer token in a JS variable only.
  Experience defect, not a security defect (nothing persisted → nothing to steal). Fix = `sessionStorage`-scoped
  token + boot probe inside `ui/app/command/` → requires a declared round.
- **F-CS1-02** — desktop (1440 px): Core sits 178 px left of the viewport centre because `.center` reserves a
  340 px detail column while `#node-detail` is hidden; centred at ≤ 900 px. Cosmetic/experience; same frozen tree.
- (informational) **F-CS1-03** — one console resource error on load: the by-design unauthenticated
  `GET /v1/auth/session` identity-mode probe returns 401. No page exception. Not a defect.

## D. BLOCKED (external / operator-owned)
- **F-CS1-04 — SECURITY, HIGH, pre-existing.** The AssemblyAI key supplied for this task is byte-identical to the
  key committed in plaintext to this **public** repository on 2026-09-07 (`521d8850`,
  `docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md`), redacted in the tree on 2026-09-09
  (`28989b04`, R177 DEC-02) but never purged from history and — proven by today's three successful paid calls —
  **never rotated**. Anyone who cloned the public repository since 2026-09-07 can spend on this account.
  Executor cannot rotate keys or rewrite public history.
- GitHub token rotation (D-R185-4) — overdue, operator-owned (token used transiently only; 0 occurrences in files,
  history, `.git/config`, PR metadata).
- Successful live **Groq** execution — BLOCKED by the external `organization_restricted` state (not re-tested: no
  Groq key in this environment).

## E. UNAVAILABLE / NOT IMPLEMENTED (by contract or operator decision — unchanged)
- Runtime "thinking / responding" Core state; token-by-token text (`delta` never emitted) — NOT AUTHORIZED.
- Provider onboarding UX beyond the API door, App Factory, API keys, webhook delivery, real e-mail — UNDEFINED BY
  OPERATOR.
- Deployment / hosting configuration — none in the repository (OUT OF SCOPE until declared).
- Hardening gaps without a contract behind them: no `X-Content-Type-Options` / `X-Frame-Options` / CSP / HSTS
  headers (I-2); `/openapi.json` served unauthenticated (I-1, route inventory only, no secrets).

## F. NOT TESTED
Durable (Postgres/Redis) profile; multi-process scope; browsers other than Chromium; load/concurrency;
`ui/admin` and `/app/` interaction depth; the `reasoning_failed` UI path was not naturally re-triggered on this
stack (on this stack `agent converse` returns an honest empty `final` turn — guarded by the R186 tests);
Groq success path.

## G. Answers
1. Backend/Core testable? **YES** — live API surface exercised end-to-end; hermetic suites green.
2. Command Center interactive? **YES** — every apparently interactive control works (Core, nodes, orbit, dialogs,
   composer, logout); none found inert-but-misleading or broken.
3. UI visually coherent? **PARTIALLY** — hierarchy and constellation coherent; desktop stage left-biased
   (F-CS1-02); the execution section is a separate full-width form below the fold (recorded design, not a defect).
4. UI responsive? **YES** at 390 / 600 / 820 px; desktop centring is the exception above.
5. Failure path correct? **YES** — honest envelopes (401/403/404/422/503), no traceback, no `undefined`.
6. Successful provider-backed execution verified? **YES — AssemblyAI via the gateway, 3/3.** Groq: **NO** (BLOCKED).
7. AssemblyAI integrated and verified? **YES**, as an LLM text-generation gateway provider through the real admin
   door; NOT as speech.
8. End-to-end testable? **YES** — API + browser + real provider success path + failure paths, today.
9. Real deployment? **NO** — sandbox-lifetime process preview only; no deployment configuration exists.
10. Exact blockers: F-CS1-04 (key exposed & unrotated); GitHub token rotation; Groq organization restriction.
11. Operator decisions required: (a) rotate the AssemblyAI key NOW; decide on public-history purge;
    (b) rotate the GitHub token; (c) declare or decline a UI round for F-CS1-01 / F-CS1-02 (`ui/app/command/`,
    ceiling 0, RED-first); (d) declare or decline a hardening round for I-1 / I-2 (`apps/` composition);
    (e) Groq organization.
12. Gap before calling the CURRENT build fully testable: none on the current contract except operator convenience
    (F-CS1-01) and the external Groq success path. It is testable today via the process preview; it is not deployed.

## H. Resume checkpoint
Branch `genspark_ai_developer_cs1` (records only) over `main` a99e2545; `evidence/cs1_state_ledger.md` last row =
checkpoint. Preview is sandbox-lifetime; relaunch with `/home/user/preview/run_stack.sh` (outside the repo; needs
`ASSEMBLYAI_API_KEY` + `ADMIN_EMAILS` in the caller env; admin password generated per run, stored only outside
the repo).
