"""Bootstrap Router — the separate path for selecting the Router Model itself
(11 §9, 41 §11 "Bootstrap Router").

11 §9 verbatim: "Router may use an LLM for task analysis, but the Router
Engine is not the LLM. To avoid recursion: Bootstrap Routing Policy selects
router-analysis model. Bootstrap selection must be simple, deterministic/
policy-driven, and safe."

Recorded derivation decisions (never silent — 11 §9 defines the requirement
but no shape):

- POLICY-DRIVEN: the bootstrap path holds ONE pre-configured (admin/deploy
  time) model policy; no policy configured => :class:`BootstrapNotConfigured`
  (deny-by-default — the bootstrap never guesses a model).
- SIMPLE: the policy is restricted to the 11 §4 single-selection modes
  (auto / tier / explicit_model). The multi-model EXPLICIT_MODELS strategies
  and AGENT_NODE_MAPPING are execution-strategy machinery (11 §15/§16), not
  analysis-model selection — rejected at CONFIGURATION time so the error
  surfaces early, not at first route.
- DETERMINISTIC: selection delegates to :class:`SimpleScoringRouter`, which
  is pure and deterministic (ties broken by key order); no I/O, no LLM.
- RECURSION GUARD: the bootstrap request is constructed INTERNALLY and never
  carries a ``task_analysis`` — task analysis is the thing this model is
  being selected FOR, so it cannot be an input here by construction.
- SAFE: the same hard eligibility filters apply (11 §5 via the delegated
  router); "Unknown = ineligible" holds on this path too.
"""

from __future__ import annotations

from core.contracts.model_policy import (
    AutoModelPolicy,
    ExplicitModelPolicy,
    ModelPolicy,
    TierModelPolicy,
)
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingDecision, RoutingRequest
from core.routing.errors import BootstrapNotConfigured
from core.routing.router import SimpleScoringRouter

#: The 11 §4 single-selection policy types admitted for bootstrap ("simple").
_BOOTSTRAP_POLICY_TYPES = (AutoModelPolicy, TierModelPolicy, ExplicitModelPolicy)


class BootstrapRouter:
    """Selects the router-analysis model via a pinned policy (11 §9).

    A separate path from request routing: it owns its policy, builds its own
    request (never accepting task analysis), and delegates to the
    deterministic scoring router.
    """

    def __init__(
        self,
        router: SimpleScoringRouter,
        policy: ModelPolicy | None = None,
    ) -> None:
        if policy is not None and not isinstance(policy, _BOOTSTRAP_POLICY_TYPES):
            msg = (
                "bootstrap policy must be a single-selection policy"
                " (auto/tier/explicit_model, 11 §4) — got"
                f" {type(policy).__name__} (11 §9 'simple, deterministic')"
            )
            raise BootstrapNotConfigured(msg)
        self._router = router
        self._policy = policy

    @property
    def is_configured(self) -> bool:
        return self._policy is not None

    def select_analysis_model(
        self,
        operation: ProviderOperation = ProviderOperation.GENERATE_TEXT,
    ) -> RoutingDecision:
        """Route the pinned bootstrap policy — no task analysis, no recursion.

        Raises :class:`BootstrapNotConfigured` when no policy is pinned.
        """
        if self._policy is None:
            msg = (
                "no Bootstrap Routing Policy configured — the bootstrap path"
                " never guesses a router-analysis model (11 §9)"
            )
            raise BootstrapNotConfigured(msg)
        request = RoutingRequest(
            operation=operation,
            model_policy=self._policy,
            # task_analysis deliberately absent: recursion guard (11 §9).
        )
        return self._router.route(request)
