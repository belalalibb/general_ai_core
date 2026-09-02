"""S3 object-storage LIVE smoke (ADR-0006 real-server verification).

NOT part of the hermetic gates: every test here is SKIPPED unless the
``OBJECT_STORAGE_*`` deployment variables point at a REAL S3-compatible
server (MinIO/S3/R2) with an existing bucket. Same posture as the
provider live suites (tests/providers/test_*_live.py): skip-when-absent,
never fabricate a pass (41 §49).

Run manually against a local MinIO, e.g.:

    OBJECT_STORAGE_ENDPOINT=http://127.0.0.1:9000 \\
    OBJECT_STORAGE_BUCKET=smoke \\
    OBJECT_STORAGE_ACCESS_KEY=... OBJECT_STORAGE_SECRET_KEY=... \\
    python3 -m pytest tests/infrastructure/test_s3_live_smoke.py -v

Scope: the THIN slice the stubs cannot prove — that the adapter's calls
match the real wire protocol (real ClientError shapes, real pagination,
real LastModified). Port SEMANTICS are already proven hermetically
(t073); this suite only needs to catch protocol drift. Keys are
uuid-namespaced and cleaned up so reruns and shared buckets stay safe.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest

from apps.composition import build_object_storage, object_storage_settings_from_env
from core.storage.errors import ObjectNotFound
from infrastructure.storage import S3ObjectStorage

requires_live_s3 = pytest.mark.skipif(
    not os.environ.get("OBJECT_STORAGE_BUCKET"),
    reason="OBJECT_STORAGE_* not set — live S3 smoke runs manually only (41 §49)",
)

TENANT = uuid4()


@pytest.fixture()
def storage() -> Iterator[S3ObjectStorage]:
    settings = object_storage_settings_from_env()
    assert settings is not None  # guarded by the skip marker
    adapter = build_object_storage(settings)
    yield adapter
    # Cleanup: remove everything this test tenant wrote.
    for key in adapter.list_keys(TENANT):
        try:
            adapter.delete(TENANT, key)
        except ObjectNotFound:  # pragma: no cover - already gone
            pass


@requires_live_s3
class TestS3LiveSmoke:
    def test_put_get_head_delete_round_trip(self, storage: S3ObjectStorage) -> None:
        key = f"smoke/{uuid4()}.bin"
        payload = b"live-smoke-payload"

        stored = storage.put(TENANT, key, payload, "application/octet-stream")
        assert stored.size_bytes == len(payload)
        assert stored.content_type == "application/octet-stream"
        assert stored.created_at is not None  # real server clock

        assert storage.get(TENANT, key) == payload
        assert storage.head(TENANT, key).size_bytes == len(payload)

        storage.delete(TENANT, key)
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT, key)

    def test_real_not_found_error_shape_maps(self, storage: S3ObjectStorage) -> None:
        # The REAL server's 404/NoSuchKey shapes must map to ObjectNotFound —
        # this is exactly what a stub cannot prove.
        with pytest.raises(ObjectNotFound):
            storage.get(TENANT, f"never-written/{uuid4()}")
        with pytest.raises(ObjectNotFound):
            storage.head(TENANT, f"never-written/{uuid4()}")
        with pytest.raises(ObjectNotFound):
            storage.delete(TENANT, f"never-written/{uuid4()}")

    def test_listing_and_tenant_prefix_on_real_server(self, storage: S3ObjectStorage) -> None:
        keys = {f"smoke/a-{uuid4()}", f"smoke/b-{uuid4()}"}
        for key in keys:
            storage.put(TENANT, key, b"x", "text/plain")

        listed = set(storage.list_keys(TENANT, "smoke/"))
        assert keys <= listed
        # Logical keys only — the tenant prefix must not leak.
        assert all(str(TENANT) not in key for key in listed)

    def test_foreign_tenant_isolation_on_real_server(self, storage: S3ObjectStorage) -> None:
        key = f"smoke/{uuid4()}"
        storage.put(TENANT, key, b"mine", "text/plain")
        with pytest.raises(ObjectNotFound):
            storage.get(uuid4(), key)
