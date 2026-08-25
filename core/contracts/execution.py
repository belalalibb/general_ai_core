"""Execution contract — Execution / ExecutionNode domain entities.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md
§5 (Execution). Carried exactly — no state value added, renamed, or dropped.

The 6-state execution lifecycle is shared with the API contract layer:
``ExecutionStatus`` is reused from :mod:`core.contracts.execute` (single
source of truth for the closed set
``queued|running|waiting_approval|succeeded|failed|cancelled``).

The strategy closed set here (8 values) is identical in 03 §5 and
12_EXECUTION_GRAPH_AND_AGENT_MODE.md §2.

Scope note (deliberate, not an omission): 12 §5/§6 defines the *runtime
execution-graph* node-type list (11 types, incl. ``approval_gate``,
``human_input``, ``finalizer``, ``provider_agent_call``) and an 8-state node
lifecycle (adds ``ready``/``waiting_approval``). Those belong to the graph
schema contract of the Execution Graph engine (a later task). This module
carries the *domain entity* closed sets of 03 §5 verbatim (7 node types,
6 node states).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.execute import ExecutionStatus

# --- Closed sets (03 §5, verbatim) --------------------------------------------


class ExecutionStrategy(StrEnum):
    """Execution strategies (03 §5 Execution entity; identical to 12 §2)."""

    SINGLE = "single"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    DEBATE = "debate"
    REVIEW_JUDGE = "review_judge"
    MAP_REDUCE = "map_reduce"
    AGENT = "agent"
    HYBRID = "hybrid"


class ExecutionNodeType(StrEnum):
    """ExecutionNode types (03 §5 ExecutionNode entity) — closed set, verbatim."""

    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    PLANNER = "planner"
    REVIEWER = "reviewer"
    TESTER = "tester"
    VALIDATOR = "validator"
    AGGREGATOR = "aggregator"


class ExecutionNodeStatus(StrEnum):
    """ExecutionNode lifecycle states (03 §5) — closed set, verbatim."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


# --- Entities (03 §5, field-for-field) ----------------------------------------


class Execution(ContractModel):
    """Execution entity (03 §5) — the root record of one orchestrated run.

    ``status`` reuses the shared 6-state :class:`ExecutionStatus`.
    ``cost_snapshot`` is an open JSON object (03 says ``json``; documented
    example shape in 11 §10: ``{"estimated_units": 2}``).
    """

    id: UUID
    tenant_id: UUID
    user_id: UUID
    conversation_id: UUID | None = None
    request_hash: BoundedStr
    idempotency_key: BoundedStr | None = None
    status: ExecutionStatus
    strategy: ExecutionStrategy
    cost_snapshot: JsonObject
    created_at: datetime
    completed_at: datetime | None = None


class ExecutionNode(ContractModel):
    """ExecutionNode entity (03 §5) — one controlled node of an execution.

    ``input_ref`` is ``string/json`` per spec: either an opaque reference
    string or an inline JSON object. ``output_ref`` is the same, nullable.
    """

    id: UUID
    execution_id: UUID
    node_key: BoundedStr
    type: ExecutionNodeType
    status: ExecutionNodeStatus
    input_ref: BoundedStr | JsonObject
    output_ref: BoundedStr | JsonObject | None = None
    retry_count: int = Field(ge=0)
    error: JsonObject | None = None
