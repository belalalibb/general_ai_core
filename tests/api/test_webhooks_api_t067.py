"""POST /v1/webhooks — FINAL Phase 18 slice 2 (T-IMPL-067).

Contract authority: 41 §21 (POST /v1/webhooks named supporting endpoint +
Webhooks named feature), 10 §12 (the ONLY documented webhook facts: six
event types + delivery payload — the contract module never redefines
them), 20 §4 (webhooks=False ⇒ no route), 20 §6 (subscriptions are
tenant-scoped records; response never echoes tenant_id).

Recorded scope (from apps/api/app.py + core/contracts/webhooks.py):
REGISTRATION only. Event DELIVERY is outbound I/O riding the documented
40 §4.2 outbox seam — never claimed (41 §49). No update/delete/list
routes exist because no doc defines them.

Hermetic: ASGI transport, in-memory everything, no sockets.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api.app import Principal, create_app
from core.contracts.execute import WebhookEventType
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def make_app(*, webhooks: bool = True) -> FastAPI:
    from core.execution.service import ExecutionService
    from core.routing.router import SimpleScoringRouter

    providers = ProviderRegistry()
    models = ModelRegistry()
    bindings = BindingRegistry()
    return create_app(
        router=SimpleScoringRouter(providers, models, bindings),
        execution_service=ExecutionService(
            adapters={}, credential_refs={}, bindings=bindings
        ),
        principal=Principal(tenant_id=uuid4(), user_id=uuid4()),
        webhooks=webhooks,
    )


async def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/v1/webhooks", json=body)


ALL_SIX = [
    "execution.queued",
    "execution.started",
    "execution.waiting_approval",
    "execution.succeeded",
    "execution.failed",
    "execution.cancelled",
]


class TestWebhookRegistration:
    def test_register_with_explicit_events_returns_201_subscription(self) -> None:
        app = make_app()
        response = run(
            _post(
                app,
                {
                    "url": "https://client.example/hook",
                    "events": ["execution.succeeded", "execution.failed"],
                },
            )
        )
        assert response.status_code == 201
        body = response.json()
        assert set(body.keys()) == {"id", "url", "events"}
        assert body["url"] == "https://client.example/hook"
        assert body["events"] == ["execution.succeeded", "execution.failed"]

    def test_absent_events_subscribes_all_six_documented_types(self) -> None:
        app = make_app()
        body = run(_post(app, {"url": "https://client.example/hook"})).json()
        assert body["events"] == ALL_SIX

    def test_the_closed_set_is_exactly_the_10_12_six(self) -> None:
        assert [e.value for e in WebhookEventType] == ALL_SIX

    def test_unknown_event_type_refused_as_validation_error(self) -> None:
        app = make_app()
        response = run(
            _post(
                app,
                {"url": "https://x.example/h", "events": ["execution.exploded"]},
            )
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_empty_explicit_events_list_refused(self) -> None:
        app = make_app()
        response = run(_post(app, {"url": "https://x.example/h", "events": []}))
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"]["field"] == "events"

    def test_missing_url_refused(self) -> None:
        app = make_app()
        response = run(_post(app, {"events": ["execution.succeeded"]}))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_response_never_echoes_tenant_id(self) -> None:
        app = make_app()
        body = run(_post(app, {"url": "https://x.example/h"})).json()
        assert "tenant_id" not in body

    def test_each_registration_gets_a_distinct_id(self) -> None:
        app = make_app()
        first = run(_post(app, {"url": "https://x.example/a"})).json()
        second = run(_post(app, {"url": "https://x.example/b"})).json()
        assert first["id"] != second["id"]

    def test_webhooks_disabled_no_route_exists(self) -> None:
        app = make_app(webhooks=False)
        response = run(_post(app, {"url": "https://x.example/h"}))
        assert response.status_code == 404

    def test_no_undocumented_collection_routes_exist(self) -> None:
        """No doc defines list/update/delete — absent, not fabricated."""
        app = make_app()
        transport = httpx.ASGITransport(app=app)

        async def probe() -> tuple[int, int]:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                listed = await c.get("/v1/webhooks")
                deleted = await c.delete(f"/v1/webhooks/{uuid4()}")
                return listed.status_code, deleted.status_code

        get_status, delete_status = run(probe())
        assert get_status in (404, 405)
        assert delete_status in (404, 405)


def test_webhooks_contract_module_does_no_io() -> None:
    import inspect

    import core.contracts.webhooks as mod

    source = inspect.getsource(mod)
    for banned in ("httpx", "requests", "urllib", "socket", "subprocess", "open("):
        assert banned not in source
