# ADR-0006 — Object Storage Production Binding (S3-compatible client)

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-29: "Accept ADR-0006 + ADR-0007")
DATE: 2026-08-28
DATE_ACCEPTED: 2026-08-29
TASK: T-IMPL-053 (proposal) / T-IMPL-073 (implementation)
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: the object-storage infrastructure binding must not land — and no
object-storage client dependency may be added to `pyproject.toml` — until
this ADR is ACCEPTED with explicit operator sign-off (same governance as
ADR-0001..0005).

---

## Context

Fixed constraints (41 §6; 40 §5.1; 20 §6; existing port):

```text
- 41 §6 Object Storage role (verbatim list): files, images, audio, video,
  datasets, large artifacts. Postgres stays the source of truth for
  structured data; blobs never live in table columns (the messages slice
  already records "attachments are references; large artifacts live in
  object storage").
- core/storage/ports.py (ObjectStoragePort) EXISTS with an in-memory
  implementation: tenant_id explicit on every method; per-tenant physical
  namespacing REQUIRED (20 §6); reads of absent OR foreign objects raise
  ObjectNotFound indistinguishably; bytes end-to-end. The binding must
  implement THIS port — the contract does not change.
- Import boundaries: the client library is confined to infrastructure/
  by a new import-linter contract in the SAME commit that pins the
  dependency (established pattern: ADR-0003 redis, ADR-0005 argon2).
- Hermetic gates: object storage needs a SERVER — unlike Argon2id, the
  real binding is NOT hermetically testable. Tests follow the ADR-0002/
  ADR-0003 posture: hermetic contract/shape tests + real-server smoke
  tests OUTSIDE the hermetic path (documented, not run in CI sandbox).
- Lane C closed: no production bucket exists; the binding lands
  configuration-driven (endpoint/credentials from environment at the
  composition root, resolved via the Secret Manager where applicable).
```

## Alternatives

### A. boto3 (official AWS SDK, sync)

Pros:

```text
- The de-facto S3 client; every S3-compatible store (AWS S3, MinIO, R2,
  Ceph RGW) documents against it.
- Battle-tested auth/retry/multipart machinery.
- ObjectStoragePort is sync (Protocol methods are def, not async def) —
  boto3 matches the port's current shape with zero adaptation.
```

Cons:

```text
- Heavy dependency tree (botocore); slow import.
- Sync-only: if the port later goes async (FastAPI context), a thread
  offload or a second binding would be needed.
- Types are loose; mypy --strict needs boto3-stubs.
```

### B. aioboto3 (async wrapper over boto3)

Pros:

```text
- Async-native fit for the FastAPI runtime.
```

Cons:

```text
- The CURRENT port is sync — adopting aioboto3 forces a port-shape change
  (async def) that ripples through core and every test double, a larger
  change than the storage slice itself.
- Wraps boto3 via aiobotocore: inherits the heavy tree PLUS a
  compatibility-pinning burden between three packages.
```

### C. minio-py (MinIO's lightweight S3 client)

Pros:

```text
- Small dependency; clean sync API; first-class S3-compatibility focus.
- Type-annotated; strict-friendly without extra stub packages.
```

Cons:

```text
- Less universal than boto3 (some AWS-specific auth modes absent).
- Smaller ecosystem; fewer eyes than the AWS SDK.
```

## Decision

ACCEPTED: **Alternative A (boto3)** with `boto3-stubs[s3]` as a dev
dependency: it matches the port's existing sync shape exactly, works
against every S3-compatible target the deployment might choose, and
follows the "boring, battle-tested" bias the stack ADRs (0001–0003)
established. Per-tenant namespacing implemented as key prefixing
(`{tenant_id}/{key}`) inside the adapter — the port's isolation contract,
enforced structurally.

## Reason

The port already fixes the semantics (tenant isolation, indistinguishable
not-found, bytes payloads); the ONLY open question is client choice.
Alternative B is rejected because it forces a core port-shape change for
an infrastructure preference — backwards. Alternative C remains viable if
the operator prefers a minimal tree; the recommendation weighs ecosystem
coverage higher.

## Consequences

```text
Easier: any S3-compatible backend (MinIO for dev, S3/R2 for prod) binds
        without code change — endpoint/credential configuration only.
Harder: real-server smoke tests need a running MinIO/S3 (documented,
        outside hermetic gates — ADR-0002 posture); boto3's import weight
        lands in infrastructure only (composition root pays it once).
Rollback: the in-memory implementation keeps passing the same port tests;
        deleting the adapter + dependency pin reverts cleanly.
```

## Status

ACCEPTED — explicit operator sign-off 2026-08-29 ("Accept ADR-0006 + ADR-0007").
Implementation: T-IMPL-073 — boto3 dependency + import-linter confinement
contract + `infrastructure/storage/s3.py` binding, all in the same commit
(established pattern: ADR-0003 redis, ADR-0005 argon2).
