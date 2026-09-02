"""/v1/workspaces + /v1/projects — closure GAP 1 (operator-verified).

Contract authority: core/contracts/identity.py (Workspace/Project are
the EXISTING 03 §2 entities — field-for-field), 20 §6 (tenant scoping +
anti-enumeration: absent and foreign-tenant ids are indistinguishable),
10 §9 (closed error-code set: unknown resource = validation_error body
with HTTP 404 — the recorded apps/api/errors.py mapping), migration
0002 (projects.workspace_id FK ondelete=RESTRICT → delete-with-projects
refuses with 409, never a cascade).

Scope truth: create/get/list/delete only. NO update route exists
because no doc defines one (absent, not fabricated — WBH-1 posture).
ids are server-generated; tenant_id never appears in bodies (server
assigns from the session) and never echoes in responses.

Hermetic: ASGI transport, in-memory stores, no sockets, no DB.
Tenant isolation is tested by TWO apps (different principals) sharing
the SAME store instances — exactly the durable topology in miniature.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api.app import Principal, create_app
from apps.api.workspaces import InMemoryProjectStore, InMemoryWorkspaceStore
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def make_app(
    *,
    principal: Principal | None = None,
    workspaces: InMemoryWorkspaceStore | None = None,
    projects: InMemoryProjectStore | None = None,
) -> FastAPI:
    from core.execution.service import ExecutionService
    from core.routing.router import SimpleScoringRouter

    providers = ProviderRegistry()
    models = ModelRegistry()
    bindings = BindingRegistry()
    return create_app(
        router=SimpleScoringRouter(providers, models, bindings),
        execution_service=ExecutionService(adapters={}, credential_refs={}, bindings=bindings),
        principal=principal or Principal(tenant_id=uuid4(), user_id=uuid4()),
        workspaces=workspaces,
        projects=projects,
    )


async def _request(
    app: FastAPI, method: str, path: str, json: dict[str, Any] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.request(method, path, json=json)


class TestWorkspaceLifecycle:
    def test_create_returns_201_with_server_generated_uuid(self) -> None:
        app = make_app()
        r = run(_request(app, "POST", "/v1/workspaces", {"name": "Research"}))
        assert r.status_code == 201
        body = r.json()
        # Closed response shape; tenant_id NEVER echoes (20 §6).
        assert set(body.keys()) == {"workspace_id", "name"}
        assert body["name"] == "Research"
        UUID(body["workspace_id"])  # server-generated, well-formed

    def test_get_roundtrip(self) -> None:
        app = make_app()
        created = run(_request(app, "POST", "/v1/workspaces", {"name": "Ops"})).json()
        r = run(_request(app, "GET", f"/v1/workspaces/{created['workspace_id']}"))
        assert r.status_code == 200
        assert r.json() == created

    def test_list_is_name_ordered(self) -> None:
        app = make_app()
        for name in ("zeta", "alpha", "mid"):
            assert (run(_request(app, "POST", "/v1/workspaces", {"name": name}))).status_code == 201
        r = run(_request(app, "GET", "/v1/workspaces"))
        assert r.status_code == 200
        names = [w["name"] for w in r.json()["workspaces"]]
        assert names == ["alpha", "mid", "zeta"]

    def test_delete_returns_204_then_404(self) -> None:
        app = make_app()
        wid = run(_request(app, "POST", "/v1/workspaces", {"name": "gone"})).json()["workspace_id"]
        assert run(_request(app, "DELETE", f"/v1/workspaces/{wid}")).status_code == 204
        after = run(_request(app, "GET", f"/v1/workspaces/{wid}"))
        assert after.status_code == 404
        assert after.json()["error"]["code"] == "validation_error"

    def test_unknown_id_is_validation_error_404(self) -> None:
        app = make_app()
        r = run(_request(app, "GET", f"/v1/workspaces/{uuid4()}"))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "validation_error"

    def test_malformed_uuid_is_422_validation_error(self) -> None:
        app = make_app()
        r = run(_request(app, "GET", "/v1/workspaces/not-a-uuid"))
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_extra_body_field_rejected(self) -> None:
        # Closed shape (extra=forbid): tenant_id in a body is NOT an input.
        app = make_app()
        r = run(
            _request(
                app,
                "POST",
                "/v1/workspaces",
                {"name": "x", "tenant_id": str(uuid4())},
            )
        )
        assert r.status_code == 422

    def test_empty_name_rejected(self) -> None:
        app = make_app()
        r = run(_request(app, "POST", "/v1/workspaces", {"name": ""}))
        assert r.status_code == 422


class TestProjectLifecycle:
    def test_create_standalone_project(self) -> None:
        app = make_app()
        r = run(_request(app, "POST", "/v1/projects", {"name": "P1", "metadata": {"k": "v"}}))
        assert r.status_code == 201
        body = r.json()
        assert set(body.keys()) == {"project_id", "workspace_id", "name", "metadata"}
        assert body["workspace_id"] is None
        assert body["metadata"] == {"k": "v"}

    def test_create_project_linked_to_workspace(self) -> None:
        app = make_app()
        wid = run(_request(app, "POST", "/v1/workspaces", {"name": "W"})).json()["workspace_id"]
        r = run(_request(app, "POST", "/v1/projects", {"name": "P", "workspace_id": wid}))
        assert r.status_code == 201
        assert r.json()["workspace_id"] == wid

    def test_link_to_unknown_workspace_is_404(self) -> None:
        # Referential admission in the caller's tenant (20 §6).
        app = make_app()
        r = run(
            _request(
                app,
                "POST",
                "/v1/projects",
                {"name": "P", "workspace_id": str(uuid4())},
            )
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "validation_error"

    def test_list_filter_by_workspace(self) -> None:
        app = make_app()
        wid = run(_request(app, "POST", "/v1/workspaces", {"name": "W"})).json()["workspace_id"]
        run(_request(app, "POST", "/v1/projects", {"name": "in", "workspace_id": wid}))
        run(_request(app, "POST", "/v1/projects", {"name": "out"}))
        r = run(_request(app, "GET", f"/v1/projects?workspace_id={wid}"))
        assert [p["name"] for p in r.json()["projects"]] == ["in"]
        r_all = run(_request(app, "GET", "/v1/projects"))
        assert len(r_all.json()["projects"]) == 2

    def test_delete_project_then_404(self) -> None:
        app = make_app()
        pid = run(_request(app, "POST", "/v1/projects", {"name": "P"})).json()["project_id"]
        assert run(_request(app, "DELETE", f"/v1/projects/{pid}")).status_code == 204
        assert run(_request(app, "GET", f"/v1/projects/{pid}")).status_code == 404


class TestRestrictSemantics:
    def test_delete_workspace_with_projects_is_409_refusal(self) -> None:
        # Migration 0002 FK ondelete=RESTRICT surfaced honestly — never
        # a silent cascade.
        app = make_app()
        wid = run(_request(app, "POST", "/v1/workspaces", {"name": "W"})).json()["workspace_id"]
        run(_request(app, "POST", "/v1/projects", {"name": "P", "workspace_id": wid}))
        r = run(_request(app, "DELETE", f"/v1/workspaces/{wid}"))
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "validation_error"
        # Workspace survives the refused delete.
        assert run(_request(app, "GET", f"/v1/workspaces/{wid}")).status_code == 200

    def test_delete_succeeds_after_projects_removed(self) -> None:
        app = make_app()
        wid = run(_request(app, "POST", "/v1/workspaces", {"name": "W"})).json()["workspace_id"]
        pid = run(_request(app, "POST", "/v1/projects", {"name": "P", "workspace_id": wid})).json()[
            "project_id"
        ]
        run(_request(app, "DELETE", f"/v1/projects/{pid}"))
        assert run(_request(app, "DELETE", f"/v1/workspaces/{wid}")).status_code == 204


class TestTenantIsolation:
    """Two apps, two tenants, SAME shared stores — the durable topology
    in miniature. Foreign ids must be indistinguishable from absent."""

    def _two_tenants(self) -> tuple[FastAPI, FastAPI]:
        shared_w = InMemoryWorkspaceStore()
        shared_p = InMemoryProjectStore()
        a = make_app(
            principal=Principal(tenant_id=uuid4(), user_id=uuid4()),
            workspaces=shared_w,
            projects=shared_p,
        )
        b = make_app(
            principal=Principal(tenant_id=uuid4(), user_id=uuid4()),
            workspaces=shared_w,
            projects=shared_p,
        )
        return a, b

    def test_foreign_workspace_get_is_same_404_as_absent(self) -> None:
        a, b = self._two_tenants()
        wid = run(_request(a, "POST", "/v1/workspaces", {"name": "secret"})).json()["workspace_id"]
        foreign = run(_request(b, "GET", f"/v1/workspaces/{wid}"))
        absent = run(_request(b, "GET", f"/v1/workspaces/{uuid4()}"))
        assert foreign.status_code == absent.status_code == 404
        # Identical error shape — no enumeration oracle (20 §6).
        assert (
            foreign.json()["error"]["code"] == absent.json()["error"]["code"] == "validation_error"
        )

    def test_foreign_delete_is_404_and_row_survives(self) -> None:
        a, b = self._two_tenants()
        wid = run(_request(a, "POST", "/v1/workspaces", {"name": "keep"})).json()["workspace_id"]
        assert run(_request(b, "DELETE", f"/v1/workspaces/{wid}")).status_code == 404
        assert run(_request(a, "GET", f"/v1/workspaces/{wid}")).status_code == 200

    def test_list_never_crosses_tenants(self) -> None:
        a, b = self._two_tenants()
        run(_request(a, "POST", "/v1/workspaces", {"name": "mine"}))
        run(_request(a, "POST", "/v1/projects", {"name": "p-mine"}))
        assert run(_request(b, "GET", "/v1/workspaces")).json()["workspaces"] == []
        assert run(_request(b, "GET", "/v1/projects")).json()["projects"] == []

    def test_cannot_link_project_to_foreign_workspace(self) -> None:
        a, b = self._two_tenants()
        wid = run(_request(a, "POST", "/v1/workspaces", {"name": "W"})).json()["workspace_id"]
        r = run(_request(b, "POST", "/v1/projects", {"name": "P", "workspace_id": wid}))
        assert r.status_code == 404  # same as absent — no oracle


class TestAuthPosture:
    def test_anonymous_caller_is_denied_before_any_write(self) -> None:
        # AUTH mode (the exactly-one identity contract): no bearer
        # token ⇒ 401 BEFORE any store work — identity runs FIRST.
        from apps.api.auth import AuthSurface
        from core.execution.service import ExecutionService
        from core.identity.service import InMemoryIdentityService
        from core.routing.router import SimpleScoringRouter

        class _Hasher:
            def hash(self, password: str) -> str:
                return f"h:{password}"

            def verify(self, password: str, hashed: str) -> bool:
                return hashed == f"h:{password}"

        class _Sink:
            def send_verification(self, email: str, token: str) -> None:
                pass

        providers = ProviderRegistry()
        models = ModelRegistry()
        bindings = BindingRegistry()
        anon_app = create_app(
            router=SimpleScoringRouter(providers, models, bindings),
            execution_service=ExecutionService(adapters={}, credential_refs={}, bindings=bindings),
            auth=AuthSurface(
                identity=InMemoryIdentityService(
                    hasher=_Hasher(), email_sender=_Sink(), default_plan_id=uuid4()
                )
            ),
        )
        for method, path, body in [
            ("POST", "/v1/workspaces", {"name": "x"}),
            ("GET", "/v1/workspaces", None),
            ("POST", "/v1/projects", {"name": "x"}),
            ("GET", "/v1/projects", None),
        ]:
            r = run(_request(anon_app, method, path, body))
            assert r.status_code == 401, (method, path)
            assert r.json()["error"]["code"] == "unauthenticated"
