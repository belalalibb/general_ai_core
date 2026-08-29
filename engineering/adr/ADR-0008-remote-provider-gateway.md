# ADR-0008 — Remote Provider Gateway (control-plane / data-plane split)

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-29: "OPERATOR DECISION — ACCEPT ADR-0008 … exactly as currently committed and remotely verified")
DATE: 2026-08-29
DATE_ACCEPTED: 2026-08-29
TASK: R103 architecture review (proposal) / implementation task NOT YET AUTHORIZED
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.

**HARD GATE (operator-mandated, verbatim scope):** This ADR is a decision
record ONLY. Its creation — and even its future ACCEPTANCE — does NOT
authorize: Gateway implementation, `RemoteGatewayAdapter` implementation,
composition changes, dependency changes, Gateway repository creation, or
execution of phases G1/G2/G3/G4. Every implementation phase requires a
separate explicit operator authorization issued AFTER this ADR is reviewed
and ACCEPTED.

Evidence base: `engineering/proposals/provider_gateway_kit/ARCH_REVIEW_REPORT.md`
(R103, reviewed at HEAD `08c8f58`) — all `[VERIFIED]` anchors cited below
were command/file-read verified in that session. Prior art:
`engineering/proposals/provider_gateway_kit/` design kit.

---

## Context

The platform executes provider work through `ProviderAdapterPort`
([VERIFIED] `core/providers/ports.py:57`) with in-repo adapters (Groq,
GenSpark) that hold upstream knowledge (URLs, SDK shapes) inside the
platform repository. Requirements force a split:

```text
- Providers whose upstream mechanics (endpoints, SDKs, account pools,
  session/cookie auth) must NOT live in the platform repo at all.
- The platform must remain the sole authority for routing, tenancy,
  entitlements, reserve→settle usage accounting, and provider
  activation (deny-by-default) — all already implemented and verified:
  routing core/routing/router.py:82-132; reserve-before-work
  core/execution/service.py:378; admin enable/disable
  core/admin/service.py:333-345.
- The existing internal envelope ProviderGenerateRequest/Response
  (core/contracts/provider.py:385+) and the closed 12-value
  ProviderErrorCategory (:312) must remain the contract vocabulary.
- Anti-enumeration posture (ObjectNotFound collapse) and the
  never-fake rule (41 §49) apply across any new boundary.
- Adding a remote provider must require ZERO changes to core/*.
```

The R103 architecture review evaluated the prior-art gateway kit against
repository reality and produced 16 reconciliation decisions plus 8 open
decisions (OPEN-1..8). The operator resolved OPEN-1..7 on 2026-08-29
(verbatim authorization in-session); this ADR records those resolutions
as the binding architecture decision.

## Alternatives

### A. Remote Provider Gateway — separate data-plane service (CHOSEN)

Control plane (platform) / data plane (Gateway) split. One generic
`RemoteGatewayAdapter` class implementing the EXISTING
`ProviderAdapterPort` unchanged; N instances, one per activated gateway
provider. The Gateway is a separate FastAPI service in a separate
repository holding all upstream knowledge.

Pros:

```text
- core/routing, core/execution, core/usage, core/identity,
  core/security, core/contracts: ZERO change (impact map, report §28).
- Upstream secrets/mechanics leave the platform repo entirely.
- The internal envelope translates almost 1:1 to the wire envelope —
  strongest compatibility evidence in the review (report §3).
- New provider = Gateway-side work only; platform side is config +
  admin action, zero platform code (report §24).
```

Cons:

```text
- The Gateway becomes the central custodian of all platform-mode
  upstream credentials (juiciest single target; report §30.1).
- Two-repo contract drift risk (mitigated by verbatim 12-category
  parity tests both sides; report §26).
- Extra network hop latency on every remote-provider call.
- Dual-service operational burden (two deploys, two secret stores).
```

### B. Keep adding in-repo adapters per provider

Pros: no new service, no new trust boundary, current pattern works
([VERIFIED] Groq/GenSpark green including live tests, R102).

Cons: upstream mechanics and platform-mode credentials accumulate INSIDE
the platform repo — exactly what the requirement forbids; every new
provider is a platform code change; session/cookie/account-pool
providers are not representable without polluting core dependencies.

### C. Third-party API gateway / general-purpose proxy (Kong, Envoy, …)

Pros: mature operational tooling.

Cons: cannot express DEFINITION-based capability declaration,
12-category error normalization, credential-mode enforcement, or the
route_token identity model without heavy custom plugins — the custom
logic would be rewritten inside a plugin sandbox anyway; adds a large
foreign dependency for no contract benefit.

