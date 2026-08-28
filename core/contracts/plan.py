"""Plan contract — the subscription/entitlement catalog entity.

Contract authority (FINAL Phase 3 gap-fix: 41 §6 lists ``plans`` as a
Postgres source-of-truth entity; ``Plan`` is in the 03 entity inventory):

- docs/ai_orchestration_pack/final_docs_v3/21_ADMIN_CONTROL_PLANE.md §5
  (Plan Configuration: ``plan: <name>`` + ``limits`` block with
  ``task_units`` / modality limits / ``max_parallel_executions`` +
  ``entitlements`` block) and §10 (per-plan ``model_control`` block).
- final_docs_v3/10_API_CONTRACTS.md §8 (GET /v1/usage exposes the plan
  name plus ``task_units`` and ``modality_limits`` — the names used here
  match that surface; :class:`core.contracts.usage.UsageSummary` already
  carries ``plan: str``).
- final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md §19 (Phase 16:
  task-unit values are configuration-driven) and
  01_PRODUCT_REQUIREMENTS.md FR-014 (plans are task units + entitlements,
  not message counts).
- final_docs_v3/03_DOMAIN_MODEL.md §2 (``Tenant.plan_id: uuid`` — the
  Plan is the catalog entity that reference resolves against).

Field derivation note (explicit, no invention hidden): 03 lists ``Plan``
in the entity inventory but defines NO yaml table for it — fields below
are derived 1:1 from the 21 §5/§10 plan-configuration shapes plus the
``id`` anchor that ``Tenant.plan_id`` requires. Plans are a PLATFORM
catalog (tenants subscribe to them), so the entity is deliberately NOT
tenant-scoped — there is no ``tenant_id`` (20 §6 applies to tenant-scoped
tables; the tenant side of this relation is ``tenants.plan_id``).

Deny-by-default posture (41 §1 rule 9), encoded in DATA:

- ``limits`` defaults to a zero budget (``task_units=0``) — a plan grants
  NOTHING until configured.
- ``entitlements`` defaults to ``{}`` — no model/tool/agent grant exists
  unless explicitly configured (21 §5 keys are admin configuration).
- ``model_control`` defaults to ``{}`` — no model-selection capability is
  granted unless explicitly configured (21 §10).

``entitlements`` and ``model_control`` stay free JSON objects on purpose:
41 §19 says values are configuration-driven and 21 §10.2 lists the keys
as admin-configurable — they are policy DATA, not contract structure
(same recorded posture as ``UsageLedger.modality_costs``). The enforcement
semantics (what an absent key denies) live with the firewall/router, which
already treat unknown ⇒ DENY.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject


class PlanLimits(ContractModel):
    """The 21 §5 ``limits`` block, aligned with the 10 §8 usage surface.

    ``task_units`` — the tenant budget the usage ledger reserves against
    (21 §5 ``limits.task_units``); defaults to 0 = no budget granted.
    ``max_parallel_executions`` — 21 §5; ``None`` = resolve via
    policy-driven defaults (the contract invents no number).
    ``modality_limits`` — per-modality caps (e.g. ``image_generations``
    from the 21 §5 example), a free map matching the 10 §8 name; values
    are configuration-driven (41 §19).
    """

    task_units: Annotated[float, Field(ge=0)] = 0
    max_parallel_executions: Annotated[int, Field(ge=0)] | None = None
    modality_limits: JsonObject = Field(default_factory=dict)


class Plan(ContractModel):
    """Plan catalog entity (03 inventory; shapes from 21 §5/§10).

    ``name`` is the ``plan:`` configuration key (21 §5: ``pro``,
    ``enterprise``) — the string GET /v1/usage exposes as ``plan``.
    """

    id: UUID
    name: BoundedStr
    limits: PlanLimits = Field(default_factory=PlanLimits)
    entitlements: JsonObject = Field(default_factory=dict)
    model_control: JsonObject = Field(default_factory=dict)
