"""Learning lifecycle — FINAL Phase 17 (41 §20; 22 §8–§11).

Public surface: the 22 §9 training-eligibility gate + the 22 §11
promotion gate, both over condition DATA with deny-by-default signals.
Actual training execution is model-ops territory (41 §49 — never
claimed); the pipeline STATE lives on LearningSample (Phase 3 contract).
"""

from core.learning.errors import (
    LearningError,
    NotEligibleForTraining,
    PromotionDenied,
)
from core.learning.gates import (
    PROMOTION_CONDITIONS,
    TRAINING_ELIGIBILITY_CONDITIONS,
    EligibilitySignals,
    PromotionGate,
    PromotionSignals,
    TrainingEligibilityGate,
)

__all__ = [
    "PROMOTION_CONDITIONS",
    "TRAINING_ELIGIBILITY_CONDITIONS",
    "EligibilitySignals",
    "LearningError",
    "NotEligibleForTraining",
    "PromotionDenied",
    "PromotionGate",
    "PromotionSignals",
    "TrainingEligibilityGate",
]