## Decision

**Alternative A** — build a separate Remote Provider Gateway service and
a platform-side generic `RemoteGatewayAdapter`, with the following
operator-resolved parameters (OPEN-1..7, resolved verbatim 2026-08-29):

```text
OPEN-1  Unified execution endpoint: POST /v1/execute with `operation`
        inside the request envelope. NO per-operation routes in v1
        (kills the double-encoding conflict class, report §7).
OPEN-2  run_provider_agent / upload_asset / download_asset stay OUT of
        Gateway v1 — no implementation, no API surface. A DEFINITION
        declaring any of the three is rejected at load time.
OPEN-3  route_token moves out of URLs entirely: protected request
        header (X-Route-Token) on ALL surfaces including discovery/GET
        (prevents access-log / proxy-log / tracing / cache exposure).
        The token is never part of a URL.
OPEN-4  Deployment recommendation: same-host / private-network first,
        with TLS from day one (TLS is a non-negotiable precondition
        for any real user_key transit). NO production cloud
        infrastructure is implemented now.
OPEN-5  Gateway framework: FastAPI/ASGI (async) with pydantic
        contracts — not Flask. Async parity with the platform's
        httpx.AsyncClient adapters.
OPEN-6  httpx must become a runtime/main dependency of the platform
        core (required by RemoteGatewayAdapter; today it is dev-only —
        [VERIFIED] pre-existing condition). The existing same-commit
        rule applies AT IMPLEMENTATION TIME: dependency + import
        contract + code/test in one change. NOT executed now; executes
        only under its own authorization or within G2.
OPEN-7  Gateway secret rotation uses a dual-accept window (current +
        previous version). Initial proposed value: 10 minutes. The
        window length is OPERATIONAL CONFIGURATION — changeable
        without ADR; it is not part of domain identity.
OPEN-8  (restated as this ADR's own gate) Building the Gateway is an
        independent implementation task requiring this ADR to be
        ACCEPTED first, followed by separate explicit operator
        authorization per phase.
```

### Boundary — Platform Control Plane vs Gateway Data Plane

```text
Platform (control plane) alone owns:
  authorization / tenant isolation / entitlements / plans / quotas;
  provider+model selection (AUTO/TIER/EXPLICIT) and failover;
  usage reserve/settle/refund/fail and all billing;
  provider activation & eligibility (deny-by-default, admin);
  route_token issuance (single issuer);
  BYOK custody (Vault, credential_ref — resolved platform-side).

Gateway (data plane) alone owns:
  upstream endpoints / SDKs / accounts / OAuth / cookies;
  platform-mode credentials (platform never learns their kind);
  first-pass error normalization to the 12 categories;
  DEFINITION declaration + /v1/describe projection.

Gateway stores NO tenants, NO plans, NO quotas, NO usage ledgers,
NO routing policy — structurally incapable of becoming a billing
engine or a tenancy authority. Zero Gateway-side retries in v1
(hidden retries = upstream usage invisible to reserve/settle =
billing-integrity violation).
```

### route_token identity separation (5 layers, no derivation)

```text
Provider.id            UUID, platform domain, never rotates, never crosses.
provider_key           = ProviderManifest.id (BoundedStr — [VERIFIED]
                        core/contracts/provider.py:195; NOT a UUID),
                        admin-chosen, identity, never crosses.
display_name           Gateway DEFINITION; the ONLY name that crosses.
internal slug          Gateway-private; NEVER crosses the boundary.
route_token            opaque secret (secrets.token_urlsafe(32),
                        ≥256-bit), platform-issued, rotates freely,
                        crosses as a credential — not a name.
No hash/derivation between any two layers. Prior-art claims
"slug = ProviderManifest.id" and "manifest.id = UUID" are REJECTED
(report §29 rows 15–16).
```

### Credential / BYOK model

```text
user_key mode:   resolved PLATFORM-side at the last moment via the
                 existing secret_resolver(credential_ref) pattern
                 ([VERIFIED] providers/real/groq/adapter.py:91);
                 crosses TLS inside the envelope; memory-only on the
                 Gateway — never persisted, never logged. Chosen over
                 giving the Gateway tenant-secret Vault access, which
                 would hand the data plane a blast radius over ALL
                 tenants' secrets.
platform mode:   resolved INTERNALLY by the Gateway, keyed by slug —
                 never from the request; the platform does not know
                 the credential kind.
Envelope carries {mode, value?}; mode MUST match the provider
DEFINITION or the request fails as bad_request. No-leak tests on both
sides (existing pattern: tests/providers/test_groq_live.py:108).
```

