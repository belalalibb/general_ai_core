"""Execution Graph spec + planner + workflow port (T-IMPL-058; 41 §12, doc 12).

Hermetic — pure contracts and an in-memory fake runtime; no network, no
adapters, no AI, NO workflow engine (41 §12: "We do not build our own
Workflow Engine" — asserted by the port being the only runtime surface).

Asserted verbatim closed sets: 12 §5 eleven node types, 12 §6 eight
lifecycle states, 12 §7 six edge conditions. Graph validation: unique node
ids + referential edges (acyclicity deliberately NOT enforced — recorded).
Planner: documented topologies only (single/pipeline/parallel/debate).
Port: idempotent submission (12 §10), approval signal auditability carrier
(12 §11), cancellation, lifecycle normalization (12 §6).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from itertools import count

import pytest
from pydantic import ValidationError

from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNodeType, ExecutionStrategy
from core.contracts.execution_graph import (
    EdgeCondition,
    ExecutionGraphSpec,
    GraphEdgeSpec,
    GraphNodeLifecycle,
    GraphNodeSpec,
    GraphNodeType,
    RetryPolicySpec,
)
from core.execution import GraphPlanner, InvalidPipeline, WorkflowRuntimePort


def run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


def _node(node_id: str, node_type: GraphNodeType = GraphNodeType.MODEL_CALL) -> GraphNodeSpec:
    return GraphNodeSpec(id=node_id, type=node_type)


def _edge(from_node: str, to_node: str, condition: str = "success") -> GraphEdgeSpec:
    return GraphEdgeSpec.model_validate({"from": from_node, "to": to_node, "condition": condition})


# --- closed sets (doc 12, verbatim) ---------------------------------------------------


def test_graph_node_types_are_the_12_s5_eleven() -> None:
    assert [t.value for t in GraphNodeType] == [
        "planner",
        "model_call",
        "tool_call",
        "aggregator",
        "reviewer",
        "tester",
        "validator",
        "approval_gate",
        "human_input",
        "finalizer",
        "provider_agent_call",
    ]


def test_graph_lifecycle_is_the_12_s6_eight() -> None:
    assert [s.value for s in GraphNodeLifecycle] == [
        "pending",
        "ready",
        "running",
        "waiting_approval",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
    ]


def test_edge_conditions_are_the_12_s7_six() -> None:
    assert [c.value for c in EdgeCondition] == [
        "success",
        "failure",
        "always",
        "score_below_threshold",
        "approval_granted",
        "approval_denied",
    ]


def test_graph_set_and_entity_set_are_kept_per_authority() -> None:
    # Recorded distinction: 12 §5 graph set (11) vs 03 §5 entity set (7) —
    # neither silently merged into the other.
    graph_values = {t.value for t in GraphNodeType}
    entity_values = {t.value for t in ExecutionNodeType}
    assert entity_values < graph_values
    assert graph_values - entity_values == {
        "approval_gate",
        "human_input",
        "finalizer",
        "provider_agent_call",
    }


# --- graph spec validation --------------------------------------------------------------


def test_graph_accepts_the_12_s3_documented_example_shape() -> None:
    spec = ExecutionGraphSpec.model_validate(
        {
            "id": "execution_uuid",
            "strategy": "agent",
            "status": "running",
            "nodes": [],
            "edges": [],
            "policies": {
                "timeout_ms": 600000,
                "retry_policy": "standard",
                "approval_policy": "tool_write_requires_approval",
                "evaluation_policy": "standard",
            },
        }
    )
    assert spec.strategy is ExecutionStrategy.AGENT
    assert spec.policies.timeout_ms == 600000


def test_node_accepts_the_12_s4_documented_example_shape() -> None:
    node = GraphNodeSpec.model_validate(
        {
            "id": "review_code",
            "type": "model_call",
            "role": "code_reviewer",
            "input_source": ["user_request", "github.files"],
            "model_policy": {"type": "tier", "tier": "medium"},
            "skills": ["code_review"],
            "tools": ["github.read"],
            "output_schema": None,
            "retry_policy": {
                "max_attempts": 2,
                "retry_on": ["timeout", "retryable_provider_error"],
            },
            "timeout_ms": 120000,
            "evaluation_policy": "code_review_basic",
        }
    )
    assert node.retry_policy is not None
    assert node.retry_policy.max_attempts == 2


def test_edge_uses_documented_from_to_aliases() -> None:
    edge = _edge("planner", "executor")
    assert edge.from_node == "planner"
    assert edge.to_node == "executor"
    assert edge.model_dump(by_alias=True)["from"] == "planner"


def test_duplicate_node_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate node id"):
        ExecutionGraphSpec(
            id="g",
            strategy=ExecutionStrategy.SINGLE,
            nodes=[_node("a"), _node("a")],
        )


def test_dangling_edges_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        ExecutionGraphSpec(
            id="g",
            strategy=ExecutionStrategy.PIPELINE,
            nodes=[_node("a")],
            edges=[_edge("a", "ghost")],
        )


def test_cycles_are_admitted_not_a_dag_constraint() -> None:
    # Recorded: doc 12 never declares a DAG; agent loops are documented.
    spec = ExecutionGraphSpec(
        id="g",
        strategy=ExecutionStrategy.AGENT,
        nodes=[_node("plan", GraphNodeType.PLANNER), _node("act")],
        edges=[_edge("plan", "act"), _edge("act", "plan", "failure")],
    )
    assert len(spec.edges) == 2


def test_zero_timeout_rejected_zero_retries_allowed() -> None:
    with pytest.raises(ValidationError):
        GraphNodeSpec(id="n", type=GraphNodeType.MODEL_CALL, timeout_ms=0)
    assert RetryPolicySpec(max_attempts=0).max_attempts == 0  # explicit "never"


def test_lookup_helpers() -> None:
    spec = ExecutionGraphSpec(
        id="g",
        strategy=ExecutionStrategy.PIPELINE,
        nodes=[_node("a"), _node("b")],
        edges=[_edge("a", "b")],
    )
    assert spec.node("a").id == "a"
    with pytest.raises(KeyError):
        spec.node("ghost")
    assert [e.to_node for e in spec.edges_from("a")] == ["b"]
    assert spec.edges_from("b") == []


# --- planner (documented topologies only) -----------------------------------------------


def test_plan_single() -> None:
    spec = GraphPlanner().plan_single("g")
    assert spec.strategy is ExecutionStrategy.SINGLE
    assert len(spec.nodes) == 1
    assert spec.nodes[0].type is GraphNodeType.MODEL_CALL
    assert spec.edges == []


def test_plan_pipeline_linear_success_chain() -> None:
    spec = GraphPlanner().plan_pipeline(
        "g", [_node("plan", GraphNodeType.PLANNER), _node("do"), _node("review")]
    )
    assert spec.strategy is ExecutionStrategy.PIPELINE
    assert [(e.from_node, e.to_node) for e in spec.edges] == [
        ("plan", "do"),
        ("do", "review"),
    ]
    assert all(e.condition is EdgeCondition.SUCCESS for e in spec.edges)


def test_plan_pipeline_needs_two_stages() -> None:
    with pytest.raises(InvalidPipeline, match="at least 2"):
        GraphPlanner().plan_pipeline("g", [_node("only")])


def test_plan_parallel_branches_feed_aggregator() -> None:
    spec = GraphPlanner().plan_parallel(
        "g",
        [_node("a"), _node("b"), _node("c")],
        _node("combine", GraphNodeType.AGGREGATOR),
    )
    assert spec.strategy is ExecutionStrategy.PARALLEL
    assert {(e.from_node, e.to_node) for e in spec.edges} == {
        ("a", "combine"),
        ("b", "combine"),
        ("c", "combine"),
    }


def test_plan_parallel_rejects_non_combining_node() -> None:
    with pytest.raises(InvalidPipeline, match="aggregator or"):
        GraphPlanner().plan_parallel(
            "g", [_node("a"), _node("b")], _node("x", GraphNodeType.MODEL_CALL)
        )


def test_plan_debate_debaters_feed_finalizer() -> None:
    spec = GraphPlanner().plan_debate(
        "g",
        [_node("pro"), _node("con")],
        _node("judge", GraphNodeType.FINALIZER),
    )
    assert spec.strategy is ExecutionStrategy.DEBATE
    assert {(e.from_node, e.to_node) for e in spec.edges} == {
        ("pro", "judge"),
        ("con", "judge"),
    }


def test_plan_debate_requires_finalizer_judge() -> None:
    with pytest.raises(InvalidPipeline, match="finalizer"):
        GraphPlanner().plan_debate(
            "g", [_node("a"), _node("b")], _node("j", GraphNodeType.AGGREGATOR)
        )


def test_validate_admits_authored_strategies() -> None:
    # review_judge/map_reduce/agent/hybrid are AUTHORED, never generated.
    authored = ExecutionGraphSpec(
        id="g",
        strategy=ExecutionStrategy.MAP_REDUCE,
        nodes=[_node("map1"), _node("map2"), _node("reduce", GraphNodeType.AGGREGATOR)],
        edges=[_edge("map1", "reduce"), _edge("map2", "reduce")],
    )
    assert GraphPlanner().validate(authored).strategy is ExecutionStrategy.MAP_REDUCE


def test_planner_generates_no_topology_for_undocumented_strategies() -> None:
    # The planner exposes ONLY the documented generators — recorded scope.
    planner_api = {name for name in dir(GraphPlanner) if name.startswith("plan_")}
    assert planner_api == {"plan_single", "plan_pipeline", "plan_parallel", "plan_debate"}


# --- workflow runtime port (12 §9/§10/§11) -----------------------------------------------


class FakeWorkflowRuntime:
    """In-memory runtime standing in for the EXTERNAL engine (12 §9)."""

    def __init__(self) -> None:
        self._seq = count(1)
        self._by_key: dict[str, str] = {}
        self._graphs: dict[str, ExecutionGraphSpec] = {}
        self._status: dict[str, ExecutionStatus] = {}
        self._nodes: dict[str, dict[str, GraphNodeLifecycle]] = {}
        self.approval_log: list[tuple[str, str, bool, str]] = []

    async def submit(
        self, graph: ExecutionGraphSpec, *, idempotency_key: str, inputs: JsonObject
    ) -> str:
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing  # 12 §10: same key => same run
        workflow_id = f"wf-{next(self._seq)}"
        self._by_key[idempotency_key] = workflow_id
        self._graphs[workflow_id] = graph
        self._status[workflow_id] = ExecutionStatus.RUNNING
        self._nodes[workflow_id] = {n.id: GraphNodeLifecycle.PENDING for n in graph.nodes}
        return workflow_id

    async def status(self, workflow_id: str) -> ExecutionStatus:
        return self._status[workflow_id]

    async def node_states(self, workflow_id: str) -> dict[str, GraphNodeLifecycle]:
        return dict(self._nodes[workflow_id])

    async def cancel(self, workflow_id: str) -> None:
        self._status[workflow_id] = ExecutionStatus.CANCELLED
        for node_id, state in self._nodes[workflow_id].items():
            if state in (GraphNodeLifecycle.PENDING, GraphNodeLifecycle.RUNNING):
                self._nodes[workflow_id][node_id] = GraphNodeLifecycle.CANCELLED

    async def signal_approval(
        self, workflow_id: str, node_id: str, *, granted: bool, approver_ref: str
    ) -> None:
        self.approval_log.append((workflow_id, node_id, granted, approver_ref))
        self._nodes[workflow_id][node_id] = (
            GraphNodeLifecycle.RUNNING if granted else GraphNodeLifecycle.FAILED
        )


# mypy-checked Protocol conformance (structural).
_runtime_check: WorkflowRuntimePort = FakeWorkflowRuntime()


def _pipeline() -> ExecutionGraphSpec:
    return GraphPlanner().plan_pipeline("g", [_node("a"), _node("b")])


def test_duplicate_submission_returns_same_workflow_id() -> None:
    # 12 §10 idempotency: duplicate delivery never duplicates a run.
    runtime = FakeWorkflowRuntime()

    async def scenario() -> tuple[str, str]:
        first = await runtime.submit(_pipeline(), idempotency_key="k1", inputs={})
        second = await runtime.submit(_pipeline(), idempotency_key="k1", inputs={})
        return first, second

    first, second = run(scenario())
    assert first == second


def test_node_states_report_the_12_s6_lifecycle() -> None:
    runtime = FakeWorkflowRuntime()

    async def scenario() -> dict[str, GraphNodeLifecycle]:
        workflow_id = await runtime.submit(_pipeline(), idempotency_key="k1", inputs={})
        return await runtime.node_states(workflow_id)

    states = run(scenario())
    assert states == {
        "a": GraphNodeLifecycle.PENDING,
        "b": GraphNodeLifecycle.PENDING,
    }


def test_cancellation_reaches_status_and_nodes() -> None:
    # 12 §12 required test: execution cancellation.
    runtime = FakeWorkflowRuntime()

    async def scenario() -> tuple[ExecutionStatus, dict[str, GraphNodeLifecycle]]:
        workflow_id = await runtime.submit(_pipeline(), idempotency_key="k1", inputs={})
        await runtime.cancel(workflow_id)
        return await runtime.status(workflow_id), await runtime.node_states(workflow_id)

    status, states = run(scenario())
    assert status is ExecutionStatus.CANCELLED
    assert set(states.values()) == {GraphNodeLifecycle.CANCELLED}


def test_approval_signal_carries_auditable_actor() -> None:
    # 12 §11: "Approval result must be auditable."
    runtime = FakeWorkflowRuntime()

    async def scenario() -> None:
        graph = ExecutionGraphSpec(
            id="g",
            strategy=ExecutionStrategy.AGENT,
            nodes=[_node("gate", GraphNodeType.APPROVAL_GATE)],
        )
        workflow_id = await runtime.submit(graph, idempotency_key="k1", inputs={})
        await runtime.signal_approval(workflow_id, "gate", granted=True, approver_ref="user:alice")

    run(scenario())
    assert runtime.approval_log == [("wf-1", "gate", True, "user:alice")]


def test_denied_approval_fails_the_node() -> None:
    runtime = FakeWorkflowRuntime()

    async def scenario() -> GraphNodeLifecycle:
        graph = ExecutionGraphSpec(
            id="g",
            strategy=ExecutionStrategy.AGENT,
            nodes=[_node("gate", GraphNodeType.APPROVAL_GATE)],
        )
        workflow_id = await runtime.submit(graph, idempotency_key="k1", inputs={})
        await runtime.signal_approval(workflow_id, "gate", granted=False, approver_ref="user:bob")
        return (await runtime.node_states(workflow_id))["gate"]

    assert run(scenario()) is GraphNodeLifecycle.FAILED


def test_core_ships_no_workflow_engine() -> None:
    # 41 §12: "We do not build our own Workflow Engine." The port module
    # must define ONLY the Protocol seam — no engine class, no scheduler.
    import inspect

    import core.execution.workflow_ports as module

    classes = [
        obj
        for name, obj in vars(module).items()
        if inspect.isclass(obj) and obj.__module__ == module.__name__
    ]
    assert [c.__name__ for c in classes] == ["WorkflowRuntimePort"]
