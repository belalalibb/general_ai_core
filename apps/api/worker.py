"""Async execution worker handler (Vision V2) — consumer over core seams.

The 40 §4.2 chain's last hop: the EXISTING core Worker (consume →
deduplicate → process → settle) drives this handler; the handler replays
the admitted request the API staged and stores the terminal report where
GET /v1/executions/{id} already reads (P2: the worker is a CONSUMER of
core services — it re-implements nothing).

Design decisions (recorded):

- The message carries the VERBATIM contract request + the COMPOSED
  execution payload the API built under the original admission. The
  handler re-validates the request (P7: queue content is still input) and
  re-ROUTES at execution time — a RoutingDecision is a point-in-time
  selection (11 §16); only the POLICY rides the queue.
- The pre-assigned execution id (the id the API acked and placeholdered)
  reaches ExecutionService through its EXISTING ``id_factory`` seam via
  ``service_factory(execution_id)`` — the composition root owns that
  bridge; ``execute_single``'s signature is untouched (zero core changes).
- Error taxonomy (40 §4.6, mapped to the core Worker's contract):
  * Malformed/unparseable message → :class:`PermanentTaskError` — a
    request-indicting failure; retrying cannot succeed → dead-letter.
  * Routing/budget denials → the execution FAILS (a terminal report is
    stored so the poll URL explains it) and the message is settled as
    processed — the DENIAL is the outcome, not a transport fault.
  * Provider failures inside execute_single already produce a FAILED
    report (the service's own taxonomy) — stored, settled.
  * Anything else (infrastructure faults) propagates — the core Worker
    leaves the message pending and ``claim_stale`` retries (its recorded
    transient path).
- Deduplication is the core Worker's duty (it checks IdempotencyPort
  BEFORE this handler runs); the handler stays single-purpose.
- V6 chunk 3: terminal webhook events (execution.succeeded /
  execution.failed, 10 §12) are staged AFTER the terminal report is
  stored — both terminal-report sites (the normal path and
  ``_store_denied``). The seams are OPTIONAL constructor kwargs
  defaulting to ``None`` (P2 — zero behavior change when absent):
  ``outbox`` (the SAME durable OutboxPort the delivery relay drains)
  and ``subscriptions`` (a lookup ``tenant_id -> rows``, the SAME
  tenant-scoped map/binding the registration route writes). Staging
  rides ``stage_execution_event`` — URL re-admission included (P7).
  A staging fault after the report is stored propagates → the core
  Worker leaves the message pending → claim_stale retries; the
  webhook idempotency key (one per subscription×event×execution)
  makes the retry safe, and re-running the execute itself under the
  pre-assigned id overwrites the same stored record (put is an
  id-keyed upsert), so the retry path stays terminally convergent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from uuid import UUID

from pydantic import ValidationError

from apps.api.store import InMemoryExecutionStore
from core.contracts.base import JsonObject, utc_now
from core.contracts.errors import ErrorCode
from core.contracts.execute import (
    ExecuteRequest,
    ExecutionStatus,
    WebhookEventType,
)
from core.contracts.execution import Execution, ExecutionStrategy
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.contracts.webhooks import WebhookSubscription
from core.events import stage_execution_event
from core.execution.service import ExecutionReport, ExecutionService
from core.routing.errors import FallbackNotConfigured, NoEligibleCandidates
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.runtime.outbox import OutboxPort
from core.runtime.ports import QueueMessage
from core.runtime.worker import PermanentTaskError
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured


class ExecutionMessageHandler:
    """One staged execute message → one stored terminal ExecutionReport."""

    def __init__(
        self,
        *,
        router: SimpleScoringRouter,
        service_factory: Callable[[UUID], ExecutionService],
        store: InMemoryExecutionStore,
        outbox: OutboxPort | None = None,
        subscriptions: Mapping[UUID, list[WebhookSubscription]] | None = None,
    ) -> None:
        """``service_factory`` returns an ExecutionService whose
        ``id_factory`` yields EXACTLY the given execution id — the
        composition-root bridge that keeps the acked id and the stored
        record identical without touching core signatures.

        ``outbox`` + ``subscriptions`` (V6 chunk 3, both optional): when
        BOTH are bound, terminal webhook events are staged after the
        terminal report is stored; either absent ⇒ zero behavior change
        (the pre-V6 handler verbatim)."""
        self._router = router
        self._service_factory = service_factory
        self._store = store
        self._outbox = outbox
        self._subscriptions = subscriptions

    async def __call__(self, message: QueueMessage) -> None:
        fields = self._parse(message)
        execution_id, tenant_id, user_id, request, payload, conversation_id = fields

        # --- route AT EXECUTION TIME (11 §16) --------------------------------
        try:
            decision = self._router.route(
                RoutingRequest(
                    operation=ProviderOperation.GENERATE_TEXT,
                    model_policy=request.model_policy,
                )
            )
        except (UnsupportedPolicyType, NoEligibleCandidates, FallbackNotConfigured) as exc:
            # The denial IS the outcome: store a FAILED terminal record so
            # the poll URL explains it, settle the message as processed.
            await self._store_denied(
                execution_id,
                tenant_id,
                user_id,
                conversation_id,
                message,
                reason=ErrorCode.MODEL_UNAVAILABLE.value,
                detail=str(exc),
            )
            return

        service = self._service_factory(execution_id)
        try:
            report = await service.execute_single(
                tenant_id=tenant_id,
                user_id=user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=message.payload["request_hash"],
                idempotency_key=message.payload.get("idempotency_key"),
                conversation_id=conversation_id,
            )
        except (BudgetExceeded, EntitlementNotConfigured) as exc:
            await self._store_denied(
                execution_id,
                tenant_id,
                user_id,
                conversation_id,
                message,
                reason=ErrorCode.ENTITLEMENT_EXCEEDED.value,
                detail=str(exc),
            )
            return
        # Provider failures are already a FAILED report (service taxonomy);
        # infrastructure faults propagate → core Worker leaves pending.
        self._store.put(report)
        # V6 chunk 3: terminal event AFTER the stored truth exists (P6 —
        # the webhook narrates the record, never precedes it).
        event = (
            WebhookEventType.EXECUTION_SUCCEEDED
            if report.execution.status is ExecutionStatus.SUCCEEDED
            else WebhookEventType.EXECUTION_FAILED
        )
        await self._stage_terminal_event(event, execution_id, tenant_id)

    # --- internals -------------------------------------------------------------

    @staticmethod
    def _parse(
        message: QueueMessage,
    ) -> tuple[UUID, UUID, UUID, ExecuteRequest, JsonObject, UUID | None]:
        """Decode and re-validate the staged message (P7 — still input).

        Any malformed field is request-indicting: PermanentTaskError →
        the core Worker dead-letters (retrying cannot succeed).
        """
        try:
            execution_id = UUID(message.payload["execution_id"])
            tenant_id = UUID(message.payload["tenant_id"])
            user_id = UUID(message.payload["user_id"])
            request = ExecuteRequest.model_validate_json(message.payload["request"])
            payload: JsonObject = json.loads(message.payload["payload"])
            raw_conversation = message.payload.get("conversation_id")
            conversation_id = (
                UUID(raw_conversation) if raw_conversation is not None else None
            )
            _ = message.payload["request_hash"]  # presence check (used later)
        except (KeyError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise PermanentTaskError(
                f"malformed execute message {message.message_id}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise PermanentTaskError(
                f"malformed execute message {message.message_id}: payload not an object"
            )
        return execution_id, tenant_id, user_id, request, payload, conversation_id

    async def _stage_terminal_event(
        self, event: WebhookEventType, execution_id: UUID, tenant_id: UUID
    ) -> None:
        """Stage a 10 §12 terminal event for the tenant's subscriptions.

        Both seams must be bound (constructor docstring); no matching
        subscription ⇒ nothing staged — silence, not failure. A staging
        fault propagates (module-header taxonomy: retry-safe by key).
        """
        if self._outbox is None or self._subscriptions is None:
            return
        rows = self._subscriptions.get(tenant_id, [])
        if not rows:
            return
        await stage_execution_event(
            self._outbox,
            rows,
            event=event,
            execution_id=str(execution_id),
            tenant_id=str(tenant_id),
            timestamp=utc_now(),
        )

    async def _store_denied(
        self,
        execution_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        conversation_id: UUID | None,
        message: QueueMessage,
        *,
        reason: str,
        detail: str,
    ) -> None:
        """Terminal FAILED record for a denied async execution.

        The safe reason code + detail ride the cost_snapshot as data —
        the poll endpoint's failure mapping stays fully usable and no
        internals leak beyond what the sync path already returns.
        """
        now = utc_now()
        report = ExecutionReport(
            execution=Execution(
                id=execution_id,
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request_hash=message.payload["request_hash"],
                idempotency_key=message.payload.get("idempotency_key"),
                status=ExecutionStatus.FAILED,
                strategy=ExecutionStrategy.SINGLE,
                cost_snapshot={"denied": {"reason": reason, "detail": detail}},
                created_at=now,
                completed_at=now,
            ),
            nodes=(),
            status_history=(
                ExecutionStatus.QUEUED,
                ExecutionStatus.FAILED,
            ),
        )
        self._store.put(report)
        # V6 chunk 3: a denial is terminal truth too — execution.failed.
        await self._stage_terminal_event(
            WebhookEventType.EXECUTION_FAILED, execution_id, tenant_id
        )
