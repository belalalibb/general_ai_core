"""Execution service — drives the ProviderAdapter port over RoutingDecisions.

MVP Phase 5 slice 2 (41 §44: "single execution" + "pipeline execution").
Architecture invariant: Router decides; Execution executes (02 §2 #5).
"""

from core.execution.errors import (
    AdapterNotBound,
    CredentialNotConfigured,
    ExecutionServiceError,
    InvalidPipeline,
)
from core.execution.service import (
    PREVIOUS_OUTPUT_KEY,
    AttemptRecord,
    ExecutionReport,
    ExecutionService,
    NodeReport,
    PipelineStage,
)

__all__ = [
    "PREVIOUS_OUTPUT_KEY",
    "AdapterNotBound",
    "AttemptRecord",
    "CredentialNotConfigured",
    "ExecutionReport",
    "ExecutionService",
    "ExecutionServiceError",
    "InvalidPipeline",
    "NodeReport",
    "PipelineStage",
]
