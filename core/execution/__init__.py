"""Execution service — drives the ProviderAdapter port over RoutingDecisions.

MVP Phase 5 slice 2 (41 §44: "single execution" + "pipeline execution") +
FINAL Phase 9 additions (41 §12: GraphPlanner, WorkflowRuntimePort).
Architecture invariant: Router decides; Execution executes (02 §2 #5);
the durable Workflow Runtime owns state — Core never builds its own engine.
"""

from core.execution.errors import (
    AdapterNotBound,
    CredentialNotConfigured,
    ExecutionServiceError,
    InvalidPipeline,
)
from core.execution.graph_planner import GraphPlanner
from core.execution.service import (
    PREVIOUS_OUTPUT_KEY,
    AttemptRecord,
    ExecutionReport,
    ExecutionService,
    NodeReport,
    PipelineStage,
)
from core.execution.workflow_ports import WorkflowRuntimePort

__all__ = [
    "PREVIOUS_OUTPUT_KEY",
    "AdapterNotBound",
    "AttemptRecord",
    "CredentialNotConfigured",
    "ExecutionReport",
    "ExecutionService",
    "ExecutionServiceError",
    "GraphPlanner",
    "InvalidPipeline",
    "NodeReport",
    "PipelineStage",
    "WorkflowRuntimePort",
]
