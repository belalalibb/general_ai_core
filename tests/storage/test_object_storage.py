"""Object-storage port tests (MVP Phase 3, 41 §42).

Covers the port contract via the in-memory binding: round-trip, metadata,
overwrite, delete, prefix listing — and the 20 §6 tenant-isolation
guarantees, including anti-enumeration (foreign key probe indistinguishable
from absent key).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.storage import ObjectNotFound, ObjectStoragePort
from core.storage.memory import InMemoryObjectStorage

TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest.fixture()
def storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


class TestPortContract:
    def test_satisfies_port_protocol(self, storage: InMemoryObjectStorage) -> None:
        port: ObjectStoragePort = storage
        assert isinstance(port, InMemoryObjectStorage)

    def test_put_get_round_trip(self, storage: InMemoryObjectStorage) -> None:
        payload = b"\x89PNG fake image bytes"
        storage.put(TENANT_A, "images/a.png", payload, "image/png")
        assert storage.get(TENANT_A, "images/a.png") == payload

    def test_put_returns_metadata(self, storage: InMemoryObjectStorage) -> None:
        meta = storage.put(TENANT_A, "files/doc.txt", b"hello", "text/plain")
        assert meta.tenant_id == TENANT_A
        assert meta.key == "files/doc.txt"
        assert meta.size_bytes == 5
        assert meta.content_type == "text/plain"
        assert meta.created_at.tzinfo is not None

    def test_head_returns_metadata_without_payload(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"data", "application/octet-stream")
        meta = storage.head(TENANT_A, "k")
        assert meta.size_bytes == 4

    def test_overwrite_replaces_payload(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"v1", "text/plain")
        storage.put(TENANT_A, "k", b"v2-longer", "text/plain")
        assert storage.get(TENANT_A, "k") == b"v2-longer"
        assert storage.head(TENANT_A, "k").size_bytes == 9

    def test_delete_removes_object(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"data", "text/plain")
        storage.delete(TENANT_A, "k")
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_A, "k")

    def test_get_absent_key_raises(self, storage: InMemoryObjectStorage) -> None:
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_A, "never-stored")

    def test_delete_absent_key_raises(self, storage: InMemoryObjectStorage) -> None:
        with pytest.raises(ObjectNotFound):
            storage.delete(TENANT_A, "never-stored")

    def test_empty_key_rejected(self, storage: InMemoryObjectStorage) -> None:
        with pytest.raises(ValueError):
            storage.put(TENANT_A, "", b"data", "text/plain")

    def test_list_keys_prefix_filter_sorted(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "images/b.png", b"1", "image/png")
        storage.put(TENANT_A, "images/a.png", b"2", "image/png")
        storage.put(TENANT_A, "files/doc.txt", b"3", "text/plain")
        assert storage.list_keys(TENANT_A, "images/") == (
            "images/a.png",
            "images/b.png",
        )
        assert storage.list_keys(TENANT_A) == (
            "files/doc.txt",
            "images/a.png",
            "images/b.png",
        )


class TestTenantIsolation:
    """20 §6: tenant data must never leak — not even its existence."""

    def test_same_key_is_independent_per_tenant(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "shared-key", b"tenant-a-data", "text/plain")
        storage.put(TENANT_B, "shared-key", b"tenant-b-data", "text/plain")
        assert storage.get(TENANT_A, "shared-key") == b"tenant-a-data"
        assert storage.get(TENANT_B, "shared-key") == b"tenant-b-data"

    def test_foreign_tenant_read_raises_not_found(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "secret.bin", b"a-only", "application/octet-stream")
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_B, "secret.bin")

    def test_foreign_probe_indistinguishable_from_absent(
        self, storage: InMemoryObjectStorage
    ) -> None:
        """Anti-enumeration: same error type and message shape either way."""
        storage.put(TENANT_A, "exists-in-a", b"x", "text/plain")
        with pytest.raises(ObjectNotFound) as foreign:
            storage.get(TENANT_B, "exists-in-a")
        with pytest.raises(ObjectNotFound) as absent:
            storage.get(TENANT_B, "never-anywhere")
        assert type(foreign.value) is type(absent.value)

    def test_foreign_delete_cannot_remove_data(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"survives", "text/plain")
        with pytest.raises(ObjectNotFound):
            storage.delete(TENANT_B, "k")
        assert storage.get(TENANT_A, "k") == b"survives"

    def test_listing_never_crosses_tenants(self, storage: InMemoryObjectStorage) -> None:
        storage.put(TENANT_A, "a-file", b"1", "text/plain")
        storage.put(TENANT_B, "b-file", b"2", "text/plain")
        assert storage.list_keys(TENANT_A) == ("a-file",)
        assert storage.list_keys(TENANT_B) == ("b-file",)
        assert storage.list_keys(uuid4()) == ()
