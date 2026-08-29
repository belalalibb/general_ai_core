# Provider Facade Template (`_template/`)

The official, stable reference for the ONE layer the platform sees.
Open `adapter.py` — it documents, line by line, everything the platform
requires, without you reading any gateway core code.

## How to use

1. **Copy this folder** to `providers/<your_provider>/` (no `_` prefix —
   `_`-prefixed packages are skipped by discovery).
2. **Fill `definition.py`** — declare ONLY what actually works
   (deny-by-default; declaration IS the source of eligibility).
3. **Fill `adapter.py`** — implement a handler for every declared
   operation; delete the stubs you don't declare; keep `HANDLERS` in exact
   parity with `DEFINITION["operations"]` (checked at startup).
4. **Apply the three layers**:
   - **Layer 1 (free):** below the facade, implement anything in any
     structure — files, SDKs, auth, sessions, account pools, chained
     calls. Invisible to the platform.
   - **Layer 2 (this template):** the mandatory translator — canonical
     success or one of the 12 error categories. No third shape.
   - **Layer 3 (fixed):** `gateway.contracts` — import it, never change it.
5. **Touch nothing outside your folder.**

## Rules that will bite you if ignored

- Never `from app import ...` — import contracts from `gateway.contracts`.
- Never declare `run_provider_agent` / `upload_asset` / `download_asset`
  (excluded from v1 — rejected at load time, ADR-0008 OPEN-2).
- An unsupported operation is left OUT of the DEFINITION entirely — no
  declared empty stubs.
- No gateway-level retries in v1 (billing integrity). Internal upstream
  behavior is yours, but one request returns exactly one canonical result.
- Never log or return: credential values, route_token, slug, upstream
  account identity, exception class names.

Working example (mock, three layers in practice): `providers/_example/`.
Full contract: `docs/CONTRACT.md`. Onboarding runbook: `docs/ONBOARDING.md`.
