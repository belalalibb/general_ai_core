"""Object-storage infrastructure bindings (ADR-0006: S3-compatible via boto3)."""

from infrastructure.storage.s3 import S3ObjectStorage

__all__ = ["S3ObjectStorage"]
