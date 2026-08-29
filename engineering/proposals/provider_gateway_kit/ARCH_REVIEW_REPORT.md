# PROVIDER GATEWAY — ARCHITECTURE REVIEW + EXTERNAL PROJECT & API BLUEPRINT

**Session:** 2026-08-29 · Planning/architecture-review only (operator-authorized).
**Repo state reviewed:** HEAD `08c8f58368f46a8eb7920e1e5927ac4783599911`,
tree `846527ac9d21ea9b02be1b3f5b2c4cb812daaadf`, worktree clean, 1515 tests collected.
**Discipline:** every claim tagged `[VERIFIED]` (command + output executed in-session),
`[INFERRED]`, `[PROPOSED]`, or `[OPEN]`. Never-fake (41 §49) applies: nothing below
is claimed as implemented — this is a specification for future authorized work.

---

## 1 — Current Repository Reality

**[VERIFIED]** Reality ritual executed:

```
$ git status                 → working tree clean
$ git rev-parse HEAD         → 08c8f58368f46a8eb7920e1e5927ac4783599911
$ git rev-parse HEAD^{tree}  → 846527ac9d21ea9b02be1b3f5b2c4cb812daaadf
$ git diff --stat            → (empty)
$ git log --oneline -1       → 08c8f58 docs(proposals): add provider-gateway design kit as prior-art
$ git remote -v              → origin https://github.com/belalalibb/general_ai_core.git
```

**[VERIFIED]** Recovery note: at session start local HEAD was `6364a2b` (R102) and the
prior-art kit was ABSENT from the local tree. `git fetch` revealed operator-pushed
commit `08c8f58` on origin/main adding the kit (11 files, 2120 insertions);
`git merge --ff-only origin/main` applied. Without the fetch this review would have
been built on an incomplete tree.

**[VERIFIED]** State file: `RESUME_TOKEN = PROJECT|R102|GROQ_LIVE_VERIFIED_6_OF_6_PLUS_GSK_8_OF_8_SAME_RUN|ALL_14_LIVE_PROVIDER_TESTS_GREEN|...`
— Lane B complete; no pending agent work without new authorization.

**[VERIFIED]** `pytest --collect-only` → **1515 tests collected**.

## 2 — Evidence / Verification (commands executed this session)

| Evidence | Source (read in-session) |
|---|---|
| `ProviderAdapterPort` — 7 methods | `core/providers/ports.py:57` |
| `ProviderOperation` — **11 operations**, closed StrEnum | `core/contracts/provider.py:41` |
| `ProviderErrorCategory` — **12 categories** verbatim | `core/contracts/provider.py:312` |
| `ProviderGenerateRequest/Response` envelopes | `core/contracts/provider.py:385+` |
| `ProviderManifest.id: BoundedStr` (NOT a UUID) | `core/contracts/provider.py:195` |
| `SecretManagerPort` (store/resolve/revoke, tenant-scoped) | `core/secrets/ports.py:37` |
| Groq adapter: `secret_resolver` callable + injectable httpx transport + `GROQ_BASE_URL` constant inside the adapter | `providers/real/groq/adapter.py:54,91-119` |
| GenSpark adapter, same pattern | `providers/real/genspark_llm/adapter.py:62` |
| Router: `SimpleScoringRouter.route()` supports AUTO/TIER/EXPLICIT | `core/routing/router.py:82-132` |
| Usage: reserve BEFORE provider work; settle/fail after | `core/usage/ports.py:36-63` + `core/execution/service.py:378-380` |
| Admin: enable/disable provider by `provider_key`; rejects template providers | `core/admin/service.py:333-345` |
| 11 import-linter contracts (core forbidden from sqlalchemy/redis/otel/argon2/boto3/hvac…) | `pyproject.toml` |
| **No gateway/route_token code exists in the production tree** — grep over `core/ apps/ providers/real/ infrastructure/` returned only descriptive comments in genspark ("aggregation gateway" as provider description) | grep executed in-session |
| Composition pattern exists: `apps/composition/{storage,secrets}.py` are the ONLY construction sites | `ls apps/composition/` |

**[VERIFIED — side finding]** `httpx` is used by production adapters
(`providers/real/*/adapter.py`) but pinned only in `[project.optional-dependencies].dev`,
not main dependencies. Pre-existing condition; will also affect any new
RemoteGatewayAdapter → recorded as OPEN-6.

## 3 — Existing Provider Architecture (as it actually is)

**[VERIFIED]** Current path:

```
API (apps/api) → SimpleScoringRouter (picks provider+model+binding from registries)
             → ExecutionService (reserve → adapter.generate → settle/fail)
             → ProviderAdapterPort ← GroqAdapter / GenSparkLLMAdapter
                                      │ direct httpx to upstream
                                      │ secret_resolver(credential_ref) at last moment
```

Key design-relevant facts:

- **[VERIFIED]** The internal envelope `ProviderGenerateRequest` already carries:
  `request_id, tenant_id, operation, provider_model_name, credential_ref, payload,
  timeout_ms` — the prior-art HTTP envelope is nearly a wire translation of it.
  Strongest compatibility evidence in the whole review.
- **[VERIFIED]** Current provider identity is layered: `Provider.id` (UUID, domain) +
  `Provider.provider_key` (string) + `ProviderManifest.id` (**BoundedStr** — in tests
  equal to provider_key). The prior art's "ProviderManifest.id = UUID" contradicts
  repository reality (corrected in §13).
