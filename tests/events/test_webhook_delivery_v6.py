"""Webhook delivery over the V2 chain — Vision V6 chunk 1 gates.

Covers the frozen clause end-to-end with the REAL existing runtime
pieces (InMemoryOutbox, OutboxRelay, InMemoryQueue, Worker) — nothing
mocked below the sender seam:

- SSRF admission matrix (validate_webhook_url) — the R095 same-commit
  validator.
- stage_execution_event: event matching, tenant-verbatim payload,
  per-subscription idempotency keys, loud refusal on inadmissible URL.
- Full chain: stage → relay → queue → Worker → sender; duplicate
  delivery dedupes; malformed/refused messages dead-letter; transient
  sender faults retry then dead-letter at max deliveries.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.contracts.execute import WebhookEventType, WebhookPayload
from core.contracts.webhooks import WebhookSubscription
from core.events import (
    WEBHOOK_STREAM,
    WebhookDeliveryHandler,
    WebhookUrlRefused,
    stage_execution_event,
    validate_webhook_url,
)
from core.runtime.memory import InMemoryQueue
from core.runtime.outbox import InMemoryOutbox, OutboxRelay
from core.runtime.worker import InMemoryIdempotencyStore, Worker

TENANT = uuid4()
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
GOOD_URL = "https://hooks.example.com/deliver"


def _subscription(
    url: str = GOOD_URL,
    events: list[WebhookEventType] | None = None,
) -> WebhookSubscription:
    return WebhookSubscription(
        id=uuid4(),
        tenant_id=TENANT,
        url=url,
        events=events or list(WebhookEventType),
    )


class _RecordingSender:
    def __init__(self, fail_times: int = 0) -> None:
        self.deliveries: list[tuple[str, WebhookPayload]] = []
        self._fail_times = fail_times

    async def __call__(self, url: str, payload: WebhookPayload) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("simulated network fault")
        self.deliveries.append((url, payload))


class TestSsrfValidator:
    @pytest.mark.parametrize(
        "url",
        [
            GOOD_URL,
            "http://example.com/hook",
            "https://api.partner.io:8443/wh?sig=1",
            "http://93.184.216.34/hook",  # public IPv4 literal
        ],
    )
    def test_admits_public_targets_unchanged(self, url: str) -> None:
        assert validate_webhook_url(url) == url  # verbatim, no normalization

    @pytest.mark.parametrize(
        ("url", "reason_fragment"),
        [
            ("", "empty url"),
            ("   ", "empty url"),
            (" https://example.com/x", "whitespace"),
            ("ftp://example.com/x", "scheme not allowed"),
            ("file:///etc/passwd", "scheme not allowed"),
            ("https://example.com".replace("https://", "https:/"), "missing host"),
            ("https://", "missing host"),
            ("https://user:pw@example.com/x", "userinfo"),
            ("https://user@example.com/x", "userinfo"),
            ("https://localhost/x", "localhost"),
            ("https://LOCALHOST/x", "localhost"),
            ("https://svc.localhost/x", "localhost"),
            ("http://127.0.0.1/x", "non-public"),
            ("http://127.8.9.1/x", "non-public"),
            ("http://10.0.0.5/x", "non-public"),
            ("http://172.16.0.1/x", "non-public"),
            ("http://192.168.1.1/x", "non-public"),
            ("http://169.254.169.254/latest/meta-data", "non-public"),
            ("http://0.0.0.0/x", "non-public"),
            ("http://[::1]/x", "non-public"),
            ("http://[fe80::1]/x", "non-public"),
            ("http://[fc00::1]/x", "non-public"),
            ("http://[::ffff:127.0.0.1]/x", "non-public"),  # v4-mapped v6
            ("http://[::ffff:10.0.0.1]/x", "non-public"),
            ("http://224.0.0.1/x", "non-public"),  # multicast
            ("http://example.com:99999/x", "invalid host/port"),
        ],
    )
    def test_refuses_ssrf_shapes_with_named_reason(
        self, url: str, reason_fragment: str
    ) -> None:
        with pytest.raises(WebhookUrlRefused) as exc:
            validate_webhook_url(url)
        assert reason_fragment in exc.value.reason
        assert exc.value.url == url

    def test_refusal_is_a_named_exception_carrying_the_url(self) -> None:
        err = WebhookUrlRefused("http://10.0.0.1/x", "non-public address refused")
        assert str(err) == "webhook url refused: non-public address refused"


class TestStaging:
    def test_stages_one_record_per_matching_subscription(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            matching = _subscription(events=[WebhookEventType.EXECUTION_SUCCEEDED])
            non_matching = _subscription(events=[WebhookEventType.EXECUTION_FAILED])
            staged = await stage_execution_event(
                outbox,
                [matching, non_matching],
                event=WebhookEventType.EXECUTION_SUCCEEDED,
                execution_id="exec-1",
                tenant_id=str(TENANT),
                timestamp=NOW,
            )
            assert len(staged) == 1
            records = await outbox.pending(10)
            assert len(records) == 1
            record = records[0]
            assert record.stream == WEBHOOK_STREAM
            assert record.payload["url"] == GOOD_URL
            assert record.payload["event"] == "execution.succeeded"
            assert record.payload["execution_id"] == "exec-1"
            assert record.payload["tenant_id"] == str(TENANT)
            assert record.idempotency_key == (
                f"webhook:{matching.id}:execution.succeeded:exec-1"
            )

        asyncio.run(run())

    def test_inadmissible_url_stages_nothing_and_refuses_loudly(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            bad = _subscription(url="http://169.254.169.254/latest")
            with pytest.raises(WebhookUrlRefused):
                await stage_execution_event(
                    outbox,
                    [bad],
                    event=WebhookEventType.EXECUTION_QUEUED,
                    execution_id="exec-1",
                    tenant_id=str(TENANT),
                    timestamp=NOW,
                )
            assert await outbox.pending(10) == ()

        asyncio.run(run())

    def test_no_matching_subscription_stages_nothing(self) -> None:
        async def run() -> None:
            outbox = InMemoryOutbox()
            staged = await stage_execution_event(
                outbox,
                [_subscription(events=[WebhookEventType.EXECUTION_FAILED])],
                event=WebhookEventType.EXECUTION_STARTED,
                execution_id="exec-1",
                tenant_id=str(TENANT),
                timestamp=NOW,
            )
            assert staged == ()
            assert await outbox.pending(10) == ()

        asyncio.run(run())


def _chain(
    sender: _RecordingSender,
) -> tuple[InMemoryOutbox, OutboxRelay, Worker]:
    outbox = InMemoryOutbox()
    queue = InMemoryQueue()
    relay = OutboxRelay(outbox, queue)
    worker = Worker(
        queue,
        InMemoryIdempotencyStore(),
        stream=WEBHOOK_STREAM,
        group="webhook-deliverers",
        consumer="w1",
        handler=WebhookDeliveryHandler(sender),
        max_deliveries=2,
    )
    return outbox, relay, worker


class TestDeliveryChain:
    def test_full_chain_stage_relay_consume_deliver(self) -> None:
        async def run() -> None:
            sender = _RecordingSender()
            outbox, relay, worker = _chain(sender)
            subscription = _subscription()
            await stage_execution_event(
                outbox,
                [subscription],
                event=WebhookEventType.EXECUTION_SUCCEEDED,
                execution_id="exec-9",
                tenant_id=str(TENANT),
                timestamp=NOW,
                data={"status": "succeeded"},
            )
            assert await relay.relay_once(10) == 1
            report = await worker.run_once(10)
            assert len(report.processed) == 1
            assert report.dead_lettered == []
            (url, payload) = sender.deliveries[0]
            assert url == GOOD_URL
            # The delivered body IS the 10 §12 contract, verbatim fields.
            assert payload.event is WebhookEventType.EXECUTION_SUCCEEDED
            assert payload.execution_id == "exec-9"
            assert payload.tenant_id == str(TENANT)
            assert payload.timestamp == NOW
            assert payload.data == {"status": "succeeded"}

        asyncio.run(run())

    def test_duplicate_bus_delivery_dedupes_exactly_one_send(self) -> None:
        async def run() -> None:
            sender = _RecordingSender()
            outbox, relay, worker = _chain(sender)
            subscription = _subscription()
            # Stage the SAME occurrence twice (producer retry) — same
            # idempotency key both times.
            for _ in range(2):
                await stage_execution_event(
                    outbox,
                    [subscription],
                    event=WebhookEventType.EXECUTION_QUEUED,
                    execution_id="exec-dup",
                    tenant_id=str(TENANT),
                    timestamp=NOW,
                )
            assert await relay.relay_once(10) == 2
            report = await worker.run_once(10)
            assert len(report.processed) == 1
            assert len(report.duplicates) == 1
            assert len(sender.deliveries) == 1  # exactly once (40 §4.3)

        asyncio.run(run())

    def test_malformed_message_dead_letters(self) -> None:
        async def run() -> None:
            sender = _RecordingSender()
            _, _, worker = _chain(sender)
            queue = worker._queue  # noqa: SLF001 — same-instance shortcut
            await queue.publish(
                WEBHOOK_STREAM,
                {"url": GOOD_URL, "event": "not.an.event"},
                "bad-1",
            )
            report = await worker.run_once(10)
            assert len(report.dead_lettered) == 1
            assert sender.deliveries == []

        asyncio.run(run())

    def test_url_refused_at_delivery_time_dead_letters(self) -> None:
        # P7: queue content re-judged — a record carrying a non-public
        # target (staged before a rule existed, or forged) never reaches
        # the sender.
        async def run() -> None:
            sender = _RecordingSender()
            _, _, worker = _chain(sender)
            queue = worker._queue  # noqa: SLF001
            await queue.publish(
                WEBHOOK_STREAM,
                {
                    "url": "http://10.0.0.7/exfil",
                    "subscription_id": str(uuid4()),
                    "event": "execution.succeeded",
                    "execution_id": "exec-x",
                    "tenant_id": str(TENANT),
                    "timestamp": NOW.isoformat(),
                    "data": "{}",
                },
                "forged-1",
            )
            report = await worker.run_once(10)
            assert len(report.dead_lettered) == 1
            assert sender.deliveries == []

        asyncio.run(run())

    def test_transient_sender_fault_retries_then_dead_letters(self) -> None:
        async def run() -> None:
            sender = _RecordingSender(fail_times=1)
            outbox, relay, worker = _chain(sender)  # max_deliveries=2
            await stage_execution_event(
                outbox,
                [_subscription()],
                event=WebhookEventType.EXECUTION_FAILED,
                execution_id="exec-retry",
                tenant_id=str(TENANT),
                timestamp=NOW,
            )
            await relay.relay_once(10)
            first = await worker.run_once(10)
            assert len(first.left_pending) == 1  # transient, not acked
            assert sender.deliveries == []
            second = await worker.recover_once(idle_ms=0, max_messages=10)
            assert len(second.processed) == 1  # retry succeeded
            assert len(sender.deliveries) == 1

        asyncio.run(run())

    def test_persistent_sender_fault_dead_letters_at_max(self) -> None:
        async def run() -> None:
            sender = _RecordingSender(fail_times=99)
            outbox, relay, worker = _chain(sender)  # max_deliveries=2
            await stage_execution_event(
                outbox,
                [_subscription()],
                event=WebhookEventType.EXECUTION_CANCELLED,
                execution_id="exec-dead",
                tenant_id=str(TENANT),
                timestamp=NOW,
            )
            await relay.relay_once(10)
            first = await worker.run_once(10)
            assert len(first.left_pending) == 1
            second = await worker.recover_once(idle_ms=0, max_messages=10)
            assert len(second.dead_lettered) == 1  # 40 §4.7 — no infinite retry
            assert sender.deliveries == []

        asyncio.run(run())
