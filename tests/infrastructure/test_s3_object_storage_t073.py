"""S3 object-storage binding tests (ADR-0006, T-IMPL-073).

Hermetic posture (recorded in ADR-0006): a real S3 needs a SERVER, so the
hermetic suite drives the binding against an in-process stub that speaks
the exact boto3 S3-client surface the adapter uses (put_object/get_object/
head_object/delete_object/list_objects_v2 pagination + ClientError
not-found shapes). What is verified here is the ADAPTER's mapping logic:
tenant prefixing, anti-enumeration error collapse, metadata construction,
logical-key round-tripping. Real-server smoke tests (MinIO/S3) live
OUTSIDE hermetic gates per ADR-0002/0003 posture.

Authority: core/storage/ports.py (bound contract), 20 §6 (tenant
isolation), tests/storage/test_object_storage.py (the port-semantics
suite the in-memory implementation passes — mirrored where meaningful).
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError

from core.storage.errors import ObjectNotFound
from core.storage.ports import ObjectStoragePort, StoredObject
from infrastructure.storage import S3ObjectStorage

TENANT_A = UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = UUID("00000000-0000-0000-0000-00000000000b")


def _not_found(operation: str) -> ClientError:
    code = "NoSuchKey" if operation == "GetObject" else "404"
    return ClientError({"Error": {"Code": code, "Message": "absent"}}, operation)


class _Paginator:
    def __init__(self, objects: dict[str, tuple[bytes, str, datetime]]) -> None:
        self._objects = objects

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        contents = [{"Key": key} for key in sorted(self._objects) if key.startswith(Prefix)]
        # Two pages exercise the pagination loop.
        middle = len(contents) // 2
        return [{"Contents": contents[:middle]}, {"Contents": contents[middle:]}]


class StubS3Client:
    """In-process double for the exact S3-client surface the adapter uses."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, datetime]] = {}
        self.buckets_seen: set[str] = set()

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> dict[str, Any]:
        self.buckets_seen.add(Bucket)
        self.objects[Key] = (Body, ContentType, datetime.now(UTC))
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise _not_found("GetObject")
        body, _, _ = self.objects[Key]
        return {"Body": io.BytesIO(body)}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise _not_found("HeadObject")
        body, content_type, created = self.objects[Key]
        return {
            "ContentLength": len(body),
            "ContentType": content_type,
            "LastModified": created,
        }

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        # Faithful to S3: idempotent, silent for absent keys.
        self.objects.pop(Key, None)
        return {}

    def get_paginator(self, name: str) -> _Paginator:
        assert name == "list_objects_v2"
        return _Paginator(self.objects)


@pytest.fixture()
def stub() -> StubS3Client:
    return StubS3Client()


@pytest.fixture()
def storage(stub: StubS3Client) -> S3ObjectStorage:
    return S3ObjectStorage(stub, "test-bucket")  # type: ignore[arg-type]


