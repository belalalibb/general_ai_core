"""Usage contract — UsageLedger entity + task-unit accounting shapes.

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md §7
  (``UsageLedger`` — carried exactly: no field added, renamed, or dropped;
  the 4-state closed set ``reserved|settled|refunded|failed`` verbatim).
- final_docs_v3/10_API_CONTRACTS.md §8 (GET /v1/usage: ``task_units``
  limit/used/remaining block, ``modality_limits`` map) and §3 (the sync
  response ``usage`` block lives in :mod:`core.contracts.execute` as
  ``UsageReport`` — this module does not duplicate it).
- final_docs_v3/21_ADMIN_CONTROL_PLANE.md §5 (plan ``limits.task_units``
  is the tenant entitlement the ledger reserves against).

Ledger lifecycle (03 §7 semantics, recorded once):

    reserved  — units held against the tenant budget BEFORE execution.
    settled   — reservation finalized from actual usage AFTER execution.
    refunded  — reservation released without any settled consumption.
    failed    — execution failed; reservation resolution recorded as failed
                settlement (units still accounted per policy, never lost).

``modality_costs`` stays a free JSON object (03 §7 ``json``): per-modality
breakdowns (e.g. image generations) are policy data, not contract structure.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from core.contracts.base import ContractModel, JsonObject


class UsageLedgerStatus(StrEnum):
    """UsageLedger states (03 §7) — verbatim, closed set."""

    RESERVED = "reserved"
    SETTLED = "settled"
    REFUNDED = "refunded"
    FAILED = "failed"


class UsageLedger(ContractModel):
    """Usage ledger entry (03 §7) — one reservation/settlement per execution."""

    id: UUID
    tenant_id: UUID
    execution_id: UUID
    units_reserved: Annotated[float, Field(ge=0)]
    units_settled: Annotated[float, Field(ge=0)] = 0
    modality_costs: JsonObject = Field(default_factory=dict)
    status: UsageLedgerStatus


class TaskUnitBudget(ContractModel):
    """``task_units`` block of GET /v1/usage (10 §8): limit/used/remaining."""

    limit: Annotated[float, Field(ge=0)]
    used: Annotated[float, Field(ge=0)]
    remaining: Annotated[float, Field(ge=0)]


class UsageSummary(ContractModel):
    """GET /v1/usage response (10 §8)."""

    plan: str
    task_units: TaskUnitBudget
    modality_limits: JsonObject = Field(default_factory=dict)
