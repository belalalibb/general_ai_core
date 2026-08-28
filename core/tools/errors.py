"""Tool fabric errors (closed, minimal set — T-IMPL-063).

Same explainable-denial posture as core/roles and core/skills (11 §14):
every refusal names the violated rule, never a silent skip. The 14 §9
forbidden list binds here: "Tool executes without Capability Firewall." /
"Client tool runs on server by assumption."
"""

from __future__ import annotations


class ToolFabricError(Exception):
    """Base class for tool registry / call-gate failures."""


class ToolNotRegistered(ToolFabricError):
    """No tool with this id in the registry (deny-by-default)."""

    def __init__(self, tool_id: object) -> None:
        super().__init__(f"tool not registered: {tool_id}")


class DuplicateToolRegistration(ToolFabricError):
    """A tool with this id is already registered (never overwritten)."""

    def __init__(self, tool_id: object) -> None:
        super().__init__(f"tool already registered: {tool_id}")


class ToolNotSelectable(ToolFabricError):
    """The tool exists but is not selectable (status != active).

    Loadable-but-not-selectable posture (31 §10 mirror, same as roles and
    skills): a disabled tool is inspectable data, never a callable surface.
    """

    def __init__(self, tool_id: object, status: str) -> None:
        self.status = status
        super().__init__(f"tool not selectable: {tool_id} (status={status})")
