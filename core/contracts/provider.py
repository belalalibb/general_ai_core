"""Provider contract — manifest, health, rate-limit state, error normalization,
and the §8 operation payloads (generate request/response, credential health,
health scope, discovered bindings).

Contract authority:
docs/ai_orchestration_pack/final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md
— §4 (capability-driven providers, common minimum), §5 (capability-specific
operations), §7 (provider manifest), §8 (adapter interface payload shapes),
§11 (health), §12 (rate-limit normalized state), §14 (error normalization).

This module is the *contract only* (data shapes the Core reasons about).
The ProviderAdapter behavioral interface itself (30 §8) lives in
``core/providers/ports.py`` (MVP Phase 4, T-IMPL-018); no network, no
provider implementations here.

Posture rules carried from 30:

- §4.2/§4.3: capabilities are declared, never assumed — undeclared operations
  make the provider ineligible for that task ("Unknown = ineligible", 11 §5).
- §11: provider health ≠ account health; one failed account never means the
  provider is down.
- §14: the Core makes decisions from normalized errors only; raw provider
  errors never cross the boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.domain import AuthType, CredentialStatus

# --- §5 capability-specific operations (closed set, verbatim) -------------------


class ProviderOperation(StrEnum):
    """Capability-specific provider operations (30 §5) — closed set, verbatim.

    A provider implements only the operations it declares. If an operation is
    not declared, the provider is ineligible for that task.
    """

    GENERATE_TEXT = "generate_text"
    GENERATE_IMAGE = "generate_image"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    SYNTHESIZE_SPEECH = "synthesize_speech"
    CREATE_EMBEDDINGS = "create_embeddings"
    RERANK_DOCUMENTS = "rerank_documents"
    MODERATE_CONTENT = "moderate_content"
    ANALYZE_VISION = "analyze_vision"
    RUN_PROVIDER_AGENT = "run_provider_agent"
    UPLOAD_ASSET = "upload_asset"
    DOWNLOAD_ASSET = "download_asset"


# --- §7 provider manifest ---------------------------------------------------------


class ManifestAuth(ContractModel):
    """``auth`` block of the provider manifest (30 §7)."""

    types: list[AuthType] = Field(min_length=1)
    supports_refresh: bool = False


class ManifestAccountPool(ContractModel):
    """``account_pool`` block of the provider manifest (30 §7).

    Account pools are optional per provider (30 §10.1) — ``supported: false``
    is a fully valid declaration.
    """

    supported: bool
    lease_required: bool = False
    fencing_required: bool = False


class ManifestModels(ContractModel):
    """``models`` block of the provider manifest (30 §7).

    30 §4.3: never assume every provider has models. ``discovery: none`` with
    an empty ``static_models`` list is valid.
    """

    discovery: BoundedStr  # e.g. "dynamic" | "static" | "none" (provider-declared)
    static_models: list[BoundedStr] = Field(default_factory=list)


class ManifestRateLimits(ContractModel):
    """``rate_limits`` block of the provider manifest (30 §7, §12).

    Rate limits are provider-specific — dimensions are declared by the
    provider (account/model/endpoint/time_window/... per 30 §12), never
    forced into one global model.
    """

    strategy: BoundedStr  # e.g. "provider_defined"
    dimensions: list[BoundedStr] = Field(default_factory=list)


class ManifestHealth(ContractModel):
    """``health`` block of the provider manifest (30 §7)."""

    checks: list[BoundedStr] = Field(default_factory=list)


class ManifestErrors(ContractModel):
    """``errors`` block of the provider manifest (30 §7)."""

    mapping: BoundedStr  # reference to the provider's error-map artifact


class ProviderCapabilities(ContractModel):
    """``capabilities`` declaration of the manifest (30 §7 example keys).

    Deny-by-default: every capability defaults to ``False``; a provider only
    has what it explicitly declares (30 §4.3 forbidden assumptions).
    ``extra="forbid"`` (ContractModel) keeps the key set closed — new
    capability keys are a contract change, not a silent addition.
    """

    chat: bool = False
    reasoning: bool = False
    code: bool = False
    vision_input: bool = False
    image_generation: bool = False
    audio_input: bool = False
    audio_output: bool = False
    file_upload: bool = False
    browser: bool = False
    agent_module: bool = False


class ProviderManifest(ContractModel):
    """Provider manifest (30 §7) — the provider's complete self-declaration.

    Covers the common minimum every provider must define (30 §4.1): identity,
    status, capabilities, auth policy, health contract, error-normalization
    contract. ``operations`` lists the §5 capability-specific operations the
    provider actually implements.
    """

    id: BoundedStr
    name: BoundedStr
    version: BoundedStr
    status: BoundedStr  # provider-declared lifecycle word, e.g. "active"
    auth: ManifestAuth
    account_pool: ManifestAccountPool
    capabilities: ProviderCapabilities
    operations: list[ProviderOperation] = Field(default_factory=list)
    models: ManifestModels
    rate_limits: ManifestRateLimits
    health: ManifestHealth
    errors: ManifestErrors


# --- §11 health -------------------------------------------------------------------


class ProviderHealthState(StrEnum):
    """Provider-wide health states (30 §11) — closed set, verbatim."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    SUSPENDED = "SUSPENDED"


