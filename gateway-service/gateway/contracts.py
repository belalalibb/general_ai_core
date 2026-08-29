"""Canonical Gateway Contract — Layer 3 of the three-layer provider model.

ADR-0008 (ACCEPTED 2026-08-29). This module is the SINGLE code source of
truth for the wire contract. ``docs/CONTRACT.md`` is the human-readable
mirror; a parity test (tests/test_contract_parity.py) keeps them aligned.
THIS FILE is authoritative when they disagree.

THREE-LAYER PROVIDER MODEL (mandatory architectural rule):

    Layer 1 — Internal Provider Implementation: 100% FREE. The contract
              imposes NOTHING on a provider's internal file layout, module
              count, classes, orchestration, SDK choice, auth mechanism
              (OAuth/session/cookies), account pools/rotation, caching, or
              internal call chaining. One gateway request may internally
              produce N upstream calls + internal fallback + renormalization
              — all invisible to the platform. (Gateway-level retries remain
              ZERO in v1 — billing integrity, ADR-0008 §usage.)
    Layer 2 — Provider Facade (mandatory): the ONLY layer the gateway sees.
              Receives a ProviderContext; returns EITHER a canonical success
              (FacadeResult with output/usage) OR a canonical error mapped to
              one of the 12 categories. No third shape exists.
    Layer 3 — THIS contract: RequestEnvelope / ResponseEnvelope / the
              12-category error taxonomy (verbatim from the platform's
              core/contracts/provider.py ProviderErrorCategory) / usage
              shape / security headers / HTTP status map. Fixed for all
              providers; never extended by a provider.

Security rules (wire level):
    - X-Gateway-Secret + X-Gateway-Secret-Version on every authed call.
    - X-Route-Token HEADER on all surfaces including GET/discovery —
      NEVER in a URL path or query string (OPEN-3).
    - route_token / slug / upstream identity never appear in responses,
      logs, or error messages.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------- #
# Base model: closed shapes only                                              #
# --------------------------------------------------------------------------- #


class ContractModel(BaseModel):
    """All wire shapes are closed: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# Operations — platform-led closed set                                        #
# --------------------------------------------------------------------------- #


class GatewayOperation(StrEnum):
    """Operations supported by Gateway v1 — 8 of the platform's 11.

    Verbatim subset of the platform's ``ProviderOperation`` (30 §5).
    OPEN-2 (ADR-0008): ``run_provider_agent``, ``upload_asset`` and
    ``download_asset`` are EXCLUDED from v1 — no implementation, no API
    surface. A DEFINITION declaring any of them is rejected at load time
    (see ``EXCLUDED_OPERATIONS``).
    """

    GENERATE_TEXT = "generate_text"
    GENERATE_IMAGE = "generate_image"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    SYNTHESIZE_SPEECH = "synthesize_speech"
    CREATE_EMBEDDINGS = "create_embeddings"
    RERANK_DOCUMENTS = "rerank_documents"
    MODERATE_CONTENT = "moderate_content"
    ANALYZE_VISION = "analyze_vision"


EXCLUDED_OPERATIONS: frozenset[str] = frozenset(
    {"run_provider_agent", "upload_asset", "download_asset"}
)
"""Platform operations that exist but are OUT of Gateway v1 (OPEN-2).

Declaring one of these in a provider DEFINITION is a LOAD-TIME error —
honest refusal instead of silent partial support.
"""


# --------------------------------------------------------------------------- #
# Error taxonomy — 12 categories VERBATIM from the platform contract          #
# --------------------------------------------------------------------------- #


class ErrorCategory(StrEnum):
    """Normalized error categories — 12 values, verbatim.

    Copied verbatim from the platform's
    ``core/contracts/provider.py::ProviderErrorCategory`` (30 §14).
    PLATFORM-LED ALWAYS: the gateway conforms and never extends this set.
    A provider facade MUST map every failure to exactly one of these.
    """

    AUTH_EXPIRED = "auth_expired"
    INVALID_CREDENTIAL = "invalid_credential"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    BAD_REQUEST = "bad_request"
    CONTENT_REJECTED = "content_rejected"
    TIMEOUT = "timeout"
    RETRYABLE_SERVER_ERROR = "retryable_server_error"
    NON_RETRYABLE_ERROR = "non_retryable_error"


class GatewayError(ContractModel):
    """The ONLY error shape that crosses the wire.

    ``message`` must be safe (no upstream internals, no exception class
    names, no secrets). ``provider_code`` carries a SANITIZED raw code for
    diagnostics only (digits/short tokens — never exception repr).
    """

    category: ErrorCategory
    retryable: bool
    message: str = Field(min_length=1, max_length=500)
    retry_after_ms: int | None = Field(default=None, ge=0)
    provider_code: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------- #
# Credential                                                                  #
# --------------------------------------------------------------------------- #


