"""Tool registry — Phase 14 Tool Fabric (T-IMPL-063).

Spec anchors:

- 03 §6 Tool entity (the registered records ARE the contracts) + 03 §8
  (verbatim): "Tool calls require Capability Firewall approval." — the
  registry exposes tool DATA only; call admission lives in the gate.
- 14 §1 (verbatim): "Tool is never trusted by default." — encoded in the
  DATA default (ToolStatus.DISABLED on the contract) and in selection
  (only ACTIVE tools are selectable).
- 31 §10 posture mirrored (same as RoleRegistry/SkillRegistry): the
  registry may LOAD disabled tools for inspection, but selection admits
  ONLY status=active — loadable-not-callable, denial with a NAMED reason
  (11 §14).

Recorded derivations: no doc defines a tool-registry interface — the shape
mirrors the EXISTING RoleRegistry/SkillRegistry (register/get/select/
list_selectable/list_all) so every registered capability domain answers
inspection and admission the same way. In-memory and hermetic; durable
persistence binds through infrastructure/ (ADR-0002) later.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.tools import Tool, ToolStatus
from core.tools.errors import (
    DuplicateToolRegistration,
    ToolNotRegistered,
    ToolNotSelectable,
)


class ToolRegistry:
    """Tool registry: load anything valid, select only active (14 §1)."""

    def __init__(self) -> None:
        self._tools: dict[UUID, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Duplicate ids are rejected, never overwritten."""
        if tool.id in self._tools:
            raise DuplicateToolRegistration(tool.id)
        self._tools[tool.id] = tool

    def get(self, tool_id: UUID) -> Tool:
        """Inspection: return the registered tool regardless of status."""
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotRegistered(tool_id)
        return tool

    def replace(self, tool: Tool) -> None:
        """Explicit re-registration (admin update path, 21 §4 Tools row).

        Mirrors ``ModelRegistry.replace`` (T-IMPL-068): the admin control
        plane publishes status changes (enable/disable) by replacing the
        stored frozen record — the tool call gate sees the change
        immediately through ``select``; no parallel admin copy. Unknown
        ids refuse loudly.
        """
        if tool.id not in self._tools:
            raise ToolNotRegistered(tool.id)
        self._tools[tool.id] = tool

    def select(self, tool_id: UUID) -> Tool:
        """Admission: return the tool ONLY if selectable (active).

        A disabled tool denies with a named reason; unknown ids raise
        ToolNotRegistered — absent and not-selectable stay DIFFERENT
        answers, both explainable (same rule as roles/skills).
        """
        tool = self.get(tool_id)
        if tool.status is not ToolStatus.ACTIVE:
            raise ToolNotSelectable(tool_id, tool.status.value)
        return tool

    def list_selectable(self) -> list[Tool]:
        """All tools that would pass :meth:`select`, name-ordered."""
        return sorted(
            (t for t in self._tools.values() if t.status is ToolStatus.ACTIVE),
            key=lambda t: t.name,
        )

    def list_all(self) -> list[Tool]:
        """Inspection view: every registered tool, name-ordered."""
        return sorted(self._tools.values(), key=lambda t: t.name)
