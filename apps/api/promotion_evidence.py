"""R177-FIX-08 — resolve 22 §11 promotion signals from RECORDED artefacts.

G-A07-1 (evidence/r177/A07_learning): ``PromotionSignals`` were caller-asserted
booleans; the gate was a correct policy engine over unverified inputs. This
module turns the three artefact-backed conditions into *resolved* verdicts:

- ``offline_eval_pass``   ← an :class:`EvaluationRecord` of the sample's source
  execution (same tenant), level above RAW, every check-style grader passed.
- ``security_eval_pass``  ← the same, but at least one grader is ``security``.
- ``regression_pass``     ← immutable per-run verification evidence bound to
  tenant/execution/scenario/input/output/check-version. Status and a replay
  label alone are never proof (R178-DEC-01).

Everything else (shadow / canary / rollback plan / admin approval) remains a
human act and is reported as ``unverified`` — never inferred. The
:class:`core.learning.gates.PromotionGate` is untouched: this module only
produces the booleans it consumes. Absent or foreign-tenant ids resolve to the
SAME ``not found`` verdict (20 §6 anti-enumeration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from apps.api.regression_evidence import evaluation_id as regression_evaluation_id
from apps.api.regression_evidence import supports_pass
from core.contracts.base import JsonObject
from core.contracts.evaluation import EvaluationRecord, GraderType, VerificationLevel
from core.contracts.execute import ExecutionStatus
from core.evaluation.errors import EvaluationNotFound
from core.evaluation.ports import EvaluationStorePort

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.api.store import ExecutionStorePort

#: The 22 §11 conditions this resolver can back with an artefact.
ARTEFACT_BACKED_CONDITIONS: tuple[str, ...] = (
    "offline_eval_pass",
    "regression_pass",
    "security_eval_pass",
)

#: The 22 §11 conditions that stay human-asserted (labelled, never resolved).
HUMAN_ASSERTED_CONDITIONS: tuple[str, ...] = (
    "shadow_performance_acceptable",
    "canary_performance_acceptable",
    "rollback_plan_exists",
    "admin_approved",
)

_SCENARIO_LABEL_KEY = "test_scenario"  # == apps.api.scenarios.SCENARIO_LABEL_KEY (pinned by test)


@dataclass(frozen=True)
class EvidenceVerdict:
    """One resolved condition — the boolean the gate consumes plus WHY."""

    condition: str
    held: bool
    ref: UUID
    reason: str
    level: VerificationLevel | None = None

    def as_json(self) -> JsonObject:
        payload: JsonObject = {
            "held": self.held,
            "ref": str(self.ref),
            "reason": self.reason,
        }
        if self.level is not None:
            payload["level"] = self.level.value
        return payload


class PromotionEvidenceResolver:
    """Read-only resolver over the SAME evaluation / execution stores the admin reads."""

    def __init__(
        self,
        *,
        evaluations: EvaluationStorePort,
        executions: ExecutionStorePort | None,
    ) -> None:
        self._evaluations = evaluations
        self._executions = executions

    # --- evaluations (offline + security) --------------------------------------

    def _record(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord | None:
        try:
            return self._evaluations.get(tenant_id, evaluation_id)
        except EvaluationNotFound:
            return None

    def _evaluation_verdict(
        self,
        condition: str,
        tenant_id: UUID,
        source_execution_id: UUID,
        evaluation_id: UUID,
        *,
        require_grader: GraderType | None,
    ) -> EvidenceVerdict:
        record = self._record(tenant_id, evaluation_id)
        if record is None:
            return EvidenceVerdict(condition, False, evaluation_id, "not found")
        if record.execution_id != source_execution_id:
            return EvidenceVerdict(
                condition,
                False,
                evaluation_id,
                "evaluation is not of the sample's source execution",
                record.level,
            )
        if record.level is VerificationLevel.RAW:
            return EvidenceVerdict(
                condition, False, evaluation_id, "record is RAW (not evaluated)", record.level
            )
        if require_grader is not None and not any(
            g.type is require_grader and g.passed is True for g in record.graders
        ):
            return EvidenceVerdict(
                condition,
                False,
                evaluation_id,
                f"no {require_grader.value} grader in the record",
                record.level,
            )
        checks = [g for g in record.graders if g.passed is not None]
        if not checks:
            return EvidenceVerdict(
                condition, False, evaluation_id, "no recorded passing checks", record.level
            )
        if not all(g.passed for g in checks):
            return EvidenceVerdict(
                condition, False, evaluation_id, "a recorded check failed", record.level
            )
        return EvidenceVerdict(condition, True, evaluation_id, "recorded evaluation", record.level)

    def evaluation(
        self, tenant_id: UUID, source_execution_id: UUID, evaluation_id: UUID
    ) -> EvidenceVerdict:
        return self._evaluation_verdict(
            "offline_eval_pass", tenant_id, source_execution_id, evaluation_id, require_grader=None
        )

    def security_evaluation(
        self, tenant_id: UUID, source_execution_id: UUID, evaluation_id: UUID
    ) -> EvidenceVerdict:
        return self._evaluation_verdict(
            "security_eval_pass",
            tenant_id,
            source_execution_id,
            evaluation_id,
            require_grader=GraderType.SECURITY,
        )

    # --- regression (scenario replay artefact) -----------------------------------

    def regression(self, tenant_id: UUID, execution_id: UUID) -> EvidenceVerdict:
        condition = "regression_pass"
        if self._executions is None:
            return EvidenceVerdict(condition, False, execution_id, "no execution store composed")
        try:
            report = self._executions.get(tenant_id, execution_id)
        except KeyError:  # ExecutionNotFound is a KeyError; absent == foreign (20 §6)
            return EvidenceVerdict(condition, False, execution_id, "not found")
        if not _is_scenario_replay(report_input_ref(report)):
            return EvidenceVerdict(
                condition, False, execution_id, "execution is not a scenario replay"
            )
        if report.execution.status is not ExecutionStatus.SUCCEEDED:
            return EvidenceVerdict(
                condition, False, execution_id, "scenario replay did not succeed"
            )
        record = self._record(tenant_id, regression_evaluation_id(tenant_id, execution_id))
        if record is None:
            return EvidenceVerdict(
                condition, False, execution_id, "missing stored regression verification evidence"
            )
        if not supports_pass(report, record):
            return EvidenceVerdict(
                condition, False, execution_id, "invalid or failed stored regression evidence"
            )
        return EvidenceVerdict(condition, True, execution_id, "recorded verified scenario replay")


def report_input_ref(report: object) -> object:
    """The stored input of the final node (``None`` for root-only rows)."""
    nodes = getattr(report, "nodes", ())
    if not nodes:
        return None
    return getattr(getattr(nodes[-1], "node", None), "input_ref", None)


def _is_scenario_replay(input_ref: object) -> bool:
    if not isinstance(input_ref, dict):
        return False
    context = input_ref.get("context")
    if not isinstance(context, dict):
        return False
    metadata = context.get("metadata")
    return isinstance(metadata, dict) and _SCENARIO_LABEL_KEY in metadata
