"""S3-compatible object-storage binding (ADR-0006, ACCEPTED 2026-08-29).

Binds :class:`core.storage.ports.ObjectStoragePort` via boto3's S3 client —
works against any S3-compatible target (AWS S3, MinIO, Cloudflare R2, Ceph
RGW): the backend choice is pure endpoint/credential configuration at the
composition root (Lane C), never code.

Spec anchors:

- 41 §6 / 40 §5.1 Object Storage role: blobs only (files, images, audio,
  video, datasets, large artifacts). PostgreSQL stays the source of truth
  for structured data.
- 20 §6 tenant isolation: per-tenant PHYSICAL namespacing is implemented as
  key prefixing — every S3 key is ``{tenant_id}/{key}``. The prefix is
  applied inside this adapter on EVERY operation; no code path can address
  another tenant's prefix, and ``list_keys`` can only ever enumerate the
  caller's prefix.
- Anti-enumeration (core/storage/errors.py): a missing object and a foreign
  tenant's object are indistinguishable — both surface as
  :class:`ObjectNotFound`. S3 reports both as 404/NoSuchKey under the
  tenant-prefixed key, so the property holds structurally.

Design decisions (recorded here):

- The boto3 CLIENT is injected, never constructed here: session/credential/
  endpoint wiring (incl. resolving credentials via the Secret Manager,
  ADR-0007) belongs to the composition root. This also keeps the binding
  hermetically testable against a stub satisfying the same method surface.
- The port is sync and boto3 is sync — zero adaptation (the deciding factor
  in ADR-0006).
- ``StoredObject.created_at``: S3's ``LastModified`` is the storage-side
  timestamp; for overwrites it reflects the LATEST write, matching the
  port's "overwrite allowed" semantics.
- Multipart/streaming upload is deliberately absent: the port is bytes
  end-to-end (its recorded contract); revisiting that is a port-level
  decision, not an adapter liberty.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from botocore.exceptions import ClientError

from core.storage.errors import ObjectNotFound
from core.storage.ports import StoredObject

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mypy_boto3_s3 import S3Client

#: S3 error codes that mean "no such object" for get/head/delete paths.
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


def _is_not_found(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code", "")
    return code in _NOT_FOUND_CODES


class S3ObjectStorage:
    """Production ``ObjectStoragePort`` binding (S3-compatible via boto3).

    ``bucket`` is a single pre-provisioned bucket; tenants are isolated by
    key prefix (20 §6) — creating/deleting buckets is a deployment concern
    and deliberately not part of this adapter.
    """

    def __init__(self, client: S3Client, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    @staticmethod
    def _object_key(tenant_id: UUID, key: str) -> str:
        """Physical S3 key: tenant prefix applied on EVERY operation (20 §6)."""
        return f"{tenant_id}/{key}"

    def put(
        self, tenant_id: UUID, key: str, data: bytes, content_type: str
    ) -> StoredObject:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._object_key(tenant_id, key),
            Body=data,
            ContentType=content_type,
        )
        # head after put: created_at comes from the STORE's clock, keeping
        # metadata consistent with what any later head() would report.
        return self.head(tenant_id, key)

    def get(self, tenant_id: UUID, key: str) -> bytes:
        try:
            response = self._s3.get_object(
                Bucket=self._bucket, Key=self._object_key(tenant_id, key)
            )
        except ClientError as error:
            if _is_not_found(error):
                raise ObjectNotFound(key) from None
            raise
        return response["Body"].read()

    def head(self, tenant_id: UUID, key: str) -> StoredObject:
        try:
            response = self._s3.head_object(
                Bucket=self._bucket, Key=self._object_key(tenant_id, key)
            )
        except ClientError as error:
            if _is_not_found(error):
                raise ObjectNotFound(key) from None
            raise
        return StoredObject(
            tenant_id=tenant_id,
            key=key,
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", "application/octet-stream"),
            created_at=response["LastModified"],
        )

    def delete(self, tenant_id: UUID, key: str) -> None:
        # S3 DeleteObject is idempotent (204 for absent keys) — the port
        # requires ObjectNotFound for absent keys, so existence is checked
        # first via head (same anti-enumeration semantics).
        self.head(tenant_id, key)
        self._s3.delete_object(
            Bucket=self._bucket, Key=self._object_key(tenant_id, key)
        )

    def list_keys(self, tenant_id: UUID, prefix: str = "") -> tuple[str, ...]:
        physical_prefix = self._object_key(tenant_id, prefix)
        tenant_prefix = f"{tenant_id}/"
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=physical_prefix):
            for item in page.get("Contents", []):
                # Strip the tenant prefix: callers only ever see logical keys.
                keys.append(item["Key"].removeprefix(tenant_prefix))
        return tuple(keys)
