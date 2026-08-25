"""Model policy contracts — advanced model control.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md §13
(Advanced Model Control Contract).
Related routing authority: final_docs_v3/11_MODEL_ROUTING_AND_MODEL_CONTROL.md
(§8 fallback policies — the closed ``FallbackScope`` set).

The five supported model policy types (10 §13, verbatim)::

    auto
    tier
    explicit_model
    explicit_models
    agent_node_mapping

Field-default posture (10 §2: "Everything else has policy-driven defaults"):
only structurally identifying fields are required (``type`` plus the selector
that the type is about). Every tunable left unset (``None``) means "resolve via
policy-driven defaults" server-side — the contract does not invent default
values the spec does not state.

Tier values are intentionally NOT a closed enum: 10 §13.2 says allowed tiers
are admin-configurable ("for example fast / medium / max / custom").
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel


class FallbackScope(StrEnum):
    """Fallback policies (11 §8) — closed set, verbatim."""

    NONE = "none"
    SAME_MODEL_DIFFERENT_PROVIDER = "same_model_different_provider"
    SAME_TIER = "same_tier"
    LOWER_COST_SAME_CAPABILITY = "lower_cost_same_capability"
    MAX_ESCALATION = "max_escalation"
    ADMIN_DEFINED_CHAIN = "admin_defined_chain"


class SelectionStrategy(StrEnum):
    """Multi-model selection strategies (10 §13.4) — closed set, verbatim."""

    FALLBACK_CHAIN = "fallback_chain"
    PARALLEL_COMPARE = "parallel_compare"
    BEST_OF_N = "best_of_n"
    DEBATE = "debate"
    SPECIALIST_ROLES = "specialist_roles"


class ModelRef(ContractModel):
    """One model entry inside ``explicit_models`` (10 §13.4).

    ``provider_id`` null means the Router may choose any eligible provider
    serving the model (10 §13.3 rule 3).
    """

    model_id: BoundedStr
    provider_id: BoundedStr | None = None


class AutoModelPolicy(ContractModel):
    """10 §13.1 — the Router chooses the best eligible model/provider/account.

    The 10 §2 request example additionally shows a ``tier`` hint and a null
    ``explicit_model_id`` on the auto policy; ``explicit_model_id`` must stay
    null for type=auto (it is typed ``None``-only).
    """

    type: Literal["auto"]
    tier: BoundedStr | None = None
    explicit_model_id: None = None
    allow_fallback: bool | None = None
    fallback_scope: FallbackScope | None = None


class TierModelPolicy(ContractModel):
    """10 §13.2 — selection constrained to an admin-configurable tier."""

    type: Literal["tier"]
    tier: BoundedStr
    allow_fallback: bool | None = None
    fallback_scope: FallbackScope | None = None


class ExplicitModelPolicy(ContractModel):
    """10 §13.3 — the user selects one model (priority over Router preference).

    The Router must still verify entitlement, availability, policy, provider
    health, and credentials (10 §13.3 rules 1-5).
    """

    type: Literal["explicit_model"]
    model_id: BoundedStr
    provider_id: BoundedStr | None = None
    allow_fallback: bool | None = None
    fallback_scope: FallbackScope | None = None


class ExplicitModelsPolicy(ContractModel):
    """10 §13.4 — a list of models plus a selection strategy."""

    type: Literal["explicit_models"]
    models: Annotated[list[ModelRef], Field(min_length=1)]
    selection_strategy: SelectionStrategy | None = None
    judge_policy: NodeModelPolicy | None = None
    allow_partial: bool | None = None
    allow_fallback: bool | None = None
    fallback_scope: FallbackScope | None = None


# Node-level policies (10 §13.5): auto / tier / explicit_model / explicit_models.
NodeModelPolicy = Annotated[
    AutoModelPolicy | TierModelPolicy | ExplicitModelPolicy | ExplicitModelsPolicy,
    Field(discriminator="type"),
]


class AgentNodeMappingPolicy(ContractModel):
    """10 §13 — the fifth policy type: per-node model mapping.

    10 §13.5 expresses the same mapping through the request-level
    ``agent_policy`` object (see :class:`AgentPolicy`); this variant carries it
    as a ``model_policy.type`` per the supported-types list in 10 §13.

    Resolution order (10 §13.5 rules 1-4): node policy > agent default >
    request model_policy > Router auto policy.
    """

    type: Literal["agent_node_mapping"]
    default_model_policy: NodeModelPolicy | None = None
    node_model_policies: dict[str, NodeModelPolicy] = Field(default_factory=dict)


# Request-level model policy: the 5 supported types (10 §13, verbatim list).
ModelPolicy = Annotated[
    AutoModelPolicy
    | TierModelPolicy
    | ExplicitModelPolicy
    | ExplicitModelsPolicy
    | AgentNodeMappingPolicy,
    Field(discriminator="type"),
]


class AgentPolicy(ContractModel):
    """Agent Mode per-node model mapping carrier (10 §13.5)."""

    workflow: BoundedStr | None = None
    default_model_policy: NodeModelPolicy | None = None
    node_model_policies: dict[str, NodeModelPolicy] = Field(default_factory=dict)


# judge_policy forward-references NodeModelPolicy — resolve now that it exists.
ExplicitModelsPolicy.model_rebuild()
