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
from core.learning.lifecycle import (
    GOLD_KNOWLEDGE_SOURCE,
    CapabilitySnapshot,
    LearningLifecycleService,
    SampleNotFound,
    SampleSource,
    SanitizationRefused,
)
from core.learning.sanitizer import (
    SECRET_LABELS,
    SanitizationFinding,
    SanitizationReport,
    sanitize_knowledge,
)

__all__ = [
    "GOLD_KNOWLEDGE_SOURCE",
    "CapabilitySnapshot",
    "LearningLifecycleService",
    "PROMOTION_CONDITIONS",
    "TRAINING_ELIGIBILITY_CONDITIONS",
    "EligibilitySignals",
    "LearningError",
    "NotEligibleForTraining",
    "PromotionDenied",
    "PromotionGate",
    "PromotionSignals",
    "SECRET_LABELS",
    "SampleNotFound",
    "SampleSource",
    "SanitizationFinding",
    "SanitizationRefused",
    "SanitizationReport",
    "TrainingEligibilityGate",
    "sanitize_knowledge",
]
