"""Bounded agent execution loop (MASTER VISION v2 roadmap, Phase V4 / X²-3).

The frozen definition, verbatim: "Bounded plan→act→observe: model proposes
structured output → platform validates (R095 attach-at-surface validators
land in the same commit) → gate admits → executor runs → observation
appended; bounded by budget/step-count/admission. Model proposes;
deterministic code disposes. `ExecutionStrategy.AGENT` stops being
vocabulary."

Consumption topology (P2 — the Agent is a CONSUMER):

- ``propose`` is the model-call seam: an async callable bound at the
  composition root (e.g. wrapping the existing adapter/execution
  machinery). The loop never talks to providers itself — same posture as
  the V3 ToolExecutor's handlers.
- Tool acts go through the V3 :class:`~core.tools.executor.ToolExecutor`
  UNCHANGED — so "every call passes the gate" holds for agent runs by
  construction: there is no tool path in this module that is not
  ``ToolExecutor.execute``.
- ``bindings`` maps model-proposable tool NAMES to composition-declared
  :class:`AgentToolBinding` security data. The model contributes ONLY the
  name + arguments (20 §1); everything the firewall consumes is fixed
  before the run starts.

Bounds (frozen clause "bounded by budget/step-count/admission"):

- step-count: ``max_steps`` proposals per run, enforced by the loop.
- budget: every tool call reserves through the ToolExecutor's 03 §7
  lifecycle — a budget denial is a refused observation. Model-call budget
  rides the ``propose`` binding (composition wires it through the existing
  execution/usage machinery).
- admission: the gate verdict inside the ToolExecutor; refusals come back
  as observations the model can adapt to, never silently dropped.

Outcome normalization (P6): refusals, handler failures, unknown tool
names, invalid proposals, and propose-seam faults are all DATA on the run
record — the loop raises for nothing the model can cause.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from core.contracts.base import JsonObject, utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.contracts.security import ActorKind, FirewallDecisionInput
from core.execution.agent import (
    AgentToolBinding,
    FinalProposal,
    InvalidAgentProposal,
    ToolCallProposal,
    parse_agent_proposal,
)
from core.tools.executor import ToolCallRecord, ToolExecutor

ProposeFn = Callable[[JsonObject], Awaitable[JsonObject]]
"""Model-call seam: receives ``{"request": ..., "observations": [...]}``
and returns the model's raw structured output (untrusted, P7)."""

#: Closed stop-reason vocabulary (deterministic disposal outcomes).
STOP_FINAL = "final"
STOP_MAX_STEPS = "max_steps_exceeded"
STOP_INVALID_PROPOSAL = "invalid_proposal"
STOP_PROPOSE_FAILED = "propose_failed"


@dataclass(frozen=True)
class AgentStep:
    """One plan→act→observe iteration, fully explainable (11 §14)."""

    index: int  # 1-based
    proposal_raw: JsonObject | None  # what the model actually emitted
    observation: JsonObject  # what the next proposal will see
    tool_record: ToolCallRecord | None = None  # present for tool_call steps


@dataclass(frozen=True)
class AgentRunReport:
    """The whole run as data: execution record, nodes, steps, stop reason."""

    execution: Execution
    nodes: tuple[ExecutionNode, ...]
    steps: tuple[AgentStep, ...]
    status_history: tuple[ExecutionStatus, ...]
    stop_reason: str
    final_output: JsonObject | None = None

    @property
    def succeeded(self) -> bool:
        return self.execution.status is ExecutionStatus.SUCCEEDED


@dataclass
class _RunState:
    """Internal accumulation for one run (never leaves the loop)."""

    nodes: list[ExecutionNode] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    observations: list[JsonObject] = field(default_factory=list)


