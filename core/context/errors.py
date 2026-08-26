"""Context composer errors (MVP Phase 6 slice 3, T-IMPL-027)."""

from __future__ import annotations


class ContextComposerError(Exception):
    """Base for all context-composer failures."""


class ContextBudgetExceeded(ContextComposerError):
    """The MANDATORY blocks (role + ask) alone exceed the context budget.

    Optional inputs (memory, history) degrade gracefully under budget
    pressure — they are trimmed with named ``over_budget`` exclusions.
    The mandatory blocks cannot be trimmed without silently changing the
    request, so an impossible budget fails loudly instead (11 §14
    fail-clearly posture).
    """

    def __init__(self, required: int, budget: int) -> None:
        self.required = required
        self.budget = budget
        super().__init__(
            f"mandatory context blocks need {required} characters "
            f"but the context budget is {budget}"
        )
