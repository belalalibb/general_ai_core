"""R168 D-08 — ``ExecuteRequest.project_id`` is admitted, never silently ignored.

Defect (ledger D-08): ``POST /v1/execute`` accepted ANY ``project_id`` — a
foreign tenant's project, an unknown UUID, or ``not-a-uuid`` — and ran the
execution unattached. Contract now: the reference is resolved in the caller's
tenant BEFORE any work; a reference that does not resolve is the ONE 404 body
``GET /v1/projects/{id}`` gives for an unknown id (absent == foreign ==
malformed — 20 §6 anti-enumeration; no oracle between the three). A
caller-owned project passes through unchanged. The field stays.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api.app import Principal, create_app
from apps.api.workspaces import InMemoryProjectStore, InMemoryWorkspaceStore
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry


def _app(principal: Principal, projects: InMemoryProjectStore) -> FastAPI:
    from core.execution.service import ExecutionService
    from core.routing.router import SimpleScoringRouter

    providers, models, bindings = ProviderRegistry(), ModelRegistry(), BindingRegistry()
    return create_app(
        router=SimpleScoringRouter(providers, models, bindings),
        execution_service=ExecutionService(adapters={}, credential_refs={}, bindings=bindings),
        principal=principal,
        workspaces=InMemoryWorkspaceStore(),
        projects=projects,
    )


async def _req(
    app: FastAPI, method: str, path: str, json: dict[str, Any] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        return await c.request(method, path, json=json)


def _two_tenants() -> tuple[FastAPI, FastAPI, str]:
    shared = InMemoryProjectStore()
    owner = _app(Principal(tenant_id=uuid4(), user_id=uuid4()), shared)
    other = _app(Principal(tenant_id=uuid4(), user_id=uuid4()), shared)
    pid = asyncio.run(_req(owner, "POST", "/v1/projects", {"name": "ops"})).json()["project_id"]
    return owner, other, pid


def _unknown_body(app: FastAPI, ref: str) -> tuple[int, bytes]:
    r = asyncio.run(_req(app, "GET", f"/v1/projects/{ref}"))
    return r.status_code, r.content


def test_foreign_project_id_is_the_unknown_404_byte_identical() -> None:
    owner, other, pid = _two_tenants()
    # Reference: what the OTHER tenant sees for this id on the projects surface.
    ref_status, ref_body = _unknown_body(other, pid)
    assert ref_status == 404
    r = asyncio.run(_req(other, "POST", "/v1/execute", {"ask": "Reply OK.", "project_id": pid}))
    assert (r.status_code, r.content) == (404, ref_body)


def test_unknown_project_id_is_the_same_404() -> None:
    owner, _, _ = _two_tenants()
    ghost = str(uuid4())
    ref_status, ref_body = _unknown_body(owner, ghost)
    assert ref_status == 404
    r = asyncio.run(_req(owner, "POST", "/v1/execute", {"ask": "Reply OK.", "project_id": ghost}))
    assert (r.status_code, r.content) == (404, ref_body)


def test_malformed_project_id_is_indistinguishable_from_unknown() -> None:
    # No oracle: "not-a-uuid" cannot name a project, so it is UNKNOWN — the
    # same 404 shape (details.project_id echoes the reference as given).
    owner, _, _ = _two_tenants()
    r = asyncio.run(
        _req(owner, "POST", "/v1/execute", {"ask": "Reply OK.", "project_id": "not-a-uuid"})
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["message"] == "Unknown project id."
    assert body["error"]["details"] == {"project_id": "not-a-uuid"}


def test_owned_project_id_passes_admission() -> None:
    owner, _, pid = _two_tenants()
    r = asyncio.run(_req(owner, "POST", "/v1/execute", {"ask": "Reply OK.", "project_id": pid}))
    assert r.status_code != 404, r.text
    # Absent field: unchanged behaviour (nothing to resolve).
    r2 = asyncio.run(_req(owner, "POST", "/v1/execute", {"ask": "Reply OK."}))
    assert r2.status_code == r.status_code
