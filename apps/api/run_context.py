"""Per-run admitted-caller context for tenant-bearing agent tools (R177-FIX-06).

The agent runtime hands tools ONLY the model's arguments (``ToolHandler``
takes a ``JsonObject``); a tool that must act inside the caller's tenant
(``repo_map``) cannot trust a ``tenant_id`` argument the model wrote. The
composition root (``POST /v1/execute``) binds the ADMITTED caller's tenant
here for the duration of one run; tools read it and refuse when unbound.
Precedent: ``apps.agent_dev.git_tools._CURRENT_MODE`` (contextvars).
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

_CURRENT_TENANT: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "agent_run_tenant", default=None
)


@contextmanager
def bind_run_tenant(tenant_id: UUID) -> Iterator[None]:
    """Bind the ADMITTED caller's tenant for the duration of one agent run."""
    token = _CURRENT_TENANT.set(tenant_id)
    try:
        yield
    finally:
        _CURRENT_TENANT.reset(token)


def current_run_tenant() -> UUID | None:
    """The bound tenant, or ``None`` outside a bound run (tools must refuse)."""
    return _CURRENT_TENANT.get()