- **[VERIFIED]** Upstream URLs today live INSIDE the adapters (constants), not in core —
  "Platform doesn't know endpoints" is already half-true: core doesn't, but the
  platform repo does. The Gateway moves that knowledge out of the repo entirely.

## 4 — Prior Art Evaluation (critical)

### Good — keep
1. **route_token opacity + internal resolution map that never leaves the Gateway** —
   matches the platform's existing anti-enumeration posture (ObjectNotFound collapse).
2. **DEFINITION declaration as sole eligibility source (no introspection)** — matches
   ProviderManifest philosophy verbatim ("registry trusts ONLY the declaration", 30 §4.2).
3. **The 12 error categories verbatim** — **[VERIFIED]** exact match with
   `ProviderErrorCategory`.
4. **`unsupported_capability` instead of silent None** — protects reserve/settle.
5. **Rotation ≠ Kill-switch (revoke identity, not change value)** — correct engineering.
6. **Out-of-band provisioning; no public registration endpoint** — correct.
7. **ProviderContext hides slug/route_token from handlers** — excellent isolation.

### Weak — change
1. **`from app import ProviderContext, ok, err` in the template** — providers import
   from the application file: inverted dependency + providers untestable in isolation.
   Contracts must live in `gateway/contracts.py`. **(mandatory change)**
2. **Flask sync** — the platform is fully async (httpx.AsyncClient adapters).
   Sync gateway = concurrency bottleneck + non-shared contract shapes. → OPEN-5.
3. **Exact-match secret-version rejection** ⇒ every rotation causes a guaranteed
   outage window (two parties can't sync atomically). → dual-accept window.
4. **`GATEWAY_ROUTES_JSON` in env** — no rotation without restart, unclear ownership.
   → reloadable protected source.
5. **`assert category in ERROR_CATEGORIES`** — deleted under `python -O`; a security
   check that silently disappears. → explicit validation.
6. **Inconsistent HTTP status mapping** (unknown route sometimes 404, sometimes 200;
   unsupported returns 200) → explicit status table (§9).
7. **Fixed per-operation routes AND an `operation` field in the envelope** — double
   encoding that can conflict (POST /generate with operation=create_embeddings is
   undefined). → §7 resolves.
8. **`provider_code=type(exc).__name__` in the catch-all** — leaks internal exception
   names (possibly SDK names ⇒ partial source leak). → sanitize.

### Over-engineered
Nothing structural — the kit is well-sized. Only: mandating AppRole "from day one" on
local/RDP may be heavier than needed as a first step; kept as the architectural target
with a staged simpler start (§16).

### Conflicts with repository reality
1. **"provider_slug = ProviderManifest.id"** (00_CONTRACT §1) — applied literally it
   would expose the slug inside the platform and couple manifest identity to a
   Gateway-internal name. Newer kit files self-correct ("slug never appears") but the
   internal contradiction must be resolved: **manifest.id = admin-chosen provider_key,
   unrelated to the slug** (§13). **[Conflict — resolved]**
2. **"ProviderManifest.id = stable UUID"** — actual type is BoundedStr; the UUID is
   `Provider.id`. **[VERIFIED conflict — corrected]**
3. **Kit's operation table covers 8 of the 11** `ProviderOperation` values (missing:
   `run_provider_agent`, `upload_asset`, `download_asset`) → explicit stance required (§7).

## 5 — Proposed Gateway Architecture (Deliverable A)

**[PROPOSED]**

