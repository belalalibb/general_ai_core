"""Phase V4 chunk 2: the bounded agent loop over the V3 gated tool runtime.

Frozen-definition mapping (roadmap V4, verbatim clauses):

- "model proposes structured output → platform validates" ->
  test_invalid_proposal_stops_run_as_failed_data,
  test_authority_injection_key_is_invalid_proposal.
- "gate admits → executor runs → observation appended" ->
  test_tool_call_flows_through_gated_executor,
  test_gate_refusal_becomes_observation_model_can_react_to,
  test_unknown_tool_name_refused_without_execution.
- "bounded by budget/step-count/admission" ->
  test_max_steps_bound_enforced, test_budget_refusal_is_observation,
  (admission = the gate tests above).
- "Model proposes; deterministic code disposes" ->
  test_final_proposal_ends_run_with_output,
  test_loop_has_no_direct_tool_path (structural: acts only via
  ToolExecutor.execute — the audit trail proves every act hit the gate).
- "`ExecutionStrategy.AGENT` stops being vocabulary" ->
  test_report_strategy_is_agent.
- P6 evidence -> test_propose_fault_contained_as_data,
  test_nodes_record_plan_and_act_trail.

Hermetic — fake propose seam + the real V3 executor over in-memory
gate/audit/usage; zero I/O.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from core.audit import InMemoryAuditLog
from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNodeStatus, ExecutionNodeType, ExecutionStrategy
from core.execution.agent import AgentToolBinding
from core.execution.loop import (
    STOP_FINAL,
    STOP_INVALID_PROPOSAL,
    STOP_MAX_STEPS,
    STOP_PROPOSE_FAILED,
    AgentLoop,
    AgentRunReport,
)
from core.identity.devices import DeviceRegistry
from core.tools import ToolCallGate, ToolExecutor, ToolRegistry
from core.usage import InMemoryUsageAccounting
from tests.tools.test_tool_fabric import (
    PERM_READ,
    TENANT,
    granting_firewall,
    make_tool,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class ScriptedProposer:
    """Propose seam double: replays proposals in order, records payloads."""

    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.payloads: list[JsonObject] = []

    async def __call__(self, payload: JsonObject) -> JsonObject:
        self.payloads.append(payload)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        assert isinstance(step, dict)
        return step


class EchoHandler:
    """Tool handler double: records arguments, echoes them back."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[JsonObject] = []
        self._error = error

    async def __call__(self, arguments: JsonObject) -> JsonObject:
        self.calls.append(arguments)
        if self._error is not None:
            raise self._error
        return {"echo": arguments}


class AgentWorld:
    """One hermetic agent world over the REAL V3 executor."""

    def __init__(self, *, budget: float = 100.0) -> None:
        self.tool = make_tool(permissions=[PERM_READ])
        self.handler = EchoHandler()
        registry = ToolRegistry()
        registry.register(self.tool)
        self.audit = InMemoryAuditLog()
        self.usage = InMemoryUsageAccounting()
        self.usage.configure_tenant(TENANT, plan="test", task_units_limit=budget)
        self.executor = ToolExecutor(
            gate=ToolCallGate(
                tools=registry,
                firewall=granting_firewall(),
                devices=DeviceRegistry(),
            ),
            handlers={self.tool.id: self.handler},
            audit=self.audit,
            usage=self.usage,
        )
        self.binding = AgentToolBinding(
            tool_id=self.tool.id,
            permission=PERM_READ,
            resource="repo:owner/name",
            scope="project",
            entitlement="github_write",
            risk_level="low",
        )

    def loop(
        self,
        script: list[object],
        *,
        max_steps: int = 5,
        bindings: dict[str, AgentToolBinding] | None = None,
    ) -> tuple[AgentLoop, ScriptedProposer]:
        proposer = ScriptedProposer(script)
        loop = AgentLoop(
            propose=proposer,
            tools=self.executor,
            bindings=(bindings if bindings is not None else {"github.read": self.binding}),
            max_steps=max_steps,
        )
        return loop, proposer

    def run(self, loop: AgentLoop) -> AgentRunReport:
        return run(
            loop.execute(
                tenant_id=TENANT,
                user_id=uuid4(),
                request={"ask": "read the repo"},
                request_hash="h" * 8,
            )
        )


