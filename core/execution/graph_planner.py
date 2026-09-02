"""Graph Planner — builds/validates ExecutionGraphSpec topologies
(41 §12 "Planner"; doc 12 §3–§8, doc 11 §10/§15).

Deterministic, pure construction of graph specs. The planner PLANS; the
workflow runtime RUNS (12 §9); the Router DECIDES models per node
(10 §13.5). No I/O, no AI.

Recorded derivation decisions (never silent):

- DOCUMENTED TOPOLOGIES ONLY. The docs define concrete node topologies for:
  * single   — one node (the trivial strategy; 03 §5).
  * pipeline — a linear chain with success edges (11 §10 output example:
    planner -> reviewer; 12 §24.1 pipeline pattern).
  * parallel — N branches feeding one aggregator/judge (11 §15.2:
    "model A/B/C -> evaluator/judge -> final"; 12 §24.2).
  * debate   — N debaters feeding a judge/finalizer (11 §15.4: "Multiple
    models produce competing analyses/critiques, then a judge/finalizer
    produces the final result"; 12 §24.3).
  For review_judge / map_reduce / agent / hybrid the docs define NO
  topology template (12 §8 shows agent workflows as domain EXAMPLES, not a
  generator rule) — the planner does NOT generate those; callers author the
  spec explicitly and :meth:`GraphPlanner.validate` admits it. Guessing a
  topology would fabricate architecture.
- NODE TYPES in generated graphs: branches/stages are ``model_call``; the
  combining node of parallel is ``aggregator`` and of debate is
  ``finalizer`` (11 §15.4 verbatim "judge/finalizer"; 12 §15: judge is a
  role played by an aggregator/finalizer-type node with its own policy).
- EDGES: generated graphs use ``success`` conditions (the documented happy
  topology); failure/approval edges are authored, not generated.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.contracts.execution import ExecutionStrategy
from core.contracts.execution_graph import (
    EdgeCondition,
    ExecutionGraphSpec,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphNodeType,
)
from core.contracts.model_policy import NodeModelPolicy
from core.execution.errors import InvalidPipeline


class GraphPlanner:
    """Builds documented graph topologies; validates authored ones."""

    def plan_single(
        self,
        graph_id: str,
        node_id: str = "task",
        *,
        model_policy: NodeModelPolicy | None = None,
    ) -> ExecutionGraphSpec:
        """One model_call node — the ``single`` strategy."""
        return ExecutionGraphSpec(
            id=graph_id,
            strategy=ExecutionStrategy.SINGLE,
            nodes=[
                GraphNodeSpec(
                    id=node_id,
                    type=GraphNodeType.MODEL_CALL,
                    model_policy=model_policy,
                )
            ],
        )

    def plan_pipeline(self, graph_id: str, stages: Sequence[GraphNodeSpec]) -> ExecutionGraphSpec:
        """Linear chain with success edges (11 §10 / 12 §24.1)."""
        if len(stages) < 2:
            msg = "a pipeline needs at least 2 stages (12 §24.1)"
            raise InvalidPipeline(msg)
        edges = [
            GraphEdgeSpec.model_validate(
                {
                    "from": stages[i].id,
                    "to": stages[i + 1].id,
                    "condition": EdgeCondition.SUCCESS,
                }
            )
            for i in range(len(stages) - 1)
        ]
        return ExecutionGraphSpec(
            id=graph_id,
            strategy=ExecutionStrategy.PIPELINE,
            nodes=list(stages),
            edges=edges,
        )

    def plan_parallel(
        self,
        graph_id: str,
        branches: Sequence[GraphNodeSpec],
        aggregator: GraphNodeSpec,
    ) -> ExecutionGraphSpec:
        """N branches feeding one aggregator (11 §15.2 / 12 §24.2)."""
        if len(branches) < 2:
            msg = "parallel needs at least 2 branches (11 §15.2)"
            raise InvalidPipeline(msg)
        if aggregator.type not in (
            GraphNodeType.AGGREGATOR,
            GraphNodeType.FINALIZER,
        ):
            msg = (
                "the parallel combining node must be an aggregator or"
                " finalizer (11 §15.2 'evaluator/judge -> final')"
            )
            raise InvalidPipeline(msg)
        edges = [
            GraphEdgeSpec.model_validate(
                {
                    "from": branch.id,
                    "to": aggregator.id,
                    "condition": EdgeCondition.SUCCESS,
                }
            )
            for branch in branches
        ]
        return ExecutionGraphSpec(
            id=graph_id,
            strategy=ExecutionStrategy.PARALLEL,
            nodes=[*branches, aggregator],
            edges=edges,
        )

    def plan_debate(
        self,
        graph_id: str,
        debaters: Sequence[GraphNodeSpec],
        judge: GraphNodeSpec,
    ) -> ExecutionGraphSpec:
        """N debaters feeding a judge/finalizer (11 §15.4 / 12 §24.3)."""
        if len(debaters) < 2:
            msg = "debate needs at least 2 debaters (11 §15.4)"
            raise InvalidPipeline(msg)
        if judge.type is not GraphNodeType.FINALIZER:
            msg = (
                "the debate combining node must be a finalizer"
                " (11 §15.4 'judge/finalizer produces the final result')"
            )
            raise InvalidPipeline(msg)
        edges = [
            GraphEdgeSpec.model_validate(
                {
                    "from": debater.id,
                    "to": judge.id,
                    "condition": EdgeCondition.SUCCESS,
                }
            )
            for debater in debaters
        ]
        return ExecutionGraphSpec(
            id=graph_id,
            strategy=ExecutionStrategy.DEBATE,
            nodes=[*debaters, judge],
            edges=edges,
        )

    def validate(self, spec: ExecutionGraphSpec) -> ExecutionGraphSpec:
        """Admit an explicitly-authored graph (any of the 8 strategies).

        Structural validation (unique ids, referential edges) already ran in
        the contract validator; this re-validates a mutated/deserialized
        spec and is the documented entry point for the strategies whose
        topology the docs leave to the author (review_judge / map_reduce /
        agent / hybrid — module docstring).
        """
        return ExecutionGraphSpec.model_validate(spec.model_dump(by_alias=True))
