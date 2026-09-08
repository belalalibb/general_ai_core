"""R177-FIX-02 — catalog completeness: mounted-but-uncatalogued capabilities get honest rows.

A04 (evidence/r177/A04_composition): the agent runtime, the source-change
workflow, skills import, workspaces/projects and evaluation records are all
served by ``create_app`` / the admin console yet ``GET /v1/admin/capabilities``
never mentioned them. This test pins the deliberate closed-set extension
17 → 22 and the state rule of every new row (same seam variable that mounts
the surface — honesty by construction, apps/api/capabilities.py header).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from apps.api import create_app
from apps.api.agent import AgentSurface
from apps.api.capabilities import CAPABILITY_IDS
from core.execution.service import ExecutionService
from tests.agent.world import AgentWorld
from tests.api.test_admin_api import World, _no_sleep

ROOT = Path(__file__).resolve().parents[2]

NEW_IDS = frozenset(
    {
        "agent.runtime",
        "sourcechange.workflow",
        "skills.import",
        "workspaces.projects",
        "evaluation.records",
    }
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


def _states(app: FastAPI) -> dict[str, str]:
    return {row.id: row.state.value for row in app.state.capability_catalog}


def _app(world: World, **extra: Any) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=world.surface(),
        **extra,
    )


def test_closed_set_is_exactly_twenty_two_and_contains_the_five_new_ids() -> None:
    assert NEW_IDS <= CAPABILITY_IDS, sorted(NEW_IDS - CAPABILITY_IDS)
    assert len(CAPABILITY_IDS) == 22


def test_minimal_admin_composition_states() -> None:
    states = _states(_app(World()))
    # Always mounted by create_app (in-memory defaults; durable when stores bound):
    assert states["workspaces.projects"] == "available"
    # Admin surface exists ⇒ the hermetic R3 workflow and evaluation reads exist:
    assert states["sourcechange.workflow"] == "available"
    assert states["evaluation.records"] == "available"
    # Not composed here ⇒ honestly INERT:
    assert states["agent.runtime"] == "inert"
    assert states["skills.import"] == "inert"


def test_route_payload_lists_the_full_closed_set() -> None:
    response = run(_get(_app(World()), "/v1/admin/capabilities"))
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["capabilities"]}
    assert ids == CAPABILITY_IDS


def test_agent_seam_flips_agent_runtime_to_available() -> None:
    agent_world = AgentWorld([])
    catalog = {"fs": agent_world.read_spec()}
    app = _app(World(), agent=AgentSurface(runtime=agent_world.runtime, catalog=catalog))
    assert _states(app)["agent.runtime"] == "available"
    # The row's evidence points at the route the seam actually mounts.
    row = next(r for r in app.state.capability_catalog if r.id == "agent.runtime")
    assert "/v1/agent-tools" in row.evidence


def test_skills_import_flag_flips_the_row() -> None:
    assert _states(_app(World(), skills_import=True))["skills.import"] == "available"


def test_without_admin_admin_bound_rows_are_inert() -> None:
    world = World()
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    app = create_app(router=world.router, execution_service=service, principal=world.principal)
    states = _states(app)
    assert states["sourcechange.workflow"] == "inert"
    assert states["evaluation.records"] == "inert"
    assert states["workspaces.projects"] == "available"


def test_runtime_profile_declares_skills_import_where_it_attaches_the_review_surface() -> None:
    """apps/composition/runtime.py attaches SkillReviewSurface ⇒ it must tell create_app."""
    source = (ROOT / "apps" / "composition" / "runtime.py").read_text(encoding="utf-8")
    assert "skill_review=SkillReviewSurface(" in source
    assert "skills_import=True," in source
