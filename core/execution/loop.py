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

import json
import time
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

VerifyFn = Callable[[JsonObject, JsonObject], Awaitable[JsonObject]]
"""Optional composition-bound verification seam (deterministic code, never
the model): receives ``(request, proposed_final_output)`` and returns a
verdict object. The single reserved key is ``"verified"`` — truthy admits
finalization; anything else REJECTS it and the whole verdict is appended
as an observation the model can correct against within the remaining step
budget (detect failure -> correct -> verify again, all bounded by
``max_steps``). The verifier holds no authority beyond this verdict and
its output is recorded verbatim as a VALIDATOR node (P6: evidence)."""

#: Closed stop-reason vocabulary (deterministic disposal outcomes).
STOP_FINAL = "final"
STOP_MAX_STEPS = "max_steps_exceeded"
STOP_INVALID_PROPOSAL = "invalid_proposal"
STOP_PROPOSE_FAILED = "propose_failed"
STOP_VERIFICATION_FAILED = "verification_failed"
STOP_DEADLINE_EXCEEDED = "deadline_exceeded"
STOP_REPEATED_FAILURE = "repeated_failure"

#: Reassessment bound: the SAME tool call (name + arguments) may fail at
#: most this many times before the loop refuses to dispatch it again. The
#: refusal is an observation naming the repetition, so the model must change
#: its action or strategy — evidence-driven reassessment, enforced by code.
DEFAULT_MAX_REPEATED_FAILURES = 2

#: Protocol-repair bound (R165): a proposal the validator refuses (non-JSON,
#: unknown action, smuggled authority keys…) is an OBSERVATION naming the
#: violation — the model gets to correct itself within its step budget, as
#: it already can for a refused tool call. This many CONSECUTIVE invalid
#: proposals stop the run with ``invalid_proposal``. 1 = the pre-R165
#: single-shot stop.
DEFAULT_MAX_INVALID_PROPOSALS = 2


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
    #: The LAST verifier verdict (composition-bound seam), when one ran.
    #: Present on success (the admitting verdict) AND on
    #: ``verification_failed`` (the final rejecting verdict) — evidence
    #: either way (P6).
    verification: JsonObject | None = None
    #: Evidence ledger (P6): every SUCCEEDED tool result of the run, in step
    #: order, so finalization and post-hoc readers can cite what the run
    #: actually observed — never what the model claims it observed.
    evidence: tuple[JsonObject, ...] = ()
    #: Deterministic run summary (steps, tool outcomes, repeated-failure
    #: refusals, elapsed ms) — the same numbers land in cost_snapshot.
    summary: JsonObject = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.execution.status is ExecutionStatus.SUCCEEDED


@dataclass
class _RunState:
    """Internal accumulation for one run (never leaves the loop)."""

    nodes: list[ExecutionNode] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    observations: list[JsonObject] = field(default_factory=list)
    evidence: list[JsonObject] = field(default_factory=list)
    #: (tool name, canonical arguments) -> consecutive failure count.
    failures: dict[str, int] = field(default_factory=dict)
    tool_ok: int = 0
    tool_failed: int = 0
    repeated_refused: int = 0
    #: Consecutive validator refusals (reset by any valid proposal).
    invalid_streak: int = 0
    invalid_total: int = 0