def _tool_call(tool: str = "github.read", **arguments: object) -> JsonObject:
    return {"action": "tool_call", "tool": tool, "arguments": dict(arguments)}


def _final(**output: object) -> JsonObject:
    return {"action": "final", "output": dict(output)}


# --- happy path -------------------------------------------------------------------


def test_final_proposal_ends_run_with_output() -> None:
    world = AgentWorld()
    loop, _ = world.loop([_final(answer=42)])
    report = world.run(loop)
    assert report.succeeded is True
    assert report.stop_reason == STOP_FINAL
    assert report.final_output == {"answer": 42}
    assert report.execution.status is ExecutionStatus.SUCCEEDED


def test_report_strategy_is_agent() -> None:
    world = AgentWorld()
    loop, _ = world.loop([_final(done=True)])
    report = world.run(loop)
    assert report.execution.strategy is ExecutionStrategy.AGENT
    assert report.execution.cost_snapshot["stop_reason"] == STOP_FINAL


def test_tool_call_flows_through_gated_executor() -> None:
    world = AgentWorld()
    loop, proposer = world.loop([_tool_call(path="README.md"), _final(done=True)])
    report = world.run(loop)
    assert report.succeeded is True
    # the handler saw exactly the model's arguments
    assert world.handler.calls == [{"path": "README.md"}]
    # observation carried the tool result back into the next proposal payload
    second_payload = proposer.payloads[1]
    assert second_payload["observations"][0]["status"] == "succeeded"
    assert second_payload["observations"][0]["result"] == {"echo": {"path": "README.md"}}
    # the act passed the gate: exactly one TOOL_CALL audit event exists
    events = world.audit.read(tenant_id=TENANT)
    assert len(events) == 1
    assert events[0].details["status"] == "succeeded"


def test_nodes_record_plan_and_act_trail() -> None:
    world = AgentWorld()
    loop, _ = world.loop([_tool_call(x=1), _final(ok=True)])
    report = world.run(loop)
    types = [node.type for node in report.nodes]
    assert types == [
        ExecutionNodeType.PLANNER,  # step 1 proposal
        ExecutionNodeType.TOOL_CALL,  # step 1 act
        ExecutionNodeType.PLANNER,  # step 2 proposal
        ExecutionNodeType.AGGREGATOR,  # finalize
    ]
    assert all(node.execution_id == report.execution.id for node in report.nodes)


# --- bounds ------------------------------------------------------------------------


def test_max_steps_bound_enforced() -> None:
    """The loop NEVER runs unbounded: step budget exhaustion = failed run."""
    world = AgentWorld()
    loop, _ = world.loop([_tool_call(n=i) for i in range(10)], max_steps=3)
    report = world.run(loop)
    assert report.succeeded is False
    assert report.stop_reason == STOP_MAX_STEPS
    assert len(report.steps) == 3
    assert len(world.handler.calls) == 3  # exactly max_steps acts, no more


def test_max_steps_must_be_positive() -> None:
    world = AgentWorld()
    with pytest.raises(ValueError, match="max_steps must be >= 1"):
        AgentLoop(
            propose=ScriptedProposer([]),
            tools=world.executor,
            bindings={},
            max_steps=0,
        )


