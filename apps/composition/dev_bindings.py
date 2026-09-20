"""Composition of the governed REST-Git engineering path (R193 = P-R192-04).

Opt-in by env, exactly like ``build_engineering`` (ADR-0012): absent ⇒ ``None`` ⇒
the runtime is byte-identical to the IMPL-024 posture (``/v1/dev`` absent, no
REST-git tools in the agent catalog). Present ⇒ the R172 owner items C2/C3/C7/C8
are composed from EXISTING authorities only:

* C2 ``JsonBindingStore(<dir>/bindings.json)``         → the ONE ``RepoBindingRegistry``
* C3 ``JsonRemoteTrustStore(<dir>/remote_trust.json)`` → the ONE ``RemoteTrustRegistry``
* C7 the registry is handed to ``create_app(dev_bindings=…)`` (read-only router)
* C8 ``GitHubRestTransport`` + a per-tenant ``GitToolset`` and the R192
  ``BoundProjectInspector`` are offered to the AgentRuntime as ``AgentToolSpec``s.

Tenancy (operator mandate, R193-DEC-01): NO admin-only path and NO new isolation
model. Every handler reads the ADMITTED caller's tenant from
``apps.api.run_context.current_run_tenant()`` (precedent: ``repo_map``,
R177-FIX-06) and refuses when unbound; inside a run the per-tenant
``GitToolset`` / ``BoundProjectInspector`` enforce
``RepoBindingRegistry.get(tenant_id=)`` → ``RemoteTrustPort`` (BEFORE any
credential) → ``SecretManagerPort.resolve`` (last moment). The state directory is
shared across tenants like every other JSON store here — records carry
``tenant_id``; isolation is enforced at each lookup, never by directory.

Approval is untouched: ``git.commit`` / ``git.publish`` keep ``BEFORE_ACTION`` from
``GitToolset`` and are therefore REFUSED inside the agent loop (no self-approval).

Env:
  AGENT_DEV_STATE_DIR   directory for ``bindings.json`` / ``remote_trust.json``;
                        refused when it is / contains / lives inside the platform
                        checkout (ADR-0009 §14).
  AGENT_DEV_GITHUB_API  optional GitHub API base URL (default api.github.com).

Trust is GRANTED only by an explicit operator act on the trust store (accepted in
the R193 proposal); no grant endpoint exists (would be a SHAPE change).
Durable per-tenant credential custody is NOT claimed: ``secrets`` is whatever the
composition root already binds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from apps.agent_dev.git_tools import (
    GIT_TOOL_NAMES,
    PERM_GIT_COMMIT,
    PERM_GIT_FETCH,
    PERM_GIT_PUBLISH,
    PERM_GIT_STATUS,
    BindingLookupRefused,
    GitToolset,
    RepoBindingRegistry,
)
from apps.agent_dev.github_transport import GITHUB_API_BASE, GitHubRestTransport
from apps.agent_dev.project_inspector import BoundProjectInspector, GitHubProjectInspector
from apps.api.run_context import current_run_tenant
from apps.composition.engineering import PLATFORM_ROOT, workspace_root_refusal
from core.agent.runtime import AgentToolSpec
from core.contracts.base import JsonObject
from core.contracts.tools import ApprovalRequirement, Tool, ToolLocation, ToolStatus
from core.secrets.ports import SecretManagerPort
from core.tools.binding_store import JsonBindingStore
from core.tools.registry import ToolRegistry
from core.tools.remote_trust import JsonRemoteTrustStore, RemoteTrustRegistry

ENV_DEV_STATE_DIR = "AGENT_DEV_STATE_DIR"
ENV_DEV_GITHUB_API = "AGENT_DEV_GITHUB_API"
BINDINGS_FILE = "bindings.json"
TRUST_FILE = "remote_trust.json"

PERM_PROJECT_INSPECT = "project.inspect"
DEV_TOOL_VERSION = "r193.1"
DEV_RESOURCE = "repo_binding"
DEV_ENTITLEMENT = "agent.tools"  # the SAME entitlement the agent catalog already uses

Handler = Callable[[JsonObject], Awaitable[JsonObject]]


class DevStateDirRefused(ValueError):
    """Raised at composition when AGENT_DEV_STATE_DIR violates ADR-0009 §14."""


@dataclass(frozen=True)
class DevBindingsComposition:
    """What composition hands to the runtime: registries + tenant-bound tool specs."""

    state_dir: Path
    bindings: RepoBindingRegistry
    trust: RemoteTrustRegistry
    tool_specs: tuple[AgentToolSpec, ...]
    toolset_for: Callable[[UUID], GitToolset]
    inspector_for: Callable[[UUID], BoundProjectInspector]


def state_dir_refusal(state_dir: Path, platform_root: Path = PLATFORM_ROOT) -> str | None:
    """§14 guard reused verbatim from the workspace composition."""
    reason = workspace_root_refusal(state_dir, platform_root)
    return None if reason is None else reason.replace("workspace root", "dev state dir")


def _tool(name: str, approval: ApprovalRequirement) -> Tool:
    return Tool(
        id=uuid4(),
        name=name,
        version=DEV_TOOL_VERSION,
        location=ToolLocation.SERVER,
        permissions=[name],
        approval_policy={name: approval},
        status=ToolStatus.ACTIVE,
    )


def _require_run_tenant(tool_name: str) -> UUID:
    tenant_id = current_run_tenant()
    if tenant_id is None:
        raise ValueError(f"{tool_name}: no admitted tenant bound for this run")
    return tenant_id


def build_dev_bindings(
    env: Mapping[str, str],
    *,
    secrets: SecretManagerPort,
    transport: httpx.AsyncBaseTransport | None = None,
    tool_registry: ToolRegistry | None = None,
    outside_of: tuple[Path, ...] = (),
) -> DevBindingsComposition | None:
    """Compose the governed REST-Git path from env, or ``None`` when not configured.

    A §14 violation is NOT forgiven: it raises so the operator sees it at boot.
    ``transport`` is injectable for hermetic tests (``httpx.MockTransport``).
    """
    raw = env.get(ENV_DEV_STATE_DIR, "").strip()
    if not raw:
        return None
    state_dir = Path(raw)
    refusal = state_dir_refusal(state_dir)
    if refusal is not None:
        raise DevStateDirRefused(f"{refusal} (ADR-0009 §14)")
    state_dir.mkdir(parents=True, exist_ok=True)

    bindings = RepoBindingRegistry(
        store=JsonBindingStore(state_dir / BINDINGS_FILE, outside_of=outside_of)
    )
    trust = RemoteTrustRegistry(
        store=JsonRemoteTrustStore(state_dir / TRUST_FILE, outside_of=outside_of)
    )
    base_url = env.get(ENV_DEV_GITHUB_API, "").strip() or GITHUB_API_BASE
    git_transport = GitHubRestTransport(base_url=base_url, transport=transport)
    inspector = GitHubProjectInspector(base_url=base_url, transport=transport)

    def toolset_for(tenant_id: UUID) -> GitToolset:
        return GitToolset(
            tenant_id=tenant_id,
            bindings=bindings,
            transport=git_transport,
            secrets=secrets,
            trust=trust,
        )

    def inspector_for(tenant_id: UUID) -> BoundProjectInspector:
        return BoundProjectInspector(
            inspector, tenant_id=tenant_id, bindings=bindings, trust=trust, secrets=secrets
        )

    registry = tool_registry if tool_registry is not None else ToolRegistry()
    specs = _tool_specs(registry, toolset_for=toolset_for, inspector_for=inspector_for)
    return DevBindingsComposition(
        state_dir=state_dir,
        bindings=bindings,
        trust=trust,
        tool_specs=specs,
        toolset_for=toolset_for,
        inspector_for=inspector_for,
    )


_GIT_APPROVAL: dict[str, ApprovalRequirement] = {
    PERM_GIT_FETCH: ApprovalRequirement.NONE,
    PERM_GIT_STATUS: ApprovalRequirement.NONE,
    PERM_GIT_COMMIT: ApprovalRequirement.BEFORE_ACTION,
    PERM_GIT_PUBLISH: ApprovalRequirement.BEFORE_ACTION,
}
_GIT_DESCRIPTIONS: dict[str, str] = {
    PERM_GIT_FETCH: "Read the remote head of ONE bound repository (binding_id) in the caller's tenant.",
    PERM_GIT_STATUS: "Describe the staged snapshot of ONE bound repository (binding_id).",
    PERM_GIT_COMMIT: "Stage a commit for ONE bound repository — approval required BEFORE action.",
    PERM_GIT_PUBLISH: (
        "Publish the staged commit (allowed publish modes) — approval required BEFORE action."
    ),
}


def _git_handler(name: str, toolset_for: Callable[[UUID], GitToolset]) -> Handler:
    async def handler(arguments: JsonObject) -> JsonObject:
        tenant_id = _require_run_tenant(name)
        toolset = toolset_for(tenant_id)
        by_name: dict[str, Handler] = {
            PERM_GIT_FETCH: toolset.fetch,
            PERM_GIT_STATUS: toolset.status,
            PERM_GIT_COMMIT: toolset.commit,
            PERM_GIT_PUBLISH: toolset.publish,
        }
        return await by_name[name](arguments)

    return handler


def _inspect_handler(inspector_for: Callable[[UUID], BoundProjectInspector]) -> Handler:
    async def inspect(arguments: JsonObject) -> JsonObject:
        tenant_id = _require_run_tenant(PERM_PROJECT_INSPECT)
        raw = arguments.get("binding_id")
        try:
            binding_id = UUID(str(raw))
        except ValueError:
            raise ValueError(f"{PERM_PROJECT_INSPECT}: binding_id must be a UUID") from None
        try:
            inventory = inspector_for(tenant_id).inspect_binding(binding_id)
        except BindingLookupRefused as exc:
            raise ValueError(
                f"{PERM_PROJECT_INSPECT}: refused {exc.code.value}: {exc.reason}"
            ) from exc
        return inventory.model_dump(mode="json")

    return inspect


def _tool_specs(
    registry: ToolRegistry,
    *,
    toolset_for: Callable[[UUID], GitToolset],
    inspector_for: Callable[[UUID], BoundProjectInspector],
) -> tuple[AgentToolSpec, ...]:
    """Tenant-bound ``AgentToolSpec``s over the EXISTING GitToolset + BoundProjectInspector."""
    specs: list[AgentToolSpec] = []
    args = {"binding_id": "string (UUID of a RepoBinding in the caller's tenant)"}
    for name in GIT_TOOL_NAMES:
        approval = _GIT_APPROVAL[name]
        tool = _tool(name, approval)
        registry.register(tool)
        specs.append(
            AgentToolSpec(
                tool=tool,
                handler=_git_handler(name, toolset_for),
                permission=name,
                resource=DEV_RESOURCE,
                entitlement=DEV_ENTITLEMENT,
                description=_GIT_DESCRIPTIONS[name],
                arguments=dict(args),
                risk_level="high" if approval is not ApprovalRequirement.NONE else "low",
            )
        )
    tool = _tool(PERM_PROJECT_INSPECT, ApprovalRequirement.NONE)
    registry.register(tool)
    specs.append(
        AgentToolSpec(
            tool=tool,
            handler=_inspect_handler(inspector_for),
            permission=PERM_PROJECT_INSPECT,
            resource=DEV_RESOURCE,
            entitlement=DEV_ENTITLEMENT,
            description=(
                "Read-only inventory of ONE bound repository (binding_id): head sha, paths, "
                "languages, manifests. Trust is checked before any credential is touched."
            ),
            arguments=dict(args),
        )
    )
    return tuple(specs)


__all__ = [
    "BINDINGS_FILE",
    "DEV_ENTITLEMENT",
    "DEV_RESOURCE",
    "ENV_DEV_GITHUB_API",
    "ENV_DEV_STATE_DIR",
    "PERM_PROJECT_INSPECT",
    "TRUST_FILE",
    "DevBindingsComposition",
    "DevStateDirRefused",
    "build_dev_bindings",
    "state_dir_refusal",
]
