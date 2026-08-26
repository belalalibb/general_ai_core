"""Routing engine — deterministic, explainable model/provider selection.

MVP Phase 5 slice 1 (41 §44 "router simple scoring"). Spec authority:
final_docs_v3/11_MODEL_ROUTING_AND_MODEL_CONTROL.md. Architecture invariant:
Router decides; Execution executes (02).
"""

from core.routing.errors import (
    FallbackNotConfigured,
    NoEligibleCandidates,
    RoutingError,
)
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType

__all__ = [
    "FallbackNotConfigured",
    "NoEligibleCandidates",
    "RoutingError",
    "SimpleScoringRouter",
    "UnsupportedPolicyType",
]