def test_budget_refusal_is_observation() -> None:
    """A budget denial refuses the act as data; the run continues."""
    world = AgentWorld(budget=1.0)
    costly = AgentToolBinding(
        tool_id=world.binding.tool_id,
        permission=world.binding.permission,
        resource=world.binding.resource,
        scope=world.binding.scope,
        entitlement=world.binding.entitlement,
        risk_level=world.binding.risk_level,
        estimated_units=5.0,
    )
    loop, proposer = world.loop(
        [_tool_call(), _final(gave_up=True)],
        bindings={"github.read": costly},
    )
    report = world.run(loop)
    assert report.succeeded is True  # the model adapted and finished
    obs = proposer.payloads[1]["observations"][0]
    assert obs["status"] == "refused"
    assert obs["error"]["reason"] == "entitlement_exceeded"
    assert world.handler.calls == []  # the handler never ran


# --- admission / security -----------------------------------------------------------


def test_gate_refusal_becomes_observation_model_can_react_to() -> None:
    """A disabled tool refuses through the gate; the loop observes it."""
    world = AgentWorld()
    disabled = make_tool(permissions=[PERM_READ], status="disabled")
    registry = ToolRegistry()
    registry.register(disabled)
    executor = ToolExecutor(
        gate=ToolCallGate(tools=registry, firewall=granting_firewall(), devices=DeviceRegistry()),
        handlers={disabled.id: world.handler},
        audit=world.audit,
        usage=world.usage,
    )
    binding = AgentToolBinding(
        tool_id=disabled.id,
        permission=PERM_READ,
        resource="repo:owner/name",
        scope="project",
        entitlement="github_write",
        risk_level="low",
    )
    proposer = ScriptedProposer([_tool_call(), _final(stopped=True)])
    loop = AgentLoop(
        propose=proposer,
        tools=executor,
        bindings={"github.read": binding},
        max_steps=5,
    )
    report = world.run(loop)
    assert report.succeeded is True
    obs = proposer.payloads[1]["observations"][0]
    assert obs["status"] == "refused"
    assert obs["error"]["detail"] == "tool_not_selectable:disabled"
    assert world.handler.calls == []


def test_unknown_tool_name_refused_without_execution() -> None:
    """A name outside the composition bindings executes NOTHING."""
    world = AgentWorld()
    loop, proposer = world.loop([_tool_call(tool="filesystem.delete_everything"), _final(ok=True)])
    report = world.run(loop)
    assert report.succeeded is True
    obs = proposer.payloads[1]["observations"][0]
    assert obs["status"] == "refused"
    assert obs["error"] == {
        "reason": "unknown_tool",
        "detail": "filesystem.delete_everything",
    }
    assert world.handler.calls == []
    # nothing was audited as a tool call — nothing reached the executor
    assert world.audit.count(TENANT) == 0


def test_loop_has_no_direct_tool_path() -> None:
    """Structural: every act audits through the executor's gate path.

    Two acts => exactly two TOOL_CALL audit events; the loop owns no
    other way to reach a handler (the handler mapping lives inside the
    executor, private).
    """
    world = AgentWorld()
    loop, _ = world.loop([_tool_call(a=1), _tool_call(b=2), _final(ok=True)])
    report = world.run(loop)
    assert report.succeeded is True
    assert world.audit.count(TENANT) == 2
    assert len(world.handler.calls) == 2


def test_authority_injection_key_is_invalid_proposal() -> None:
    """A proposal smuggling authority keys fails validation, runs nothing."""
    world = AgentWorld()
    smuggled = {
        "action": "tool_call",
        "tool": "github.read",
        "arguments": {},
        "permission": "admin.everything",
    }
    loop, _ = world.loop([smuggled, smuggled])
    report = world.run(loop)
    assert report.succeeded is False
    assert report.stop_reason == STOP_INVALID_PROPOSAL
    assert world.handler.calls == []
    assert world.audit.count(TENANT) == 0


# --- fault containment ---------------------------------------------------------------


