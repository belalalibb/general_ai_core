"""Routing contracts — router input/output shapes.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/
11_MODEL_ROUTING_AND_MODEL_CONTROL.md (doc 11):

- §3  Task Analysis Output (:class:`TaskAnalysis`)
- §5  Hard Eligibility Filters ("Unknown = ineligible")
- §6  Scoring Formula (:class:`ScoringWeights` — policy-driven, VERSIONED)
- §7  Candidate Score (:class:`CandidateScore`)
- §8  Fallback Policies (``FallbackScope`` — lives in model_policy.py)
- §13 Priority Order (explicit choice outranks Router preference, never
  security/entitlement/availability)
- §16 Agent Node Mapping Resolution ("the Router must record the resolved
  policy snapshot in the Execution Plan" — :class:`RoutingDecision`
  carries ``policy_snapshot``)

Scope note (MVP Phase 5 slice 1, 41 §44): these contracts cover the router
SELECTION surface (request -> scored decision). The full §10 Router Output
Contract (Execution Plan with nodes) belongs to the execution-graph slice —
:class:`RoutingDecision` is the model-selection component that plan will embed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, utc_now
from core.contracts.domain import Modality
from core.contracts.model_policy import FallbackScope, ModelPolicy
from core.contracts.provider import ProviderOperation

# Scoring weight component: policy fractions in [0, 1] (11 §6 example values).
WeightValue = Annotated[float, Field(ge=0.0, le=1.0)]


class TaskAnalysis(ContractModel):
    """Task analysis output (11 §3, field-for-field).

    ``complexity`` and ``risk_level`` stay open bounded strings: doc 11 shows
    example values ("medium") but declares no closed set for them.
    """

    task_type: BoundedStr
    complexity: BoundedStr
    modalities_required: list[Modality] = Field(default_factory=list)
    capabilities_required: list[BoundedStr] = Field(default_factory=list)
    tools_required: list[BoundedStr] = Field(default_factory=list)
    risk_level: BoundedStr
    needs_agent: bool | None = None
    needs_evaluation: bool | None = None
    language: BoundedStr | None = None


class ScoringWeights(ContractModel):
    """Configurable scoring weights (11 §6).

    Defaults are the §6 initial values, verbatim. "Weights are policy-driven
    and versioned" — ``version`` identifies the weight set used so a decision
    stays explainable after admin weight changes.
    """

    version: BoundedStr = "11s6-initial"
    quality: WeightValue = 0.35
    reliability: WeightValue = 0.20
    cost: WeightValue = 0.15
    latency: WeightValue = 0.15
    context_fit: WeightValue = 0.10
    policy_preference: WeightValue = 0.05


class CandidateScore(ContractModel):
    """One scored candidate (11 §7, field-for-field).

    ``account_id`` is nullable: account selection happens in the
    provider/account-selection stage (11 §2) — the scoring slice may emit a
    candidate before an account is chosen; accounts are optional (30 §10.1).
    """

    model_id: UUID
    provider_id: UUID
    account_id: UUID | None = None
    score: float
    reasons: list[BoundedStr] = Field(default_factory=list)
    risks: list[BoundedStr] = Field(default_factory=list)


class ExclusionRecord(ContractModel):
    """Why a candidate was excluded — explainability for deny paths.

    11 §5 requires "Unknown = ineligible"; an explainable router must be able
    to say WHICH filter excluded WHICH candidate without leaking internals.
    """

    model_key: BoundedStr
    provider_key: BoundedStr | None = None
    reason: BoundedStr


class RoutingRequest(ContractModel):
    """Router selection input (MVP slice of the 11 §2 pipeline).

    ``model_policy`` None means AUTO (10 §13 default posture). Explicit
    capability/modality lists win over ``task_analysis`` when both are given;
    when the explicit lists are empty the router derives requirements from
    the analysis (11 §2: Task Analysis feeds Capability Requirements).
    """

    operation: ProviderOperation
    required_capabilities: list[BoundedStr] = Field(default_factory=list)
    required_modalities: list[Modality] = Field(default_factory=list)
    model_policy: ModelPolicy | None = None
    task_analysis: TaskAnalysis | None = None
    context_length_hint: int | None = Field(default=None, ge=1)
    weights: ScoringWeights | None = None


class RoutingDecision(ContractModel):
    """Router selection output — deterministic and explainable.

    - ``selected``  : the winning candidate.
    - ``ranked``    : all eligible candidates, best first (ties broken
      deterministically by model/provider key order).
    - ``fallback_candidates``: ordered fallback route (11 §8/§14) — the
      candidates execution may try next, best first, excluding ``selected``.
    - ``excluded``  : explainable deny records (11 §5).
    - ``policy_snapshot``: the RESOLVED model policy this decision honored
      (11 §16 snapshot rule — future policy changes must not alter an
      already-started execution).
    - ``weights``   : the versioned weight set actually used (11 §6).
    """

    selected: CandidateScore
    ranked: list[CandidateScore] = Field(min_length=1)
    fallback_candidates: list[CandidateScore] = Field(default_factory=list)
    excluded: list[ExclusionRecord] = Field(default_factory=list)
    policy_snapshot: ModelPolicy
    fallback_policy: FallbackScope | None = None
    weights: ScoringWeights
    decided_at: datetime = Field(default_factory=utc_now)
