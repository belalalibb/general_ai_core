"""Hermetic world for the SHARED AgentRuntime.

A REAL routing + execution path (scripted provider adapter), the REAL core
ToolRegistry / CapabilityFirewall / ToolCallGate / ToolExecutor, and an
in-memory execution store. The only doubles are the provider (scripted
model outputs) and tool handlers. Reused by the runtime, HTTP, admin-agent
and coding-benchmark test modules so every consumer is exercised on the
SAME composition.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

from core.agent import AgentRuntime, AgentToolSpec
from core.audit.memory import InMemoryAuditLog
from core.contracts.base import JsonObject
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.tools import Tool
from core.execution.service import ExecutionReport, ExecutionService
from core.identity.devices import DeviceRegistry
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.tools.registry import ToolRegistry
from core.usage.memory import InMemoryUsageAccounting
from tests.execution.test_multi_model import ScriptedAdapter, _manifest

TENANT = uuid4()
USER = uuid4()
OTHER_TENANT = uuid4()

PERM_READ = "fs.read"
PERM_WRITE = "fs.write"
ENTITLEMENT = "agent.tools"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(_: float) -> None:
    return None


def model_says(proposal: JsonObject) -> JsonObject:
    """A scripted provider output carrying ONE agent proposal as content."""
    return {"content": json.dumps(proposal)}


def tool_call(tool: str, **arguments: object) -> JsonObject:
    return {"action": "tool_call", "tool": tool, "arguments": dict(arguments)}


def final(answer: str, *evidence: int) -> JsonObject:
    return {"action": "final", "output": {"answer": answer, "evidence": list(evidence)}}


class FakeFs:
    """Tool handler double: a tiny in-memory file system."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = dict(files or {})
        self.reads: list[str] = []
        self.writes: list[tuple[str, str]] = []

    async def read(self, arguments: JsonObject) -> JsonObject:
        path = str(arguments.get("path", ""))
        self.reads.append(path)
        if path not in self.files:
            msg = f"no such file: {path}"
            raise FileNotFoundError(msg)
        return {"path": path, "content": self.files[path]}

    async def write(self, arguments: JsonObject) -> JsonObject:
        path = str(arguments.get("path", ""))
        content = str(arguments.get("content", ""))
        self.files[path] = content
        self.writes.append((path, content))
        return {"path": path, "bytes": len(content)}


def make_tool(name: str, permissions: list[str]) -> Tool:
    return Tool.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "location": "server",
            "permissions": permissions,
            "approval_policy": {p: "none" for p in permissions},
            "status": "active",
        }
    )


class AgentWorld:
    """One composed platform slice: model script + real seams + store."""

    def __init__(
        self,
        script: list[object] | None = None,
        *,
        grant: bool = True,
        budget_units: float = 100.0,
        max_steps: int = 8,
        deadline_ms: int | None = 60_000,
    ) -> None:
        # --- routing + execution (the propose seam) ----------------------------
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapter = ScriptedAdapter(script)
        provider = Provider(
            id=uuid4(),
            provider_key="prov_agent",
            display_name="prov_agent",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(provider, _manifest("prov_agent"))
        model = Model(
            id=uuid4(),
            model_key="model-agent",
            display_name="model-agent",
            tier=ModelTier.MEDIUM,
            modalities=["text"],
            capabilities=[],
            status=ModelStatus.ACTIVE,
        )
        self.models.register(model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name="vendor/model-agent",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.usage = InMemoryUsageAccounting()
        self.usage.configure_tenant(TENANT, plan="test", task_units_limit=budget_units)
        self.execution_service = ExecutionService(
            adapters={provider.id: self.adapter},
            credential_refs={provider.id: "secret-ref://agent"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            usage=self.usage,
            sleeper=_no_sleep,
        )
        # --- the ONE tool authority chain ------------------------------------------
        self.tool_registry = ToolRegistry()
        self.firewall = CapabilityFirewall()
        if grant:
            self.firewall.set_tenant_policy(
                TENANT,
                TenantPolicy(
                    granted_permissions=frozenset({PERM_READ}),  # write NOT granted
                    granted_entitlements=frozenset({ENTITLEMENT}),
                ),
            )
        self.devices = DeviceRegistry()
        self.audit = InMemoryAuditLog()
        self.fs = FakeFs({"README.md": "hello", "src/app.py": "def f():\n    return 1\n"})
        self.fs_tool = make_tool("fs", [PERM_READ, PERM_WRITE])
        self.tool_registry.register(self.fs_tool)
        self.stored: list[ExecutionReport] = []
        self.runtime = AgentRuntime(
            router=self.router,
            execution_service=self.execution_service,
            tool_registry=self.tool_registry,
            firewall=self.firewall,
            devices=self.devices,
            audit=self.audit,
            usage=self.usage,
            store_report=self.stored.append,
            max_steps=max_steps,
            deadline_ms=deadline_ms,
        )

    # -- tool specs ---------------------------------------------------------------

    def read_spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            tool=self.fs_tool,
            handler=self.fs.read,
            permission=PERM_READ,
            resource="fs:workspace",
            entitlement=ENTITLEMENT,
            description="Read a file from the workspace.",
            arguments={"path": "string"},
        )

    def write_spec(self) -> AgentToolSpec:
        # A SECOND Tool record with its own name (registry keyed by id; the
        # runtime keys bindings by name). Its permission is NOT granted.
        write_tool = make_tool("fs_write", [PERM_WRITE])
        self.tool_registry.register(write_tool)
        return AgentToolSpec(
            tool=write_tool,
            handler=self.fs.write,
            permission=PERM_WRITE,
            resource="fs:workspace",
            entitlement=ENTITLEMENT,
            description="Write a file to the workspace.",
            arguments={"path": "string", "content": "string"},
            risk_level="medium",
        )

    # -- run ----------------------------------------------------------------------

    def run(
        self,
        task: JsonObject,
        *,
        tools: list[AgentToolSpec] | None = None,
        tenant_id: UUID = TENANT,
        **kwargs: Any,
    ) -> Any:
        return run(
            self.runtime.run(
                tenant_id=tenant_id,
                user_id=USER,
                task=task,
                tools=tools if tools is not None else [self.read_spec()],
                **kwargs,
            )
        )
