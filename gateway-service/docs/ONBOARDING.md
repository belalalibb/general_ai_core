# Provider Onboarding Runbook (v1)

Minimum safe steps to turn `providers/_example/` (working mock reference)
into a real provider. Contract: `docs/CONTRACT.md` (code authority:
`gateway/contracts.py`). Template: `providers/_template/` (line-by-line
documented facade). New provider = **gateway work only**; platform side =
config + admin action, zero platform code.

## The three-layer rule (read once, apply always)

- **Layer 1 — yours, free:** any files, any SDK, any auth (OAuth/session/
  cookies), account pools, chained upstream calls, internal fallback.
  Invisible outside your package.
- **Layer 2 — the facade (mandatory):** `adapter.py` translates your
  internal result into the canonical contract — success schema or one of
  the 12 error categories. No third shape.
- **Layer 3 — fixed:** `gateway.contracts`. Import it. Never change it.

## Gateway-side steps

1. **Copy** `providers/_example/` (working start) or `providers/_template/`
   (documented empty facade) → `providers/<your_provider>/`
   (no `_` prefix — `_`-packages are skipped by discovery).
2. **Fill `definition.py`** honestly — deny-by-default:
   - declare ONLY operations that work (subset of the 8 v1 operations;
     never `run_provider_agent`/`upload_asset`/`download_asset` — load-time
     rejection, OPEN-2);
   - an unsupported operation is left out entirely (no empty stubs —
     declaration IS eligibility);
   - capabilities from the closed key set; `models: []` is honest if none;
   - semver `definition_version`; bump on every declaration change.
3. **Implement the facade** in `adapter.py`: one handler per declared
   operation; keep `HANDLERS` in exact parity (startup check kills liars).
   Internals (Layer 1) go in your own private modules (`_engine.py`, …).
4. **Credentials:** `user_key` ⇒ store NOTHING gateway-side (the value
   arrives per-request, memory-only). `platform` ⇒ provision credentials in
   the gateway's own secret store keyed by your slug; never read them from
   the request.
5. **Hermetic tests** in `tests/providers/test_<your_provider>.py` — mock
   upstream only, no network. Must cover: canonical success shape, error
   mapping to the 12 categories, no-leak (your keys/session material never
   appear in any FacadeResult), and DEFINITION↔HANDLERS parity.
6. **Run the suite:** `python3 -m pytest` from `gateway-service/` — all
   green before any registration.

## Provider Development Form (fill per operation)

| Field | Answer |
|---|---|
| Operation | one of the 8 (`generate_text`, …) |
| Input accepted | payload fields per CONTRACT.md — validate, reject extras as `bad_request` |
| Internal processing | **FREE FORM** — your files, your SDK, your auth, your call chain |
| Final output | **MUST match the canonical output schema** for the operation (CONTRACT.md) |
| Errors | **MUST map to exactly one of the 12 categories** (mapping table in `_template/adapter.py`) |

## Platform-side steps (operator/admin — separate authorization)

1. Admin reviews `GET /v1/describe` output; creates the platform config row
   with `status: disabled`.
2. Activation: the platform generates the route_token (sole issuer);
   the operator provisions it **out-of-band** into the gateway route map
   (no HTTP registration endpoint exists, by design).
3. One live contract smoke (happy path + one failure case) — evidence
   recorded.
4. Admin enables via the existing platform enable path.

## Hard rules (violations = rejected provider)

- Never import `app` — contracts come from `gateway.contracts`.
- One request → one canonical response (internal call count is invisible).
- Zero gateway-level retries in v1 (billing integrity).
- Never log/return: credential values, route_token, slug, upstream account
  identity, exception class names.
- Touch nothing outside your provider folder.