class CredentialMode(StrEnum):
    """Who supplies the upstream credential (ADR-0008 credential/BYOK model).

    user_key: resolved PLATFORM-side, crosses TLS inside the envelope,
              memory-only on the gateway — never persisted, never logged.
    platform: resolved INTERNALLY by the gateway, keyed by slug — never
              from the request; the platform never learns the kind.
    """

    USER_KEY = "user_key"
    PLATFORM = "platform"


class EnvelopeCredential(ContractModel):
    """``credential`` block of the request envelope.

    ``mode`` MUST match the provider DEFINITION or the request fails as
    ``bad_request``. ``value`` is present ONLY for ``user_key``.
    """

    mode: CredentialMode
    value: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def _value_matches_mode(self) -> EnvelopeCredential:
        # Explicit validation, never `assert` (deleted under python -O).
        if self.mode is CredentialMode.USER_KEY and self.value is None:
            msg = "credential.value is required when mode is user_key"
            raise ValueError(msg)
        if self.mode is CredentialMode.PLATFORM and self.value is not None:
            msg = "credential.value must be absent when mode is platform"
            raise ValueError(msg)
        return self


# --------------------------------------------------------------------------- #
# Request / Response envelopes                                                #
# --------------------------------------------------------------------------- #


class RequestEnvelope(ContractModel):
    """Wire request for ``POST /v1/execute`` (OPEN-1: unified endpoint).

    ``operation`` inside the envelope is the SINGLE source of truth — v1
    has no per-operation routes. Forbidden by construction (extra=forbid):
    ``provider_slug``, ``upstream_url`` or any gateway-internal identifier —
    the envelope cannot address a provider except via the route token,
    which itself travels in the X-Route-Token HEADER (OPEN-3), not here.
    """

    operation: GatewayOperation
    model: str = Field(min_length=1, max_length=256)
    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    credential: EnvelopeCredential
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(ge=1, le=600_000)


class Usage(ContractModel):
    """Raw usage evidence — the gateway reports, the PLATFORM bills.

    The gateway has no plans, no ledger, no tenant records; it is
    structurally incapable of billing (ADR-0008 usage/billing authority).
    """

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    units: int = Field(default=1, ge=0)


class ResponseEnvelope(ContractModel):
    """Wire response for ``POST /v1/execute``.

    HTTP 200 carries BOTH success and EXECUTION failures — the caller reads
    ``error.category`` (mirrors the platform's
    ``ProviderGenerateResponse.succeeded`` discipline). Exactly one of
    ``output``/``error`` is meaningful.
    """

    succeeded: bool
    output: dict[str, Any] | None = None
    usage: Usage | None = None
    latency_ms: int = Field(ge=0)
    error: GatewayError | None = None

    @model_validator(mode="after")
    def _one_of_output_error(self) -> ResponseEnvelope:
        if self.succeeded and self.error is not None:
            msg = "succeeded response must not carry an error"
            raise ValueError(msg)
        if not self.succeeded and self.error is None:
            msg = "failed response must carry a GatewayError"
            raise ValueError(msg)
        return self


# --------------------------------------------------------------------------- #
# HTTP status map (fixed, ADR-0008 / report §9)                               #
# --------------------------------------------------------------------------- #

HTTP_STATUS_MAP: dict[int, str] = {
    200: "envelope delivered (success OR execution failure — read error.category)",
    400: "malformed envelope -> bad_request",
    401: (
        "gateway auth failure (wrong secret=invalid_credential; "
        "stale version=auth_expired retryable)"
    ),
    404: "unknown/revoked/disabled route token -> uniform provider_unavailable 'unknown route'",
    500: "gateway internal fault -> retryable_server_error, sanitized provider_code",
}

UNKNOWN_ROUTE_BODY: dict[str, Any] = {
    "error": {
        "category": "provider_unavailable",
        "retryable": False,
        "message": "unknown route",
    }
}
"""Anti-enumeration: IDENTICAL body for unknown, revoked AND disabled tokens."""


# --------------------------------------------------------------------------- #
# Provider DEFINITION — sole eligibility source (deny-by-default)             #
# --------------------------------------------------------------------------- #

CAPABILITY_KEYS: frozenset[str] = frozenset(
    {
        "chat",
        "reasoning",
        "code",
        "vision_input",
        "image_generation",
        "audio_input",
        "audio_output",
        "file_upload",
        "browser",
        "agent_module",
        "embeddings",
        "rerank",
        "moderation",
        "tool_use",
    }
)
"""Closed capability key set — verbatim from the platform's
``ProviderCapabilities`` (core/contracts/provider.py). New keys are a
contract change, never a silent addition."""

_SEMVER_PARTS = 3


