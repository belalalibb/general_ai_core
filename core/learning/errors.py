"""Learning-lifecycle boundary errors (FINAL Phase 17, 41 §20; 22 §9/§11)."""

from __future__ import annotations


class LearningError(Exception):
    """Base class for learning-lifecycle failures."""


class NotEligibleForTraining(LearningError):
    """The sample failed the 22 §9 gate — the FAILED conditions are named.

    Deny-by-default: data enters training ONLY when every condition holds;
    a failure names exactly what blocked it (11 §14 posture), never a
    silent drop.
    """

    def __init__(self, sample_id: object, failed: list[str]) -> None:
        super().__init__(f"sample {sample_id} not eligible for training; failed: {failed}")
        self.sample_id = sample_id
        self.failed = failed


class PromotionDenied(LearningError):
    """The candidate failed the 22 §11 promotion gate — conditions named."""

    def __init__(self, candidate: str, failed: list[str]) -> None:
        super().__init__(f"promotion of {candidate!r} denied; failed: {failed}")
        self.candidate = candidate
        self.failed = failed
