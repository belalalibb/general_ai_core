"""Immutable replay evidence codec; existing stores/contracts, no parallel authority.

A digest binds persisted content, not authenticity against a compromised DB.
Only the trusted replay producer writes evidence. One deterministic ID per run
prevents cherry-picking appended judgments. Legacy runs must be replayed.
"""

from __future__ import annotations

import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from core.contracts.base import JsonObject
from core.contracts.evaluation import EvaluationRecord, GraderResult, GraderType, VerificationLevel
from core.contracts.execute import ExecutionStatus
from core.evaluation.policy import MVP_DETERMINISTIC_CHECKS
from core.execution.service import ExecutionReport

CHECK_POLICY_REVISION = "mvp-deterministic-v1"
_CHECK_NAMES = frozenset(check.name for check in MVP_DETERMINISTIC_CHECKS)


def replay_metadata(scenario_id: UUID, checks: tuple[str, ...]) -> JsonObject:
    return {
        "scenario_id": str(scenario_id),
        "evidence_version": 1,
        "policy_revision": CHECK_POLICY_REVISION,
        "checks": list(checks),
    }


def evaluation_id(tenant_id: UUID, execution_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"qevion:regression:v1:{tenant_id}:{execution_id}")


def required_checks(report: ExecutionReport) -> tuple[str, ...]:
    if not report.nodes:
        raise ValueError("missing replay node")
    payload = report.nodes[-1].node.input_ref
    if not isinstance(payload, dict):
        raise ValueError("missing replay input")
    context = payload.get("context")
    metadata = context.get("metadata") if isinstance(context, dict) else None
    label = metadata.get("test_scenario") if isinstance(metadata, dict) else None
    if not isinstance(label, dict):
        raise ValueError("missing replay provenance")
    if type(label.get("evidence_version")) is not int or label["evidence_version"] != 1:
        raise ValueError("legacy or unsupported replay evidence")
    if label.get("policy_revision") != CHECK_POLICY_REVISION:
        raise ValueError("unsupported check policy revision")
    scenario = label.get("scenario_id")
    if not isinstance(scenario, str) or str(UUID(scenario)) != scenario:
        raise ValueError("invalid scenario identity")
    checks = label.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("missing required checks")
    if not all(isinstance(name, str) and name in _CHECK_NAMES for name in checks):
        raise ValueError("unknown required check")
    if len(checks) != len(set(checks)):
        raise ValueError("duplicate required check")
    return tuple(checks)


def fingerprint(report: ExecutionReport, graders: tuple[GraderResult, ...]) -> str:
    required_checks(report)
    content = {
        "tenant_id": str(report.execution.tenant_id),
        "execution_id": str(report.execution.id),
        "request_hash": report.execution.request_hash,
        "status": report.execution.status.value,
        "node_id": str(report.nodes[-1].node.id),
        "input": report.nodes[-1].node.input_ref,
        "output": report.final_output,
        "graders": [g.model_dump(mode="json") for g in graders],
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "regression:v1:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_record(report: ExecutionReport, results: tuple[GraderResult, ...]) -> EvaluationRecord:
    if tuple(g.name for g in results) != required_checks(report):
        raise ValueError("incomplete replay check results")
    passed = report.execution.status is ExecutionStatus.SUCCEEDED and all(
        g.type is GraderType.REGRESSION and g.passed is True for g in results
    )
    return EvaluationRecord(
        id=evaluation_id(report.execution.tenant_id, report.execution.id),
        tenant_id=report.execution.tenant_id,
        execution_id=report.execution.id,
        level=VerificationLevel.VALIDATED if passed else VerificationLevel.EVALUATED,
        graders=results,
        evidence_ref=fingerprint(report, results),
    )


def supports_pass(report: ExecutionReport, record: EvaluationRecord) -> bool:
    try:
        checks = required_checks(report)
        return (
            record.id == evaluation_id(report.execution.tenant_id, report.execution.id)
            and record.tenant_id == report.execution.tenant_id
            and record.execution_id == report.execution.id
            and record.level is VerificationLevel.VALIDATED
            and tuple(g.name for g in record.graders) == checks
            and all(g.type is GraderType.REGRESSION and g.passed is True for g in record.graders)
            and record.evidence_ref == fingerprint(report, record.graders)
        )
    except (ValueError, TypeError):
        return False