```
┌─────────────────────────── PLATFORM (Control Plane) ───────────────────────────┐
│  API → Router (AUTO/TIER/EXPLICIT) → ExecutionService (reserve→execute→settle) │
│                                            │                                   │
│         ProviderAdapterPort (unchanged) ───┼──────────────┐                    │
│              │                │            │              │                    │
│         GroqAdapter    GenSparkAdapter   RemoteGatewayAdapter  ← NEW, generic  │
│         (as-is, direct)  (as-is, direct)   │  one class; N instances           │
│                                            │  (instance per activated          │
│  Platform stores per gateway-provider:     │   gateway provider)               │
│   provider.id (UUID) · provider_key ·      │                                   │
│   display_name · gateway_base_url ·        │  builds manifest from /describe   │
│   route_token(opaque) · status ·           │  resolves credential_ref → value  │
│   credential_mode                          │  at last moment (existing pattern)│
└────────────────────────────────────────────┼───────────────────────────────────┘
                              TLS + X-Gateway-Secret(+Version) │ private network
┌────────────────────────────────────────────▼───────────────────────────────────┐
│                    PROVIDER GATEWAY (Data Plane — raw execution)                │
│  security middleware (secret+version, dual-accept) → envelope validation        │
│  → Route Registry: route_token → internal slug (secret map, reloadable)         │
│  → Provider Registry: slug → DEFINITION + handlers (packages, lazy-load)        │
│  → Credential Resolver: user_key(from envelope) | platform(internal, by slug)   │
│  → handler(ProviderContext) → upstream API/SDK/accounts                         │
│  → Error Normalizer (12 categories) → unified Response Envelope                 │
│                                                                                  │
│  Gateway stores: route map · provider packages · platform-mode credentials ·    │
│                  its own secret material. Gateway does NOT store: tenants,      │
│                  plans, quotas, usage ledgers, routing policy.                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Component responsibilities (who owns what):**

| Concern | Platform | Gateway |
|---|---|---|
| Authorization / tenant isolation / entitlements / plans / quota | ✅ alone | ❌ |
| Provider+model selection (routing) | ✅ alone | ❌ (executes the choice only) |
| Usage reserve/settle/refund/fail + billing | ✅ alone | ❌ (returns raw usage evidence only) |
| Provider activation / eligibility (deny-by-default) | ✅ (Admin + manifest from /describe) | ❌ (declares, never decides) |
| route_token issuance | ✅ (single issuer) | ❌ (consumer of the mapping only) |
| Upstream endpoints / SDKs / accounts / OAuth / cookies | ❌ never knows them | ✅ alone |
| BYOK custody (Vault, credential_ref) | ✅ | ❌ (receives value per-request, memory-only) |
| Platform-mode credentials | ❌ doesn't even know their kind | ✅ alone |
| Error normalization to the 12 categories | (re-normalizes defensively) | ✅ first |

**"One adapter, N instances" pattern:** one generic `RemoteGatewayAdapter` class
implements the EXISTING `ProviderAdapterPort` with zero changes to it. Each activated
gateway provider = one instance with its own
`(gateway_base_url, route_token, credential_mode, secret_resolver?)`, registered in the
existing `ProviderRegistry` like any other adapter. **Router / ExecutionService / Usage
never know it is remote — that is the essence of minimal change.**

## 6 — Gateway Project Structure (Deliverable B)

**[PROPOSED]** Separate repository `provider-gateway/`:

```
provider-gateway/
├── app.py                      # entrypoint ONLY: build_app() + uvicorn run. No logic.
├── gateway/                    # the core package (providers depend on it, never on app.py)
│   ├── contracts.py            # RequestEnvelope / ResponseEnvelope / GatewayError /
│   │                           #   12 error categories (verbatim) / ProviderContext /
│   │                           #   DEFINITION schema — all pydantic, extra="forbid"
│   ├── config.py               # env/config loading; misconfig = loud ValueError at startup
│   ├── auth.py                 # secret+version middleware; dual-accept; constant-time compare
│   ├── routes.py               # HTTP surface (thin: validate → dispatch → respond)
│   ├── route_registry.py       # route_token → internal slug; reloadable WITHOUT restart
│   ├── provider_registry.py    # package discovery; eager DEFINITION validation at startup;
│   │                           #   lazy handler import; duplicate slug = startup error
│   ├── context.py              # ProviderContext construction (hides slug/route_token)
│   ├── credentials.py          # user_key (from envelope) | platform (internal, by slug)
│   ├── errors.py               # normalization + HTTP status map + provider_code sanitizer
│   ├── discovery.py            # /describe projection (hides slug + upstream identity)
│   └── observability.py        # closed allowed-fields log/metric emission (§21)
├── providers/
│   ├── _template/              # copy-me package
│   │   ├── definition.py       # DEFINITION only
│   │   └── handlers.py         # operation handlers importing gateway.contracts
│   └── <provider_pkg>/         # one PACKAGE per provider (may add _session.py,
│                               #   _accounts.py … — prior art used single files)
└── tests/
    ├── test_contracts.py  test_auth.py  test_route_registry.py
    ├── test_provider_registry.py  test_dispatch.py  test_discovery.py
    └── providers/               # per-provider hermetic tests