class AgentLoop:
    """Bounded plan→act→observe over the V3 gated tool runtime."""

    def __init__(
        self,
        *,
        propose: ProposeFn,
        tools: ToolExecutor,
        bindings: Mapping[str, AgentToolBinding],
        max_steps: int,
        verify: VerifyFn | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        max_repeated_failures: int = DEFAULT_MAX_REPEATED_FAILURES,
        deadline_ms: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_invalid_proposals: int = DEFAULT_MAX_INVALID_PROPOSALS,
    ) -> None:
        if max_steps < 1:
            msg = "max_steps must be >= 1"
            raise ValueError(msg)
        if max_repeated_failures < 1:
            msg = "max_repeated_failures must be >= 1"
            raise ValueError(msg)
        if max_invalid_proposals < 1:
            msg = "max_invalid_proposals must be >= 1"
            raise ValueError(msg)
        if deadline_ms is not None and deadline_ms < 1:
            msg = "deadline_ms must be >= 1 when set"
            raise ValueError(msg)
        self._propose = propose
        self._tools = tools
        self._bindings: dict[str, AgentToolBinding] = dict(bindings)
        self._max_steps = max_steps
        self._verify = verify
        self._id_factory = id_factory
        self._max_repeated_failures = max_repeated_failures
        self._max_invalid_proposals = max_invalid_proposals
        # Wall-clock bound for the WHOLE run (S4): checked before every
        # proposal; a run past its deadline stops with a closed reason
        # instead of spending another model call. None = step-bound only.
        self._deadline_ms = deadline_ms
        self._clock = clock

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
        verification: JsonObject | None = None
        started = self._clock()

        for index in range(1, self._max_steps + 1):
            # --- bound: wall clock (S4) -----------------------------------------
            if self._deadline_ms is not None:
                elapsed_ms = (self._clock() - started) * 1000.0
                if elapsed_ms >= self._deadline_ms:
                    state.steps.append(
                        AgentStep(
                            index=index,
                            proposal_raw=None,
                            observation={
                                "step": index,
                                "error": STOP_DEADLINE_EXCEEDED,
                                "elapsed_ms": int(elapsed_ms),
                                "deadline_ms": self._deadline_ms,
                            },
                        )
                    )
                    stop_reason = STOP_DEADLINE_EXCEEDED
                    break
            payload: JsonObject = {
                "request": dict(request),
                "observations": list(state.observations),
                # Budget awareness for the model (data only): how many
                # proposals remain — so it can plan to finalize in time.
                "budget": {"step": index, "max_steps": self._max_steps},
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
                state.invalid_streak += 1
                state.invalid_total += 1
                self._planner_node(
                    state,
                    execution_id,
                    payload,
                    output=raw if isinstance(raw, dict) else None,
                    status=ExecutionNodeStatus.FAILED,
                    error={"reason": STOP_INVALID_PROPOSAL, "detail": exc.reason},
                )
                refusal: JsonObject = {
                    "step": index,
                    "error": STOP_INVALID_PROPOSAL,
                    "detail": exc.reason,
                }
                state.steps.append(
                    AgentStep(
                        index=index,
                        proposal_raw=raw if isinstance(raw, dict) else None,
                        observation=refusal,
                    )
                )
                if state.invalid_streak >= self._max_invalid_proposals or index == self._max_steps:
                    stop_reason = STOP_INVALID_PROPOSAL
                    break
                # R165: the violation is DATA the model can correct — it
                # rides the next payload's observations like a refused call.
                state.observations.append(
                    {**refusal, "status": "refused", "nothing_happened": True}
                )
                continue

            state.invalid_streak = 0
            self._planner_node(
                state,
                execution_id,
                payload,
                output=raw,
                status=ExecutionNodeStatus.SUCCEEDED,
            )

            # --- dispose: deterministic code decides (P4) ----------------------
            if isinstance(proposal, FinalProposal):
                # Verification-before-finalization (composition-bound seam):
                # a rejected final is an OBSERVATION the model can correct
                # against within the remaining step budget — never a silent
                # pass and never an unbounded retry.
                if self._verify is not None:
                    verdict = await self._run_verifier(
                        state, execution_id, index, request, proposal.output
                    )
                    verification = verdict
                    if not verdict.get("verified"):
                        rejection: JsonObject = {
                            "step": index,
                            "verification": verdict,
                            "final_rejected": True,
                        }
                        state.steps.append(
                            AgentStep(
                                index=index,
                                proposal_raw=raw,
                                observation=rejection,
                            )
                        )
                        state.observations.append(rejection)
                        if index == self._max_steps:
                            stop_reason = STOP_VERIFICATION_FAILED
                        continue
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
            # A repeated-failure refusal on the LAST step is the honest stop
            # reason (the model never changed strategy within its budget).
            if (
                index == self._max_steps
                and observation.get("error", {}).get("reason") == STOP_REPEATED_FAILURE
            ):
                stop_reason = STOP_REPEATED_FAILURE

        elapsed_total_ms = int((self._clock() - started) * 1000.0)
        summary: JsonObject = {
            "steps": len(state.steps),
            "max_steps": self._max_steps,
            "stop_reason": stop_reason,
            "tool_calls_ok": state.tool_ok,
            "tool_calls_failed": state.tool_failed,
            "repeated_failure_refusals": state.repeated_refused,
            "invalid_proposals": state.invalid_total,
            "evidence_items": len(state.evidence),
            "elapsed_ms": elapsed_total_ms,
        }
        if self._deadline_ms is not None:
            summary["deadline_ms"] = self._deadline_ms
        status = ExecutionStatus.SUCCEEDED if stop_reason == STOP_FINAL else ExecutionStatus.FAILED
        execution = Execution(
            id=execution_id,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            status=status,
            strategy=ExecutionStrategy.AGENT,
            cost_snapshot=dict(summary),
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
            verification=verification,
            evidence=tuple(state.evidence),
            summary=summary,
        )

    # --- internals --------------------------------------------------------------

    @staticmethod
    def _call_key(proposal: ToolCallProposal) -> str:
        """Canonical identity of a tool call (name + sorted arguments)."""
        try:
            args = json.dumps(proposal.arguments, sort_keys=True, default=str)
        except (TypeError, ValueError):
            args = repr(proposal.arguments)
        return f"{proposal.tool}:{args}"

    async def _run_verifier(
        self,
        state: _RunState,
        execution_id: UUID,
        index: int,
        request: JsonObject,
        output: JsonObject,
    ) -> JsonObject:
        """Run the composition-bound verifier; every outcome is data.

        A verifier FAULT is a rejecting verdict naming the fault (P6) —
        deterministic code failing must never silently admit a final.
        """
        verify = self._verify
        assert verify is not None  # caller checks; kept explicit for typing
        try:
            verdict = await verify(dict(request), dict(output))
        except Exception as exc:  # noqa: BLE001 — seam fault becomes data
            verdict = {
                "verified": False,
                "error": "verifier_failed",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        if not isinstance(verdict, dict):
            verdict = {
                "verified": False,
                "error": "verifier_invalid",
                "detail": f"verdict must be a JSON object, got {type(verdict).__name__}",
            }
        passed = bool(verdict.get("verified"))
        state.nodes.append(
            ExecutionNode(
                id=self._id_factory(),
                execution_id=execution_id,
                node_key=f"verify-{index}",
                type=ExecutionNodeType.VALIDATOR,
                status=(ExecutionNodeStatus.SUCCEEDED if passed else ExecutionNodeStatus.FAILED),
                input_ref=dict(output),
                output_ref=verdict,
                retry_count=0,
                error=None if passed else {"reason": STOP_VERIFICATION_FAILED},
            )
        )
        return verdict

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
        call_key = self._call_key(proposal)
        prior_failures = state.failures.get(call_key, 0)
        if binding is not None and prior_failures >= self._max_repeated_failures:
            # Reassessment enforced by code: the identical call already
            # failed ``max_repeated_failures`` times this run. Nothing is
            # dispatched; the observation names the repetition so the model
            # must change its action or strategy (or finalize honestly).
            state.repeated_refused += 1
            error = {
                "reason": STOP_REPEATED_FAILURE,
                "detail": (
                    f"identical call to '{proposal.tool}' already failed "
                    f"{prior_failures} time(s); change arguments, tool, or "
                    "strategy"
                ),
                "prior_failures": prior_failures,
            }
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
            state.steps.append(AgentStep(index=index, proposal_raw=raw, observation=observation))
            return observation
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
            observation = {
                "step": index,
                "tool": proposal.tool,
                "status": "refused",
                "error": error,
            }
            state.steps.append(AgentStep(index=index, proposal_raw=raw, observation=observation))
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
        if succeeded:
            state.tool_ok += 1
            state.failures.pop(call_key, None)
            state.evidence.append(
                {
                    "step": index,
                    "tool": proposal.tool,
                    "arguments": dict(proposal.arguments),
                    "result": record.result,
                }
            )
        else:
            state.tool_failed += 1
            state.failures[call_key] = prior_failures + 1
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
            status=(ExecutionNodeStatus.SUCCEEDED if succeeded else ExecutionNodeStatus.FAILED),
            output=record.result,
            error=(None if succeeded else {"reason": record.error, "detail": record.error_detail}),
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
