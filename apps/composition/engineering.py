"""Composition of the SHARED engineering capability (ADR-0012).

Opt-in by env. Absent/invalid ⇒ absent tools (P2): the platform never fails to
boot over an optional seam. The §14 guard is composition DATA: the platform's
OWN checkout can never be an agent workspace (ADR-0009 §14 unchanged).

Env:
  AGENT_WORKSPACE_ROOT      directory the agent may engineer inside (jailed)
  AGENT_WORKSPACE_REMOTE    git remote name for pushes (default ``origin``)
  AGENT_WORKSPACE_COMMANDS  comma-separated executable allowlist
                            (default ``python3,pytest,ruff``)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from core.audit.ports import AuditLogPort
from core.engineering import (
    DEFAULT_COMMAND_ALLOWLIST,
    AuthorizationLedger,
    CommandPolicy,
    EngineeringBundle,
    WorkspaceFs,
)
from core.engineering.tools import ENGINEERING_READ_PERMISSIONS, ENGINEERING_WRITE_PERMISSIONS
from core.security.firewall import CapabilityFirewall, TenantPolicy
from infrastructure.engineering import GitCli, SubprocessCommandRunner

ENV_WORKSPACE_ROOT = "AGENT_WORKSPACE_ROOT"
ENV_WORKSPACE_REMOTE = "AGENT_WORKSPACE_REMOTE"
ENV_WORKSPACE_COMMANDS = "AGENT_WORKSPACE_COMMANDS"

#: The platform's own checkout (apps/composition/engineering.py → repo root).
PLATFORM_ROOT = Path(__file__).resolve().parents[2]


class WorkspaceRootRefused(ValueError):
    """Raised at composition when AGENT_WORKSPACE_ROOT violates ADR-0009 §14."""


@dataclass(frozen=True)
class EngineeringComposition:
    """What composition hands to the runtime + Admin seam."""

    bundle: EngineeringBundle
    root: Path
    remote: str
    commands: tuple[str, ...]


def workspace_root_refusal(root: Path, platform_root: Path = PLATFORM_ROOT) -> str | None:
    """§14 guard: the workspace may not be, contain, or live inside the platform."""
    resolved = root.resolve()
    platform = platform_root.resolve()
    if resolved == platform:
        return "workspace root is the platform checkout (ADR-0009 §14)"
    if platform in resolved.parents:
        return "workspace root is inside the platform checkout (ADR-0009 §14)"
    if resolved in platform.parents:
        return "workspace root contains the platform checkout (ADR-0009 §14)"
    return None


def _commands(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return DEFAULT_COMMAND_ALLOWLIST
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def build_engineering(
    env: Mapping[str, str], *, audit: AuditLogPort
) -> EngineeringComposition | None:
    """Compose the engineering bundle from env, or None when not configured.

    A §14 violation is NOT forgiven: it raises so the operator sees it at boot.
    """
    raw_root = env.get(ENV_WORKSPACE_ROOT, "").strip()
    if not raw_root:
        return None
    root = Path(raw_root)
    if not root.is_dir():
        return None
    refusal = workspace_root_refusal(root)
    if refusal is not None:
        raise WorkspaceRootRefused(refusal)
    remote = env.get(ENV_WORKSPACE_REMOTE, "").strip() or "origin"
    commands = _commands(env.get(ENV_WORKSPACE_COMMANDS))
    runner = SubprocessCommandRunner()
    workspace = WorkspaceFs(root=root)
    bundle = EngineeringBundle(
        workspace=workspace,
        workspace_label=str(workspace.root),
        command_policy=CommandPolicy(allowlist=commands),
        runner=runner,
        git=GitCli(root=workspace.root, runner=runner, remote_name=remote),
        ledger=AuthorizationLedger(audit),
    )
    return EngineeringComposition(
        bundle=bundle, root=workspace.root, remote=remote, commands=commands
    )


def _merge(current: TenantPolicy, permissions: frozenset[str]) -> TenantPolicy:
    return TenantPolicy(
        granted_permissions=frozenset(current.granted_permissions | permissions),
        granted_entitlements=current.granted_entitlements,
        approval_gated_permissions=current.approval_gated_permissions,
        limited_permissions=current.limited_permissions,
    )


def grant_engineering_reads(firewall: CapabilityFirewall, tenant_id: UUID) -> None:
    """Add the engineering READ permissions to a tenant's existing policy."""
    current = firewall.policy_for(tenant_id)
    if current is None:
        return
    firewall.set_tenant_policy(tenant_id, _merge(current, ENGINEERING_READ_PERMISSIONS))


def grant_engineering_writes(
    firewall: CapabilityFirewall, tenant_id: UUID, permissions: frozenset[str]
) -> frozenset[str]:
    """Admin decision: grant a subset of the engineering WRITE permissions.

    Returns the tenant's resulting granted permission set. Unknown permission
    names are refused (deny-by-default vocabulary).
    """
    unknown = permissions - ENGINEERING_WRITE_PERMISSIONS
    if unknown:
        raise ValueError(f"unknown engineering permissions: {sorted(unknown)}")
    current = firewall.policy_for(tenant_id)
    if current is None:
        raise ValueError("tenant has no policy; admit the tenant first")
    merged = _merge(current, permissions)
    firewall.set_tenant_policy(tenant_id, merged)
    return merged.granted_permissions


__all__ = [
    "ENV_WORKSPACE_COMMANDS",
    "ENV_WORKSPACE_REMOTE",
    "ENV_WORKSPACE_ROOT",
    "PLATFORM_ROOT",
    "EngineeringComposition",
    "WorkspaceRootRefused",
    "build_engineering",
    "grant_engineering_reads",
    "grant_engineering_writes",
    "workspace_root_refusal",
]
