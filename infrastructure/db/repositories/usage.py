"""PostgreSQL usage repository — UsageAccountingPort binding.

Binds :class:`core.usage.ports.UsageAccountingPort` (03 §7; 10 §8; 21 §5)
against the ``usage_ledger`` table (migration 0009) with entitlements
sourced from ``plans``/``tenants`` (migrations 0001/0002).

Design decisions (recorded):

- DURABLE BUDGET DERIVATION — no budgets table exists and none is
  invented. The 21 §5 authority is explicit: "plan ``limits.task_units``
  is the tenant entitlement the ledger reserves against". Therefore:
  entitlement = ``plans.limits`` (parsed through the ``PlanLimits``
  contract — extra keys reject loudly, deny-by-default) reached via
  ``tenants.plan_id``; ``held``/``consumed`` are AGGREGATED from the
  ledger itself (held = Σ units_reserved of RESERVED rows; consumed =
  Σ units_settled of resolved rows — identical to the in-memory
  ``budget.held``/``budget.consumed`` bookkeeping, but with the ledger
  as the single source of truth). Plan changes preserving consumed/held
  (in-memory ``configure_tenant`` invariant) is therefore automatic.
- ``configure_tenant`` is the SAME admin seam: it upserts the plan row
  BY NAME (plans.name is UNIQUE — the 21 §5 ``plan:`` configuration
  key) merging ``limits`` via JSONB ``||`` (preserves keys this seam
  does not own, e.g. ``max_parallel_executions``), then points
  ``tenants.plan_id`` at it. RECORDED DIVERGENCE: plans are a SHARED
  catalog (21 §5) — two tenants configured onto the same plan name
  share limits; the in-memory per-tenant copy is process-local
  convenience, the durable model is the spec's. An unknown tenant is a
  wiring bug (identity slice owns tenant rows): loud ``ValueError``.
- DENY-BY-DEFAULT mapping: absent tenant row → ``EntitlementNotConfigured``
  (no identity = no entitlement); a tenant whose plan ``limits`` lacks
  ``task_units`` gets the contract default 0 — every positive
  reservation is denied ``BudgetExceeded`` (a plan grants nothing it
  does not state, core/contracts/plan.py posture).
- CONCURRENCY: ``reserve`` serializes per tenant by locking the tenant
  row (``FOR UPDATE OF tenants``) before the budget check — two
  concurrent reserves cannot both pass against the same remainder.
  The ``uq_usage_ledger_execution_id`` constraint is the durable
  authority for "one reservation per execution": an insert race
  surfaces as ``ReservationAlreadyResolved`` (same error, same facts).
  ``_resolve`` locks the ledger row (``FOR UPDATE``) — a reservation
  resolves exactly once (03 §7).
- The refusal ladder, error types and messages are core's own
  (core/usage/errors.py — fix once, benefit everywhere); validation of
  negative units happens BEFORE any I/O, mirroring the in-memory
  binding line for line.
- The port is sync (Protocol methods are ``def``); this binding is
  async (asyncpg) — same recorded posture as the conversation binding:
  the composition root owns the bridge; names/shapes match otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.base import JsonObject
from core.contracts.plan import PlanLimits
from core.contracts.usage import TaskUnitBudget, UsageLedger, UsageLedgerStatus, UsageSummary
from core.usage.errors import (
    BudgetExceeded,
    EntitlementNotConfigured,
    ReservationAlreadyResolved,
    ReservationNotFound,
)
from infrastructure.db.tables import plans, tenants, usage_ledger

_EXECUTION_UNIQUE_CONSTRAINT = "uq_usage_ledger_execution_id"


def _row_to_ledger(row: Any) -> UsageLedger:
    return UsageLedger(
        id=row.id,
        tenant_id=row.tenant_id,
        execution_id=row.execution_id,
        units_reserved=row.units_reserved,
        units_settled=row.units_settled,
        modality_costs=row.modality_costs,
        status=row.status,
    )


class PostgresUsageRepository:
    """Durable UsageAccountingPort binding over asyncpg sessions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._sessions = session_factory
        self._id_factory = id_factory

    # --- entitlement configuration (the 21 §5 plan seam) ----------------------

    async def configure_tenant(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        task_units_limit: float,
        modality_limits: JsonObject | None = None,
    ) -> None:
        """Grant/replace the tenant's plan budget (admin control plane seam).

        Upserts the SHARED plan catalog row by name (21 §5) and points the
        tenant at it. Ledger-derived accounting means consumed/held survive
        any plan change by construction (in-memory invariant preserved).
        """
        if task_units_limit < 0:
            msg = "task_units_limit must be >= 0"
            raise ValueError(msg)
        new_limits: JsonObject = {
            "task_units": task_units_limit,
            "modality_limits": dict(modality_limits) if modality_limits else {},
        }
        insert_stmt = pg_insert(plans).values(
            id=self._id_factory(),
            name=plan,
            limits=new_limits,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["name"],
            # JSONB merge: this seam owns task_units/modality_limits only;
            # other limit keys (e.g. max_parallel_executions) survive.
            set_={"limits": plans.c.limits.op("||")(insert_stmt.excluded.limits)},
        ).returning(plans.c.id)
        async with self._sessions() as session:
            async with session.begin():
                plan_id = (await session.execute(upsert_stmt)).scalar_one()
                result = await session.execute(
                    update(tenants)
                    .where(tenants.c.id == tenant_id)
                    .values(plan_id=plan_id)
                    .returning(tenants.c.id)
                )
                if result.scalar_one_or_none() is None:
                    msg = f"unknown tenant: {tenant_id}"
                    raise ValueError(msg)

    # --- port implementation ---------------------------------------------------

    async def reserve(
        self, tenant_id: UUID, execution_id: UUID, units: float
    ) -> UsageLedger:
        if units < 0:
            msg = "reservation units must be >= 0"
            raise ValueError(msg)
        try:
            async with self._sessions() as session:
                async with session.begin():
                    budget = await self._read_budget(
                        session, tenant_id, lock_tenant=True
                    )
                    if budget is None:
                        raise EntitlementNotConfigured(tenant_id)
                    _, limits = budget
                    existing = (
                        await session.execute(
                            select(usage_ledger.c.status).where(
                                usage_ledger.c.execution_id == execution_id
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        raise ReservationAlreadyResolved(execution_id, existing)
                    used = await self._read_used(session, tenant_id)
                    remaining = limits.task_units - used
                    if units > remaining:
                        raise BudgetExceeded(
                            tenant_id, requested=units, remaining=max(remaining, 0.0)
                        )
                    row = (
                        await session.execute(
                            usage_ledger.insert()
                            .values(
                                id=self._id_factory(),
                                tenant_id=tenant_id,
                                execution_id=execution_id,
                                units_reserved=units,
                                units_settled=0.0,
                                modality_costs={},
                                status=UsageLedgerStatus.RESERVED.value,
                            )
                            .returning(usage_ledger)
                        )
                    ).one()
                    return _row_to_ledger(row)
        except IntegrityError as exc:
            # Insert race lost: the unique constraint is the durable
            # authority for one-reservation-per-execution.
            if _EXECUTION_UNIQUE_CONSTRAINT not in str(exc.orig):
                raise
            status = await self._read_status(execution_id)
            if status is None:  # pragma: no cover - constraint fired, row gone
                raise
            raise ReservationAlreadyResolved(execution_id, status) from exc

    async def settle(
        self,
        execution_id: UUID,
        units_settled: float,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return await self._resolve(
            execution_id,
            units_settled,
            UsageLedgerStatus.SETTLED,
            modality_costs=modality_costs,
        )

    async def refund(self, execution_id: UUID) -> UsageLedger:
        return await self._resolve(execution_id, 0.0, UsageLedgerStatus.REFUNDED)

    async def fail(
        self,
        execution_id: UUID,
        units_settled: float = 0,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        return await self._resolve(
            execution_id,
            units_settled,
            UsageLedgerStatus.FAILED,
            modality_costs=modality_costs,
        )

    async def get(self, execution_id: UUID) -> UsageLedger:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(usage_ledger).where(
                        usage_ledger.c.execution_id == execution_id
                    )
                )
            ).one_or_none()
        if row is None:
            raise ReservationNotFound(execution_id)
        return _row_to_ledger(row)

    async def summary(self, tenant_id: UUID) -> UsageSummary:
        async with self._sessions() as session:
            budget = await self._read_budget(session, tenant_id, lock_tenant=False)
            if budget is None:
                raise EntitlementNotConfigured(tenant_id)
            plan_name, limits = budget
            used = await self._read_used(session, tenant_id)
        return UsageSummary(
            plan=plan_name,
            task_units=TaskUnitBudget(
                limit=limits.task_units,
                used=used,
                remaining=max(limits.task_units - used, 0.0),
            ),
            modality_limits=dict(limits.modality_limits),
        )

    # --- internals ----------------------------------------------------------------

    async def _read_budget(
        self, session: AsyncSession, tenant_id: UUID, *, lock_tenant: bool
    ) -> tuple[str, PlanLimits] | None:
        """The tenant's durable entitlement: plan name + parsed 21 §5 limits."""
        stmt = (
            select(plans.c.name, plans.c.limits)
            .select_from(tenants.join(plans, tenants.c.plan_id == plans.c.id))
            .where(tenants.c.id == tenant_id)
        )
        if lock_tenant:
            # Per-tenant serialization of budget checks (recorded above).
            stmt = stmt.with_for_update(of=tenants)
        row = (await session.execute(stmt)).one_or_none()
        if row is None:
            return None
        # PlanLimits is the 21 §5 authority — unknown keys reject loudly.
        return row.name, PlanLimits.model_validate(row.limits)

    async def _read_used(self, session: AsyncSession, tenant_id: UUID) -> float:
        """used = consumed + held, aggregated from the ledger (single truth)."""
        reserved = UsageLedgerStatus.RESERVED.value
        held_sum = func.coalesce(
            func.sum(usage_ledger.c.units_reserved).filter(
                usage_ledger.c.status == reserved
            ),
            0.0,
        )
        consumed_sum = func.coalesce(
            func.sum(usage_ledger.c.units_settled).filter(
                usage_ledger.c.status != reserved
            ),
            0.0,
        )
        row = (
            await session.execute(
                select(held_sum, consumed_sum).where(
                    usage_ledger.c.tenant_id == tenant_id
                )
            )
        ).one()
        return float(row[0]) + float(row[1])

    async def _read_status(self, execution_id: UUID) -> str | None:
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(usage_ledger.c.status).where(
                        usage_ledger.c.execution_id == execution_id
                    )
                )
            ).scalar_one_or_none()

    async def _resolve(
        self,
        execution_id: UUID,
        units_settled: float,
        status: UsageLedgerStatus,
        *,
        modality_costs: JsonObject | None = None,
    ) -> UsageLedger:
        if units_settled < 0:
            msg = "units_settled must be >= 0"
            raise ValueError(msg)
        async with self._sessions() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(usage_ledger)
                        .where(usage_ledger.c.execution_id == execution_id)
                        .with_for_update()
                    )
                ).one_or_none()
                if row is None:
                    raise ReservationNotFound(execution_id)
                if row.status != UsageLedgerStatus.RESERVED.value:
                    raise ReservationAlreadyResolved(execution_id, row.status)
                # Book the actual consumption (may exceed the reservation —
                # honest accounting, never clamped; in-memory rule verbatim).
                updated = (
                    await session.execute(
                        update(usage_ledger)
                        .where(usage_ledger.c.execution_id == execution_id)
                        .values(
                            units_settled=units_settled,
                            status=status.value,
                            modality_costs=(
                                dict(modality_costs) if modality_costs else {}
                            ),
                        )
                        .returning(usage_ledger)
                    )
                ).one()
                return _row_to_ledger(updated)
