"""R194-B — webhook delivery composed at the production root (R176 §22 item).

RED-first for `apps/composition/runtime.py` + `apps/main.py`: the runtime
profile owns ONE tenant-scoped subscription map shared by `create_app` and
`ExecutionMessageHandler`, exposes a second existing-class `Worker` on
`WEBHOOK_STREAM` driving the existing `WebhookDeliveryHandler` with an httpx
sender built at the root (ADR-0008), and `apps.main` drives that worker in
the lifespan. Tenancy: a second tenant's subscription receives nothing.
Failure posture: a non-2xx receiver leaves the message un-acked (retry /
dead-letter per 40 §4.7); redirects are not followed.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from collections.abc import Coroutine
from typing import Any

import httpx

from apps.composition.runtime import (
    WEBHOOK_TIMEOUT_ENV,
    RuntimeProfile,
    build_runtime_profile,
    build_webhook_sender,
)
from core.contracts.execute import WebhookPayload

ADMIN_EMAIL = "r194-hooks-admin@example.test"
TENANT_A = "r194-hooks-a@example.test"
TENANT_B = "r194-hooks-b@example.test"
PASSWORD = "correct horse battery staple"
RECEIVER = "https://hooks.example.test/in"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _session(profile: RuntimeProfile, email: str) -> str:
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(email, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(email, PASSWORD).token


class _Receiver:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self.status in (301, 302, 307, 308):
                return httpx.Response(self.status, headers={"location": "http://127.0.0.1:9/steal"})
            return httpx.Response(self.status)

        return httpx.MockTransport(handle)


async def _drive(profile: RuntimeProfile, receiver_calls: int = 6) -> None:
    for _ in range(receiver_calls):
        await profile.relay.relay_once(max_records=20)
        await profile.worker.run_once(max_messages=20)
        await profile.relay.relay_once(max_records=20)
        await profile.webhook_worker.run_once(max_messages=20)


def _profile(receiver: _Receiver) -> RuntimeProfile:
    return build_runtime_profile(
        environ={"ADMIN_EMAILS": ADMIN_EMAIL},
        webhook_transport=receiver.transport(),
    )


async def _api(
    profile: RuntimeProfile, token: str, method: str, path: str, body: Any = None
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
    ) as client:
        return await client.request(
            method, path, json=body, headers={"Authorization": f"Bearer {token}"}
        )


class TestProfileShape:
    def test_default_profile_exposes_a_webhook_worker(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        assert type(profile.webhook_worker) is type(profile.worker)
        assert profile.webhook_worker is not profile.worker

    def test_sender_posts_json_payload_without_following_redirects(self) -> None:
        receiver = _Receiver(status=302)
        sender = build_webhook_sender({WEBHOOK_TIMEOUT_ENV: "3"}, transport=receiver.transport())
        payload = WebhookPayload(
            event="execution.queued",
            execution_id="e-1",
            tenant_id="t-1",
            timestamp="2026-09-20T00:00:00+00:00",
            data={},
        )
        try:
            run(sender(RECEIVER, payload))
        except Exception:
            pass  # a redirect is a failed delivery, never a followed one
        assert [str(r.url) for r in receiver.requests] == [RECEIVER]
        assert receiver.requests[0].method == "POST"
        assert receiver.requests[0].headers["content-type"].startswith("application/json")
        assert json.loads(receiver.requests[0].content)["execution_id"] == "e-1"

    def test_sender_refuses_non_2xx(self) -> None:
        receiver = _Receiver(status=500)
        sender = build_webhook_sender({}, transport=receiver.transport())
        payload = WebhookPayload(
            event="execution.queued",
            execution_id="e-2",
            tenant_id="t-1",
            timestamp="2026-09-20T00:00:00+00:00",
            data={},
        )
        try:
            run(sender(RECEIVER, payload))
        except Exception:
            return
        raise AssertionError("a 500 from the receiver must raise so the Worker retries")


class TestEndToEndDelivery:
    def test_registered_tenant_receives_queued_and_terminal_events_only_for_itself(self) -> None:
        receiver = _Receiver()
        profile = _profile(receiver)
        token_a = _session(profile, TENANT_A)
        token_b = _session(profile, TENANT_B)

        created = run(_api(profile, token_a, "POST", "/v1/webhooks", {"url": RECEIVER}))
        assert created.status_code == 201, created.text
        foreign = run(_api(profile, token_b, "POST", "/v1/webhooks", {"url": RECEIVER + "/b"}))
        assert foreign.status_code == 201, foreign.text

        accepted = run(
            _api(
                profile,
                token_a,
                "POST",
                "/v1/execute",
                {"ask": "hello", "execution_policy": {"async": True}},
            )
        )
        assert accepted.status_code == 202, accepted.text
        execution_id = accepted.json()["execution_id"]

        run(_drive(profile))

        bodies = [json.loads(r.content) for r in receiver.requests]
        events = sorted((b["event"], b["execution_id"]) for b in bodies)
        assert ("execution.queued", execution_id) in events
        terminal = [e for e, eid in events if eid == execution_id and e != "execution.queued"]
        assert len(terminal) == 1 and terminal[0].startswith("execution.")
        assert len(events) == 2
        assert {str(r.url) for r in receiver.requests} == {RECEIVER}
        tenants = {b["tenant_id"] for b in bodies}
        assert len(tenants) == 1
        assert "authorization" not in {k.lower() for r in receiver.requests for k in r.headers}

    def test_failed_delivery_is_not_acked(self) -> None:
        receiver = _Receiver(status=503)
        profile = _profile(receiver)
        token_a = _session(profile, TENANT_A)
        assert (
            run(_api(profile, token_a, "POST", "/v1/webhooks", {"url": RECEIVER})).status_code
            == 201
        )
        accepted = run(
            _api(
                profile,
                token_a,
                "POST",
                "/v1/execute",
                {"ask": "x", "execution_policy": {"async": True}},
            )
        )
        assert accepted.status_code == 202
        run(_drive(profile, receiver_calls=2))
        # Retried at least once (delivery count grows) — never silently acked.
        assert len(receiver.requests) >= 2


class TestMainLifespan:
    def test_lifespan_drives_the_webhook_worker(self) -> None:
        from apps.main import create_runtime_app

        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        app = create_runtime_app(profile)

        async def _run() -> set[str]:
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                return {t.get_name() for t in asyncio.all_tasks()}

        names = run(_run())
        assert {"outbox-relay", "exec-worker", "webhook-worker"} <= names
