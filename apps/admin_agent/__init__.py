"""Admin Agent (AA-2, doc C §4 AGT-1) — R0/R1 tools + conversation loop."""

from apps.admin_agent.contracts import (
    AA2_REGISTRABLE_CLASSES,
    AgentAnswer,
    AgentClaim,
    Diagnosis,
    DiagnosisTier,
    EvidenceKind,
    EvidenceRef,
    ExecutionTrace,
    ToolCallRecord,
    ToolClass,
)
from apps.admin_agent.dispatcher import (
    DuplicateTool,
    ToolClassNotRegistrable,
    ToolDispatcher,
    ToolRegistry,
    ToolSpec,
)
from apps.admin_agent.http import create_agent_router, session_resolver
from apps.admin_agent.service import AdminAgentService
from apps.admin_agent.tools import AGENT_LABEL_KEY, AgentToolSurface, build_registry

__all__ = [
    "AA2_REGISTRABLE_CLASSES",
    "AGENT_LABEL_KEY",
    "AdminAgentService",
    "AgentAnswer",
    "AgentClaim",
    "AgentToolSurface",
    "Diagnosis",
    "DiagnosisTier",
    "DuplicateTool",
    "EvidenceKind",
    "EvidenceRef",
    "ExecutionTrace",
    "ToolCallRecord",
    "ToolClass",
    "ToolClassNotRegistrable",
    "ToolDispatcher",
    "ToolRegistry",
    "ToolSpec",
    "build_registry",
    "create_agent_router",
    "session_resolver",
]
