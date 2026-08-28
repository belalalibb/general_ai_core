"""Tool Fabric (FINAL Phase 14, 41 §17; T-IMPL-063).

Registry (loadable-not-callable: 14 §1 "Tool is never trusted by default",
only ACTIVE tools selectable) + the ToolCallGate — the single mandatory
admission path composing the EXISTING CapabilityFirewall (41 §17 "every
Tool Call passes through the Capability Firewall"), tool status, permission
declaration, device trust for client/hybrid tools (14 §9 "Client tool runs
on server by assumption" forbidden), and the tool's own 14 §4 approval
policy — tightening only. The gate executes nothing: transport/sandboxing
are adapter territory; skills cannot bypass (no skill input exists).
"""

from core.tools.errors import (
    DuplicateToolRegistration,
    ToolFabricError,
    ToolNotRegistered,
    ToolNotSelectable,
)
from core.tools.gate import ToolCallDecision, ToolCallGate
from core.tools.registry import ToolRegistry

__all__ = [
    "DuplicateToolRegistration",
    "ToolCallDecision",
    "ToolCallGate",
    "ToolFabricError",
    "ToolNotRegistered",
    "ToolNotSelectable",
    "ToolRegistry",
]
