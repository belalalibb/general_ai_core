"""Completion program v2 — Phase 1/2 runtime behaviour over the REAL runtime profile.

Operator rulings: D-1 = b (dev token in register response, in-memory only), D-2 =
HttpOnly cookie session (+ CSRF header rule), D-3 = yes (tenant agent path + own
trace), D-4 = yes (additive execution context), D-6 = yes (tenant panels; server
side = existing routes), D-7 = hermetic-first. Everything here runs through
``build_runtime_profile`` (P1: no test-only wiring) with the local echo adapter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import httpx

from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.contracts.provider import ProviderError, ProviderErrorCategory

ADMIN = "admin@completion.test"
PW = "correct horse battery staple"
CSRF = {"X-Requested-With": "QEVION"}


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _profile() -> RuntimeProfile:
    return build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN})


def _client(profile: RuntimeProfile) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=profile.app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def _register_verify(client: httpx.AsyncClient, email: str) -> dict[str, Any]:
    reg = await client.post("/v1/auth/register", json={"email": email, "password": PW})
    assert reg.status_code == 201, reg.text
    body = reg.json()
    ver = await client.post("/v1/auth/verify", json={"token": body["dev_verification_token"]})
    assert ver.status_code == 200, ver.text
    return dict(body)


async def _bearer(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    await _register_verify(client, email)
    login = await client.post("/v1/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


class TestC01RootEntry:
    def test_root_redirects_to_the_workbench(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                r = await c.get("/", follow_redirects=False)
                assert r.status_code == 307
                assert r.headers["location"] == "/app/"

        run(scenario())


class TestC02DevOnboarding:
    def test_in_memory_register_returns_a_labelled_dev_token(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                body = await _register_verify(c, "u1@completion.test")
                assert body["verification"] == "dev_token"
                assert "development" in body["dev_note"]
                assert "no email was sent" in body["dev_note"]
                login = await c.post(
                    "/v1/auth/login", json={"email": "u1@completion.test", "password": PW}
                )
                assert login.status_code == 200

        run(scenario())

    def test_register_shape_is_unchanged_without_the_dev_capture(self) -> None:
        # The register route alone (no capture bound) ⇒ byte-identical pre-C-02 body.
        from fastapi import FastAPI

        from apps.api.auth import AuthSurface, create_auth_router
        from tests.api.test_aa1_api_seams import make_identity

        identity, _sink = make_identity()
        app = FastAPI()
        app.include_router(create_auth_router(AuthSurface(identity=identity)))

        async def scenario() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/v1/auth/register", json={"email": "d@x.test", "password": PW})
                assert r.status_code == 201
                assert set(r.json()) == {"user_id", "tenant_id", "email", "status", "verification"}
                assert r.json()["verification"] == "sent"

        run(scenario())


class TestC05CookieSession:
    def test_login_sets_httponly_cookie_and_cookie_only_reads_work(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                await _register_verify(c, "cookie@completion.test")
                login = await c.post(
                    "/v1/auth/login", json={"email": "cookie@completion.test", "password": PW}
                )
                set_cookie = login.headers["set-cookie"].lower()
                assert "qevion_session=" in set_cookie
                assert "httponly" in set_cookie and "samesite=strict" in set_cookie
                session = await c.get("/v1/auth/session")  # cookie jar only
                assert session.status_code == 200
                assert session.json()["email"] == "cookie@completion.test"

        run(scenario())

    def test_cookie_only_state_change_requires_csrf_header(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                await _register_verify(c, "csrf@completion.test")
                creds = {"email": "csrf@completion.test", "password": PW}
                await c.post("/v1/auth/login", json=creds)
                refused = await c.post("/v1/workspaces", json={"name": "ws"})
                assert refused.status_code == 403
                assert refused.json()["error"]["code"] == "unauthorized"
                ok = await c.post("/v1/workspaces", json={"name": "ws"}, headers=CSRF)
                assert ok.status_code == 201
                out = await c.post("/v1/auth/logout", headers=CSRF)
                assert out.status_code == 204
                assert "qevion_session=" in out.headers["set-cookie"].lower()
                assert (await c.get("/v1/auth/session")).status_code == 401

        run(scenario())

    def test_bearer_clients_are_unchanged_and_need_no_csrf_header(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                headers = await _bearer(c, "bearer@completion.test")
                c.cookies.clear()
                r = await c.post("/v1/workspaces", json={"name": "ws"}, headers=headers)
                assert r.status_code == 201

        run(scenario())


class TestC04ExecutionContext:
    def test_single_template_and_async_records_carry_context(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                h = await _bearer(c, "ctx@completion.test")
                ws = (await c.post("/v1/workspaces", json={"name": "w"}, headers=h)).json()
                prj = (
                    await c.post(
                        "/v1/projects",
                        json={"name": "p", "workspace_id": ws["workspace_id"]},
                        headers=h,
                    )
                ).json()
                single = await c.post(
                    "/v1/execute", json={"ask": "hi", "project_id": prj["project_id"]}, headers=h
                )
                assert single.status_code == 200, single.text
                assert single.json()["context"] == {
                    "strategy": "single",
                    "mode": "single",
                    "project_id": prj["project_id"],
                }
                status = await c.get(f"/v1/executions/{single.json()['execution_id']}", headers=h)
                assert status.json()["context"]["project_id"] == prj["project_id"]

                templates = (await c.get("/v1/templates", headers=h)).json()["templates"]
                ref = templates[0]["ref"]
                tpl = await c.post(
                    "/v1/execute",
                    json={
                        "ask": "hi",
                        "execution_strategy": {"mode": "template", "template_id": ref},
                    },
                    headers=h,
                )
                assert tpl.status_code == 200, tpl.text
                assert tpl.json()["context"] == {
                    "strategy": "hybrid",
                    "mode": "template",
                    "template_ref": ref,
                }

                queued = await c.post(
                    "/v1/execute",
                    json={"ask": "hi", "execution_policy": {"async": True}},
                    headers=h,
                )
                assert queued.status_code == 202
                placeholder = await c.get(
                    f"/v1/executions/{queued.json()['execution_id']}", headers=h
                )
                assert placeholder.json()["context"]["mode"] == "single"

                rows = (await c.get("/v1/executions", headers=h)).json()["executions"]
                assert all("context" in row for row in rows)
                assert any(row["context"].get("project_id") == prj["project_id"] for row in rows)
                assert any(row["context"].get("template_ref") == ref for row in rows)

        run(scenario())

    def test_worker_folds_the_same_context_into_the_terminal_record(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                h = await _bearer(c, "worker@completion.test")
                queued = await c.post(
                    "/v1/execute",
                    json={"ask": "hi", "execution_policy": {"async": True}},
                    headers=h,
                )
                eid = queued.json()["execution_id"]
                await profile.relay.relay_once(max_records=20)
                await profile.worker.run_once(max_messages=20)
                done = await c.get(f"/v1/executions/{eid}", headers=h)
                assert done.json()["status"] == "succeeded", done.text
                assert done.json()["context"] == {"strategy": "single", "mode": "single"}

        run(scenario())


class TestC11TenantAgentAccess:
    def test_owning_tenant_reads_own_trace_foreign_404_control_plane_admin(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                h1 = await _bearer(c, "t1@completion.test")
                c.cookies.clear()
                h2 = await _bearer(c, "t2@completion.test")
                c.cookies.clear()
                run_r = await c.post(
                    "/v1/execute",
                    json={"ask": "do it", "execution_policy": {"strategy": "agent"}},
                    headers=h1,
                )
                body = run_r.json()
                eid = body.get("execution_id") or body["error"]["details"]["execution_id"]
                own = await c.get(f"/v1/agent/executions/{eid}/trace", headers=h1)
                assert own.status_code == 200, own.text
                assert own.json()["execution_id"] == eid
                diag = await c.get(f"/v1/agent/executions/{eid}/diagnosis", headers=h1)
                assert diag.status_code == 200
                foreign = await c.get(f"/v1/agent/executions/{eid}/trace", headers=h2)
                assert foreign.status_code == 404
                assert foreign.json()["error"]["code"] == "validation_error"
                assert (await c.get("/v1/agent/tools", headers=h1)).status_code == 403
                converse = await c.post("/v1/agent/converse", json={"message": "x"}, headers=h1)
                assert converse.status_code == 403

        run(scenario())


class TestC12RuntimeModelTruth:
    def test_models_carry_runtime_rows_and_degrade_on_signals(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                h = await _bearer(c, "models@completion.test")
                before = (await c.get("/v1/models", headers=h)).json()["models"]
                assert before and before[0]["availability"] == "available"
                assert before[0]["runtime"][0]["eligible"] is True
                model = before[0]
                binding = profile.bindings_registry.bindings_for_model(UUID(model["id"]))[0]
                # the SAME board the Router reads (one authority)
                signals = profile.app.state.strategy_executor._router.signals  # noqa: SLF001
                assert signals is not None
                signals.record_error(
                    provider_id=binding.provider_id,
                    model_id=UUID(model["id"]),
                    error=ProviderError(
                        category=ProviderErrorCategory.QUOTA_EXCEEDED,
                        retryable=True,
                        safe_message="provider plan refused inference",
                    ),
                )
                after = (await c.get("/v1/models", headers=h)).json()["models"][0]
                assert after["availability"] == "unavailable"
                assert after["runtime"][0]["eligible"] is False
                assert "quota_exceeded" in after["runtime"][0]["reason"]

        run(scenario())


class TestC17MeasuredDashboard:
    def test_dashboard_is_measured_when_lifecycle_is_composed(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                h = await _bearer(c, ADMIN)
                dash = (await c.get("/v1/admin/learning/dashboard", headers=h)).json()
                assert dash["placeholder"] is False
                assert dash["samples_total"] == 0 and dash["gold_samples"] == 0
                assert "specialist_models" in dash["deferred"]
                assert "measured_at" in dash

        run(scenario())