```

**Dependency direction (fixes prior-art weakness #1):**

```
providers/*  ──imports──▶  gateway/contracts.py  ◀──imports──  gateway core  ◀──  app.py
```

Providers never import `app.py`; `app.py` contains zero logic. Every provider package is
testable in complete isolation against `gateway/contracts.py` alone.

## 7 — API Surface (Deliverable C)

**[OPEN-1 → recommendation: unified endpoint]** The prior art defines fixed
per-operation routes (`POST /generate`, `POST /embeddings`, …) AND an `operation`
field in the envelope — double encoding that can conflict (prior-art weakness #7).
Recommended: **one `POST /v1/execute`** with `operation` in the envelope as the single
source of truth. This kills the conflict class, matches the internal
`ProviderGenerateRequest` shape 1:1, and means new operations never add routes.

| Method + Path | Auth | Purpose |
|---|---|---|
| `POST /v1/execute` | Secret+Version | Execute any declared operation (envelope carries `operation`) |
| `GET /v1/describe` | Secret+Version | Provider manifest projection (per route_token) |
| `GET /v1/models` | Secret+Version | Declared model list (subset of describe, cheap) |
| `GET /v1/health` | Secret+Version | Provider-level health (may be `UNKNOWN`) |
| `GET /healthz` | none | Gateway process liveness only (no provider info, no secrets) |

**[OPEN-2 → recommendation: out of v1 scope]** `run_provider_agent`, `upload_asset`,
`download_asset` (3 of the 11 `ProviderOperation` values, absent from the prior-art
kit) are **excluded from Gateway v1**: they imply streaming/large-binary/long-poll
semantics that deserve their own contract revision. A DEFINITION declaring any of the
three is **rejected at load time** with an explicit error — honest failure instead of
silent partial support.

## 8 — Request Envelope

**[PROPOSED]** `RequestEnvelope` (pydantic, `extra="forbid"`):

| Field | Type | Semantics |
|---|---|---|
| `route_token` | str | Opaque routing credential (sensitive). Only key the platform holds for addressing a provider. |
| `operation` | str (closed set) | One of the platform's `ProviderOperation` values declared in DEFINITION. |
| `model` | str | Exact upstream model name. **Gateway never substitutes or redirects models.** |
| `request_id` | str | Platform-issued correlation id; passed upstream where supported (idempotency evidence). |
| `tenant_id` | str | Evidence/audit only. **The Gateway makes zero decisions on it** (no per-tenant state). |
| `credential` | object | `{mode: "user_key"\|"platform", value?: str}` — `mode` MUST match the provider DEFINITION else `bad_request`. `value` present only for `user_key`; memory-only, never persisted/logged. |
| `payload` | object | Operation-specific payload (same shape family as internal envelope's payload). |
| `timeout_ms` | int | Upper bound the Gateway enforces toward upstream. |

Forbidden by construction: `provider_slug`, `upstream_url`, or any Gateway-internal
identifier — the envelope cannot address a provider except via `route_token`.

## 9 — Response Envelope + HTTP Status Map + Wire Examples

**[PROPOSED]** Status discipline:

| HTTP | Meaning |
|---|---|
| `200` | Envelope delivered — includes BOTH success and **execution failures** (adapter reads `error.category`; mirrors internal `ProviderGenerateResponse.succeeded`) |
| `400` | Malformed envelope → `bad_request` |
| `401` | Gateway auth failure. Wrong secret = `invalid_credential`. **Stale version = `auth_expired`, `retryable: true`** → adapter re-reads Vault and retries once: rotation becomes self-healing |
| `404` | Unknown / revoked / disabled route_token → **uniform** `provider_unavailable` "unknown route" (anti-enumeration: identical body for all three causes) |
| `500` | Gateway internal fault → `retryable_server_error`, sanitized `provider_code` (never exception class names — prior-art weakness #8) |

All examples use placeholder values; headers on every authed call:
`X-Gateway-Secret: <value>` + `X-Gateway-Secret-Version: 7`.

**A — execute request**
```http
POST /v1/execute HTTP/1.1
X-Gateway-Secret: <secret-value>
X-Gateway-Secret-Version: 7
Content-Type: application/json

{
  "route_token": "rtk_kJ8vN2xQ...opaque...",
  "operation": "generate_text",
  "model": "upstream-model-name",
  "request_id": "req_01J8...",
  "tenant_id": "ten_01J8...",
  "credential": {"mode": "user_key", "value": "<user-provided-key>"},
  "payload": {"messages": [{"role": "user", "content": "..."}]},
  "timeout_ms": 30000
}
```

**B — success (200)**
```json
{
  "succeeded": true,
  "output": {"text": "...", "finish_reason": "stop"},
  "usage": {"input_tokens": 431, "output_tokens": 208, "units": 1},
  "latency_ms": 812,
  "error": null
}
```

**C — unsupported operation (200, execution failure)**
```json
{
  "succeeded": false, "output": null, "usage": null, "latency_ms": 3,
  "error": {"category": "unsupported_capability", "retryable": false,
            "message": "operation not declared by this provider", "provider_code": null}
}
```

**D — upstream rate limit (200, execution failure)**
```json
{
  "succeeded": false, "output": null, "usage": null, "latency_ms": 240,
  "error": {"category": "rate_limited", "retryable": true,
            "retry_after_ms": 2000, "message": "upstream rate limit", "provider_code": "429"}
}
```

**E — describe (200)** — note: NO slug, NO upstream identity
```json
{
  "display_name": "Example Provider",
  "credential_mode": "user_key",
  "capabilities": {"text_generation": true, "embeddings": false},
  "operations": ["generate_text"],
  "models": [{"name": "upstream-model-name", "context_window": 128000}],
  "definition_version": "1.2.0",
  "health_supported": true
}
```

**F — models (200)**
```json
{"models": [{"name": "upstream-model-name", "context_window": 128000}]}
```

**G — health (200)**
```json
{"status": "UNKNOWN", "checked_at": null}
```

**H — wrong secret (401)**
```json
{"error": {"category": "invalid_credential", "retryable": false,
           "message": "gateway authentication failed"}}
```

**I — stale secret version (401, self-healing)**
```json
{"error": {"category": "auth_expired", "retryable": true,
           "message": "secret version 5 no longer accepted; current is 7"}}
```

**J — unknown/revoked/disabled route (404, uniform)**
```json
{"error": {"category": "provider_unavailable", "retryable": false,
           "message": "unknown route"}}
```

## 10 — Provider DEFINITION Schema

**[PROPOSED]** Sole eligibility source (matches ProviderManifest philosophy — the
registry trusts ONLY the declaration; never introspection):

| Field | Rule |
|---|---|
| `display_name` | Human label; the only name that may cross the boundary |
| `definition_version` | semver; bump → platform rebuilds manifest, nothing else |
| `credential_mode` | `"user_key"` \| `"platform"` — checked against every envelope |
| `capabilities` | Deny-by-default map over the PLATFORM's closed capability keys |
| `operations` | ⊆ the 11 `ProviderOperation` values; **each declared operation MUST have a registered handler** |
| `models` | Declared list; `[]` is honest and valid |
| `health_supported` | bool; false ⇒ /v1/health returns `UNKNOWN` |

**Stricter than prior art:** an operation declared without a handler (or handler
without declaration) is a **STARTUP failure**, not a runtime 500 — the gateway refuses
to boot with a lying DEFINITION.

## 11 — Provider Registry (Gateway-side)

**[PROPOSED]**
- Auto-discovery of packages under `providers/` (skip `_`-prefixed).
- **Discovery ≠ activation**: a discovered provider with no route_token mapping is
  simply unreachable — the platform's deny-by-default extends across the wire.
- Eager DEFINITION validation at startup; lazy handler import at first dispatch
  (heavy SDK imports don't block boot; broken DEFINITIONs still fail loud).
- Duplicate slug across packages = startup error.
- Disable paths: per-provider flag in gateway config, or route-map line removal
  (both take effect without code change; the latter without restart).

## 12 — Discovery / Manifest Flow

**[PROPOSED — Option A recommended]** Three options weighed:
- **A. DEFINITION declaration → /describe projection** ✅ — single source of truth,
  matches platform manifest philosophy verbatim.
- **B. Runtime introspection of handlers** ❌ rejected — violates deny-by-default
  ("code exists" ≠ "capability declared"); exactly what ProviderManifest was built to prevent.
- **C. Separate manifest file maintained beside code** ❌ rejected — second source of
  truth, guaranteed drift.

`/describe` unavailable behavior: at FIRST registration → registration fails loud (no
manifest = no activation). For an EXISTING provider → platform keeps the last known
manifest, marks health `UNKNOWN`; **no auto-disable** (transient gateway outage must
not de-register providers).

## 13 — Identity Model (5 layers, no derivation)

**[PROPOSED — resolves both prior-art conflicts]**

| Layer | Type | Owner | Rotation | Crosses boundary? |
|---|---|---|---|---|
| `Provider.id` | UUID | Platform domain | never | no |
| `provider_key` (= `ProviderManifest.id`, **BoundedStr**) | admin-chosen string | Platform admin | never (identity) | no |
| `display_name` | string | Gateway DEFINITION | free | yes (the only name that does) |
| internal `slug` | string | Gateway | on gateway's terms | **never** |
| `route_token` | opaque secret | Platform-issued | freely | yes (as credential, not name) |

**No hash/derivation between any two layers.** Rotating a route_token changes nothing
about provider identity; renaming a slug is invisible to the platform. This corrects
prior-art conflict #1 ("slug = manifest.id") and #2 ("manifest.id = UUID" — the actual
type is BoundedStr **[VERIFIED]** `core/contracts/provider.py:195`; the UUID is `Provider.id`).

## 14 — route_token Lifecycle

**[PROPOSED]**
- Generation: `secrets.token_urlsafe(32)` ⇒ ≥256-bit entropy. **Platform is the sole issuer.**
- Storage: platform side as a secret (via existing `SecretManagerPort`); gateway side
  only inside the protected route map.
- Provisioning: **out-of-band only** (operator copies into gateway route map). No HTTP
  registration endpoint exists, by design (keep from prior art).
- Revocation: remove the route-map line → instant uniform 404-J. Per-provider,
  immediate, no restart (reloadable registry, §11).
- **[OPEN-3 → recommendation: header]** Prior art put the token in the URL path/query
  for GETs → tokens land in access logs and proxies. Recommended: `X-Route-Token`
  header on all endpoints including GETs.

## 15 — Credential Handling (both modes)

**[PROPOSED]**
- **user_key (BYOK):** resolved **PLATFORM-side** at the last moment via the existing
  `secret_resolver(credential_ref)` pattern (**[VERIFIED]** same as
  `providers/real/groq/adapter.py:91`), then crosses TLS inside the envelope,
  **memory-only** on the gateway (never persisted, never logged). Deliberate choice:
  the alternative — giving the Gateway direct access to tenant-secret Vault — would
  hand the data plane a far bigger blast radius over ALL tenants' secrets.
- **platform mode:** resolved **internally by the Gateway, keyed by slug** — never
  from the request. The platform doesn't even know what kind of credential it is
  (API key, OAuth, session cookies, account pool).
- No-leak discipline enforced on BOTH sides with the existing test pattern
  (**[VERIFIED]** `tests/providers/test_groq_live.py:108` asserts the key never
  appears in logs/errors).

## 16 — Gateway Authentication (staged)

**[PROPOSED]**
- **NOW:** TLS + `X-Gateway-Secret` (stored platform-side via existing
  `SecretManagerPort`/Vault) + `X-Gateway-Secret-Version` + private network. Constant-time compare.
- **LATER (G4):** Vault AppRole for the gateway's own identity → HMAC request signing
  (kills replay) → optional mTLS.
- **Why the version header matters:** it distinguishes an attack (wrong value ⇒ H)
  from an in-progress rotation (stale version ⇒ I with `retryable: true`), enabling the
  self-healing adapter retry.
- **Dual-accept:** during a grace window (OPEN-7, recommended 10 min) the gateway
  accepts current AND previous secret versions. Fixes the prior art's exact-match rule,
  which guaranteed an outage on every rotation (two parties cannot swap atomically).

## 17 — Rotation vs Revocation vs Kill-switch

**[PROPOSED]** (prior art's core insight kept: changing a secret VALUE is NOT a kill-switch)

| Action | Mechanism | Downtime | Scope |
|---|---|---|---|
| Secret rotation | new version + dual-accept window | none | whole link, planned |
| Route revocation | remove route-map line | immediate | one provider |
| Admin disable | existing platform pre-call check (**[VERIFIED]** `core/admin/service.py:333-345`) | immediate | one provider, platform-side |
| **Kill-switch** | **revoke the platform's Vault identity/token** — it can no longer read the gateway secret at all | immediate | whole link |
| Gateway compromise | network stop + revoke platform-mode creds at upstreams + rotate recently transited user_keys | — | containment |

## 18 — Routing Boundary

**[VERIFIED then PROPOSED]** The platform owns AUTO/TIER/EXPLICIT selection and
failover (**[VERIFIED]** `core/routing/router.py:82-132`) — **unchanged**. The Gateway
receives a finished `(operation, model)` decision. If the model is missing upstream →
`model_unavailable` (200-with-failure), and the platform's existing failover picks
another binding. The Gateway **never** substitutes models or redirects requests.

## 19 — Usage Boundary

**[PROPOSED]**
- Gateway returns **raw usage + latency evidence only** (example B). The platform's
  reserve→settle/fail pipeline is untouched (**[VERIFIED]** reserve happens before
  provider work, `core/execution/service.py:378`).
- **ZERO gateway-side retries in v1**: a hidden retry means real upstream usage
  invisible to the reserve/settle ledger — a billing-integrity violation, not a
  convenience feature.
- `request_id` is passed upstream where supported, as the idempotency/dedup anchor.
- The Gateway is **structurally incapable** of becoming a billing engine: it has no
  plans, no ledger, no tenant records.

## 20 — Threat Model

**[PROPOSED]** (Risk / Attack path / Mitigation / Residual)

| # | Risk | Path | Mitigation | Residual |
|---|---|---|---|---|
| 1 | SSRF via gateway_base_url | Admin registers hostile URL | URL allowlist + admin-only registration + https-only + no-redirect-follow in adapter | Compromised admin |
| 2 | Direct gateway access | Attacker reaches gateway port | Private network + TLS + gateway secret; /healthz reveals nothing | Network misconfig |
| 3 | Provider enumeration | Probe route tokens | ≥256-bit tokens + uniform 404-J for unknown/revoked/disabled + rate limiting | Negligible |
| 4 | route_token theft | Platform log/config leak | Token stored as secret; header not URL (OPEN-3); rotation is free | Window until rotation |
| 5 | user_key interception | On-the-wire capture | TLS mandatory precondition; memory-only; no-leak tests | TLS termination points |
| 6 | Secret leak via logs/traces | Any log line | Closed allowed-fields enum (§21) + hermetic unknown-key test | Third-party lib logging |
| 7 | Replay of captured request | Re-send valid envelope | TLS now; HMAC + timestamp in G4 | Until G4 |
| 8 | Stale token after revocation | Old token reused | Reloadable registry ⇒ instant 404-J | None |
| 9 | Stale gateway secret | Old secret reused | Dual-accept window is bounded (OPEN-7); outside window ⇒ H | Grace window |
| 10 | Compromised platform | Attacker holds platform creds | Kill-switch = revoke platform Vault identity (§17) | Damage before detection |
| 11 | Compromised gateway | Attacker in data plane | Slug-scoped platform creds only; NO user_key store to steal (memory-only); containment playbook §17 | In-flight user_keys |
| 12 | Malicious gateway response | Gateway returns crafted output | Platform treats gateway output as **untrusted model output** (existing R095 rule) + defensive re-validation in adapter | Content-level trust |
| 13 | Capability spoofing | DEFINITION over-declares | Admin review at onboarding + startup handler↔declaration parity + health checks | Deliberately false but consistent DEFINITION |
| 14 | Billing manipulation | Inflated usage numbers | Reserve caps exposure upfront + anomaly detection + reconciliation vs real upstream invoices | Small-scale inflation |
| 15 | Tenant isolation bypass | tenant_id abuse | Gateway holds ZERO per-tenant state — nothing to bypass; isolation stays platform-side | None structural |
| 16 | Exception-name leak | Catch-all handler | Sanitized provider_code (§9, fixes prior-art weakness #8) | None |
| 17 | Version-check deletion | `python -O` strips asserts | Explicit validation, never `assert`, for all security checks | None |

## 21 — Observability Contract

**[PROPOSED]** Closed **allowed** field set (anything else = build-time/test failure):
`request_id, execution_id, operation, model, latency_ms, error.category, retryable,
usage.{input_tokens,output_tokens,units}, api_version, definition_version`.

**Forbidden always:** secrets, `credential.value`, `credential_ref`, `route_token`,
slug, upstream URL/host, upstream account identity, raw payload (by default),
exception class names.

**Enforcement:** the closed enum lives in `gateway/observability.py`; a hermetic test
feeds an unknown key and asserts rejection. Same pattern platform-side in the adapter.

## 22 — Failure Behavior Matrix

**[PROPOSED]**

| Failure | Gateway behavior | Platform behavior |
|---|---|---|
| Gateway unreachable | — | Adapter → `provider_unavailable` → existing failover picks another binding |
| Gateway times out | — | Adapter timeout → `timeout` category → fail/refund reserve |
| Malformed gateway response | — | Adapter defensive parse → `non_retryable_error` + operator signal "contract bug" |
| Capability disappears (definition_version bump) | /describe reflects it | Manifest rebuild; in-flight requests get `unsupported_capability` (honest) |
| Model gone upstream | `model_unavailable` (200-failure) | Router failover to other binding |
| user_key expired/invalid | Upstream 401 → `invalid_credential` | Surfaces to the OWNING USER (their key), not ops |
| route_token rotated | Overlap window honors both; after: 404-J | Adapter config update required (provisioning runbook) |
| Gateway secret rotated | Dual-accept window; stale ⇒ I | Adapter re-reads Vault on I, retries once (self-heal) |
| Vault down (platform-side) | — | user_key resolution fails BEFORE any gateway call; **platform-mode providers keep working** (creds are gateway-side) |
| Provider package crashes at import | Lazy import ⇒ dispatch-time `retryable_server_error`, other providers unaffected | Failover |
| DEFINITION invalid | **Startup refusal** (whole gateway, loud) | — |

## 23 — Versioning (6 independent axes)

**[PROPOSED]** No inter-axis coupling — each rotates/bumps on its own terms:

1. **API version** — URL path `/v1`; breaking envelope changes ⇒ `/v2` alongside.
2. **Contract shapes** — follow API version; **the 12 error categories are
   platform-led always** (gateway conforms, never extends).
3. **definition_version** — semver per provider; bump ⇒ platform manifest rebuild only.
4. **Provider implementation** — free to change behind a stable DEFINITION.
5. **route_token** — generational; rotation is invisible to identity.
6. **Gateway secret** — integer version + dual-accept window.

## 24 — Provider Onboarding Runbook (Deliverable D)

**[PROPOSED]** New provider = **Gateway work only**; platform side = config + admin
action, **ZERO platform code**.

**Gateway side:**
- **G1** Copy `providers/_template/` → new package; fill DEFINITION honestly
  (deny-by-default: declare only what works).
- **G2** Implement handlers for every declared operation; map upstream errors to the
  12 categories.
- **G3** Configure credentials: `user_key` ⇒ nothing stored gateway-side;
  `platform` ⇒ provision creds in gateway secret store keyed by slug.
- **G4** Hermetic tests (mock upstream) + startup parity check passes.

**Platform side:**
- **P1** Admin reviews `/v1/describe` output; creates config row (§25) with
  `status: disabled`.
- **P2** Activation: platform generates route_token; operator provisions it
  out-of-band into the gateway route map.
- **P3** One live contract smoke (execute happy-path + one failure case) — evidence
  recorded.
- **P4** Admin enables via the existing enable path
  (**[VERIFIED]** `core/admin/service.py:333-345`).

## 25 — Platform-side Provider Config (per gateway provider)

**[PROPOSED]** YAML/DB row shape:

```yaml
provider_key: "example-provider"        # admin-chosen; becomes ProviderManifest.id (BoundedStr)
display_name: "Example Provider"
gateway_base_url: "https://gw.internal.example:8443"   # must pass allowlist
route_token_ref: "secret://gateway/routes/example"     # token stored AS A SECRET, never inline
credential_mode: "user_key"             # snapshot for audit; checked vs /describe
status: "disabled"                      # deny-by-default; admin enables after P3
```

`Provider.id` (UUID) is generated platform-side as for any provider — nothing special.

## 26 — Test Strategy

**[PROPOSED]**

| Layer | Where | Technique | Gate |
|---|---|---|---|
| Hermetic platform adapter | platform repo | `httpx.MockTransport` — exact existing Groq pattern (**[VERIFIED]** injectable transport `providers/real/groq/adapter.py:94`) | **MANDATORY** in repo gates |
| Hermetic gateway | gateway repo | FastAPI TestClient + mock upstreams; includes **verbatim 12-category parity test** | **MANDATORY** |
| Cross-repo contract parity | both | Same category list asserted verbatim on both sides against `00_CONTRACT.md` | **MANDATORY** |
| Integration (real gateway process, fake upstream) | env-gated | skip-if-no-env pattern (matches existing live-test discipline) | **MANDATORY** when env present |
| Live (real upstream key) | env-gated | same pattern as `test_groq_live.py` incl. no-leak assertions | **MANDATORY** when key available |
| Failure matrix (§22) | both, hermetic | fault injection per row | **MANDATORY** |
| Load/perf | gateway | optional | Lane C, optional |

## 27 — Deployment Shape

**[PROPOSED + OPEN-4]** Recommendation: **private network / same-host first, TLS from
day one**. TLS is a **non-negotiable precondition for any real user_key transit** —
BYOK over plaintext is disqualifying. Cloud later = the same shape lifted into a VPC
(private subnets, no public gateway ingress). OPEN-4 aligns with the existing R101
deployment-shape open decision; nothing here forecloses it.

## 28 — Platform Impact Map (minimal-change proof)

**[PROPOSED, anchored in VERIFIED contracts]**

| Area | Impact |
|---|---|
| `core/routing` | **ZERO** — router sees ordinary providers |
| `core/execution` | **ZERO** — reserve/settle/fail unchanged |
| `core/usage` | **ZERO** |
| `core/identity` / `core/security` | **ZERO** |
| `core/contracts` | **ZERO** for v1 (envelopes/categories already fit) |
| `core/admin` | zero mandatory (existing enable/disable suffices; nicer UX optional later) |
| `providers/real/gateway/` | **NEW** — `RemoteGatewayAdapter` (~Groq adapter size; reference 492 lines) |
| `apps/composition/gateway.py` | **NEW**, small — constructs instances from config (matches existing composition pattern) |
| `pyproject.toml` | promote `httpx` dev → main deps (pre-existing OPEN-6, not caused by this design) |
| tests | additive only |
| Groq / GenSpark adapters | **untouched** |

**Success criterion met:** adding remote providers touches only NEW files plus one
dependency promotion. **Sole declared exception:** introducing a NEW `ProviderOperation`
value is a contract change requiring an ADR — by design, not a gateway limitation.

## 29 — Prior-Art Reconciliation Table (16 decisions)

| # | Prior-art element | Verdict | Reason |
|---|---|---|---|
| 1 | route_token opacity + internal-only resolution | **KEEP** | Matches anti-enumeration posture |
| 2 | /describe hides slug | **KEEP** | Correct boundary |
| 3 | DEFINITION as sole eligibility source | **KEEP + stricter** | Startup parity failure (§10) |
| 4 | ProviderContext hides internals from handlers | **KEEP** (moved to `gateway/contracts.py`) | Isolation |
| 5 | user_key / platform credential modes | **KEEP + add** mode↔DEFINITION check | Prevents mode confusion |
| 6 | Vault/AppRole chain | **KEEP as target, staged** (§16) | Right destination, heavy first step |
| 7 | Rotation ≠ kill-switch | **KEEP** | Correct engineering |
| 8 | Out-of-band provisioning, no HTTP registration | **KEEP** | Correct |
| 9 | Token in URL/query for GETs | **CHANGE** → header (OPEN-3) | Access-log leak |
| 10 | Exact secret-version match | **CHANGE** → dual-accept window | Guaranteed rotation outage |
| 11 | `GATEWAY_ROUTES_JSON` env | **CHANGE** → reloadable protected source | Rotation without restart |
| 12 | Fixed per-operation routes | **CHANGE** → unified `/v1/execute` (OPEN-1) | Double-encoding conflict |
| 13 | Flask sync / single-file providers / `from app import` | **CHANGE** → FastAPI + packages + `gateway/contracts.py` | Async platform; dependency direction |
| 14 | `assert` for category check; `type(exc).__name__` leak | **CHANGE** → explicit validation; sanitized code | `-O` deletion; info leak |
| 15 | "slug = ProviderManifest.id" | **REJECT** | Leaks slug; self-contradicted by newer kit files |
| 16 | "ProviderManifest.id = UUID" | **REJECT** | **[VERIFIED]** actual type BoundedStr (`core/contracts/provider.py:195`) |

## 30 — Honest Risks of This Design

1. **The Gateway becomes the central vault for all platform-mode credentials** — the
   juiciest single target. Mitigated (slug-scoping, no tenant secrets), not eliminated.
2. **Two-repo contract drift** — mitigated by verbatim-parity tests on both sides
   pinned to `00_CONTRACT.md`; still a standing operational duty.
3. **Platform-logic creep into the gateway** (retries, model fallback, caching are
   tempting) — must be rejected in review; §19's zero-retry rule is the first fence.
4. **Extra network hop latency** on every remote-provider call — inherent cost of the
   boundary; measure in G3.
5. **Dual-service operational burden** — two deploys, two secret stores, one runbook
   spanning both.

## 31 — Open Decisions (OPEN-1 … OPEN-8)

| ID | Question | Recommendation |
|---|---|---|
| OPEN-1 | Unified `/v1/execute` vs fixed per-operation routes | **Unified** (kills double encoding) |
| OPEN-2 | `run_provider_agent` / `upload_asset` / `download_asset` in v1? | **Out of v1**; DEFINITION declaring them rejected at load |
| OPEN-3 | route_token in header vs URL | **`X-Route-Token` header** everywhere |
| OPEN-4 | Deployment shape (ties to existing R101 open) | **Private network + TLS day one**; VPC later |
| OPEN-5 | FastAPI vs Flask for gateway | **FastAPI** (async parity with platform, shared pydantic idioms) |
| OPEN-6 | `httpx` promotion dev → main deps | **Yes**, same commit as any adapter work (pre-existing issue) |
| OPEN-7 | Dual-accept grace window length | **10 minutes** |
| OPEN-8 | Implementation authorization | **Requires NEW operator authorization + ADR-0008 before ANY code.** This report authorizes nothing. |

## 32 — Phased Plan (if/when OPEN-8 is granted)

- **G0** — ADR-0008 platform-side capturing OPEN-1..7 resolutions; **operator accepts first**.
- **G1** — Gateway skeleton (`gateway/` core + template + hermetic suite green).
- **G2** — Platform `RemoteGatewayAdapter` + `apps/composition/gateway.py` +
  MockTransport suite (repo gates stay green: 1493+22 hermetic baseline must hold).
- **G3** — First real provider end-to-end: integration + live smoke + a settled usage
  record proving the reserve→settle path across the wire.
- **G4** — Hardening: HMAC signing, AppRole, rotation drills, optional mTLS.

## 33 — Final Recommendation

The prior-art kit's **core design is sound** — its envelope is very nearly an HTTP
translation of the platform's existing `ProviderGenerateRequest/Response` contracts,
which is the strongest possible compatibility evidence. The 16 reconciliation
decisions (§29) are **implementation corrections, not a redesign**. Headline fixes:

1. **Identity model corrected to the repository's actual types** (BoundedStr
   provider_key; slug never crosses; no UUID conflation).
2. **Unified `/v1/execute`** removes the operation double-encoding conflict class.
3. **Dual-accept secret versioning** turns every rotation from a guaranteed outage
   into a non-event, with a self-healing 401-I retry.
4. **Dependency-direction inversion** (`gateway/contracts.py` at the bottom) makes
   every provider package hermetically testable.

---

**Compliance footer.** This session performed planning/architecture review only; the
sole repository mutation is this report file, whose persistence + commit + push was
explicitly operator-ordered ("نفذ لتقارير هذه الجلسه كامل commit و push"). No gateway
code, no platform code, no contract changes were made. All implementation work awaits
OPEN-8: new operator authorization + ADR-0008. Never-fake (41 §49) upheld: every
`[VERIFIED]` tag corresponds to a command/file-read executed in this session at
HEAD `08c8f58`.
