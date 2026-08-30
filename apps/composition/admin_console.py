"""Admin Console composition — AA-2 mounting point.

apps/api/** is NOT in the AA-2 allowed-files set, so the agent router and
the static admin UI are attached HERE, post-hoc, onto the app returned by
``create_app`` — include_router/mount only, zero edits to apps/api.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.http import create_agent_router, session_resolver
from apps.admin_agent.service import AdminAgentService
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api.auth import AuthSurface

#: repo_root/ui/admin — the static 7-surface shell (doc D §2).
UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "admin"


def attach_admin_console(
    app: FastAPI,
    *,
    surface: AgentToolSurface,
    auth: AuthSurface,
    ui: bool = True,
) -> AdminAgentService:
    """Mount /v1/agent routes (+ optionally /admin static UI) onto ``app``."""
    registry = build_registry(surface)
    dispatcher = ToolDispatcher(registry, audit=surface.audit)
    service = AdminAgentService(surface, registry, dispatcher)
    app.include_router(
        create_agent_router(service, registry, resolve=session_resolver(auth))
    )
    if ui and UI_DIR.is_dir():
        app.mount("/admin", StaticFiles(directory=str(UI_DIR), html=True), name="admin_ui")
    return service
