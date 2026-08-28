"""POST /v1/webhooks shapes (41 §21) — webhook subscription registration.

Contract authority:

- 41 §21 (FINAL Phase 18): ``POST /v1/webhooks`` is a named supporting
  endpoint and ``Webhooks`` a named feature.
- 10 §12: the ONLY webhook facts any doc defines — the six event types
  (closed set, already ``WebhookEventType`` in core/contracts/execute.py)
  and the delivery payload (already ``WebhookPayload``). This module
  NEVER redefines either.

Recorded derivation decisions (no doc defines the registration shape):

- POST /v1/webhooks = REGISTER a subscription: a delivery URL + the event
  types it wants. That is the minimal reading of "Webhooks" as a feature
  next to an endpoint named like a collection; nothing beyond
  registration is invented (no doc defines update/delete/list — absent
  routes stay absent rather than fabricated).
- ``events`` absent ⇒ ALL six documented types. Event filtering is a
  convenience over the caller's OWN tenant's execution events — not a
  security grant, so deny-by-default (20 §4) does not apply to the
  default breadth; the closed 10 §12 set is the universe. An UNKNOWN
  event name still refuses loudly (enum validation, 11 §14).
- ``url`` is an opaque bounded string. Scheme/reachability validation is
  DELIVERY-side policy (outbound I/O, not claimed here — 41 §49); the
  contract stores what the caller registered.
- The subscription carries ``tenant_id`` so delivery stays tenant-scoped
  (20 §6): a subscription only ever receives its OWN tenant's events.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.execute import WebhookEventType


class WebhookSubscriptionRequest(ContractModel):
    """POST /v1/webhooks request body (recorded shape — see module header)."""

    url: BoundedStr
    events: list[WebhookEventType] | None = None


class WebhookSubscription(ContractModel):
    """A registered webhook subscription (tenant-scoped record)."""

    id: UUID
    tenant_id: UUID
    url: BoundedStr
    events: list[WebhookEventType] = Field(min_length=1)


class WebhookSubscriptionResponse(ContractModel):
    """POST /v1/webhooks 201 body — the created subscription, sans tenant.

    ``tenant_id`` never rides the response: the caller IS the tenant
    (principal-scoped), and echoing internal tenant ids adds enumeration
    surface for nothing (20 §6 posture).
    """

    id: BoundedStr
    url: BoundedStr
    events: list[WebhookEventType] = Field(min_length=1)

    @classmethod
    def from_subscription(cls, sub: WebhookSubscription) -> WebhookSubscriptionResponse:
        return cls(id=str(sub.id), url=sub.url, events=list(sub.events))
