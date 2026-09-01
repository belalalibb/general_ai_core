"""/v1/execute API contracts — request, responses, status, streaming, webhooks.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md
    §2 request, §3 sync success response, §4 async accepted response,
    §5 execution status, §11 streaming events, §12 webhook events.
Execution status values: final_docs_v3/03_DOMAIN_MODEL.md (Execution entity)::

    queued | running | waiting_approval | succeeded | failed | cancelled

Field-default posture (10 §2): only ``ask`` is required — "Everything else has
policy-driven defaults." Optional tunables left unset (``None``) mean "resolve
via policy-driven defaults" server-side; the contract does not invent defaults
the spec does not state.

``mode`` is a free-form string (10 §2 shows ``"auto"``, 10 §13.5 shows
``"agent"``); the closed set of execution strategies lives in 12 §2 and is
resolved by the Router, not fixed at the API boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.errors import ErrorDetail
from core.contracts.model_policy import AgentPolicy, ModelPolicy


class ExecutionStatus(StrEnum):
    """Execution lifecycle states (03 Domain Model, Execution entity)."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Request sub-objects (10 §2) --------------------------------------------


class RoleSelector(ContractModel):
    """``role`` object: which persona/system role executes the ask."""

    type: BoundedStr
    id: BoundedStr


class ExecutionPolicy(ContractModel):
    """``execution_policy`` object: strategy/async/stream/cost/approval knobs."""

    strategy: BoundedStr | None = None
    async_: Annotated[bool | None, Field(alias="async")] = None
    stream: bool | None = None
    max_cost_units: Annotated[int | None, Field(ge=0)] = None
    approval_required_for_tools: bool | None = None


class ToolsPolicy(ContractModel):
    """``tools`` object: allow/deny lists + approval mode.

    Unknown tools default to DENY (14 — Capability Firewall); the deny list
    exists to explicitly override broader allows.
    """

    allowed: list[BoundedStr] = Field(default_factory=list)
    denied: list[BoundedStr] = Field(default_factory=list)
    approval_mode: BoundedStr | None = None


class RequestContext(ContractModel):
    """``context`` object: attachments, metadata, language."""

    attachments: list[JsonObject] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)
    language: BoundedStr | None = None


class OutputSpec(ContractModel):
    """``output`` object: requested format/language/schema of the result."""

    format: BoundedStr | None = None
    language: BoundedStr | None = None
    schema_: Annotated[JsonObject | None, Field(alias="schema")] = None


class ExecuteRequest(ContractModel):
    """POST /v1/execute request body (10 §2). Only ``ask`` is required."""

    ask: BoundedStr = Field(max_length=100_000)
    mode: BoundedStr | None = None
    conversation_id: BoundedStr | None = None
    project_id: BoundedStr | None = None
    role: RoleSelector | None = None
    # Chunk-5 field (10 §7 skills are SELECTABLE; 41 §16 'Selected Skills'):
    # explicit skill selection by MANIFEST id — the SAME stable key the
    # GET /v1/skills listing shows (never the registry UUID, 20 §6).
    # Absent/empty ⇒ no skills ride the request (deny-by-default).
    skills: list[BoundedStr] | None = None
    model_policy: ModelPolicy | None = None
    agent_policy: AgentPolicy | None = None
    execution_policy: ExecutionPolicy | None = None
    tools: ToolsPolicy | None = None
    context: RequestContext | None = None
    output: OutputSpec | None = None
    webhook_url: BoundedStr | None = None


# --- Response objects (10 §3-§5) ---------------------------------------------


class ExecutionResult(ContractModel):
    """``result`` object of a successful execution (10 §3)."""

    type: BoundedStr
    content: str
    format: BoundedStr | None = None
    artifacts: list[JsonObject] = Field(default_factory=list)


class UsageReport(ContractModel):
    """``usage`` object: reserved vs settled task units (10 §3)."""

    units_reserved: Annotated[int, Field(ge=0)]
    units_settled: Annotated[int, Field(ge=0)]
    details: JsonObject = Field(default_factory=dict)


class EvaluationReport(ContractModel):
    """``evaluation`` object (10 §3); ``level`` values per 22 (RAW..GOLD)."""

    visible: bool
    level: BoundedStr
    summary: str | None = None


class ExecuteSyncResponse(ContractModel):
    """Sync success response (10 §3)."""

    execution_id: BoundedStr
    status: ExecutionStatus
    result: ExecutionResult
    usage: UsageReport | None = None
    evaluation: EvaluationReport | None = None


class ExecuteAsyncAccepted(ContractModel):
    """Async accepted response (10 §4): queued + poll URL."""

    execution_id: BoundedStr
    status: Literal[ExecutionStatus.QUEUED]
    poll_url: BoundedStr


class ExecutionProgress(ContractModel):
    """``progress`` object of GET /v1/executions/{id} (10 §5)."""

    current_stage: BoundedStr | None = None
    percent: Annotated[int | None, Field(ge=0, le=100)] = None


class ExecutionStatusResponse(ContractModel):
    """GET /v1/executions/{id} response (10 §5)."""

    execution_id: BoundedStr
    status: ExecutionStatus
    progress: ExecutionProgress | None = None
    result: ExecutionResult | None = None
    error: ErrorDetail | None = None


# --- Streaming events (10 §11) ------------------------------------------------


class ExecutionStartedEvent(ContractModel):
    type: Literal["execution_started"]
    execution_id: BoundedStr


class NodeStartedEvent(ContractModel):
    type: Literal["node_started"]
    node: BoundedStr


class DeltaEvent(ContractModel):
    type: Literal["delta"]
    content: str


class NodeCompletedEvent(ContractModel):
    type: Literal["node_completed"]
    node: BoundedStr


class FinalEvent(ContractModel):
    type: Literal["final"]
    result: JsonObject = Field(default_factory=dict)


class ErrorEvent(ContractModel):
    type: Literal["error"]
    error: JsonObject = Field(default_factory=dict)


# Discriminated union over the 6 documented stream event types (10 §11).
StreamEvent = Annotated[
    ExecutionStartedEvent
    | NodeStartedEvent
    | DeltaEvent
    | NodeCompletedEvent
    | FinalEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


# --- Webhooks (10 §12) ---------------------------------------------------------


class WebhookEventType(StrEnum):
    """The 6 webhook event types (10 §12) — closed set, verbatim."""

    EXECUTION_QUEUED = "execution.queued"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_WAITING_APPROVAL = "execution.waiting_approval"
    EXECUTION_SUCCEEDED = "execution.succeeded"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_CANCELLED = "execution.cancelled"


class WebhookPayload(ContractModel):
    """Webhook delivery body (10 §12)."""

    event: WebhookEventType
    execution_id: BoundedStr
    tenant_id: BoundedStr
    timestamp: datetime
    data: JsonObject = Field(default_factory=dict)
