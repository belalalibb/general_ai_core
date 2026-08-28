"""Core domain types — Models / Providers / Accounts.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/03_DOMAIN_MODEL.md
§4 (Models / Providers / Accounts) and §9 (Agent-Capable Models / Provider
Agent Modules). Carried exactly — no state value added, renamed, or dropped.

The model registry entry doubles as the "model contract" consumed by the
Router (11_MODEL_ROUTING_AND_MODEL_CONTROL.md: capabilities, tiers, scoring
inputs, constraints).

Security posture: ``Credential.credential_ref`` is an opaque reference into a
secret store — raw secret values never appear in any contract object
(20_SECURITY_THREAT_MODEL.md; 30 §10 credentials rule).

Important rule (03 §9.3, verbatim)::

    Provider Agent Capability ≠ Platform Agent Runtime
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Closed sets (03 §4, verbatim) -------------------------------------------


class ModelTier(StrEnum):
    """Model tier (03 §4 Model entity) — closed at the domain level.

    Note: request-side *policy* tier strings stay open (10 §13.2 says allowed
    tiers are admin-configurable); ``custom`` is the domain-level bucket for
    admin-defined tiers.
    """

    FAST = "fast"
    MEDIUM = "medium"
    MAX = "max"
    CUSTOM = "custom"


class Modality(StrEnum):
    """Model modalities (03 §4 Model entity) — closed set, verbatim."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    CODE = "code"


class ModelStatus(StrEnum):
    """Model lifecycle status (03 §4) — closed set, verbatim."""

    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class ProviderStatus(StrEnum):
    """Provider lifecycle status (03 §4) — closed set, verbatim."""

    ACTIVE = "active"
    DISABLED = "disabled"
    MAINTENANCE = "maintenance"


class AuthType(StrEnum):
    """Provider auth types (03 §4 Provider entity) — closed set, verbatim."""

    API_KEY = "api_key"
    OAUTH = "oauth"
    SESSION_COOKIE = "session_cookie"
    CUSTOM = "custom"


class BindingAvailability(StrEnum):
    """ProviderModelBinding availability (03 §4) — closed set, verbatim."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class OwnerType(StrEnum):
    """Credential/account owner scope (03 §4) — closed set, verbatim."""

    PLATFORM = "platform"
    TENANT = "tenant"
    USER = "user"


class CredentialPolicy(StrEnum):
    """Credential-ownership selection policy (30 §10.5, 41 §10) — closed set,
    verbatim: platform_only / user_only / prefer_user / auto.

    FINAL Phase 7 (T-IMPL-056). Recorded readings (never silent):

    - ``user_only``/``prefer_user`` treat the USER SIDE as tenant- or
      user-owned credentials — 41 §10 splits ownership as
      ``Platform → Platform Account Pool`` vs ``Tenant/User → User
      Credential``, so tenant-owned and user-owned are both the user side.
    - ``auto`` places no ownership restriction; selection proceeds by the
      normal account-selection rules (no preference order is stated by the
      spec for auto, so none is invented).
    """

    PLATFORM_ONLY = "platform_only"
    USER_ONLY = "user_only"
    PREFER_USER = "prefer_user"
    AUTO = "auto"


class CredentialStatus(StrEnum):
    """Credential status (03 §4) — closed set, verbatim."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    INVALID = "invalid"


class AccountLifecycleState(StrEnum):
    """ProviderAccount lifecycle_state (03 §4) — closed set, verbatim.

    Distinct from the 4-value account *health check* surface of 30 §11
    (see ``core.contracts.provider.AccountHealthCheckState``).
    """

    READY = "READY"
    COOLDOWN = "COOLDOWN"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    INVALID = "INVALID"
    PENDING = "PENDING"
    DISABLED = "DISABLED"


