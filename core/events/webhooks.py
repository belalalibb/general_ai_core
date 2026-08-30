"""Webhook delivery over the V2 outbox→worker chain (Vision V6; 10 §12).

REUSE map (P1 — nothing rebuilt):

- Staging:   the EXISTING ``OutboxPort.append`` (40 §4.2 — written by the
  producer inside its state transaction; the PostgresOutbox binding and
  ``append_in_session`` seam landed in V2).
- Transport: the EXISTING ``OutboxRelay`` → ``QueuePort`` (publish-then-
  mark, at-least-once).
- Consumption: the EXISTING core ``Worker`` (dedupe via IdempotencyPort,
  40 §4.6/4.7 retry taxonomy) driving :class:`WebhookDeliveryHandler`.
- Shapes: the EXISTING ``WebhookEventType`` / ``WebhookPayload`` (10 §12,
  closed set) and ``WebhookSubscription`` (41 §21) — never redefined.

SSRF admission (R095 same-commit rule — the validator lands WITH the
delivery surface it protects):

- :func:`validate_webhook_url` refuses, deterministically and pre-I/O,
  every statically refusable SSRF shape: non-http(s) schemes, missing
  host, userinfo smuggling, credentials, localhost names, and IP-literal
  targets in loopback/private/link-local/multicast/reserved/unspecified
  ranges (both v4 and v6, including v4-mapped v6).
- It runs at STAGING (a bad subscription never reaches the bus) and
  AGAIN at DELIVERY (queue content is untrusted input, P7; a record
  staged before a rule tightened is re-judged by today's rule).
- DNS-rebinding defence for NAMED hosts requires resolution at connect
  time — outbound I/O, which core never performs (ADR-0008). That duty
  is RECORDED on the sender seam: the composition-root sender must
  resolve-and-check or pin. Core refuses what purity can refuse.

Fault taxonomy at delivery (maps to the Worker's 40 §4.6 handling):

- Malformed queue payload / unknown event / refused URL ⇒
  ``PermanentTaskError`` → dead-letter (retrying cannot fix data).
- Sender faults (network, 5xx normalized by the sender) propagate ⇒
  left pending → ``claim_stale`` retry → dead-letter at max deliveries.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from urllib.parse import urlsplit

from core.contracts.execute import WebhookEventType, WebhookPayload
from core.contracts.webhooks import WebhookSubscription
from core.runtime.outbox import OutboxPort
from core.runtime.ports import QueueMessage
from core.runtime.worker import PermanentTaskError

# The stream webhook deliveries ride (one stream, per-record fan-out —
# same posture as the V2 executions stream name).
WEBHOOK_STREAM = "webhooks.deliveries"

# The delivery effector, injected at the composition root (ADR-0008:
# the HTTP client never enters core). Receives the admitted URL and the
# 10 §12 payload; raises on delivery failure (the Worker owns retries).
WebhookSender = Callable[[str, WebhookPayload], Awaitable[None]]

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REFUSED_HOSTNAMES = frozenset({"localhost"})


class WebhookUrlRefused(Exception):
    """A webhook URL failed SSRF admission (named refusal, 11 §14)."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"webhook url refused: {reason}")
        self.url = url
        self.reason = reason


def validate_webhook_url(url: str) -> str:
    """Admit an outbound webhook URL or raise :class:`WebhookUrlRefused`.

    Deterministic, pure, pre-I/O (P7). Returns the url UNCHANGED — what
    was validated is what is used; no normalization gap.
    """
    if not url or not url.strip():
        raise WebhookUrlRefused(url, "empty url")
    if url != url.strip():
        raise WebhookUrlRefused(url, "leading/trailing whitespace")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise WebhookUrlRefused(url, f"unparseable url: {exc}") from exc
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise WebhookUrlRefused(url, f"scheme not allowed: {parts.scheme!r}")
    if parts.username is not None or parts.password is not None:
        raise WebhookUrlRefused(url, "userinfo (credentials) not allowed")
    try:
        hostname = parts.hostname
        port = parts.port  # raises ValueError on out-of-range port
    except ValueError as exc:
        raise WebhookUrlRefused(url, f"invalid host/port: {exc}") from exc
    _ = port
    if not hostname:
        raise WebhookUrlRefused(url, "missing host")
    if hostname.lower() in _REFUSED_HOSTNAMES or hostname.lower().endswith(
        ".localhost"
    ):
        raise WebhookUrlRefused(url, "localhost target refused")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Named host: statically admissible; connect-time resolution
        # checking is the sender's recorded duty (module header).
        return url
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise WebhookUrlRefused(url, f"non-public address refused: {address}")
    return url


def _idempotency_key(
    subscription_id: str, event: WebhookEventType, execution_id: str
) -> str:
    # One delivery per (subscription, event, execution) — duplicate
    # staging or duplicate bus delivery dedupes at the Worker (40 §4.3).
    return f"webhook:{subscription_id}:{event.value}:{execution_id}"


async def stage_execution_event(
    outbox: OutboxPort,
    subscriptions: Iterable[WebhookSubscription],
    *,
    event: WebhookEventType,
    execution_id: str,
    tenant_id: str,
    timestamp: datetime,
    data: dict[str, object] | None = None,
) -> tuple[str, ...]:
    """Stage one delivery per matching subscription; returns record ids.

    Matching = the subscription lists ``event`` (subscriptions are
    already tenant-scoped rows — the CALLER passes only the event's own
    tenant's subscriptions; this function never widens scope, 20 §6).
    URLs are admitted HERE so an inadmissible subscription stages
    nothing (refusal is loud — a producer passing a bad row is a defect,
    not data).
    """
    payload_data = json.dumps(data or {}, sort_keys=True)
    staged: list[str] = []
    for subscription in subscriptions:
        if event not in subscription.events:
            continue
        validate_webhook_url(subscription.url)
        record_id = await outbox.append(
            WEBHOOK_STREAM,
            {
                "url": subscription.url,
                "subscription_id": str(subscription.id),
                "event": event.value,
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "timestamp": timestamp.isoformat(),
                "data": payload_data,
            },
            _idempotency_key(str(subscription.id), event, execution_id),
        )
        staged.append(record_id)
    return tuple(staged)


class WebhookDeliveryHandler:
    """The Worker handler for ``WEBHOOK_STREAM`` messages (40 §4.6)."""

    def __init__(self, sender: WebhookSender) -> None:
        self._sender = sender

    async def __call__(self, message: QueueMessage) -> None:
        payload = message.payload
        try:
            url = payload["url"]
            event = WebhookEventType(payload["event"])
            body = WebhookPayload(
                event=event,
                execution_id=payload["execution_id"],
                tenant_id=payload["tenant_id"],
                timestamp=datetime.fromisoformat(payload["timestamp"]),
                data=json.loads(payload["data"]),
            )
        except Exception as exc:
            # Malformed queue content: retrying cannot repair data (P7).
            raise PermanentTaskError(
                f"malformed webhook delivery message: {type(exc).__name__}: {exc}"
            ) from exc
        try:
            # Re-judged at delivery time — queue content is untrusted
            # and rules may have tightened since staging (P7).
            validate_webhook_url(url)
        except WebhookUrlRefused as exc:
            raise PermanentTaskError(str(exc)) from exc
        # Sender faults propagate: transient → left pending →
        # claim_stale; repeated → dead-letter at max deliveries.
        await self._sender(url, body)
