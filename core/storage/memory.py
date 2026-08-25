"""In-memory object storage (MVP Phase 3 skeleton binding, 41 §42).

Satisfies :class:`~core.storage.ports.ObjectStoragePort` against process
memory — the same skeleton discipline as ``InMemoryIdentityService``
(Phase 2): real S3-compatible infrastructure arrives later behind the same
port; tests and early wiring use this.

Isolation mechanics (20 §6): the physical namespace is keyed by
``(tenant_id, key)`` — a foreign tenant's key can never be addressed, and
probing it raises the same :class:`ObjectNotFound` as a truly absent key.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.base import utc_now
from core.storage.errors import ObjectNotFound
from core.storage.ports import StoredObject


class InMemoryObjectStorage:
    """Process-memory implementation of ``ObjectStoragePort``."""

    def __init__(self) -> None:
        self._objects: dict[tuple[UUID, str], tuple[StoredObject, bytes]] = {}

    def put(
        self, tenant_id: UUID, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        if not key:
            raise ValueError("object key must be non-empty")
        meta = StoredObject(
            tenant_id=tenant_id,
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            created_at=utc_now(),
        )
        self._objects[(tenant_id, key)] = (meta, bytes(data))
        return meta

    def get(self, tenant_id: UUID, key: str) -> bytes:
        entry = self._objects.get((tenant_id, key))
        if entry is None:
            raise ObjectNotFound(key)
        return entry[1]

    def head(self, tenant_id: UUID, key: str) -> StoredObject:
        entry = self._objects.get((tenant_id, key))
        if entry is None:
            raise ObjectNotFound(key)
        return entry[0]

    def delete(self, tenant_id: UUID, key: str) -> None:
        if self._objects.pop((tenant_id, key), None) is None:
            raise ObjectNotFound(key)

    def list_keys(self, tenant_id: UUID, prefix: str = "") -> tuple[str, ...]:
        return tuple(
            sorted(
                obj_key
                for (obj_tenant, obj_key) in self._objects
                if obj_tenant == tenant_id and obj_key.startswith(prefix)
            )
        )
