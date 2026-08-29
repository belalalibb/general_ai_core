# ADR-0007 — Secret Manager Production Binding

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-29: "Accept ADR-0006 + ADR-0007")
DATE: 2026-08-28
DATE_ACCEPTED: 2026-08-29
TASK: T-IMPL-053 (proposal) / T-IMPL-074 (implementation)
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: the secret-manager infrastructure binding must not land — and no
secret-manager client dependency may be added to `pyproject.toml` — until
this ADR is ACCEPTED with explicit operator sign-off.

---

## Context

Fixed constraints (20 §5 verbatim; 40 §5.1; 41 §6; existing port):

```text
- 20 §5: secrets stored ONLY in a Secret Manager/KMS-backed system; the
  DB stores credential_ref only (the credentials table, migration 0012,
  already enforces this — ref column, no value column); no secrets in
  logs.
- core/secrets/ports.py (SecretManagerPort) EXISTS with an in-memory
  implementation: store() is the only method that sees a value and mints
  an immutable opaque ref; resolve() is the only method that returns one;
  refs are tenant-scoped (20 §6); NO list/dump/export operation exists.
  The binding must implement THIS port.
- Unlike the object-storage decision, the BACKEND choice here is a
  deployment-environment decision (which secret manager runs in prod?)
  that only the operator can make — the client library follows from it.
- Hermetic gates: same posture as ADR-0006 — hermetic contract tests +
  real-backend smoke tests outside the hermetic path.
- Lane C closed: no production secret manager exists yet.
```

## Alternatives

### A. HashiCorp Vault (client: hvac)

Pros:

```text
- Backend-agnostic deployment (self-host or HCP); KV v2 versioning maps
  cleanly to the port's immutable-ref rotation model (store new + revoke
  old == new KV version + destroy old).
- hvac is the mature official-adjacent Python client.
- Cloud-neutral: no coupling of the platform to one hyperscaler.
```

Cons:

```text
- Operating Vault itself is real infrastructure work (sealing, HA,
  audit device configuration).
- hvac types are loose; strict mypy needs care.
```

### B. AWS Secrets Manager (client: boto3, shared with ADR-0006)

Pros:

```text
- Zero additional dependency IF ADR-0006 Alternative A is accepted —
  boto3 covers both roles; one pinned tree, one import-linter contract.
- Managed service: no secret-manager infrastructure to operate.
```

Cons:

```text
- Couples secret custody to AWS specifically (R2/MinIO work S3-compatibly
  for storage, but Secrets Manager has no such compatibility ecosystem).
- Per-secret pricing; ref semantics (ARN + version-stage) need a thin
  mapping layer to the port's opaque-ref model.
```

### C. Environment/file-based secrets (no new dependency)

Pros:

```text
- No dependency, no external service; deployable TODAY for dev/staging.
- The composition root already reads environment configuration.
```

Cons:

```text
- NOT a "Secret Manager/KMS-backed system" — fails the 20 §5 verbatim
  requirement for PRODUCTION; acceptable only as the dev-profile default
  the way the in-memory port double already serves tests.
- No rotation/audit machinery; refs degenerate to variable names.
```

## Decision

ACCEPTED: **Alternative A (Vault via hvac)** for cloud-neutrality, with
**Alternative B recorded as the stated fallback** if the deployment lands on AWS
and ADR-0006's boto3 is accepted (one shared dependency tree). In BOTH
cases the in-memory implementation remains the dev/test profile;
Alternative C is recorded as REJECTED for production (20 §5 verbatim).

## Reason

The port already enforces the security semantics (single sight of the
value, opaque refs, tenant scoping, no export surface); the decision is
custody backend + client. That is an operations/deployment call —
proposing both viable paths with a recommendation honors the ADR protocol
without fabricating an infrastructure decision the specs leave to the
operator.

## Consequences

```text
Easier: credentials table (0012) + Credential contract already carry
        refs — the binding slots in with zero schema change.
Harder: Vault path adds an operated service; AWS path adds cloud
        coupling. Real-backend smoke tests live outside hermetic gates.
Rollback: in-memory implementation keeps the port green; removing the
        adapter + pin reverts cleanly.
```

## Status

ACCEPTED — explicit operator sign-off 2026-08-29 ("Accept ADR-0006 + ADR-0007").
Backend: HashiCorp Vault (KV v2); client: hvac. Alternative C stays
REJECTED for production (20 §5 verbatim); the in-memory implementation
remains the dev/test profile. Implementation: T-IMPL-074 — hvac dependency
+ import-linter confinement contract + `infrastructure/secrets/vault.py`
binding, all in the same commit.
