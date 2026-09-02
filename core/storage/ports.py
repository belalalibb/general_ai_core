"""Object-storage port (dependency-inversion boundary; MVP Phase 3, 41 §42).

Spec anchors:

- 41 §42 deliverable: "object storage abstraction".
- 40 §5.1 storage roles: Object Storage = images, audio, video, files,
  datasets, large artifacts, model artifacts. PostgreSQL stays the source
  of truth for structured data; this port is for blobs only.
- 20 §6 tenant isolation: every operation is tenant-scoped. Keys are only
  meaningful within a tenant namespace; there is deliberately NO
  cross-tenant or "global" read operation on this port.
- 02 §5: object storage is an infrastructure component; core sees only
  this abstraction.

Design decisions (recorded here, mirroring the identity-port pattern):

- ``tenant_id`` is an explicit parameter on every method, not ambient
  state — isolation is enforced at the boundary, never inferred.
- Payloads are ``bytes`` end-to-end. Streaming/multipart upload is an
  infrastructure concern of the real S3-compatible binding (later slice)
  and does not change this contract.
- Metadata travels as an immutable :class:`StoredObject` value object;
  the port never exposes provider-native handles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class StoredObject:
    """Immutable metadata for one stored blob (never the payload itself)."""

    tenant_id: UUID
    key: str
    size_bytes: int
    content_type: str
    created_at: datetime


class ObjectStoragePort(Protocol):
    """Tenant-scoped blob storage (40 §5.1 Object Storage role).

    Every method takes ``tenant_id`` explicitly; implementations MUST
    namespace physical storage per tenant so no key can address another
    tenant's data (20 §6). Reads of absent OR foreign objects raise
    ``ObjectNotFound`` indistinguishably.
    """

    def put(self, tenant_id: UUID, key: str, data: bytes, content_type: str) -> StoredObject:
        """Store ``data`` at ``key`` within ``tenant_id``; overwrite allowed."""
        ...

    def get(self, tenant_id: UUID, key: str) -> bytes:
        """Return the payload at ``key`` within ``tenant_id`` or raise ObjectNotFound."""
        ...

    def head(self, tenant_id: UUID, key: str) -> StoredObject:
        """Return metadata only (no payload) or raise ObjectNotFound."""
        ...

    def delete(self, tenant_id: UUID, key: str) -> None:
        """Delete the object at ``key``; raise ObjectNotFound if absent."""
        ...

    def list_keys(self, tenant_id: UUID, prefix: str = "") -> tuple[str, ...]:
        """List keys under ``prefix`` — only ever within ``tenant_id``."""
        ...
