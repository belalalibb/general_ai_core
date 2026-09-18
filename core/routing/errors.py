"""Router-boundary errors (11 §14: "if fallback disabled → fail clearly").

Core-side selection failures. Distinct from the normalized ProviderError
contract (30 §14) and from the provider-boundary errors in core/providers/.
"""

from __future__ import annotations

from core.contracts.routing import ExclusionRecord


class RoutingError(Exception):
    """Base class for router selection failures."""


class NoEligibleCandidates(RoutingError):
    """No candidate survived the hard eligibility filters (11 §5).

    Carries the explainable exclusion records so the failure is diagnosable
    without re-running the router ("fail clearly", 11 §14).
    """

    def __init__(
        self,
        message: str,
        excluded: list[ExclusionRecord],
        *,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.excluded = excluded
        # R188 A2: when runtime resource signals emptied the pool, the earliest
        # moment a candidate may become eligible again — WAIT data for the
        # caller (never a busy loop inside the router). None = no such hint.
        self.retry_after_ms = retry_after_ms


class FallbackNotConfigured(RoutingError):
    """The requested fallback scope needs admin configuration that is absent.

    ``admin_defined_chain`` (11 §8) requires an admin-defined chain; routing
    with that scope and no chain configured must fail clearly, never guess.
    """


class BootstrapNotConfigured(RoutingError):
    """The Bootstrap Routing Policy is absent or invalid (11 §9).

    Bootstrap selection is policy-driven; without a pinned policy the
    bootstrap path never guesses a router-analysis model (deny-by-default).
    """


class UnknownStrategy(RoutingError):
    """A requested execution strategy is outside the 03 §5 closed set.

    Unknown values are rejected loudly, never coerced (11 §5 posture).
    """
