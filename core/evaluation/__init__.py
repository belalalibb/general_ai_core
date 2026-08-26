"""Evaluation subsystem (MVP Phase 7, 41 §46).

Public surface: the store seam + errors + the in-memory binding
(T-IMPL-029) and the evaluation POLICY service — deterministic graders,
optional model judge seam, aggregator, level assignment (T-IMPL-030).
"""

from core.evaluation.errors import (
    DuplicateEvaluation,
    EvaluationNotFound,
    EvaluationStoreError,
    InactiveGraderType,
    JudgeFailure,
)
from core.evaluation.memory import InMemoryEvaluationStore
from core.evaluation.policy import (
    MVP_DETERMINISTIC_CHECKS,
    AdapterModelJudge,
    DeterministicCheck,
    EvaluationPolicyService,
    ModelJudgePort,
)
from core.evaluation.ports import EvaluationStorePort

__all__ = [
    "MVP_DETERMINISTIC_CHECKS",
    "AdapterModelJudge",
    "DeterministicCheck",
    "DuplicateEvaluation",
    "EvaluationNotFound",
    "EvaluationPolicyService",
    "EvaluationStoreError",
    "EvaluationStorePort",
    "InMemoryEvaluationStore",
    "InactiveGraderType",
    "JudgeFailure",
    "ModelJudgePort",
]
