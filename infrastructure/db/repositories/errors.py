"""Named repository refusals (11 §14 posture — refusals are named data).

Anti-enumeration rule (20 §6): "absent" and "exists in a foreign tenant"
raise the SAME error type with the SAME message shape — existence must
not leak across tenants. This mirrors apps/api/store.py:ExecutionNotFound
and core/storage/errors.py:ObjectNotFound.
"""

from __future__ import annotations

from uuid import UUID


class RepositoryError(Exception):
    """Base class for repository failures."""


class ExecutionNotFound(RepositoryError):
    """No execution record exists for the requested id IN THIS TENANT.

    Deliberately identical for "absent" and "foreign tenant" (20 §6).
    """

    def __init__(self, execution_id: UUID) -> None:
        super().__init__(f"unknown execution id: {execution_id}")
        self.execution_id = execution_id


class DuplicateIdempotencyKey(RepositoryError):
    """A different execution already holds this (tenant, idempotency_key).

    10 §10: same tenant + same idempotency key must not create duplicate
    executions — the DB unique constraint is the durable authority; this
    error is its named surface.
    """

    def __init__(self, tenant_id: UUID, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key already used in this tenant: {idempotency_key}"
        )
        self.tenant_id = tenant_id
        self.idempotency_key = idempotency_key