class AccountHealthCheckState(StrEnum):
    """Account-level health-check states (30 §11) — closed set, verbatim.

    Distinct from the 7-value domain ``AccountLifecycleState`` (03 §4): this
    is the health-check surface, that is the stored lifecycle.
    """

    READY = "READY"
    COOLDOWN = "COOLDOWN"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    INVALID = "INVALID"


class ProviderHealth(ContractModel):
    """Health report for a provider (30 §11).

    ``accounts`` reports per-account states separately so "one account
    failed" can never be conflated with "the whole provider is down".
    """

    provider_id: BoundedStr
    state: ProviderHealthState
    accounts: dict[str, AccountHealthCheckState] = Field(default_factory=dict)
    checked_at: datetime | None = None
    detail: BoundedStr | None = None


# --- §12 normalized rate-limit state ------------------------------------------------


class RateLimitState(StrEnum):
    """Normalized rate-limit state (30 §12) — closed set, verbatim."""

    AVAILABLE = "available"
    LIMITED = "limited"
    COOLDOWN_UNTIL = "cooldown_until"
    UNKNOWN = "unknown"


class RateLimitStatus(ContractModel):
    """A provider's real limits translated into normalized state (30 §12)."""

    state: RateLimitState
    cooldown_until: datetime | None = None


# --- §14 error normalization ----------------------------------------------------------


class ProviderErrorCategory(StrEnum):
    """Normalized provider error categories (30 §14) — 12 values, verbatim."""

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


class ProviderError(ContractModel):
    """Normalized provider error (30 §14) — the only error shape the Core sees.

    ``safe_message`` must never leak raw provider internals; ``provider_code``
    carries the raw code for diagnostics only.
    """

    category: ProviderErrorCategory
    retryable: bool
    retry_after_ms: int | None = Field(default=None, ge=0)
    provider_code: BoundedStr | None = None
    safe_message: BoundedStr


# --- §8 adapter interface payload shapes (MVP Phase 4, T-IMPL-018) -----------------


class HealthScope(StrEnum):
    """Scope selector for ``ProviderAdapter.health_check`` (30 §8.1).

    30 §11: provider health and account health are separate questions —
    the scope makes the caller say which one it is asking.
    """

    PROVIDER = "provider"
    ACCOUNT = "account"


class CredentialHealth(ContractModel):
    """Result of ``ProviderAdapter.validate_credential`` (30 §8.1).

    Carries only the opaque ``credential_ref`` and its observed status —
    never secret material (20 §5). ``detail`` must be a safe message.
    """

    credential_ref: BoundedStr
    status: CredentialStatus
    checked_at: datetime | None = None
    detail: BoundedStr | None = None


class DiscoveredModel(ContractModel):
    """One provider-declared model surfaced by ``discover_models`` (30 §8.1).

    This is the provider's raw self-declaration, NOT a registry
    ``ProviderModelBinding`` (03 §4): binding creation is a Core/registry
    decision made from this input, never the provider's decision.
    """

    provider_model_name: BoundedStr
    endpoint_ref: BoundedStr | None = None
    modalities: list[BoundedStr] = Field(default_factory=list)
    capabilities: JsonObject = Field(default_factory=dict)
    limits_metadata: JsonObject = Field(default_factory=dict)


class ProviderGenerateRequest(ContractModel):
    """Normalized generation request handed to a provider adapter (30 §8.1).

    ``operation`` selects the capability-specific operation (30 §5); the
    adapter must reject undeclared operations with
    ``unsupported_capability`` (30 §8.1 note). ``credential_ref`` stays an
    opaque reference end-to-end (20 §5). ``payload`` carries the
    operation-specific normalized input; provider-specific request
    mechanics live in the provider runtime, never here (30 §9).
    """

    request_id: UUID
    tenant_id: UUID
    operation: ProviderOperation
    provider_model_name: BoundedStr
    credential_ref: BoundedStr
    account_id: UUID | None = None
    payload: JsonObject = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class ProviderGenerateResponse(ContractModel):
    """Normalized generation response returned by a provider adapter (30 §8.1).

    Exactly one of ``output``/``error`` is meaningful: a failed call carries
    the normalized :class:`ProviderError` (30 §14) — raw provider errors
    never cross this boundary. ``usage`` is provider-reported accounting
    metadata (tokens, units) for reservation settlement.
    """

    request_id: UUID
    succeeded: bool
    output: JsonObject = Field(default_factory=dict)
    usage: JsonObject = Field(default_factory=dict)
    error: ProviderError | None = None
    latency_ms: int | None = Field(default=None, ge=0)
