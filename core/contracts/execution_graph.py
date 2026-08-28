"""Execution Graph specification contracts (12 §3–§7; 41 §12 FINAL Phase 9).

The GRAPH SPEC layer: what a planned execution looks like BEFORE it runs.
Distinct from the 03 §5 record entities (``Execution``/``ExecutionNode`` in
core/contracts/execution.py) which persist what DID run — the spec is the
plan, the entities are the trail. Both live side by side; neither replaces
the other.

Verbatim closed sets:

- :class:`GraphNodeType` — 12 §5, ELEVEN types. NOTE the recorded
  distinction: 03 §5 ``ExecutionNodeType`` is the persisted-entity set
  (7 values) while 12 §5 is the GRAPH node-type set (adds approval_gate /
  human_input / finalizer / provider_agent_call). Doc 12 is the single
  authority for the graph, so the spec layer uses the 12 §5 set unchanged;
  the entity enum stays as 03 defines it (no silent merging of closed sets
  across authorities).
- :class:`GraphNodeLifecycle` — 12 §6, EIGHT states (the entity's 03 §5
  six-state ``ExecutionNodeStatus`` lacks ``ready`` and
  ``waiting_approval``; again, per-authority sets are kept verbatim).
- :class:`EdgeCondition` — 12 §7, six conditions.

Recorded derivation decisions (never silent):

- GRAPH VALIDATION scope: node ids must be unique and edges must reference
  declared nodes (a graph with dangling edges cannot be planned or
  recovered deterministically). ACYCLICITY IS NOT ENFORCED: doc 12 never
  states the graph is a DAG, and agent workflows (12 §8) naturally revisit
  stages; inventing a DAG constraint would forbid documented behavior.
- ``retry_on`` values stay open bounded strings: 12 §4 shows examples
  ("timeout", "retryable_provider_error") but declares no closed set.
- ``policies`` (12 §3) is a typed object with the four documented keys;
  ``retry_policy``/``approval_policy``/``evaluation_policy`` are open
  policy NAMES (12 §3 shows string identifiers, not inline policies).
- ``status`` on the graph schema reuses the shared 6-state
  ``ExecutionStatus`` (12 §3 example value "running"); optional because a
  SPEC has no status until submitted.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionStrategy
from core.contracts.model_policy import NodeModelPolicy

# --- Closed sets (doc 12, verbatim) ----------------------------------------------


class GraphNodeType(StrEnum):
    """Graph node types (12 §5) — closed set, verbatim, eleven values.

    ``provider_agent_call`` "is a node type inside this graph, never a
    replacement for the platform graph" (12 §5).
    """

    PLANNER = "planner"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    AGGREGATOR = "aggregator"
    REVIEWER = "reviewer"
    TESTER = "tester"
    VALIDATOR = "validator"
    APPROVAL_GATE = "approval_gate"
    HUMAN_INPUT = "human_input"
    FINALIZER = "finalizer"
    PROVIDER_AGENT_CALL = "provider_agent_call"


class GraphNodeLifecycle(StrEnum):
    """Graph node lifecycle (12 §6) — closed set, verbatim, eight states."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class EdgeCondition(StrEnum):
    """Edge conditions (12 §7) — closed set, verbatim, six values."""

    SUCCESS = "success"
    FAILURE = "failure"
    ALWAYS = "always"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"


# --- Spec shapes (12 §3/§4/§7, field-for-field) -----------------------------------


class RetryPolicySpec(ContractModel):
    """Node retry policy (12 §4 ``retry_policy``).

    ``max_attempts`` bounded below (40 §4.7: no infinite retry — zero means
    "never retry", a valid explicit claim). ``retry_on`` values are open
    strings (12 §4 shows examples, declares no closed set — recorded).
    """

    max_attempts: int = Field(ge=0)
    retry_on: list[BoundedStr] = Field(default_factory=list)


class GraphNodeSpec(ContractModel):
    """One graph node (12 §4 node schema, field-for-field).

    ``model_policy`` uses the node-level policy union (10 §13.5); nodes
    that need no model (tool_call, approval_gate, ...) leave it None.
    ``timeout_ms`` present => positive (a zero timeout can never elapse
    into anything but instant failure and is a spec error, not a choice).
    """

    id: BoundedStr
    type: GraphNodeType
    role: BoundedStr | None = None
    input_source: list[BoundedStr] = Field(default_factory=list)
    model_policy: NodeModelPolicy | None = None
    skills: list[BoundedStr] = Field(default_factory=list)
    tools: list[BoundedStr] = Field(default_factory=list)
    output_schema: JsonObject | None = None
    retry_policy: RetryPolicySpec | None = None
    timeout_ms: int | None = Field(default=None, ge=1)
    evaluation_policy: BoundedStr | None = None


class GraphEdgeSpec(ContractModel):
    """One graph edge (12 §7 edge schema, field-for-field).

    ``from``/``to`` are Python keywords/builtins-adjacent — carried as
    ``from_node``/``to_node`` with the documented JSON aliases.
    """

    from_node: BoundedStr = Field(alias="from")
    to_node: BoundedStr = Field(alias="to")
    condition: EdgeCondition


class GraphPolicies(ContractModel):
    """Graph-level policies block (12 §3 ``policies``, field-for-field).

    The three ``*_policy`` fields are policy NAMES (12 §3 example:
    "standard", "tool_write_requires_approval") — open identifiers resolved
    by their owning subsystems, not inline policy bodies (recorded).
    """

    timeout_ms: int | None = Field(default=None, ge=1)
    retry_policy: BoundedStr | None = None
    approval_policy: BoundedStr | None = None
    evaluation_policy: BoundedStr | None = None


class ExecutionGraphSpec(ContractModel):
    """The execution graph (12 §3 schema, field-for-field).

    Validation (recorded scope): unique node ids + referential edge
    integrity. NOT enforced: acyclicity — doc 12 never declares a DAG and
    12 §8 agent workflows may revisit stages (module docstring).
    """

    id: BoundedStr
    strategy: ExecutionStrategy
    status: ExecutionStatus | None = None
    nodes: list[GraphNodeSpec] = Field(default_factory=list)
    edges: list[GraphEdgeSpec] = Field(default_factory=list)
    policies: GraphPolicies = Field(default_factory=GraphPolicies)

    @model_validator(mode="after")
    def _nodes_unique_and_edges_resolve(self) -> ExecutionGraphSpec:
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                msg = f"duplicate node id in graph: {node.id!r}"
                raise ValueError(msg)
            seen.add(node.id)
        for edge in self.edges:
            if edge.from_node not in seen:
                msg = f"edge references unknown node: {edge.from_node!r}"
                raise ValueError(msg)
            if edge.to_node not in seen:
                msg = f"edge references unknown node: {edge.to_node!r}"
                raise ValueError(msg)
        return self

    def node(self, node_id: str) -> GraphNodeSpec:
        """Lookup helper; raises ``KeyError`` for unknown ids."""
        for candidate in self.nodes:
            if candidate.id == node_id:
                return candidate
        raise KeyError(node_id)

    def edges_from(self, node_id: str) -> list[GraphEdgeSpec]:
        """Outgoing edges of one node, in declaration order."""
        return [e for e in self.edges if e.from_node == node_id]
