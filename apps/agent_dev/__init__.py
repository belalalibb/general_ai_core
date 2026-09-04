"""Development-agent composition root (R169).

Separate from ``apps.admin_agent`` by design (INV-7): the admin agent's
registry and permission classes are never widened; new power lives here.
"""

from apps.agent_dev.surface import (
    DEV_ENTITLEMENT,
    DEV_TOOL_NAMES,
    PERM_SOURCE_READ,
    PERM_SOURCE_WRITE,
    DevAgentSurface,
    build_dev_surface,
    dev_tenant_policy,
    source_read_handler,
)

__all__ = [
    "DEV_ENTITLEMENT",
    "DEV_TOOL_NAMES",
    "PERM_SOURCE_READ",
    "PERM_SOURCE_WRITE",
    "DevAgentSurface",
    "build_dev_surface",
    "dev_tenant_policy",
    "source_read_handler",
]
