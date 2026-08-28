"""Provider-native agent contract — run lifecycle payloads and normalized
events (30 §15.2 interface shapes, §15.3 event normalization).

Contract authority:
docs/ai_orchestration_pack/final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md
— §15.2 (ProviderAgentModule interface payloads), §15.3 (event
normalization: "The platform must not expose raw provider agent semantics
directly to the rest of the Core"), §15.4 (security rule: deny-by-default
tool posture), and
docs/ai_orchestration_pack/final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md
— §23.3 ("Provider-agent node events must be normalized into the platform
node lifecycle: pending/ready/running/waiting_approval/succeeded/failed/
cancelled. Provider-specific intermediate events are stored as trace
events, not leaked as Core semantics.").

This module is the *contract only*. The ProviderAgentModulePort behavioral
interface (30 §15.2) lives in ``core/providers/ports.py`` (FINAL Phase 4,
T-IMPL-054); no network, no provider implementations here.

Recorded derivation decisions (never silent):

- ``ProviderAgentRunState`` uses the 12 §23.3 seven-state platform node
  lifecycle VERBATIM — that section is the documented normalization target
  for provider-agent runs; 30 §15.2's ``ProviderAgentRunStatus`` names the
  shape but defines no state set, so the state set comes from 12 §23.3 and
  is NOT invented here.
- ``ProviderAgentEventType`` is the 30 §15.3 seven-event closed set,
  verbatim (dotted names preserved as values).
- Failure coherence: a ``provider_agent.failed`` event and a ``failed`` run
  status MUST carry a normalized :class:`ProviderError` and non-failures
  MUST NOT — derived from 30 §14 ("The Core makes decisions from normalized
  errors only"): a failure with no normalized error is undecidable, and an
  error attached to a non-failure is contradictory data. Same hardening
  posture as ``RateLimitStatus`` (T-IMPL-034, recorded there).
- ``provider_side_tools_allowed`` on the request defaults ``False`` —
  30 §15.4 "provider-side tool use must be policy-controlled" +
  ``ManifestSecurity.provider_side_tools_allowed_by_default = False``
  (deny-by-default, 20 §4): the platform must explicitly grant it per run.
- ``run_id`` is an opaque provider-managed handle (BoundedStr, not UUID):
  30 §15 state models are provider-managed (thread/run ids are the
  provider's namespace, never platform UUIDs).
- ``credential_ref`` stays an opaque reference end-to-end (20 §5) — same
  posture as :class:`~core.contracts.provider.ProviderGenerateRequest`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.provider import ProviderError

# --- 12 §23.3 normalized run lifecycle (closed set, verbatim) ---------------------


class ProviderAgentRunState(StrEnum):
    """Normalized provider-agent run states — the 12 §23.3 platform node
    lifecycle, verbatim. Provider-specific intermediate states are trace
    events (30 §15.3), never new members of this set.
    """

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- 30 §15.3 normalized events (closed set, verbatim) ----------------------------


class ProviderAgentEventType(StrEnum):
    """The seven normalized provider-agent platform events (30 §15.3)."""

    STARTED = "provider_agent.started"
    STEP_STARTED = "provider_agent.step_started"
    TOOL_REQUESTED = "provider_agent.tool_requested"
    TOOL_COMPLETED = "provider_agent.tool_completed"
    MESSAGE_DELTA = "provider_agent.message_delta"
    COMPLETED = "provider_agent.completed"
    FAILED = "provider_agent.failed"


class ProviderAgentEvent(ContractModel):
    """One normalized provider-agent event (30 §15.3).

    ``payload`` carries the provider-specific trace detail as opaque data
    (12 §23.3: stored as trace events, not leaked as Core semantics).
    Failure coherence per the module docstring: ``failed`` events REQUIRE a
    normalized error; all other events must not carry one.
    """

    type: ProviderAgentEventType
    run_id: BoundedStr
    payload: JsonObject = Field(default_factory=dict)
    error: ProviderError | None = None
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _failed_events_carry_normalized_error(self) -> ProviderAgentEvent:
        if self.type is ProviderAgentEventType.FAILED and self.error is None:
            msg = (
                "provider_agent.failed events must carry a normalized"
                " ProviderError (30 §14/§15.3)"
            )
            raise ValueError(msg)
        if self.type is not ProviderAgentEventType.FAILED and self.error is not None:
            msg = "only provider_agent.failed events may carry an error (30 §15.3)"
            raise ValueError(msg)
        return self


# --- 30 §15.2 interface payload shapes ---------------------------------------------


class ProviderAgentRequest(ContractModel):
    """Normalized provider-agent invocation (30 §15.2 ``runAgent`` /
    ``createAgentRun`` input).

    ``provider_agent_id`` names the explicitly registered provider agent
    (12 §22: "Provider-native agents must be registered explicitly").
    ``credential_ref`` is an opaque reference only (20 §5).
    ``provider_side_tools_allowed`` defaults False (30 §15.4 deny-by-default).
    """

    request_id: UUID
    tenant_id: UUID
    provider_agent_id: BoundedStr
    credential_ref: BoundedStr
    account_id: UUID | None = None
    payload: JsonObject = Field(default_factory=dict)
    provider_side_tools_allowed: bool = False
    timeout_ms: int | None = Field(default=None, ge=1)


class ProviderAgentResponse(ContractModel):
    """One-shot provider-agent result (30 §15.2 ``runAgent`` output).

    Mirrors :class:`~core.contracts.provider.ProviderGenerateResponse`:
    exactly one of ``output``/``error`` is meaningful, and raw provider
    errors never cross this boundary (30 §14).
    """

    request_id: UUID
    succeeded: bool
    output: JsonObject = Field(default_factory=dict)
    usage: JsonObject = Field(default_factory=dict)
    error: ProviderError | None = None
    latency_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _failure_requires_normalized_error(self) -> ProviderAgentResponse:
        if not self.succeeded and self.error is None:
            msg = "failed responses must carry a normalized ProviderError (30 §14)"
            raise ValueError(msg)
        if self.succeeded and self.error is not None:
            msg = "successful responses must not carry an error (30 §14)"
            raise ValueError(msg)
        return self


class ProviderAgentRun(ContractModel):
    """Handle for a provider-managed run (30 §15.2 ``createAgentRun`` output).

    ``run_id`` is the provider's opaque handle (thread/run id in the
    provider's namespace — recorded derivation, module docstring).
    """

    run_id: BoundedStr
    request_id: UUID
    state: ProviderAgentRunState


class ProviderAgentRunStatus(ContractModel):
    """Point-in-time run status (30 §15.2 ``getAgentRun`` output).

    Failure coherence per the module docstring: ``failed`` state REQUIRES a
    normalized error; non-failed states must not carry one.
    """

    run_id: BoundedStr
    state: ProviderAgentRunState
    output: JsonObject = Field(default_factory=dict)
    usage: JsonObject = Field(default_factory=dict)
    error: ProviderError | None = None

    @model_validator(mode="after")
    def _failed_state_carries_normalized_error(self) -> ProviderAgentRunStatus:
        if self.state is ProviderAgentRunState.FAILED and self.error is None:
            msg = "failed runs must carry a normalized ProviderError (30 §14)"
            raise ValueError(msg)
        if self.state is not ProviderAgentRunState.FAILED and self.error is not None:
            msg = "only failed runs may carry an error (30 §14)"
            raise ValueError(msg)
        return self
