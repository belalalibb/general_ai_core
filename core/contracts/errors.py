"""Unified error contract.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md §9
(Unified Error Format + Error Categories). Carried exactly — no category added,
renamed, or dropped.

Wire shape (10 §9):

.. code-block:: json

    {
      "error": {
        "code": "capability_denied",
        "message": "This tool is not allowed for the current user or plan.",
        "retryable": false,
        "details": {"capability": "github.pr.merge"},
        "trace_id": "trace-id"
      }
    }
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject, TraceId


class ErrorCode(StrEnum):
    """The 11 unified error categories (10 §9) — verbatim, closed set."""

    VALIDATION_ERROR = "validation_error"
    UNAUTHENTICATED = "unauthenticated"
    UNAUTHORIZED = "unauthorized"
    ENTITLEMENT_EXCEEDED = "entitlement_exceeded"
    CAPABILITY_DENIED = "capability_denied"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    TOOL_APPROVAL_REQUIRED = "tool_approval_required"
    RATE_LIMITED = "rate_limited"
    EXECUTION_FAILED = "execution_failed"
    INTERNAL_ERROR = "internal_error"


class ErrorDetail(ContractModel):
    """The ``error`` object of the unified error format (10 §9)."""

    code: ErrorCode
    message: BoundedStr
    retryable: bool
    details: JsonObject = Field(default_factory=dict)
    trace_id: TraceId | None = None


class ErrorEnvelope(ContractModel):
    """Top-level unified error response body: ``{"error": {...}}`` (10 §9)."""

    error: ErrorDetail