class AccountHealthState(StrEnum):
    """ProviderAccount health_state (03 §4) — closed set, verbatim."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AgentCapabilityType(StrEnum):
    """Agent-specific capability type (03 §9.1) — closed set, verbatim."""

    NONE = "none"
    TOOL_USING_MODEL = "tool_using_model"
    PROVIDER_AGENT = "provider_agent"
    MANAGED_ASSISTANT = "managed_assistant"
    CODE_AGENT = "code_agent"
    RESEARCH_AGENT = "research_agent"


# --- Agent capability extension (03 §9.1–§9.2) --------------------------------


class AgentCapability(ContractModel):
    """Optional agent-specific metadata on a Model (03 §9.1).

    All flags default unset (``None`` = undeclared): 30 §4.3 forbids assuming
    capabilities a provider/model did not declare; unknown must not read as
    supported.
    """

    type: AgentCapabilityType = AgentCapabilityType.NONE
    supports_threads: bool | None = None
    supports_tools: bool | None = None
    supports_files: bool | None = None
    supports_stateful_runs: bool | None = None
    supports_streaming: bool | None = None
    provider_managed_state: bool | None = None


class AgentRuntimeBinding(ContractModel):
    """Per-binding agent runtime declaration (03 §9.2).

    Agent behavior may differ per provider even for similar model names, so
    this lives on the binding, not only on the Model.
    """

    provider_managed: bool
    state_model: Literal["stateless", "thread", "run", "session"]
    tool_policy: Literal["platform_controlled", "provider_controlled", "hybrid"]
    file_support: bool | None = None
    max_steps: int | None = Field(default=None, ge=1)


# --- Entities (03 §4) -----------------------------------------------------------


class Model(ContractModel):
    """Model registry entry (03 §4) — the Router's model contract.

    ``capabilities`` is an open set of declared capability keys (e.g.
    reasoning, coding, vision, image_generation, tool_use, provider_agent per
    03 §9.1) — new capabilities may be introduced by admins without a contract
    change; the Router treats unknown/undeclared as ineligible (11 §5).
    """

    id: UUID
    model_key: BoundedStr
    display_name: BoundedStr
    tier: ModelTier
    modalities: list[Modality] = Field(min_length=1)
    capabilities: list[BoundedStr] = Field(default_factory=list)
    context_window: int | None = Field(default=None, ge=1)
    quality_score: float | None = None
    speed_score: float | None = None
    cost_score: float | None = None
    reliability_score: float | None = None
    status: ModelStatus
    agent_capability: AgentCapability | None = None


class Provider(ContractModel):
    """Provider registry entry (03 §4)."""

    id: UUID
    provider_key: BoundedStr
    display_name: BoundedStr
    status: ProviderStatus
    auth_types: list[AuthType] = Field(min_length=1)
    supports_account_pool: bool


class ProviderModelBinding(ContractModel):
    """Binds one model to one provider (03 §4; agent extension per §9.2).

    The same model may be bound to multiple providers; availability and agent
    behavior are per-binding facts.
    """

    provider_id: UUID
    model_id: UUID
    provider_model_name: BoundedStr
    endpoint_ref: BoundedStr | None = None
    availability: BindingAvailability
    limits_metadata: JsonObject = Field(default_factory=dict)
    capabilities: JsonObject = Field(default_factory=dict)
    agent_runtime: AgentRuntimeBinding | None = None


class Credential(ContractModel):
    """Credential record (03 §4). ``credential_ref`` is an opaque reference —
    never a raw secret value."""

    id: UUID
    owner_type: OwnerType
    owner_id: UUID | None = None
    provider_id: UUID
    credential_ref: BoundedStr
    status: CredentialStatus


class ProviderAccount(ContractModel):
    """Provider account record (03 §4).

    Do not confuse "one account failed" with "the whole provider is down"
    (30 §11) — account state never implies provider state.
    """

    id: UUID
    provider_id: UUID
    credential_id: UUID
    owner_type: OwnerType
    lifecycle_state: AccountLifecycleState
    health_state: AccountHealthState
    cooldown_until: datetime | None = None
