"""Composition of the SHARED agent surface (R160).

Builds — ONCE per process — the core authority chain every agent consumer
shares (``ToolRegistry`` → ``CapabilityFirewall`` → ``DeviceRegistry``), the
``AgentRuntime`` over the SAME router / execution service / audit / usage the
rest of the platform already uses, and the deployment's offered tool catalog.

Catalog posture (20 §4, deny-by-default):

- Tools are composition DATA: the catalog names what this deployment is
  *able* to offer. A tenant may still be refused per call by the firewall.
- The only tools composed today are the READ-ONLY source-inspection tools
  over the jailed ``SourceReader`` (mandate §9) — present only when
  ``AGENT_SOURCE_ROOT`` names a directory; absent ⇒ empty catalog (an agent
  run is then a pure-answer run; ``strategy=agent`` still works).
- Tenant grants: ``grant_agent_tenant`` installs the read-only policy for a
  tenant. The runtime calls it for the demo principal and on first tenant
  appearance (register/login/session) — the SAME first-appearance seam the
  budget grant already uses (``BudgetGrantingIdentity``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from apps.api.agent import AgentSurface
from apps.api.store import ExecutionStorePort
from core.agent import (
    DEFAULT_AGENT_DEADLINE_MS,
    DEFAULT_AGENT_MAX_STEPS,
    AgentRuntime,
    AgentToolSpec,
)
from core.audit.ports import AuditLogPort
from core.contracts.base import JsonObject
from core.contracts.tools import Tool
from core.engineering import EngineeringBundle, engineering_tool_specs
from core.execution.service import ExecutionService
from core.identity.devices import DeviceRegistry
from core.routing.router import SimpleScoringRouter
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.tools.registry import ToolRegistry
from core.tools.source_reader import SourceReader, SourceReadRefused
from core.usage.ports import UsageAccountingPort

#: Permission + entitlement vocabulary for the composed read-only tools.
SOURCE_READ_PERMISSION = "source.read"
AGENT_TOOLS_ENTITLEMENT = "agent.tools"
SOURCE_RESOURCE = "source:root"

#: The read-only tenant policy every admitted tenant receives (composition
#: DATA — a stricter/broader policy is an admin decision, not a code path).
READ_ONLY_AGENT_POLICY = TenantPolicy(
    granted_permissions=frozenset({SOURCE_READ_PERMISSION}),
    granted_entitlements=frozenset({AGENT_TOOLS_ENTITLEMENT}),
)


@dataclass(frozen=True)
class ComposedAgent:
    """Everything the runtime needs to hand out: surface + shared authority."""

    surface: AgentSurface
    tool_registry: ToolRegistry
    firewall: CapabilityFirewall
    devices: DeviceRegistry


def grant_agent_tenant(firewall: CapabilityFirewall, tenant_id: UUID) -> None:
    """Install the read-only agent policy for one tenant (idempotent)."""
    firewall.set_tenant_policy(tenant_id, READ_ONLY_AGENT_POLICY)


def _source_tool(name: str) -> Tool:
    return Tool.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "location": "server",
            "permissions": [SOURCE_READ_PERMISSION],
            "approval_policy": {SOURCE_READ_PERMISSION: "none"},
            "status": "active",
        }
    )


def _refusal_as_error(
    call: Callable[[JsonObject], dict[str, object]],
) -> Callable[[JsonObject], object]:
    async def handler(arguments: JsonObject) -> JsonObject:
        try:
            return dict(call(arguments))
        except SourceReadRefused as exc:
            # Typed refusal → raised so the executor records status=failed
            # with the reason as data (never swallowed, never re-raised up).
            raise ValueError(f"source read refused: {exc}") from exc

    return handler


def source_tool_specs(reader: SourceReader, registry: ToolRegistry) -> list[AgentToolSpec]:
    """The three read-only source tools as AgentToolSpecs (registered)."""

    def _read(args: JsonObject) -> dict[str, object]:
        return reader.read_file(str(args.get("path", "")))

    def _list(args: JsonObject) -> dict[str, object]:
        return reader.list_files(str(args.get("path", "")), str(args.get("glob", "**/*")))

    def _search(args: JsonObject) -> dict[str, object]:
        return reader.search(
            str(args.get("text", "")),
            str(args.get("path", "")),
            str(args.get("glob", "**/*.py")),
        )

    entries: list[tuple[str, str, JsonObject, Callable[[JsonObject], dict[str, object]]]] = [
        (
            "source_read",
            "Read one file (byte-capped) from the jailed source root.",
            {"path": "string (relative path)"},
            _read,
        ),
        (
            "source_list",
            "List files under a relative path matching a glob (entry-capped).",
            {"path": "string (relative dir, optional)", "glob": "string (default **/*)"},
            _list,
        ),
        (
            "source_search",
            "Literal substring search across files (match-capped).",
            {
                "text": "string (non-empty)",
                "path": "string (relative dir, optional)",
                "glob": "string (default **/*.py)",
            },
            _search,
        ),
    ]
    specs: list[AgentToolSpec] = []
    for name, description, arguments, call in entries:
        tool = _source_tool(name)
        registry.register(tool)
        specs.append(
            AgentToolSpec(
                tool=tool,
                handler=_refusal_as_error(call),  # type: ignore[arg-type]
                permission=SOURCE_READ_PERMISSION,
                resource=SOURCE_RESOURCE,
                entitlement=AGENT_TOOLS_ENTITLEMENT,
                description=description,
                arguments=arguments,
            )
        )
    return specs


def build_agent(
    *,
    router: SimpleScoringRouter,
    execution_service: ExecutionService,
    store: ExecutionStorePort,
    audit: AuditLogPort,
    usage: UsageAccountingPort,
    repo_reader: SourceReader | None,
    engineering: EngineeringBundle | None = None,
    max_steps: int = DEFAULT_AGENT_MAX_STEPS,
    deadline_ms: int | None = DEFAULT_AGENT_DEADLINE_MS,
) -> ComposedAgent:
    """Compose the shared agent authority chain + runtime + catalog.

    ``engineering`` (ADR-0012) adds the 17 workspace/command/git tools to the
    SAME registry and catalog; absent ⇒ absent tools (P2).

    ``max_steps`` / ``deadline_ms`` (R165) are the OPERATOR's per-run caps for
    this runtime (``AgentRuntime`` enforces the hard cap of 32); a request may
    only ask for less. Engineering turns (inspect → change → test → diagnose →
    fix → verify → git) need more than the 8-step default.
    """
    tool_registry = ToolRegistry()
    firewall = CapabilityFirewall()
    devices = DeviceRegistry()
    runtime = AgentRuntime(
        router=router,
        execution_service=execution_service,
        tool_registry=tool_registry,
        firewall=firewall,
        devices=devices,
        audit=audit,
        usage=usage,
        store_report=store.put,
        max_steps=max_steps,
        deadline_ms=deadline_ms,
    )
    catalog: dict[str, AgentToolSpec] = {}
    if repo_reader is not None:
        for spec in source_tool_specs(repo_reader, tool_registry):
            catalog[spec.name] = spec
    if engineering is not None:
        for spec in engineering_tool_specs(engineering, tool_registry):
            catalog[spec.name] = spec
    return ComposedAgent(
        surface=AgentSurface(runtime=runtime, catalog=catalog),
        tool_registry=tool_registry,
        firewall=firewall,
        devices=devices,
    )
