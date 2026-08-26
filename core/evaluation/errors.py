"""Evaluation store errors (closed, minimal set for the MVP port).

Anti-enumeration posture carried from core/storage and core/memory
(20 §6): an evaluation that is absent and one that exists in ANOTHER
tenant raise the SAME NotFound error — cross-tenant probes must not
distinguish "absent" from "present elsewhere".
"""

from __future__ import annotations


class EvaluationStoreError(Exception):
    """Base class for evaluation store failures."""


class EvaluationNotFound(EvaluationStoreError):
    """No evaluation with this id within the caller's tenant scope.

    Deliberately also raised for evaluations owned by ANOTHER tenant
    (anti-enumeration, 20 §6).
    """

    def __init__(self, evaluation_id: object) -> None:
        super().__init__(f"evaluation not found: {evaluation_id}")


class InactiveGraderType(EvaluationStoreError):
    """A requested grader type is representable but does not RUN this phase.

    R049 boundary (c): only ``MVP_ACTIVE_GRADER_TYPES`` execute in MVP
    Phase 7. Naming any other 22 §5 type is denied LOUDLY — silently
    skipping it would fake evaluation coverage that never ran.
    """

    def __init__(self, inactive: object) -> None:
        super().__init__(f"grader type(s) not active in MVP Phase 7: {inactive}")


class JudgeFailure(EvaluationStoreError):
    """The optional model judge could not produce a usable judgment.

    Raised by judge implementations for ANY failure mode (adapter raise,
    failed call, unusable score/confidence). The policy service CONTAINS
    this error — evaluation degrades to deterministic-only (41 §46
    "optional model judge") and never crashes the caller.
    """


class DuplicateEvaluation(EvaluationStoreError):
    """An evaluation with this id is already recorded (never overwritten).

    Evaluation records are evidence (22 §6/22 §12 "evidence integrity" —
    the 21 §4 control matrix marks it unbreakable): re-recording under the
    same id would silently rewrite history, so the store denies loudly.
    """

    def __init__(self, evaluation_id: object) -> None:
        super().__init__(f"evaluation already recorded: {evaluation_id}")
