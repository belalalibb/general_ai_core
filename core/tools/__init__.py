"""Tool Fabric (FINAL Phase 14, 41 §17; T-IMPL-063).

Registry (loadable-not-callable: 14 §1 "Tool is never trusted by default",
only ACTIVE tools selectable) + the ToolCallGate — the single mandatory
admission path composing the EXISTING CapabilityFirewall (41 §17 "every
Tool Call passes through the Capability Firewall"), tool status, permission
declaration, device trust for client/hybrid tools (14 §9 "Client tool runs
on server by assumption" forbidden), and the tool's own 14 §4 approval
policy — tightening only. The gate executes nothing: transport/sandboxing
are adapter territory; skills cannot bypass (no skill input exists).

V3 (roadmap X²-2) adds the ToolExecutor — the SINGLE execution path that
calls the gate itself (no bypass parameter exists), dispatches to handlers
bound at composition, normalizes outcomes as ToolCallRecord data, and
emits the TOOL_CALL audit event + 03 §7 reserve/settle/fail accounting.
"""

from core.tools.errors import (
    DuplicateToolRegistration,
    ToolFabricError,
    ToolHandlerNotBound,
    ToolNotRegistered,
    ToolNotSelectable,
)
from core.tools.executor import ToolCallRecord, ToolExecutor, ToolHandler
from core.tools.gate import ToolCallDecision, ToolCallGate
from core.tools.registry import ToolRegistry

__all__ = [
    "DuplicateToolRegistration",
    "ToolCallDecision",
    "ToolCallGate",
    "ToolCallRecord",
    "ToolExecutor",
    "ToolFabricError",
    "ToolHandler",
    "ToolHandlerNotBound",
    "ToolNotRegistered",
    "ToolNotSelectable",
    "ToolRegistry",
]
