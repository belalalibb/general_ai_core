"""Object-storage composition wiring (ADR-0006 binding at the root).

Environment contract (deployment surface — Lane C):

- ``OBJECT_STORAGE_ENDPOINT``    — S3-compatible endpoint URL (MinIO/R2/…);
                                   empty/absent for AWS S3 proper.
- ``OBJECT_STORAGE_BUCKET``      — REQUIRED. The single pre-provisioned
                                   bucket (tenancy is key-prefixing inside
                                   the adapter, 20 §6).
- ``OBJECT_STORAGE_ACCESS_KEY``  — REQUIRED (with SECRET_KEY) unless the
                                   runtime provides ambient credentials
                                   (IAM role / instance profile).
- ``OBJECT_STORAGE_SECRET_KEY``  — see above. Values are handed straight
                                   to boto3 and NEVER logged (20 §5).
- ``OBJECT_STORAGE_REGION``      — optional (default us-east-1; MinIO
                                   ignores it).

"Not configured ⇒ absent": without a BUCKET there is nothing to bind and
``object_storage_settings_from_env`` returns None — callers keep the
in-memory profile. Partial credential configuration (one of ACCESS/SECRET
without the other) is an ERROR, not a guess: silently proceeding could
bind production storage to anonymous access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import boto3

from infrastructure.storage import S3ObjectStorage

_ENV_ENDPOINT = "OBJECT_STORAGE_ENDPOINT"
_ENV_BUCKET = "OBJECT_STORAGE_BUCKET"
_ENV_ACCESS_KEY = "OBJECT_STORAGE_ACCESS_KEY"
_ENV_SECRET_KEY = "OBJECT_STORAGE_SECRET_KEY"
_ENV_REGION = "OBJECT_STORAGE_REGION"


@dataclass(frozen=True, slots=True)
class ObjectStorageSettings:
    """Validated object-storage deployment settings (no secrets in repr)."""

    bucket: str
    endpoint_url: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    region: str = "us-east-1"

    def __repr__(self) -> str:  # 20 §5: credentials never appear in repr/logs
        return (
            f"ObjectStorageSettings(bucket={self.bucket!r}, "
            f"endpoint_url={self.endpoint_url!r}, region={self.region!r}, "
            f"credentials={'set' if self.access_key else 'ambient'})"
        )


def object_storage_settings_from_env(
    environ: dict[str, str] | None = None,
) -> ObjectStorageSettings | None:
    """Read settings from the environment; None when not configured.

    ``environ`` is injectable for hermetic tests; production callers pass
    nothing and get ``os.environ``.
    """
    env = os.environ if environ is None else environ
    bucket = env.get(_ENV_BUCKET, "").strip()
    if not bucket:
        return None  # not configured ⇒ binding absent (recorded posture)

    access_key = env.get(_ENV_ACCESS_KEY, "").strip() or None
    secret_key = env.get(_ENV_SECRET_KEY, "").strip() or None
    if (access_key is None) != (secret_key is None):
        raise ValueError(
            "Object storage misconfigured: OBJECT_STORAGE_ACCESS_KEY and "
            "OBJECT_STORAGE_SECRET_KEY must be provided together (or neither, "
            "for ambient IAM credentials)."
        )

    return ObjectStorageSettings(
        bucket=bucket,
        endpoint_url=env.get(_ENV_ENDPOINT, "").strip() or None,
        access_key=access_key,
        secret_key=secret_key,
        region=env.get(_ENV_REGION, "").strip() or "us-east-1",
    )


def build_object_storage(settings: ObjectStorageSettings) -> S3ObjectStorage:
    """Construct the production binding from validated settings.

    The ONLY place a boto3 S3 client is created for the platform.
    """
    client = boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region,
    )
    return S3ObjectStorage(client, settings.bucket)
