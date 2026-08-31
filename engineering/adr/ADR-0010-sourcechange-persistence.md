# ADR-0010 — Source-change proposal/snapshot persistence schema

**Status:** ACCEPTED (2026-08-31)
**Phase:** Post-V9 P-A.3 (operator directive: durability, local-first)
**Relates to:** ADR-0009 (R3 source-change sandbox), ADR-0002 (persistence stack)

## Context

ADR-0009 recorded: "in-process bindings now; a durable repository binding
is a later conscious slice. The PORTS are the architecture — criterion 12:
swapping the binding never touches the workflow." This is that slice.

The P-A.3 directive binds `InMemoryProposalStore` / `InMemorySnapshotStore`
(the only V8 stores without durable backing) to PostgreSQL — **persistence
only**. Persisting a proposal is NOT applying it.

## Decision

### Scope guard (§14 — restated as a schema-level fact)

This ADR adds durable **records**. It does not add, enable, or move any
apply capability:

- `authoritative_applier=None` stays (apps/api/app.py — the §14 gate).
- R3 stays in `NEVER_REGISTRABLE_CLASSES`.
- The stores implement the EXISTING sync ports (`ProposalStorePort`,
  `SnapshotStorePort`) verbatim; `SourceChangeWorkflow` is untouched.

### Schema (migration 0017)

Two tables, tenant-scoped entity data (20 §6 posture — composite PKs
keyed by tenant):

**`source_snapshots`** — PK `(tenant_id, snapshot_id)`
- `snapshot_id TEXT` — the content address (`sha256:<manifest-digest>`).
- `files JSONB` — `{path: base64(content)}`. Base64 because snapshot
  content is arbitrary BYTES and JSONB is UTF-8; the recorded V8 sandbox
  scope is small source trees, so a single JSONB document is proportionate
  (criterion: object storage per 41 §6 becomes justified only when
  snapshots outgrow row-sized documents — a later, separate slice).
- `created_at TIMESTAMPTZ`.

**`source_change_proposals`** — PK `(tenant_id, proposal_id)`
- Latest-record-per-id semantics (the port's contract) ⇒ UPSERT on save.
- Scalar columns: `actor_id`, `base_snapshot_id`, `rationale`, `state`
  (CHECK-constrained to the closed `ProposalState` set), `patch_hash`,
  `created_at`, `applied_snapshot_id NULL`.
- `patch JSONB` / `inverse_patch JSONB NULL` — operation lists
  `[{kind, path, content?}]` with base64 content (same bytes rule).
- `approval JSONB NULL` — `{approver_id, approved_patch_hash, decided_at}`.

### Integrity is re-derived, never trusted (criterion 1)

- Snapshots: `verify_integrity()` runs on save AND on read in the store
  layer (the port's stated duty) — a row whose bytes lie about their
  content address is refused with the named `SnapshotIntegrityError`.
- Proposals: `patch_hash` is **not trusted from the row**. Reconstruction
  passes the stored hash to `ChangeProposal.__post_init__`, which
  re-derives it from the stored patch + base snapshot id and raises
  `ApprovalHashMismatch` on any divergence — a tampered row cannot
  produce a quietly-wrong proposal.

### Sync/async

The stores are sync (the existing ports); the repository is async (the
V1 pattern). They meet through the shared `AsyncBridge` (P-A.1) — the
recorded ONE-primitive decision, no second mechanism.

### Refusal mapping (20 §6)

Absent and foreign-tenant reads answer the identical named error
(`ProposalNotFound` / `UnknownSnapshot`) — the WHERE clause carries
`tenant_id`, so a foreign row is structurally invisible, same as every
V1 repository.

## Consequences

- Proposals/snapshots survive process restarts; the §14 review trail
  becomes durable evidence (P6) instead of process-local state.
- Snapshot JSONB rows grow with tree size; acceptable for the recorded
  V8 sandbox scope, revisit via object storage when evidence demands.
- Base64 inflates storage ~33%; accepted for schema simplicity at this
  scope (same tradeoff recorded for JSONB refs in 0003).

## Alternatives considered

- **bytea per file in a child table** — more relational purity, but the
  snapshot is read/written ONLY whole (content-addressed unit); a child
  table buys joins, not capability. Rejected for this scope.
- **Object storage (41 §6) now** — right for large trees, premature for
  the V8 sandbox scope; would add a second infrastructure dependency to
  the local-first runtime for no present need. Deferred, recorded.