### Usage / billing authority

```text
Gateway returns RAW usage + latency evidence only. The platform's
reserve→settle/fail pipeline is untouched ([VERIFIED] reserve before
provider work, core/execution/service.py:378). request_id passes
upstream as the idempotency/dedup anchor. Internal retry/failover
never multiplies user cost — and v1 has zero Gateway retries.
```

### Security model

```text
Transport:   TLS + X-Gateway-Secret (platform side stored via the
             existing SecretManagerPort/Vault) + X-Gateway-Secret-Version
             + private network; constant-time compare. Staged target
             (G4, future authorization): Vault AppRole → HMAC request
             signing (anti-replay) → optional mTLS.
Rotation:    dual-accept window (OPEN-7). Stale version ⇒ HTTP 401
             auth_expired with retryable:true ⇒ adapter re-reads Vault
             and retries once (self-healing rotation).
Kill-switch: revoke the platform's Vault identity (it can no longer
             read the gateway secret) — changing a secret VALUE is
             NOT a kill-switch (prior-art insight kept).
Enumeration: unknown / revoked / disabled route_token ⇒ uniform
             HTTP 404 "unknown route" (single indistinguishable body).
Observability: closed allowed-field enum (request_id, execution_id,
             operation, model, latency_ms, error.category, retryable,
             usage counters, api_version, definition_version);
             secrets / credential values / credential_ref /
             route_token / slug / upstream identity / exception class
             names are forbidden always, enforced by a closed enum +
             hermetic unknown-key test on both sides.
Validation:  explicit checks only — never `assert` (deleted under
             python -O). Full 17-row threat model: report §20.
```

### Migration / compatibility constraints

```text
- ProviderAdapterPort, ProviderGenerateRequest/Response, and the
  12-category ProviderErrorCategory remain UNCHANGED; the wire
  contract conforms to them (platform-led vocabulary — the Gateway
  never extends the category set).
- Groq and GenSpark adapters remain untouched; existing providers
  continue direct-call operation indefinitely (no forced migration).
- Impact map (report §28): core/* ZERO; NEW files only —
  providers/real/gateway/ (adapter) + apps/composition/gateway.py —
  plus the OPEN-6 httpx promotion at implementation time.
- Sole declared exception: introducing a NEW ProviderOperation value
  is a contract change requiring its own ADR — by design.
- Versioning: 6 independent axes (API /v1 path; contract shapes;
  per-provider definition_version semver; provider implementation;
  route_token generation; gateway-secret integer version) — no
  inter-axis coupling (report §23).
- Cross-repo drift control: verbatim 12-category parity tests
  MANDATORY on both sides, pinned to the shared contract document.
```

## Reason

The invariants (final_docs_v3/02) demand deny-by-default eligibility,
tenant isolation, reserve-before-work billing integrity, and secret
custody outside the repo — Alternative A is the only option that
extends all four across a process boundary while leaving every verified
core contract byte-identical. The review's strongest evidence is that
the existing internal envelope already IS the wire contract in all but
serialization (report §3), so the split adds a boundary without
inventing a new vocabulary. Alternative B violates the "upstream
mechanics must not live in the platform repo" requirement that
motivated the work; Alternative C cannot express the platform's closed
contracts without re-implementing them as plugins.

## Consequences

```text
Easier:  onboarding providers with hostile/unusual upstreams (account
         pools, cookies, OAuth) with zero platform code; independent
         Gateway deploy/rotate cycles; platform repo stays free of
         upstream secrets.
Harder:  the Gateway is a new high-value target requiring its own
         hardening path (G4); two repos must hold contract parity;
         one extra hop of latency; two operational runbooks.
Rollback: the platform side is additive (new adapter + composition
         file); removing them restores the exact current state. The
         Gateway repo is external — platform rollback does not depend
         on it. Existing direct adapters are untouched throughout.
Migration: none forced — direct adapters and gateway adapters coexist
         behind the same port indefinitely.
```

## Status

ACCEPTED — explicit operator sign-off 2026-08-29, issued against the
remotely verified document at commit `35d9454c02351dcbacb713ddd722291be74e15c2`
(decision text preserved verbatim; this status block is the only change).

Acceptance of this ADR records the DECISION only. Implementation
phases (G1 gateway skeleton, G2 platform adapter + composition +
OPEN-6 dependency promotion, G3 first real provider end-to-end,
G4 hardening) each require a separate explicit operator authorization
issued after acceptance (operator hard gate, 2026-08-29, recorded
verbatim at the top of this file).