class AgentLoop:
    """Bounded plan→act→observe over the V3 gated tool runtime."""

    def __init__(
        self,
        *,
        propose: ProposeFn,
        tools: ToolExecutor,
        bindings: Mapping[str, AgentToolBinding],
        max_steps: int,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if max_steps < 1:
            msg = "max_steps must be >= 1"
            raise ValueError(msg)
        self._propose = propose
        self._tools = tools
        self._bindings: dict[str, AgentToolBinding] = dict(bindings)
        self._max_steps = max_steps
        self._id_factory = id_factory

    async def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        request: JsonObject,
        request_hash: str,
        actor: ActorKind = ActorKind.USER,
        actor_id: UUID | None = None,
        conversation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> AgentRunReport:
        """Run one bounded agent execution; every outcome is data."""
        execution_id = self._id_factory()
        created_at = utc_now()
        state = _RunState()
        stop_reason = STOP_MAX_STEPS
        final_output: JsonObject | None = None

        for index in range(1, self._max_steps + 1):
            payload: JsonObject = {
                "request": dict(request),
                "observations": list(state.observations),
            }

            # --- plan: model proposes (untrusted output, P7) ------------------
            try:
                raw = await self._propose(payload)
            except Exception as exc:  # noqa: BLE001 — seam fault becomes data
                self._planner_node(
                    state,
                    execution_id,
                    payload,
                    status=ExecutionNodeStatus.FAILED,
                    error={
                        "reason": STOP_PROPOSE_FAILED,
                        "detail": f"{type(exc).__name__}: {exc}",
                    },
                )
                state.steps.append(
                    AgentStep(
                        index=index,
                        proposal_raw=None,
                        observation={"step": index, "error": STOP_PROPOSE_FAILED},
                    )
                )
                stop_reason = STOP_PROPOSE_FAILED
                break

            # --- validate: the R095 attach-at-surface validator ---------------
            try:
                proposal = parse_agent_proposal(raw)
            except InvalidAgentProposal as exc:
                self._planner_node(
                    state,
                    execution_id,
                    payload,
                    output=raw if isinstance(raw, dict) else None,
                    status=ExecutionNodeStatus.FAILED,
                    error={"reason": STOP_INVALID_PROPOSAL, "detail": exc.reason},
                )
                state.steps.append(
                    AgentStep(
                        index=index,
                        proposal_raw=raw if isinstance(raw, dict) else None,
                        observation={
                            "step": index,
                            "error": STOP_INVALID_PROPOSAL,
                            "detail": exc.reason,
                        },
                    )
                )
                stop_reason = STOP_INVALID_PROPOSAL
                break

            self._planner_node(
                state,
                execution_id,
                payload,
                output=raw,
                status=ExecutionNodeStatus.SUCCEEDED,
            )

            # --- dispose: deterministic code decides (P4) ----------------------
            if isinstance(proposal, FinalProposal):
                state.nodes.append(
                    ExecutionNode(
                        id=self._id_factory(),
                        execution_id=execution_id,
                        node_key=f"finalize-{index}",
                        type=ExecutionNodeType.AGGREGATOR,
                        status=ExecutionNodeStatus.SUCCEEDED,
                        input_ref=raw,
                        output_ref=proposal.output,
                        retry_count=0,
                    )
                )
                state.steps.append(
                    AgentStep(
                        index=index,
                        proposal_raw=raw,
                        observation={"step": index, "final": True},
                    )
                )
                final_output = proposal.output
                stop_reason = STOP_FINAL
                break

            # --- act: through the V3 gated executor ONLY -----------------------
            observation = await self._act(
                state,
                execution_id,
                index,
                proposal,
                raw,
                tenant_id=tenant_id,
                actor=actor,
                actor_id=actor_id,
            )
            state.observations.append(observation)

        status = (
            ExecutionStatus.SUCCEEDED
            if stop_reason == STOP_FINAL
            else ExecutionStatus.FAILED
        )
        execution = Execution(
            id=execution_id,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            status=status,
            strategy=ExecutionStrategy.AGENT,
            cost_snapshot={
                "steps": len(state.steps),
                "max_steps": self._max_steps,
                "stop_reason": stop_reason,
            },
            created_at=created_at,
            completed_at=utc_now(),
        )
        return AgentRunReport(
            execution=execution,
            nodes=tuple(state.nodes),
            steps=tuple(state.steps),
            status_history=(
                ExecutionStatus.QUEUED,
                ExecutionStatus.RUNNING,
                status,
            ),
            stop_reason=stop_reason,
            final_output=final_output,
        )

    # --- internals --------------------------------------------------------------

    async def _act(
        self,
        state: _RunState,
        execution_id: UUID,
        index: int,
        proposal: ToolCallProposal,
        raw: JsonObject,
        *,
        tenant_id: UUID,
        actor: ActorKind,
        actor_id: UUID | None,
    ) -> JsonObject:
        """One tool act; the observation is appended by the caller."""
        binding = self._bindings.get(proposal.tool)
        if binding is None:
            # Unknown NAME is a model mistake, observed as data — the model
            # may correct itself within the step budget; nothing executed.
            error = {"reason": "unknown_tool", "detail": proposal.tool}
            self._tool_node(
                state,
                execution_id,
                index,
                proposal,
                status=ExecutionNodeStatus.FAILED,
                error=error,
            )
            observation: JsonObject = {
                "step": index,
                "tool": proposal.tool,
                "status": "refused",
                "error": error,
            }
            state.steps.append(
                AgentStep(index=index, proposal_raw=raw, observation=observation)
            )
            return observation

        record = await self._tools.execute(
            tool_id=binding.tool_id,
            request=FirewallDecisionInput(
                actor=actor,
                tenant_id=tenant_id,
                permission=binding.permission,
                resource=binding.resource,
                scope=binding.scope,
                entitlement=binding.entitlement,
                approval_state=binding.approval_state,
                risk_level=binding.risk_level,
            ),
            arguments=proposal.arguments,
            device_id=binding.device_id,
            actor_id=actor_id,
            estimated_units=binding.estimated_units,
        )
        succeeded = record.status == "succeeded"
        observation = {
            "step": index,
            "tool": proposal.tool,
            "status": record.status,
        }
        if record.result is not None:
            observation["result"] = record.result
        if record.error is not None:
            observation["error"] = {
                "reason": record.error,
                "detail": record.error_detail,
            }
        self._tool_node(
            state,
            execution_id,
            index,
            proposal,
            status=(
                ExecutionNodeStatus.SUCCEEDED
                if succeeded
                else ExecutionNodeStatus.FAILED
            ),
            output=record.result,
            error=(
                None
                if succeeded
                else {"reason": record.error, "detail": record.error_detail}
            ),
        )
        state.steps.append(
            AgentStep(
                index=index,
                proposal_raw=raw,
                observation=observation,
                tool_record=record,
            )
        )
        return observation

    def _planner_node(
        self,
        state: _RunState,
        execution_id: UUID,
        payload: JsonObject,
        *,
        status: ExecutionNodeStatus,
        output: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None:
        state.nodes.append(
            ExecutionNode(
                id=self._id_factory(),
                execution_id=execution_id,
                node_key=f"plan-{len(state.steps) + 1}",
                type=ExecutionNodeType.PLANNER,
                status=status,
                input_ref=payload,
                output_ref=output,
                retry_count=0,
                error=error,
            )
        )

    def _tool_node(
        self,
        state: _RunState,
        execution_id: UUID,
        index: int,
        proposal: ToolCallProposal,
        *,
        status: ExecutionNodeStatus,
        output: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None:
        state.nodes.append(
            ExecutionNode(
                id=self._id_factory(),
                execution_id=execution_id,
                node_key=f"act-{index}-{proposal.tool}",
                type=ExecutionNodeType.TOOL_CALL,
                status=status,
                input_ref=dict(proposal.arguments),
                output_ref=output,
                retry_count=0,
                error=error,
            )
        )
