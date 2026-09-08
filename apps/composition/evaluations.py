"""Durable evaluation store binding — durable profile only (R177-FIX-11).

Closes G-A07-4: before this slice ``EvaluationPolicyService`` and the admin
evaluation reads sat over ``InMemoryEvaluationStore`` in BOTH profiles, so
the artefacts FIX-08 relies on for promotion evidence vanished on restart.
Now the ``DATABASE_URL`` branch of the runtime binds
:class:`DurableEvaluationStore` — the SAME sync ``EvaluationStorePort``
surface the in-memory binding exposes, with the async bridge inside —
over :class:`PostgresEvaluationRepository` writing the EXISTING
``evaluations`` table (migration 0010). The in-memory store remains the
hermetic default; no caller changes.

Same posture as ``apps/composition/sourcechange.py``: the repository is a
Protocol so hermetic tests can drive the store with a fake async repository
holding the same encoded payloads, and the live Postgres round-trip is
env-gated (41 §49).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.evaluation import EvaluationRecord
from infrastructure.db.repositories.evaluations import PostgresEvaluationRepository

__all__ = [
    "DurableEvaluationStore",
    "EvaluationRepositoryPort",
    "build_durable_evaluation_store",
]


class EvaluationRepositoryPort(Protocol):
    """Async persistence seam the durable store composes over."""

    async def record(self, evaluation: EvaluationRecord) -> None: ...

    async def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord: ...

    async def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]: ...


class DurableEvaluationStore:
    """Durable ``EvaluationStorePort`` binding (sync surface, bridge inside).

    Append-only: ``record`` inserts and returns the SAME record the caller
    passed (the port contract); a duplicate id surfaces the repository's
    :class:`DuplicateEvaluation`. Absent and foreign-tenant ids answer the
    identical :class:`EvaluationNotFound` through both layers (20 §6).
    Infrastructure failures propagate loudly — a store that swallowed a
    write failure would fake durability.
    """

    def __init__(self, *, repository: EvaluationRepositoryPort, bridge: AsyncBridge) -> None:
        self._repository = repository
        self._bridge = bridge

    def record(self, evaluation: EvaluationRecord) -> EvaluationRecord:
        self._bridge.run(self._repository.record(evaluation))
        return evaluation

    def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        return self._bridge.run(self._repository.get(tenant_id, evaluation_id))

    def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        return self._bridge.run(self._repository.list_for_execution(tenant_id, execution_id))


def build_durable_evaluation_store(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> DurableEvaluationStore:
    """Compose the durable store over the shared session factory.

    Callers reach here only via the ``database_settings_from_env`` branch —
    no DATABASE_URL, no durable store (in-memory binding, byte-identical
    to today).
    """
    repository = PostgresEvaluationRepository(bindings.session_factory)
    return DurableEvaluationStore(repository=repository, bridge=bridge)
