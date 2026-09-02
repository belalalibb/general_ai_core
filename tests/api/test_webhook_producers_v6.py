"""Webhook producer wiring — Vision V6 chunk 3 gates.

The chunk-3 clause (recorded at R115): the DELIVERY machinery (V6-1) and
the SUBSCRIPTION rows (T-IMPL-067) finally meet the PRODUCERS.

Three surfaces, all hermetic (ASGI transport, in-memory runtime pieces):

1. Registration admission: POST /v1/webhooks refuses SSRF-inadmissible
   URLs with a NAMED 422 (validate_webhook_url at registration — the
   first of the three admission points; staging and delivery re-judge).
   The pre-existing t067 URLs (https://x.example/..., https://x — a
   VALID named host) stay admissible: the matrix here asserts both
   directions.
2. execution.queued staged by the async execute path (10 §12): the 202
   ack and the staged event ride the SAME durable outbox; no matching
   subscription ⇒ nothing extra staged (silence, not failure); the sync
   path stages nothing.
3. execution.succeeded / execution.failed staged by the worker at BOTH
   terminal-report sites (normal path AND _store_denied); seams absent ⇒
   pre-V6 behavior byte-identical; end-to-end: async execute → relay →
   queue → worker → terminal report → webhook delivery over the FULL
   V6-1 chain to a recording sender.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.worker import ExecutionMessageHandler
from core.contracts.execute import WebhookEventType, WebhookPayload
from core.contracts.webhooks import WebhookSubscription
from core.events import WEBHOOK_STREAM, WebhookDeliveryHandler
from core.execution.service import ExecutionService
from core.routing.router import SimpleScoringRouter
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import InMemoryOutbox, OutboxRelay
from core.runtime.worker import InMemoryIdempotencyStore, Worker
from tests.api.test_execute_api import World

EXECUTE_STREAM = "executions.requests"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


def _app(
    world: World,
    *,
    outbox: InMemoryOutbox | None = None,
    subscriptions: dict[UUID, list[WebhookSubscription]] | None = None,
) -> FastAPI:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        webhooks=True,
        webhook_subscriptions=subscriptions,
        outbox=outbox,
    )


async def _post(app: FastAPI, path: str, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body)


def _subscription(
    tenant_id: UUID,
    *,
    url: str = "https://hooks.example.com/deliver",
    events: list[WebhookEventType] | None = None,
) -> WebhookSubscription:
    return WebhookSubscription(
        id=uuid4(),
        tenant_id=tenant_id,
        url=url,
        events=events or list(WebhookEventType),
    )


def _webhook_records(outbox: InMemoryOutbox) -> list[Any]:
    records = run(outbox.pending(max_records=50))
    return [r for r in records if r.stream == WEBHOOK_STREAM]


# --- 1. registration admission ---------------------------------------------------


class TestRegistrationAdmission:
    @pytest.mark.parametrize(
        "url",
        [
            "https://hooks.example.com/deliver",
            "http://example.com/hook",
            # The pre-existing t067 shapes MUST stay admissible (resume
            # plan: 'https://x' is a VALID named host).
            "https://x.example/h",
            "https://x",
        ],
    )
    def test_admissible_urls_register_201(self, url: str) -> None:
        world = World()
        app = _app(world)
        response = run(_post(app, "/v1/webhooks", {"url": url}))
        assert response.status_code == 201

    @pytest.mark.parametrize(
        ("url", "fragment"),
        [
            ("ftp://example.com/hook", "scheme"),
            ("https://localhost/hook", "localhost"),
            ("https://evil.localhost/hook", "localhost"),
            ("https://127.0.0.1/hook", "non-public"),
            ("https://10.0.0.8/hook", "non-public"),
            ("https://[::1]/hook", "non-public"),
            ("https://user:pw@example.com/hook", "userinfo"),
            ("https:///nohost", "missing host"),
            ("  https://example.com/hook", "whitespace"),
        ],
    )
    def test_inadmissible_urls_refused_named_422(self, url: str, fragment: str) -> None:
        world = World()
        app = _app(world)
        response = run(_post(app, "/v1/webhooks", {"url": url}))
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert fragment in body["error"]["message"]
        assert body["error"]["details"]["field"] == "url"

    def test_refused_registration_stores_no_row(self) -> None:
        world = World()
        subscriptions: dict[UUID, list[WebhookSubscription]] = {}
        app = _app(world, subscriptions=subscriptions)
        run(_post(app, "/v1/webhooks", {"url": "https://127.0.0.1/hook"}))
        assert subscriptions == {}  # zero residue on refusal


# --- 2. execution.queued staged by the async execute path ------------------------


class TestQueuedEventStaging:
    def test_async_execute_stages_queued_event_for_matching_subscription(
        self,
    ) -> None:
        world = World()
        outbox = InMemoryOutbox()
        subscription = _subscription(world.principal.tenant_id)
        subscriptions = {world.principal.tenant_id: [subscription]}
        app = _app(world, outbox=outbox, subscriptions=subscriptions)
        response = run(
            _post(app, "/v1/execute", {"ask": "hi", "execution_policy": {"async": True}})
        )
        assert response.status_code == 202
        execution_id = response.json()["execution_id"]
        webhook_records = _webhook_records(outbox)
        assert len(webhook_records) == 1
        payload = webhook_records[0].payload
        assert payload["event"] == "execution.queued"
        assert payload["execution_id"] == execution_id
        assert payload["tenant_id"] == str(world.principal.tenant_id)
        assert payload["url"] == subscription.url
        # Per-(subscription, event, execution) idempotency key (V6-1 rule).
        assert webhook_records[0].idempotency_key == (
            f"webhook:{subscription.id}:execution.queued:{execution_id}"
        )

    def test_no_subscription_stages_nothing_extra(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        app = _app(world, outbox=outbox, subscriptions={})
        response = run(
            _post(app, "/v1/execute", {"ask": "hi", "execution_policy": {"async": True}})
        )
        assert response.status_code == 202
        assert _webhook_records(outbox) == []
        # The execute message itself is still staged (the flip untouched).
        all_records = run(outbox.pending(max_records=10))
        assert len(all_records) == 1
        assert all_records[0].stream == EXECUTE_STREAM

    def test_subscription_not_listing_queued_stages_nothing(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        subscription = _subscription(
            world.principal.tenant_id,
            events=[WebhookEventType.EXECUTION_SUCCEEDED],
        )
        subscriptions = {world.principal.tenant_id: [subscription]}
        app = _app(world, outbox=outbox, subscriptions=subscriptions)
        run(_post(app, "/v1/execute", {"ask": "hi", "execution_policy": {"async": True}}))
        assert _webhook_records(outbox) == []

    def test_sync_execute_stages_no_webhook_event(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        subscription = _subscription(world.principal.tenant_id)
        subscriptions = {world.principal.tenant_id: [subscription]}
        app = _app(world, outbox=outbox, subscriptions=subscriptions)
        response = run(_post(app, "/v1/execute", {"ask": "hi"}))
        assert response.status_code == 200
        assert run(outbox.pending(max_records=10)) == ()

    def test_foreign_tenant_subscription_never_matched(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        foreign = uuid4()
        subscriptions = {foreign: [_subscription(foreign)]}
        app = _app(world, outbox=outbox, subscriptions=subscriptions)
        run(_post(app, "/v1/execute", {"ask": "hi", "execution_policy": {"async": True}}))
        assert _webhook_records(outbox) == []  # 20 §6: caller tenant only


# --- 3. terminal events staged by the worker --------------------------------------


def _service_factory(world: World) -> Any:
    def factory(execution_id: UUID) -> ExecutionService:
        return ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
            usage=world.usage,
            sleeper=_no_sleep,
            id_factory=lambda: execution_id,
        )

    return factory


def _handler(
    world: World,
    *,
    outbox: InMemoryOutbox | None = None,
    subscriptions: dict[UUID, list[WebhookSubscription]] | None = None,
) -> ExecutionMessageHandler:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    return ExecutionMessageHandler(
        router=router,
        service_factory=_service_factory(world),
        store=world.store,
        outbox=outbox,
        subscriptions=subscriptions,
    )


def _execute_message_payload(world: World, execution_id: UUID) -> dict[str, str]:
    return {
        "execution_id": str(execution_id),
        "tenant_id": str(world.principal.tenant_id),
        "user_id": str(world.principal.user_id),
        "request": '{"ask": "hi"}',
        "payload": '{"ask": "hi"}',
        "request_hash": "h" * 64,
    }


def _queue_message(payload: dict[str, str]) -> Any:
    from core.runtime.ports import QueueMessage

    return QueueMessage(
        message_id="m-1",
        stream=EXECUTE_STREAM,
        payload=payload,
        idempotency_key="k",
        delivery_count=1,
    )


class TestWorkerTerminalStaging:
    def test_success_stages_execution_succeeded(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        subscription = _subscription(world.principal.tenant_id)
        handler = _handler(
            world,
            outbox=outbox,
            subscriptions={world.principal.tenant_id: [subscription]},
        )
        execution_id = uuid4()
        run(handler(_queue_message(_execute_message_payload(world, execution_id))))
        records = _webhook_records(outbox)
        assert len(records) == 1
        assert records[0].payload["event"] == "execution.succeeded"
        assert records[0].payload["execution_id"] == str(execution_id)

    def test_routing_denial_stages_execution_failed(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        subscription = _subscription(world.principal.tenant_id)
        handler = _handler(
            world,
            outbox=outbox,
            subscriptions={world.principal.tenant_id: [subscription]},
        )
        execution_id = uuid4()
        payload = _execute_message_payload(world, execution_id)
        # An unroutable policy: pin a model id that is not registered.
        payload["request"] = (
            '{"ask": "hi", "model_policy": {"type": "explicit_model", "model_id": "no-such-model"}}'
        )
        run(handler(_queue_message(payload)))
        # The denial is stored terminal truth (pre-V6 behavior kept) …
        report = world.store.get(world.principal.tenant_id, execution_id)
        assert report.execution.status.value == "failed"
        # … AND narrated (V6 chunk 3).
        records = _webhook_records(outbox)
        assert len(records) == 1
        assert records[0].payload["event"] == "execution.failed"

    def test_seams_absent_is_pre_v6_behavior(self) -> None:
        world = World()
        handler = _handler(world)  # no outbox, no subscriptions
        execution_id = uuid4()
        run(handler(_queue_message(_execute_message_payload(world, execution_id))))
        report = world.store.get(world.principal.tenant_id, execution_id)
        assert report.execution.status.value == "succeeded"

    def test_no_matching_subscription_stages_nothing(self) -> None:
        world = World()
        outbox = InMemoryOutbox()
        handler = _handler(world, outbox=outbox, subscriptions={})
        run(handler(_queue_message(_execute_message_payload(world, uuid4()))))
        assert _webhook_records(outbox) == []


# --- 4. end-to-end: async execute → worker → webhook delivery ---------------------


class _RecordingSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, WebhookPayload]] = []

    async def __call__(self, url: str, payload: WebhookPayload) -> None:
        self.deliveries.append((url, payload))


def test_end_to_end_async_execute_to_webhook_delivery() -> None:
    """The FULL V6 promise over REAL existing pieces only.

    API 202 (stages execute msg + execution.queued) → OutboxRelay →
    InMemoryQueue → execution Worker (stages execution.succeeded) →
    OutboxRelay again → webhook Worker → recording sender receives BOTH
    events for the SAME execution id.
    """
    world = World()
    outbox = InMemoryOutbox()
    queue = InMemoryQueue()
    subscription = _subscription(world.principal.tenant_id)
    subscriptions = {world.principal.tenant_id: [subscription]}

    app = _app(world, outbox=outbox, subscriptions=subscriptions)
    response = run(_post(app, "/v1/execute", {"ask": "go", "execution_policy": {"async": True}}))
    assert response.status_code == 202
    execution_id = response.json()["execution_id"]

    sender = _RecordingSender()
    relay = OutboxRelay(outbox, queue)
    execute_worker = Worker(
        queue,
        InMemoryIdempotencyStore(),
        stream=EXECUTE_STREAM,
        group="g",
        consumer="c",
        handler=_handler(world, outbox=outbox, subscriptions=subscriptions),
    )
    webhook_worker = Worker(
        queue,
        InMemoryIdempotencyStore(),
        stream=WEBHOOK_STREAM,
        group="g",
        consumer="c",
        handler=WebhookDeliveryHandler(sender),
    )

    async def _drive() -> None:
        # Pass 1: relay execute msg + queued event; deliver queued; run execute.
        await relay.relay_once(max_records=10)
        await webhook_worker.run_once(max_messages=10)
        await execute_worker.run_once(max_messages=10)
        # Pass 2: relay the terminal event staged by the worker; deliver it.
        await relay.relay_once(max_records=10)
        await webhook_worker.run_once(max_messages=10)

    run(_drive())

    events = [(p.event.value, p.execution_id) for _, p in sender.deliveries]
    assert events == [
        ("execution.queued", execution_id),
        ("execution.succeeded", execution_id),
    ]
    # Every delivery hit the registered URL; the payload tenant matches.
    assert all(url == subscription.url for url, _ in sender.deliveries)
    assert all(p.tenant_id == str(world.principal.tenant_id) for _, p in sender.deliveries)
    # The poll surface agrees with the narrated truth (P6).
    report = world.store.get(world.principal.tenant_id, UUID(execution_id))
    assert report.execution.status.value == "succeeded"
