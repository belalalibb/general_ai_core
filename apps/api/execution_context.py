"""Execution request context — C-04 (completion program v2, operator D-4 = yes).

One derivation of the ADDITIVE metadata a run record carries so a user can
see which project a run belongs to and distinguish single / agent / template
executions (audit finding P-4). Values come ONLY from authoritative request
admission facts (the project reference the API already ownership-checked,
the resolved strategy spec, the admitted agent strategy) — nothing inferred,
nothing invented.

Storage: the ``Execution.cost_snapshot`` open JSON object (03 §5 ``json``)
under the ``request_context`` key — additive, durable through the existing
JSONB column (no schema migration), invisible to every pre-C-04 reader.
Both the sync API path and the async worker write it through the SAME
helper so the two records agree.
"""

from __future__ import annotations

import dataclasses

from core.contracts.base import JsonObject
from core.contracts.execute import ExecuteRequest, ExecutionContextInfo
from core.contracts.execution_strategy import ExecutionStrategySpec
from core.execution.service import ExecutionReport

REQUEST_CONTEXT_KEY = "request_context"


def request_context(
    body: ExecuteRequest,
    *,
    agent: bool = False,
    spec: ExecutionStrategySpec | None = None,
) -> JsonObject:
    """Derive the request-context facts of ONE admitted execute request."""
    if agent:
        mode = "agent"
    elif spec is not None:
        mode = spec.mode
    else:
        mode = "single"
    policy = body.execution_policy
    context: JsonObject = {
        "mode": mode,
        "async": bool(policy is not None and policy.async_ is True),
    }
    if body.project_id is not None:
        context["project_id"] = body.project_id
    if spec is not None and spec.template_id is not None:
        context["template_ref"] = spec.template_id
    return context


def with_request_context(report: ExecutionReport, context: JsonObject) -> ExecutionReport:
    """Return the report with ``request_context`` folded into ``cost_snapshot``."""
    execution = report.execution
    snapshot = dict(execution.cost_snapshot)
    snapshot[REQUEST_CONTEXT_KEY] = dict(context)
    return dataclasses.replace(
        report, execution=execution.model_copy(update={"cost_snapshot": snapshot})
    )


def context_info(report: ExecutionReport) -> ExecutionContextInfo:
    """Project the stored record onto the served ``context`` block (10 §5 additive)."""
    stored = report.execution.cost_snapshot.get(REQUEST_CONTEXT_KEY)
    stored = stored if isinstance(stored, dict) else {}
    project_id = stored.get("project_id")
    template_ref = stored.get("template_ref")
    mode = stored.get("mode")
    return ExecutionContextInfo(
        strategy=report.execution.strategy.value,
        mode=str(mode) if isinstance(mode, str) else None,
        project_id=str(project_id) if isinstance(project_id, str) else None,
        template_ref=str(template_ref) if isinstance(template_ref, str) else None,
    )
