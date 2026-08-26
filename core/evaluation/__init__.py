"""Evaluation subsystem (MVP Phase 7, 41 §46).

Public surface: the store seam + errors + the in-memory binding. The
evaluation POLICY service (graders/aggregator/level assignment) is the
next slice (T-IMPL-030) and will export from here when it lands.
"""

from core.evaluation.errors import (
    DuplicateEvaluation,
    EvaluationNotFound,
    EvaluationStoreError,
)
from core.evaluation.memory import InMemoryEvaluationStore
from core.evaluation.ports import EvaluationStorePort

__all__ = [
    "DuplicateEvaluation",
    "EvaluationNotFound",
    "EvaluationStoreError",
    "EvaluationStorePort",
    "InMemoryEvaluationStore",
]
