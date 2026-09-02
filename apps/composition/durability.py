"""P-A.1 — durable ExecutionStore binding over the EXISTING V1 repository.

Directive class: INERT SEAM (wire only, no migration).  The Postgres
side (``PostgresExecutionRepository``, tables from migration 0003) has
existed since V1 with zero production callers; this module gives it one
— WITHOUT touching route handlers, the worker, or the in-memory store
(P2: the composition root swaps implementations, call sites stay
byte-identical, exactly as ``apps/api/store.py`` promised).

Shape (recorded R138):

- WRITE-THROUGH: ``put`` persists the durable truth FIRST
  (Execution + nodes via the repository), THEN caches the full-fidelity
  ``ExecutionReport`` in the process-local in-memory store.  A durable
  write failure propagates loudly and caches NOTHING (P6 — no state
  that the database does not have).
- READ-THROUGH: ``get`` serves the cached full-fidelity report when
  present; on a cache miss (fresh process after restart) it reads the
  durable record and reconstructs a DEGRADED-BUT-HONEST report.
- LIST: the durable rows are the authority (they survive restarts);
  each row is presented through its cached full report when one exists,
  else through honest reconstruction from the root entity alone.

Degraded-but-honest reconstruction (41 §49 — never fake):

- Every API-visible field is derived from STORED FACTS: status,
  created_at, node statuses (→ progress), the succeeded output
  (``node.output_ref`` — the service stored the response output there),
  and the normalized failure (``node.error`` — the service stored the
  ``ProviderError`` dump there; same fact ``apps/api/streaming.py``
  already derives from).
- ``NodeReport.attempts`` were process-local diagnostics never durably
  promised — reconstructed as empty, never invented.
- ``status_history`` reconstructs as the single stored terminal status.
- The reconstructed ``ProviderGenerateResponse.request_id`` reuses the
  durable node id (the original request id was never persisted; this
  field never crosses the API — only ``.output`` does, via
  ``ExecutionReport.final_output``).
- Node ordering: the repository orders nodes by ``node_key`` (the
  schema has no sequence column — recorded 0003 limitation).  For the
  MVP pipeline shapes (``single``, ``stage-0..n`` with n<10) this equals
  pipeline order; a ≥10-stage pipeline would need a sequence column
  first (a migration, out of scope for this INERT seam — recorded).

Sync/async: all repository calls cross the shared
:class:`~apps.composition.bridge.AsyncBridge` (ONE primitive, R138).
Named refusals translate: the repository's ``ExecutionNotFound`` becomes
the app-level ``ExecutionNotFound`` route handlers already catch —
foreign-tenant and absent stay indistinguishable through BOTH layers
(20 §6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from apps.api.store import ExecutionNotFound, InMemoryExecutionStore
from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
)
from core.contracts.provider import ProviderGenerateResponse
from core.execution.service import ExecutionReport, NodeReport
from infrastructure.db.repositories.errors import (
    ExecutionNotFound as RepositoryExecutionNotFound,
)
from infrastructure.db.repositories.executions import ExecutionRecord


class ExecutionRepositoryPort(Protocol):
    """The async repository surface this store persists through.

    Structural mirror of ``PostgresExecutionRepository`` — hermetic
    tests bind a fake with identical semantics (41 §49: the live
    Postgres round-trip is tested env-gated, never simulated as green).
    """

    async def put(self, execution: Execution, nodes: tuple[ExecutionNode, ...] = ()) -> None: ...

    async def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionRecord: ...

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[Execution, ...]: ...


_TERMINAL_NODE_STATES = (
    ExecutionNodeStatus.SUCCEEDED,
    ExecutionNodeStatus.FAILED,
    ExecutionNodeStatus.SKIPPED,
)


def report_from_record(record: ExecutionRecord) -> ExecutionReport:
    """Reconstruct an :class:`ExecutionReport` from the durable record.

    Degraded-but-honest per the module docstring: every field is a
    stored fact or an explicitly-recorded absence — nothing invented.
    """
    node_reports = []
    for node in record.nodes:
        response: ProviderGenerateResponse | None = None
        if node.status is ExecutionNodeStatus.SUCCEEDED and isinstance(node.output_ref, dict):
            # The service stored ``run.response.output`` as output_ref
            # (core/execution/service.py) — reconstructing the response
            # restores ``final_output`` for the GET route.  request_id
            # reuses the durable node id (original never persisted;
            # never crosses the API — docstring).
            response = ProviderGenerateResponse(
                request_id=node.id,
                succeeded=True,
                output=node.output_ref,
            )
        node_reports.append(NodeReport(node=node, attempts=(), response=response))
    return ExecutionReport(
        execution=record.execution,
        nodes=tuple(node_reports),
        status_history=(record.execution.status,),
        usage=None,  # settlement ledger is process-local; absent ≠ zero
    )


class DurableExecutionStore:
    """Write-through durable ExecutionStore (P-A.1).

    Implements the exact sync surface of ``InMemoryExecutionStore``
    (structural ``ExecutionStorePort``) so ``create_app`` and the worker
    accept it unchanged.
    """

    def __init__(
        self,
        *,
        repository: ExecutionRepositoryPort,
        bridge: AsyncBridge,
        cache: InMemoryExecutionStore | None = None,
    ) -> None:
        self._repository = repository
        self._bridge = bridge
        self._cache = cache if cache is not None else InMemoryExecutionStore()

    def put(self, report: ExecutionReport) -> None:
        """Persist durably FIRST, then cache (P6 — no cache-only state).

        Repository refusals (e.g. ``DuplicateIdempotencyKey`` across a
        restart, where the process-local idempotency index is empty)
        propagate loudly and unchanged — a named constraint violation,
        never silently absorbed.
        """
        nodes = tuple(entry.node for entry in report.nodes)
        self._bridge.run(self._repository.put(report.execution, nodes))
        self._cache.put(report)

    def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionReport:
        """Cached full-fidelity report, else durable reconstruction.

        Foreign-tenant and absent raise the SAME app-level
        ``ExecutionNotFound`` through both layers (20 §6).
        """
        try:
            return self._cache.get(tenant_id, execution_id)
        except ExecutionNotFound:
            pass  # cache miss — the durable record is the authority
        try:
            record = self._bridge.run(self._repository.get(tenant_id, execution_id))
        except RepositoryExecutionNotFound as exc:
            raise ExecutionNotFound(execution_id) from exc
        report = report_from_record(record)
        # Re-cache the reconstruction: repeated polls of a restart-
        # recovered execution stay one DB round-trip, not many.  A later
        # live ``put`` overwrites with full fidelity.
        self._cache.put(report)
        return report

    def list(
        self,
        tenant_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        initiated_by: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[ExecutionReport, ...]:
        """Durable rows are the authority; cached reports enrich them.

        The repository applies tenant scoping and filters (semantics
        mirror the in-memory store exactly — recorded in the V1 repo).
        Rows without a cached report present as root-entity-only
        reconstructions (progress derives from zero nodes → absent, the
        honest posture for restart-recovered list rows; ``get`` serves
        the node-level reconstruction).
        """
        rows = self._bridge.run(
            self._repository.list(
                tenant_id,
                status=status,
                initiated_by=initiated_by,
                created_after=created_after,
                created_before=created_before,
                limit=limit,
            )
        )
        reports = []
        for execution in rows:
            try:
                reports.append(self._cache.get(tenant_id, execution.id))
            except ExecutionNotFound:
                reports.append(
                    ExecutionReport(
                        execution=execution,
                        nodes=(),
                        status_history=(execution.status,),
                        usage=None,
                    )
                )
        return tuple(reports)


def build_durable_execution_store(
    bindings: DatabaseBindings, bridge: AsyncBridge
) -> DurableExecutionStore:
    """Compose the durable store from the EXISTING V1 bindings.

    The env branch stays where it always was: callers obtain
    ``bindings`` via ``database_settings_from_env`` →
    ``build_database_bindings`` (None ⇒ not configured ⇒ keep the
    in-memory store — byte-identical to today, recorded posture).
    """
    return DurableExecutionStore(repository=bindings.executions, bridge=bridge)
