# ADR-0011 — Provider Onboarding Durability & Gateway Registration Records

```text
STATUS: ACCEPTED
DATE: 2026-09-01
TASK: PR #12 remediation — GAP 1 (provider onboarding executable + durable)
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
No significant architecture change is allowed without an ADR.

---

## Context

The 31 §19 onboarding walker (`core/providers/onboarding.py`) registered
providers/models/bindings into the in-memory registries only. Two gaps:

1. **Executability**: `ExecutionService._validate_route` requires the
   provider's adapter in the `adapters` map and its opaque credential_ref
   in the `credential_refs` map. Onboarding populated neither — an
   onboarded provider could never actually run a request.
2. **Durability**: nothing survived restart. `infrastructure/db/
   repositories/catalog.py` had explicitly RESERVED a future
   `provider_model_bindings` table for "the runtime binding-registration
   surface that needs it" — that surface now exists.

The durability question forces one architectural decision this ADR
records: **how does the composition root rebuild a working ADAPTER at
startup?** Provider/model/binding rows are plain entities, but an adapter
needs the gateway base_url, the provider's declared surface (operations/
capabilities/static models), its opaque `route_token_ref`/`credential_ref`,
and its `credential_mode`. Constraints: manifests are code self-declarations
and deliberately NOT persisted (catalog.py recorded decision); secret
values never touch rows (20 §5); the gateway env contract (G2,
`apps/composition/gateway.py`) stays the source of base_url + shared
secret.

## Alternatives

**A. Persist the full ProviderManifest per provider.**
- Pro: adapter rebuild is one deserialization.
- Con: violates the recorded catalog.py decision — a DB row claiming
  capabilities the shipped code does not have would fabricate
  architecture. Two definitions of the same manifest drift.

**B. Persist the OPERATOR's registration definition (chosen).**
One JSONB `definition` row per gateway provider
(`provider_gateway_registrations`, PK provider_id): exactly the
onboarding request body — provider_key, display_name, declared
operations/capabilities/static_models, `credential_ref`,
`route_token_ref` (both opaque), `credential_mode`, definition_version.
The manifest is RE-DERIVED at startup via the existing
`build_gateway_manifest` (same OPEN-2 exclusions, same
`status="disabled"` rule), the adapter via the existing
`build_gateway_adapter` with resolvers bound to the SecretManagerPort.
- Pro: one derivation, two consumers (route + hydration) — no drift;
  manifests stay code-derived; refs-only custody.
- Con: hydration re-runs derivation logic at startup (cheap, pure).

**C. Re-onboard from env at every boot (no persistence).**
- Pro: zero schema.
- Con: onboarding is an admin RUNTIME act, not deployment config —
  losing it on restart is exactly the gap being remediated. Rejected.

## Decision

Alternative B, plus:

- **Migration 0018** creates `provider_model_bindings` (03 §4 entity,
  composite PK provider_id+model_id, closed availability set, FKs
  RESTRICT) and `provider_gateway_registrations` (PK provider_id, JSONB
  definition). `PostgresBindingCatalog` and
  `PostgresGatewayRegistrationCatalog` mirror the existing catalog
  pattern (load_all/upsert, pg ON CONFLICT).
- **Write-through order**: onboarding persists rows only AFTER every
  in-memory registration succeeded — a refused/rolled-back onboarding
  never leaves a durable row; hydration replays rows at the next boot.
- **Executability**: onboarding receives the SAME `adapters`/
  `credential_refs` maps the composed ExecutionService reads
  (instance-agreement duty) and populates them at registration; startup
  hydration repopulates them from the stored definitions.
- **Custody scope**: platform-owned gateway route tokens live under the
  fixed `PLATFORM_TENANT_ID` custody scope (deterministic across
  restarts) so refs stored in a durable secret manager stay resolvable.
- **DECISION 2 (operator, binding)**: this whole path is
  canonical-gateway ONLY. A foreign/native-API provider still REQUIRES
  its own adapter/shim; the caveat is part of the route's response
  contract and every touched docstring.
- **Degradation is loud**: hydrating registrations without a configured
  gateway binding registers the DATA (catalog visibility) but leaves the
  adapter absent — routing refuses with AdapterNotBound; nothing fakes
  a working provider (41 §49).

## Reason

Reuse-first (P1): every moving part — manifest builder, adapter builder,
catalog pattern, AsyncBridge, admin-router pattern, draft→publish enable
path — already existed; this ADR only adds the two reserved tables and
the definition record that makes adapter REBUILD possible without
persisting manifests or secrets. Deny-by-default and secret custody
invariants (20 §4/§5) are preserved structurally: refs only, closed
sets, absent-seam ⇒ absent-route.

## Consequences

- Enable stays the audited AdminConfigService draft→publish lifecycle
  (`enable_provider`) — onboarding never enables anything (31 §19 step 14).
- The in-memory dev profile onboards without durability (honest scope).
- Rotating a route token = store new value under a new ref + update the
  registration row; the resolver reads at the last moment, no restart.
- A future Vault binding replaces the InMemorySecretManager at the
  composition root only (ADR-0007 posture); refs/rows are unchanged.
