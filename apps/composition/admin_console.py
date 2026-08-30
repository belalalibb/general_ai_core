"""Admin Console composition — AA-2/AA-3 mounting point.

The agent router, the AA-3 seams (NTF-1 notifications, SKL-1 skill-import
review), and the static admin UI are attached HERE, post-hoc, onto the app
returned by ``create_app`` — include_router/mount only.

AA-3 (doc C §5): the notification read-model derives from the SAME injected
stores the tools read (audit/executions/changes — composition-root
agreement duty); the skill-review surface is optional (absent ⇒ its routes
are absent entirely — nothing to probe, 20 §4).
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
from apps.api.notifications import (
    NotificationService,
    NotificationSources,
    create_notifications_router,
)
from apps.api.skills_import import SkillReviewSurface, create_skills_import_router

#: repo_root/ui/admin — the static 7-surface shell (doc D §2).
UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "admin"


def attach_admin_console(
    app: FastAPI,
    *,
    surface: AgentToolSurface,
    auth: AuthSurface,
    ui: bool = True,
    skill_review: SkillReviewSurface | None = None,
) -> AdminAgentService:
    """Mount /v1/agent + AA-3 seams (+ optionally /admin static UI)."""
    registry = build_registry(surface)
    dispatcher = ToolDispatcher(registry, audit=surface.audit)
    service = AdminAgentService(surface, registry, dispatcher)
    resolve = session_resolver(auth)
    app.include_router(create_agent_router(service, registry, resolve=resolve))

    # NTF-1: derive-on-read notifications over the SAME injected records.
    notifications = NotificationService(
        NotificationSources(
            audit=surface.audit,
            executions=surface.execution_store,
            changes=surface.admin.service,
        )
    )
    app.include_router(create_notifications_router(notifications, resolve=resolve))

    # SKL-1: optional seam — absent ⇒ no route exists at all (20 §4).
    if skill_review is not None:
        app.include_router(create_skills_import_router(skill_review, resolve=resolve))

    if ui and UI_DIR.is_dir():
        app.mount("/admin", StaticFiles(directory=str(UI_DIR), html=True), name="admin_ui")
    return service
