"""Object-storage errors (closed, minimal set for the MVP port).

A missing object and a cross-tenant read are indistinguishable to callers:
both raise :class:`ObjectNotFound` (anti-enumeration; 20 §6 — tenant data
must never leak, not even its existence).
"""

from __future__ import annotations


class StorageError(Exception):
    """Base class for object-storage failures."""


class ObjectNotFound(StorageError):
    """No object at this key within the caller's tenant scope.

    Deliberately also raised for objects that exist in ANOTHER tenant:
    cross-tenant probes must not be able to distinguish "absent" from
    "present elsewhere" (20 §6).
    """
