"""Event delivery primitives (Vision V6 — X²-4 + X²-6).

Webhook delivery rides the PROVEN V2 chain (40 §4.2): producers stage
flat payloads on the EXISTING OutboxPort inside the state transaction;
the EXISTING OutboxRelay publishes onto the EXISTING QueuePort; the
EXISTING core Worker drives :class:`WebhookDeliveryHandler`, which
re-validates everything (P7) and hands the delivery to an INJECTED
async sender — core never does outbound HTTP (ADR-0008: the client
lives at the composition root / providers).

SSRF URL admission (:func:`validate_webhook_url`) ships in the SAME
module as the delivery surface (R095 same-commit rule) and runs BOTH
at staging and again at delivery time — registration-time data is
untrusted input (P7).
"""

from core.events.scheduler import ScheduleEntry, Scheduler
from core.events.webhooks import (
    WEBHOOK_STREAM,
    WebhookDeliveryHandler,
    WebhookSender,
    WebhookUrlRefused,
    stage_execution_event,
    validate_webhook_url,
)

__all__ = [
    "WEBHOOK_STREAM",
    "ScheduleEntry",
    "Scheduler",
    "WebhookDeliveryHandler",
    "WebhookSender",
    "WebhookUrlRefused",
    "stage_execution_event",
    "validate_webhook_url",
]
