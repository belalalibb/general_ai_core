# R174 §5 — The last link: platform process → gateway process (live, two processes)

Date: 2026-09-05 · HEAD at start: 07a1b24 · Driver: `probe.py` (10/10 checks, `checks.json`)

Processes: `gateway-service/app.py` on :8800 (route map `rt_aai_r174:assemblyai`), `python3 -m apps.main`
on :8000 (in-memory profile, `GATEWAY_BASE_URL=http://127.0.0.1:8800`, `ADMIN_EMAILS` set). The driver talks
**only to the platform**, as an operator: register → verify (console token) → login → `POST
/v1/admin/providers/onboard`. Paid upstream calls: **0** (the AssemblyAI key was not in either process env —
none of these cases can reach an upstream model).

## Verdict in one line

**The chain is broken at the platform→gateway link, in two independent places. AssemblyAI (or Groq, or any
gateway provider) cannot be onboarded through the real admin door of the real `apps.main` process today.**
§4 proved the gateway half works; §5 proves the platform half does not reach it.

## Cases

| case | what | result | predicted? |
|---|---|---|---|
| G | control: `GET /v1/describe` on the gateway with the correct route token | 200, `display_name="AssemblyAI LLM Gateway"` — network + route map fine | — |
| bootstrap | real identity flow on the platform | register 201 → verify 200 → login 200 → `is_admin=true` | — |
| **E** | onboard, `credential_mode=platform`, `route_token_ref` | **HTTP 500 `internal_error`**; gateway log: **no request arrived** | yes — F-3 |
| **F** | onboard, `credential_mode=user_key` | **HTTP 409** `"user_key credential mode requires a user_key_resolver"` | yes — F-2 |
| after | `GET /v1/admin/providers` | neither provider registered — walker failed **before** step 11, no half-state | — |
| **H** | hypothetical F-3 fix: store the route token by hand, build the adapter with the **real** `adapter_from_definition`, run step 6 against the real gateway | request **did** reach the gateway (`GET /v1/health 200`), gateway says `UNKNOWN` → adapter `UNAVAILABLE` → walker would refuse `step-6-health-check` | **no — new finding F-6** |

## E in detail — F-3 confirmed (route-token custody has no seam)

`platform.log` traceback (verbatim frames):

```
apps/api/provider_onboarding.py:245  onboard_provider → surface.onboarding.onboard(
core/providers/onboarding.py:218     health = await adapter.health_check(HealthScope.PROVIDER)
providers/real/gateway/adapter.py:285  route_token = self._resolve_route_token()
apps/composition/gateway.py:173      return secrets.resolve(tenant_id, route_token_ref)
core/secrets/memory.py:46            raise SecretNotFound(credential_ref)
core.secrets.errors.SecretNotFound: route-token-ref-assemblyai-r174
```

- `runtime.py:747` composes `onboarding_secrets = InMemorySecretManager()` — fresh and empty. Nothing in
  `apps/` ever calls `.store()` on it (the only `.store()` in composition is `runtime.py:564`, env provider
  keys, a **different** manager). So there is **no way**, from outside the process, to make any
  `route_token_ref` resolvable. The docs' "operator provisions the route token" step has no code behind it.
- The failure is a **500**, not a refusal: `SecretNotFound` is not caught anywhere between the adapter and the
  route; it lands in the generic `Exception` handler (`apps/api/app.py:701`). The operator sees
  `"Internal error."` with no hint. Compare F, where the same class of problem (unbuildable definition) is a
  clean 409 with the reason.
- Hermetic tests didn't catch this because they build their own `InMemorySecretManager` and `.store()` the token
  into it before onboarding — they test the adapter's resolver, not the composition's custody.

## F in detail — F-2 confirmed (user_key mode unbuildable through composition)

409, message exactly as predicted. `adapter_from_definition` (`apps/composition/provider_onboarding.py:99-116`)
never passes `user_key_resolver`; `RemoteGatewayAdapter.__init__:186` raises. The contract advertises two
credential modes; the composition can build one. At least this one fails loudly and early (before any I/O).

## H in detail — **F-6, new: step 6 can never pass for a gateway provider**

Even with F-3 fixed, onboarding still refuses:

- gateway `project_health` (`gateway-service/gateway/discovery.py:34-41`) returns `UNKNOWN` unconditionally —
  "health checks are not implemented; UNKNOWN is the honest answer". Both live definitions declare
  `health_supported: False`.
- platform `_HEALTH_STATUS_MAP` (`providers/real/gateway/adapter.py:111-116`) maps `UNKNOWN → UNAVAILABLE`
  ("unknown is never healthy" — correct posture on its own).
- walker `core/providers/onboarding.py:218-224` refuses unless `HEALTHY`.

Each of the three is individually defensible; together they make the door **unopenable** for every provider the
gateway currently has. Note the asymmetry with step 5: the walker treats a *missing credential-check surface*
as "UNVERIFIED, recorded, continue" (41 §49), but a *missing health surface* as "refuse". The gateway provides
no way to distinguish "no health surface" from "health surface says unknown" (`checked_at=None` is the only
hint).

The only test pinning step 6 for the gateway (`tests/api/test_provider_onboarding_api.py:256`) uses
`health_supported: True` with a fake gateway answering `OK` — a state no real gateway provider is in.

## What this means for the R174 question

| link | status | evidence |
|---|---|---|
| gateway-service provider (Layer 1/2) → canonical contract | **works live** | §4 A–D |
| gateway registry / route map / auth | **works live**, zero changes for 2nd provider | §4, `git diff` empty |
| platform `RemoteGatewayAdapter` → gateway over TCP | **works** when handed a token (H reached `/v1/health`) | H, gateway.log |
| platform composition → adapter (route-token custody) | **broken** — F-3, 500 | E |
| platform composition → adapter (`user_key` mode) | **broken** — F-2, 409 | F |
| onboarding walker step 6 vs gateway health semantics | **broken** — F-6, would refuse | H |
| core/ | untouched; zero AssemblyAI lines (`git grep -i assemblyai -- core/` = 0) | — |

Therefore the §1-D definition of "counts as proof" (a `POST /v1/execute` on the platform returning AssemblyAI
text) is **not reachable without code changes to `apps/`** — and those changes are the *finding*, not a detour.
Nothing here is AssemblyAI-specific; Groq would fail identically through this door (its live proofs used the
direct `providers/real/groq` adapter, not the gateway route).

## Decision (standing authority, logged)

Do **not** paper over F-3/F-6 inside the probe to "get the green run". §6 will propose the minimal fixes as
separate, test-pinned commits and re-run this exact driver; only then spend the ≤3 paid calls on the
platform-side `POST /v1/execute`. Order: F-3 (custody seam) → F-6 (health semantics for `health_supported=false`)
→ re-run → paid call. F-2 is recorded and left for a later round unless trivially adjacent.