class TestPortConformance:
    def test_satisfies_port_protocol(self, storage: S3ObjectStorage) -> None:
        port: ObjectStoragePort = storage
        assert port is storage

    def test_put_get_round_trip(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "docs/a.txt", b"payload", "text/plain")
        assert storage.get(TENANT_A, "docs/a.txt") == b"payload"

    def test_put_returns_metadata(self, storage: S3ObjectStorage) -> None:
        stored = storage.put(TENANT_A, "docs/a.txt", b"12345", "text/plain")
        assert isinstance(stored, StoredObject)
        assert stored.tenant_id == TENANT_A
        assert stored.key == "docs/a.txt"
        assert stored.size_bytes == 5
        assert stored.content_type == "text/plain"

    def test_head_returns_metadata_without_payload(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"abc", "application/octet-stream")
        meta = storage.head(TENANT_A, "k")
        assert meta.size_bytes == 3
        assert not hasattr(meta, "data")

    def test_overwrite_replaces_payload(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"old", "text/plain")
        storage.put(TENANT_A, "k", b"new-payload", "text/plain")
        assert storage.get(TENANT_A, "k") == b"new-payload"
        assert storage.head(TENANT_A, "k").size_bytes == len(b"new-payload")

    def test_delete_removes_object(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"x", "text/plain")
        storage.delete(TENANT_A, "k")
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_A, "k")

    def test_get_absent_key_raises(self, storage: S3ObjectStorage) -> None:
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_A, "missing")

    def test_head_absent_key_raises(self, storage: S3ObjectStorage) -> None:
        with pytest.raises(ObjectNotFound):
            storage.head(TENANT_A, "missing")

    def test_delete_absent_key_raises(self, storage: S3ObjectStorage) -> None:
        # S3's DeleteObject is silently idempotent; the ADAPTER must still
        # honour the port's ObjectNotFound contract.
        with pytest.raises(ObjectNotFound):
            storage.delete(TENANT_A, "missing")

    def test_list_keys_prefix_filter(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "docs/a", b"1", "t")
        storage.put(TENANT_A, "docs/b", b"2", "t")
        storage.put(TENANT_A, "img/c", b"3", "t")
        assert set(storage.list_keys(TENANT_A, "docs/")) == {"docs/a", "docs/b"}
        assert set(storage.list_keys(TENANT_A)) == {"docs/a", "docs/b", "img/c"}

    def test_list_keys_returns_logical_keys(self, storage: S3ObjectStorage) -> None:
        # The tenant prefix is an adapter-internal detail — it must never
        # leak into the keys callers see.
        storage.put(TENANT_A, "k1", b"1", "t")
        keys = storage.list_keys(TENANT_A)
        assert keys == ("k1",)
        assert not any(str(TENANT_A) in key for key in keys)


class TestTenantIsolation:
    def test_physical_keys_are_tenant_prefixed(
        self, storage: S3ObjectStorage, stub: StubS3Client
    ) -> None:
        # The 20 §6 mechanism itself: every physical key carries the tenant.
        storage.put(TENANT_A, "shared-name", b"a", "t")
        storage.put(TENANT_B, "shared-name", b"b", "t")
        assert set(stub.objects) == {
            f"{TENANT_A}/shared-name",
            f"{TENANT_B}/shared-name",
        }

    def test_same_key_is_independent_per_tenant(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"tenant-a", "t")
        storage.put(TENANT_B, "k", b"tenant-b", "t")
        assert storage.get(TENANT_A, "k") == b"tenant-a"
        assert storage.get(TENANT_B, "k") == b"tenant-b"

    def test_foreign_tenant_read_raises_not_found(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"secret", "t")
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT_B, "k")

    def test_foreign_probe_indistinguishable_from_absent(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"secret", "t")
        with pytest.raises(ObjectNotFound) as foreign:
            storage.get(TENANT_B, "k")
        with pytest.raises(ObjectNotFound) as absent:
            storage.get(TENANT_B, "never-existed")
        assert type(foreign.value) is type(absent.value)

    def test_foreign_delete_cannot_remove_data(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "k", b"keep", "t")
        with pytest.raises(ObjectNotFound):
            storage.delete(TENANT_B, "k")
        assert storage.get(TENANT_A, "k") == b"keep"

    def test_listing_never_crosses_tenants(self, storage: S3ObjectStorage) -> None:
        storage.put(TENANT_A, "a1", b"1", "t")
        storage.put(TENANT_B, "b1", b"2", "t")
        assert storage.list_keys(TENANT_A) == ("a1",)
        assert storage.list_keys(TENANT_B) == ("b1",)
        # Empty-prefix listing for a fresh tenant sees NOTHING.
        assert storage.list_keys(uuid4()) == ()


class TestErrorFidelity:
    def test_non_not_found_errors_propagate(self, stub: StubS3Client) -> None:
        # The adapter must not swallow real faults into ObjectNotFound.
        class Failing(StubS3Client):
            def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
                raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetObject")

        storage = S3ObjectStorage(Failing(), "b")  # type: ignore[arg-type]
        with pytest.raises(ClientError):
            storage.get(TENANT_A, "k")
