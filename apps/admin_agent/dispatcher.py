"""Deterministic tool registry + dispatcher — AA-2 (doc A §3.2/§3.3).

Security model — "model proposes / deterministic code disposes":

- ``ToolRegistry`` is CONFIG DATA. Construction refuses any spec whose
  class is above R1 (``ToolClassNotRegistrable``) and duplicate names
  (``DuplicateTool``). Injection cannot reach an R2 tool: none exists.
- ``ToolDispatcher.dispatch`` NEVER raises for adversarial input. Unknown
  tool names, non-admin callers, and undeclared arguments all become typed
  refusals inside a :class:`ToolCallRecord` — denials are content.
- EVERY dispatch outcome (ok or refused) is appended to the audit log as a
  ``TOOL_CALL`` event when an audit port is bound (doc A §3.2 rule: the
  agent's actions are themselves auditable platform facts).
- Adversarial names are normalized (``[:512]``, empty → ``"<empty>"``)
  before entering BoundedStr-constrained records, so an attacker cannot
  crash the transcript with an oversized or empty name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from apps.admin_agent.contracts import (
    AA2_REGISTRABLE_CLASSES,
    ToolCallRecord,
    ToolClass,
)
from apps.api.app import Principal
from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject

ToolHandler = Callable[[Principal, JsonObject], Awaitable[JsonObject]]


class ToolClassNotRegistrable(Exception):
    """Raised at REGISTRY CONSTRUCTION for any class outside R0/R1."""


class DuplicateTool(Exception):
    """Raised at REGISTRY CONSTRUCTION for a repeated tool name."""


@dataclass(frozen=True)
class ToolSpec:
    """One registered tool — pure configuration data."""

    name: str
    tool_class: ToolClass
    handler: ToolHandler
    allowed_args: frozenset[str] = field(default_factory=frozenset)
    description: str = ""


class ToolRegistry:
    """Closed R0/R1 tool set — refuses unsafe classes at construction."""

    def __init__(self, specs: Iterable[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.tool_class not in AA2_REGISTRABLE_CLASSES:
                msg = (
                    f"tool {spec.name!r} has class {spec.tool_class.value!r}; "
                    "AA-2 registers R0/R1 ONLY"
                )
                raise ToolClassNotRegistrable(msg)
            if spec.name in self._specs:
                raise DuplicateTool(spec.name)
            self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def describe(self) -> list[JsonObject]:
        """Registry as data — what the UI's tools table renders."""
        return [
            {
                "name": spec.name,
                "class": spec.tool_class.value,
                "arguments": sorted(spec.allowed_args),
                "description": spec.description,
            }
            for spec in sorted(self._specs.values(), key=lambda s: s.name)
        ]


class ToolDispatcher:
    """Deterministic admission: registry membership, admin gate, arg check."""

    def __init__(self, registry: ToolRegistry, *, audit: AuditLogPort | None = None) -> None:
        self._registry = registry
        self._audit = audit

    async def dispatch(
        self, caller: Principal, tool_name: str, arguments: JsonObject
    ) -> ToolCallRecord:
        """Admit-or-refuse; NEVER raises for adversarial input."""
        spec = self._registry.get(tool_name)
        if spec is None:
            return self._record(
                caller,
                tool_name,
                ToolClass.R4_FORBIDDEN,
                arguments,
                refusal="tool is not in the registered R0/R1 set",
            )
        if not caller.is_admin:
            return self._record(
                caller,
                tool_name,
                spec.tool_class,
                arguments,
                refusal="admin access required",
            )
        unknown = set(arguments) - spec.allowed_args
        if unknown:
            return self._record(
                caller,
                tool_name,
                spec.tool_class,
                arguments,
                refusal=f"unknown arguments: {sorted(unknown)}",
            )
        result = await spec.handler(caller, arguments)
        return self._record(
            caller, tool_name, spec.tool_class, arguments, result=result
        )

    def _record(
        self,
        caller: Principal,
        tool: str,
        tool_class: ToolClass,
        arguments: JsonObject,
        *,
        result: JsonObject | None = None,
        refusal: str | None = None,
    ) -> ToolCallRecord:
        # Normalize adversarial names for BoundedStr (1..512) fields.
        safe_tool = (tool or "<empty>")[:512]
        safe_refusal = refusal[:512] if refusal is not None else None
        record = ToolCallRecord(
            tool=safe_tool,
            tool_class=tool_class,
            arguments=arguments,
            ok=refusal is None,
            result=result,
            refusal=safe_refusal,
        )
        if self._audit is not None:
            details: JsonObject = {
                "surface": "admin_agent",
                "tool": safe_tool,
                "class": tool_class.value,
                "ok": record.ok,
            }
            if safe_refusal is not None:
                details["refusal"] = safe_refusal
            self._audit.append(
                AuditEvent(
                    tenant_id=caller.tenant_id,
                    event_type=AuditEventType.TOOL_CALL,
                    actor_id=caller.user_id,
                    details=details,
                )
            )
        return record
