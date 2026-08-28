"""Routing engine — deterministic, explainable model/provider selection.

MVP Phase 5 slice 1 (41 §44 "router simple scoring") + FINAL Phase 8
additions (41 §11: Bootstrap Router, Strategy Planner, Resource Selector).
Spec authority: final_docs_v3/11_MODEL_ROUTING_AND_MODEL_CONTROL.md.
Architecture invariant: Router decides; Execution executes (02).
"""

from core.routing.bootstrap import BootstrapRouter
from core.routing.errors import (
    BootstrapNotConfigured,
    FallbackNotConfigured,
    NoEligibleCandidates,
    RoutingError,
    UnknownStrategy,
)
from core.routing.planner import StrategyPlanner
from core.routing.resources import ResourceSelector
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType

__all__ = [
    "BootstrapNotConfigured",
    "BootstrapRouter",
    "FallbackNotConfigured",
    "NoEligibleCandidates",
    "ResourceSelector",
    "RoutingError",
    "SimpleScoringRouter",
    "StrategyPlanner",
    "UnknownStrategy",
    "UnsupportedPolicyType",
]