class DeclaredModel(ContractModel):
    """One declared model. ``[]`` overall is honest and valid."""

    name: str = Field(min_length=1, max_length=256)
    context_window: int | None = Field(default=None, ge=1)


class ProviderDefinition(ContractModel):
    """Provider DEFINITION — the registry trusts ONLY this declaration.

    Never introspection: "code exists" != "capability declared". An
    operation declared without a registered facade handler (or a handler
    without declaration) is a STARTUP failure, not a runtime 500.

    ``display_name`` is the ONLY name that may cross the boundary
    (5-layer identity model, ADR-0008): the internal slug NEVER crosses.
    """

    display_name: str = Field(min_length=1, max_length=200)
    definition_version: str = Field(min_length=1, max_length=32)
    credential_mode: CredentialMode
    capabilities: dict[str, bool] = Field(default_factory=dict)
    operations: list[GatewayOperation] = Field(min_length=1)
    models: list[DeclaredModel] = Field(default_factory=list)
    health_supported: bool = False

    @model_validator(mode="after")
    def _validate_definition(self) -> ProviderDefinition:
        parts = self.definition_version.split(".")
        if len(parts) != _SEMVER_PARTS or not all(p.isdigit() for p in parts):
            msg = f"definition_version must be semver X.Y.Z, got {self.definition_version!r}"
            raise ValueError(msg)
        unknown = set(self.capabilities) - CAPABILITY_KEYS
        if unknown:
            msg = f"unknown capability keys (closed set): {sorted(unknown)}"
            raise ValueError(msg)
        if len(set(self.operations)) != len(self.operations):
            msg = "duplicate operations in DEFINITION"
            raise ValueError(msg)
        return self


def reject_excluded_operations(raw_operations: list[str]) -> None:
    """LOAD-TIME rejection of OPEN-2 excluded operations.

    Called by the provider registry BEFORE pydantic parsing so the error
    names the policy (OPEN-2) instead of a generic enum failure.
    """

    excluded = sorted(set(raw_operations) & EXCLUDED_OPERATIONS)
    if excluded:
        msg = (
            f"operations {excluded} are excluded from Gateway v1 (ADR-0008 OPEN-2); "
            "a DEFINITION declaring them is rejected at load time"
        )
        raise ValueError(msg)


# --------------------------------------------------------------------------- #
# Provider-facing shapes (Layer 2 boundary)                                   #
# --------------------------------------------------------------------------- #


class ProviderContext(ContractModel):
    """What a provider facade receives — and ALL it receives.

    Deliberately hides: slug, route_token, gateway secret, caller network
    identity. ``credential_value`` is set for user_key mode (memory-only);
    for platform mode the facade resolves credentials internally.
    ``tenant_id`` is evidence/audit only — facades make ZERO decisions on it.
    """

    operation: GatewayOperation
    model: str
    request_id: str
    tenant_id: str
    credential_mode: CredentialMode
    credential_value: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(ge=1)


class FacadeResult(ContractModel):
    """What a provider facade returns — and the ONLY thing it may return.

    Either a canonical success (``output`` + optional ``usage``) or a
    canonical ``error`` in one of the 12 categories. No third shape.
    """

    succeeded: bool
    output: dict[str, Any] | None = None
    usage: Usage | None = None
    error: GatewayError | None = None

    @model_validator(mode="after")
    def _one_of(self) -> FacadeResult:
        if self.succeeded and (self.output is None or self.error is not None):
            msg = "successful FacadeResult requires output and no error"
            raise ValueError(msg)
        if not self.succeeded and self.error is None:
            msg = "failed FacadeResult requires a GatewayError"
            raise ValueError(msg)
        return self


# --------------------------------------------------------------------------- #
# Discovery projections (/v1/describe, /v1/models, /v1/health)                #
# --------------------------------------------------------------------------- #


class DescribeResponse(ContractModel):
    """/v1/describe projection — NO slug, NO upstream identity, ever."""

    display_name: str
    credential_mode: CredentialMode
    capabilities: dict[str, bool]
    operations: list[GatewayOperation]
    models: list[DeclaredModel]
    definition_version: str
    health_supported: bool


class ModelsResponse(ContractModel):
    """/v1/models — cheap subset of describe."""

    models: list[DeclaredModel]


class HealthResponse(ContractModel):
    """/v1/health — provider-level health; UNKNOWN is a legal answer."""

    status: Literal["OK", "DEGRADED", "DOWN", "UNKNOWN"]
    checked_at: str | None = None


# --------------------------------------------------------------------------- #
# Security header names (single definition point)                             #
# --------------------------------------------------------------------------- #

HEADER_GATEWAY_SECRET = "X-Gateway-Secret"
HEADER_GATEWAY_SECRET_VERSION = "X-Gateway-Secret-Version"
HEADER_ROUTE_TOKEN = "X-Route-Token"  # header ALWAYS — never URL (OPEN-3)
