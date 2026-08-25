"""Storage abstraction layer (MVP Phase 3, 41 §42).

Public surface: the object-storage port, its metadata value object, and its
errors. Real infrastructure bindings (S3-compatible object storage) arrive in
``infrastructure/`` in a later slice behind the same port; core stays pure.
"""

from core.storage.errors import ObjectNotFound, StorageError
from core.storage.memory import InMemoryObjectStorage
from core.storage.ports import ObjectStoragePort, StoredObject

__all__ = [
    "InMemoryObjectStorage",
    "ObjectNotFound",
    "ObjectStoragePort",
    "StorageError",
    "StoredObject",
]
