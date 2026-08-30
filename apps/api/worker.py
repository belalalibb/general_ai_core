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
"""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID

from pydantic import ValidationError

from apps.api.store import InMemoryExecutionStore
from core.contracts.base import JsonObject, utc_now
from core.contracts.errors import ErrorCode
from core.contracts.execute import ExecuteRequest, ExecutionStatus
from core.contracts.execution import Execution, ExecutionStrategy
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.execution.service import ExecutionReport, ExecutionService
from core.routing.errors import FallbackNotConfigured, NoEligibleCandidates
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
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
    ) -> None:
        """``service_factory`` returns an ExecutionService whose
        ``id_factory`` yields EXACTLY the given execution id — the
        composition-root bridge that keeps the acked id and the stored
        record identical without touching core signatures."""
        self._router = router
        self._service_factory = service_factory
        self._store = store

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
            self._store_denied(
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
            self._store_denied(
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

    def _store_denied(
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
