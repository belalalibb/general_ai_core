"""Execution service — drives the ProviderAdapter port over RoutingDecisions.

MVP Phase 5 slice 2 (41 §44: "single execution" + "pipeline execution") +
FINAL Phase 9 additions (41 §12: GraphPlanner, WorkflowRuntimePort).
Architecture invariant: Router decides; Execution executes (02 §2 #5);
the durable Workflow Runtime owns state — Core never builds its own engine.
"""

from core.execution.agent import (
    AgentProposal,
    AgentToolBinding,
    FinalProposal,
    InvalidAgentProposal,
    ToolCallProposal,
    parse_agent_proposal,
)
from core.execution.errors import (
    AdapterNotBound,
    CredentialNotConfigured,
    ExecutionServiceError,
    InvalidPipeline,
)
from core.execution.graph_planner import GraphPlanner
from core.execution.loop import (
    STOP_FINAL,
    STOP_INVALID_PROPOSAL,
    STOP_MAX_STEPS,
    STOP_PROPOSE_FAILED,
    AgentLoop,
    AgentRunReport,
    AgentStep,
)
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
    "STOP_FINAL",
    "STOP_INVALID_PROPOSAL",
    "STOP_MAX_STEPS",
    "STOP_PROPOSE_FAILED",
    "AdapterNotBound",
    "AgentLoop",
    "AgentProposal",
    "AgentRunReport",
    "AgentStep",
    "AgentToolBinding",
    "AttemptRecord",
    "CredentialNotConfigured",
    "ExecutionReport",
    "ExecutionService",
    "ExecutionServiceError",
    "FinalProposal",
    "GraphPlanner",
    "InvalidAgentProposal",
    "InvalidPipeline",
    "NodeReport",
    "PipelineStage",
    "ToolCallProposal",
    "WorkflowRuntimePort",
    "parse_agent_proposal",
]