def test_invalid_proposal_stops_run_as_failed_data() -> None:
    """R165 bound: two CONSECUTIVE invalid proposals stop the run (default)."""
    world = AgentWorld()
    loop, proposer = world.loop([{"action": "improvise"}, {"action": "improvise"}])
    report = world.run(loop)
    assert report.succeeded is False
    assert report.stop_reason == STOP_INVALID_PROPOSAL
    assert report.final_output is None
    assert len(report.steps) == 2
    assert report.summary["invalid_proposals"] == 2
    failed_planner = report.nodes[-1]
    assert failed_planner.type is ExecutionNodeType.PLANNER
    assert failed_planner.error is not None
    assert failed_planner.error["reason"] == STOP_INVALID_PROPOSAL
    assert "action must be one of" in failed_planner.error["detail"]
    # The second proposal SAW the first refusal as an observation (data).
    second_payload = proposer.payloads[1]
    assert second_payload["observations"][0]["error"] == STOP_INVALID_PROPOSAL
    assert second_payload["observations"][0]["nothing_happened"] is True


def test_invalid_proposal_then_repair_succeeds() -> None:
    """R165: the model corrects a protocol violation within its budget."""
    world = AgentWorld()
    loop, _ = world.loop(
        [
            {"action": "improvise"},
            {"action": "final", "output": {"answer": "recovered", "evidence": []}},
        ]
    )
    report = world.run(loop)
    assert report.succeeded is True
    assert report.stop_reason == STOP_FINAL
    assert report.summary["invalid_proposals"] == 1
    assert [n.status for n in report.nodes if n.type is ExecutionNodeType.PLANNER][:2] == [
        ExecutionNodeStatus.FAILED,
        ExecutionNodeStatus.SUCCEEDED,
    ]


def test_invalid_proposal_single_shot_bound_is_configurable() -> None:
    """max_invalid_proposals=1 restores the pre-R165 stop-on-first behaviour."""
    world = AgentWorld()
    proposer = ScriptedProposer([{"action": "improvise"}])
    loop = AgentLoop(
        propose=proposer,
        tools=world.executor,
        bindings={"github.read": world.binding},
        max_steps=5,
        max_invalid_proposals=1,
    )
    report = world.run(loop)
    assert report.stop_reason == STOP_INVALID_PROPOSAL
    assert len(report.steps) == 1


def test_invalid_proposal_on_last_step_stops() -> None:
    """A violation on the final budgeted step cannot be repaired — honest stop."""
    world = AgentWorld()
    loop, _ = world.loop([{"action": "improvise"}], max_steps=1)
    report = world.run(loop)
    assert report.stop_reason == STOP_INVALID_PROPOSAL


def test_propose_fault_contained_as_data() -> None:
    world = AgentWorld()
    loop, _ = world.loop([RuntimeError("model service down")])
    report = world.run(loop)
    assert report.succeeded is False
    assert report.stop_reason == STOP_PROPOSE_FAILED
    assert report.nodes[-1].error == {
        "reason": STOP_PROPOSE_FAILED,
        "detail": "RuntimeError: model service down",
    }


def test_handler_failure_observed_and_run_continues() -> None:
    world = AgentWorld()
    failing = EchoHandler(error=OSError("disk full"))
    registry = ToolRegistry()
    registry.register(world.tool)
    executor = ToolExecutor(
        gate=ToolCallGate(tools=registry, firewall=granting_firewall(), devices=DeviceRegistry()),
        handlers={world.tool.id: failing},
        audit=world.audit,
        usage=world.usage,
    )
    proposer = ScriptedProposer([_tool_call(), _final(recovered=True)])
    loop = AgentLoop(
        propose=proposer,
        tools=executor,
        bindings={"github.read": world.binding},
        max_steps=5,
    )
    report = world.run(loop)
    assert report.succeeded is True
    obs = proposer.payloads[1]["observations"][0]
    assert obs["status"] == "failed"
    assert obs["error"]["reason"] == "execution_failed"
    assert obs["error"]["detail"] == "OSError: disk full"
