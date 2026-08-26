"""FastAPI composition root — POST /v1/execute + GET /v1/executions/{id}.

MVP Phase 5 slice 3 (T-IMPL-023; 41 §44 API surface; 10 §2-§5 contracts).
ADR-0001: FastAPI lives ONLY here in apps/ — core/ and providers/ stay
framework-free (import-linter contract in pyproject.toml, landed with the
dependency pin in the same commit).

The app is a pure composition of already-verified core services:

    ExecuteRequest (10 §2)  ->  SimpleScoringRouter (T-IMPL-021)
                            ->  ExecutionService    (T-IMPL-022)
                            ->  ExecuteSyncResponse / unified error (10 §3/§9)

Scope decisions for this slice (loud rejections, never silent degradation):

- Sync execution only. ``execution_policy.async=true`` and ``stream=true``
  are REJECTED with ``validation_error`` — the durable async runtime and
  streaming belong to later phases (12 §9; 10 §11) and are not faked.
- Text surface: requests route as ``generate_text`` (30 §5); mode stays a
  free-form hint (10 §2) and does not change the operation in this slice.
- Authentication is a later MVP phase; the composition injects a fixed
  dev tenant/user principal. The seam (``principal`` parameter) is where
  the auth dependency will plug in without touching handlers.
- Idempotency (10 §10): same tenant + same ``Idempotency-Key`` header
  returns the SAME execution instead of creating a duplicate.
- Persistence is the process-local InMemoryExecutionStore (slice decision
  recorded in PROJECT_EXECUTION_STATE.md); repository-backed storage swaps
  in at the composition root without handler changes.
- Usage accounting (T-IMPL-024; 10 §3 ``usage`` block): when the injected
  ExecutionService carries a UsageAccountingPort, entitlement denials
  (missing budget / budget exceeded) map to the unified
  ``entitlement_exceeded`` code (10 §9, HTTP 403) BEFORE any provider work,
  and successful responses surface the settled ledger as the ``usage``
  block. A service without accounting keeps ``usage`` absent — never faked.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.api.errors import (
    HTTP_STATUS_BY_CODE,
    error_response,
    execution_failure_detail,
)
from apps.api.store import ExecutionNotFound, InMemoryExecutionStore
from core.contracts.base import JsonObject
from core.contracts.errors import ErrorCode
from core.contracts.execute import (
    ExecuteRequest,
    ExecuteSyncResponse,
    ExecutionProgress,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStatusResponse,
    UsageReport,
)
from core.contracts.provider import ProviderError, ProviderOperation
from core.contracts.routing import RoutingRequest
from core.contracts.usage import UsageLedger
from core.execution.service import ExecutionReport, ExecutionService
from core.routing.errors import (
    FallbackNotConfigured,
    NoEligibleCandidates,
)
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity — the seam the auth phase will fill."""

    tenant_id: UUID
    user_id: UUID


def _request_hash(payload: ExecuteRequest) -> str:
    """Deterministic content hash of the request (03 §5 Execution.request_hash)."""
    canonical = json.dumps(
        payload.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result_from_output(output: JsonObject, format_hint: str | None) -> ExecutionResult:
    """Shape the final node output as the 10 §3 ``result`` object.

    Adapters return normalized JSON objects; when the output carries a string
    ``content`` field it is surfaced verbatim, otherwise the whole object is
    serialized — the API never invents content.
    """
    content = output.get("content")
    if not isinstance(content, str):
        content = json.dumps(output, sort_keys=True)
    return ExecutionResult(
        type="message",
        content=content,
        format=format_hint,
        artifacts=[],
    )


def _progress(report: ExecutionReport) -> ExecutionProgress:
    """Stage-completion progress for GET /v1/executions/{id} (10 §5).

    This slice runs executions synchronously, so stored reports are always
    terminal — every node is in a terminal state and percent is 100 for any
    non-empty report. The shape still honors 10 §5 so an async runtime can
    reuse it unchanged.
    """
    terminal = ("succeeded", "failed", "skipped")
    total = len(report.nodes)
    done = sum(1 for entry in report.nodes if entry.node.status.value in terminal)
    percent = int(round(100 * done / total)) if total else None
    current = report.nodes[-1].node.node_key if report.nodes else None
    return ExecutionProgress(current_stage=current, percent=percent)


def _usage_report(ledger: UsageLedger | None) -> UsageReport | None:
    """Shape the settled ledger as the 10 §3 ``usage`` block (absent if none).

    The ledger carries floats (estimates may be fractional in later plans);
    the 10 §3 block is whole task units — int conversion is exact for the
    MVP metric (1 unit per stage) and any fractional policy would change
    the contract first, not silently truncate here.
    """
    if ledger is None:
        return None
    return UsageReport(
        units_reserved=int(ledger.units_reserved),
        units_settled=int(ledger.units_settled),
        details={"status": ledger.status.value},
    )


def _last_provider_error(report: ExecutionReport) -> ProviderError | None:
    for node_report in reversed(report.nodes):
        for attempt in reversed(node_report.attempts):
            if attempt.error is not None:
                return attempt.error
    return None


def create_app(
    *,
    router: SimpleScoringRouter,
    execution_service: ExecutionService,
    store: InMemoryExecutionStore | None = None,
    principal: Principal,
) -> FastAPI:
    """Build the API application from injected, already-verified services."""
    app = FastAPI(title="AI Orchestration Platform", version="0.1.0", docs_url=None)
    execution_store = store if store is not None else InMemoryExecutionStore()
    # Idempotency index (10 §10): (tenant_id, key) -> execution_id.
    idempotency_index: dict[tuple[UUID, str], UUID] = {}

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request body failed contract validation.",
            details={"errors": [str(err.get("msg", "")) for err in exc.errors()]},
        )

    @app.exception_handler(Exception)
    async def _internal_handler(_request: Request, _exc: Exception) -> JSONResponse:
        # 20 §4: internals never leak to clients.
        return error_response(
            ErrorCode.INTERNAL_ERROR, "Internal error.", retryable=False
        )

    @app.post("/v1/execute")
    async def execute(
        body: ExecuteRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Response:
        # --- loud scope rejections (module docstring posture) ------------------
        policy = body.execution_policy
        if policy is not None and policy.async_ is True:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Async execution is not available on this deployment slice.",
                details={"field": "execution_policy.async"},
            )
        if policy is not None and policy.stream is True:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Streaming is not available on this deployment slice.",
                details={"field": "execution_policy.stream"},
            )
        conversation_id: UUID | None = None
        if body.conversation_id is not None:
            try:
                conversation_id = UUID(body.conversation_id)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "conversation_id must be a UUID.",
                    details={"field": "conversation_id"},
                )

        # --- idempotent replay (10 §10) ----------------------------------------
        if idempotency_key is not None:
            replay_id = idempotency_index.get((principal.tenant_id, idempotency_key))
            if replay_id is not None:
                return _sync_response(execution_store.get(replay_id), body)

        # --- route (11; Router decides) ----------------------------------------
        routing_request = RoutingRequest(
            operation=ProviderOperation.GENERATE_TEXT,
            model_policy=body.model_policy,
        )
        try:
            decision = router.route(routing_request)
        except UnsupportedPolicyType as exc:
            return error_response(
                ErrorCode.VALIDATION_ERROR, str(exc), details={"field": "model_policy"}
            )
        except NoEligibleCandidates as exc:
            return error_response(
                ErrorCode.MODEL_UNAVAILABLE,
                "No eligible model candidates for this request.",
                details={
                    "excluded": [
                        record.model_dump(mode="json", exclude_none=True)
                        for record in exc.excluded
                    ]
                },
            )
        except FallbackNotConfigured as exc:
            return error_response(ErrorCode.MODEL_UNAVAILABLE, str(exc))

        # --- execute (02 invariant 5: Execution executes) -----------------------
        payload: JsonObject = {"ask": body.ask}
        if body.output is not None:
            payload["output"] = body.output.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        try:
            report = await execution_service.execute_single(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=_request_hash(body),
                idempotency_key=idempotency_key,
                conversation_id=conversation_id,
            )
        except BudgetExceeded as exc:
            # Denied BEFORE any provider work (03 §7; 10 §9). The accounting
            # facts explain the denial without leaking other tenants' data.
            return error_response(
                ErrorCode.ENTITLEMENT_EXCEEDED,
                "Task-unit budget exceeded for this request.",
                details={"requested": exc.requested, "remaining": exc.remaining},
            )
        except EntitlementNotConfigured:
            # Deny-by-default (20 §4): no budget configured means DENY, and
            # the client-facing message stays generic.
            return error_response(
                ErrorCode.ENTITLEMENT_EXCEEDED,
                "No task-unit entitlement is configured for this tenant.",
            )
        execution_store.put(report)
        if idempotency_key is not None:
            idempotency_index[(principal.tenant_id, idempotency_key)] = (
                report.execution.id
            )
        return _sync_response(report, body)

    def _sync_response(report: ExecutionReport, body: ExecuteRequest) -> Response:
        if report.execution.status is ExecutionStatus.SUCCEEDED:
            output = report.final_output
            assert output is not None  # succeeded => last node has output
            format_hint = body.output.format if body.output is not None else None
            sync = ExecuteSyncResponse(
                execution_id=str(report.execution.id),
                status=report.execution.status,
                result=_result_from_output(output, format_hint),
                usage=_usage_report(report.usage),
                evaluation=None,
            )
            return JSONResponse(
                status_code=200,
                content=sync.model_dump(mode="json", exclude_none=True),
            )
        # Failed execution: unified error (10 §9) carrying the execution id so
        # GET /v1/executions/{id} remains fully usable for diagnosis.
        detail = execution_failure_detail(
            str(report.execution.id), _last_provider_error(report)
        )
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CODE[detail.code],
            content={"error": detail.model_dump(mode="json", exclude_none=True)},
        )

    @app.get("/v1/executions/{execution_id}")
    async def execution_status(execution_id: str) -> Response:
        try:
            parsed = UUID(execution_id)
        except ValueError:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "execution id must be a UUID.",
                details={"field": "execution_id"},
            )
        try:
            report = execution_store.get(parsed)
        except ExecutionNotFound:
            # Closed 10 §9 code set has no not_found; mapping decision in
            # apps/api/errors.py — validation_error body with HTTP 404.
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown execution id.",
                details={"execution_id": execution_id},
                http_status=404,
            )

        status = report.execution.status
        result = None
        error_detail = None
        if status is ExecutionStatus.SUCCEEDED and report.final_output is not None:
            result = _result_from_output(report.final_output, None)
        elif status is ExecutionStatus.FAILED:
            error_detail = execution_failure_detail(
                execution_id, _last_provider_error(report)
            )
        status_response = ExecutionStatusResponse(
            execution_id=execution_id,
            status=status,
            progress=_progress(report),
            result=result,
            error=error_detail,
        )
        return JSONResponse(
            status_code=200,
            content=status_response.model_dump(mode="json", exclude_none=True),
        )

    return app
