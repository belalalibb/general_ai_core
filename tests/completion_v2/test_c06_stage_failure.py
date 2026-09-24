"""Completion program v2 — C-06: a failed template/custom stage names ITSELF.

The hermetic runtime's local echo adapter never fails, so the projection is
proven at the ONE StrategyExecutor (scripted provider failure through the
R188 fixture) and at the ONE API failure mapper (``execution_failure_detail``):
the failed stage node carries ``stage`` + the child's normalized provider
error (category + safe_message only), the attempt trail rides the projected
node so the API maps the REAL category, and ``details.stage`` reaches clients.
"""

from __future__ import annotations

from uuid import uuid4

from apps.api.app import _failed_stage, _last_provider_error
from apps.api.errors import execution_failure_detail
from core.contracts.errors import ErrorCode
from core.contracts.execute import ExecutionStatus, ExecutionStrategySpec
from core.contracts.execution import ExecutionNodeStatus
from core.contracts.provider import (
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
)
from tests.execution.test_r188_strategy_executor import DIAMOND, RecordingAdapter, World


class QuotaAdapter(RecordingAdapter):
    """Scripted QUOTA_EXCEEDED on one stage — the category the API must surface."""

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        stage = request.payload.get("stage", {})
        if stage.get("key") == self.fail_when:
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=ProviderError(
                    category=ProviderErrorCategory.QUOTA_EXCEEDED,
                    retryable=False,
                    safe_message="provider quota exhausted",
                ),
                latency_ms=1,
            )
        return await super().generate(request)


def test_failed_stage_node_names_stage_and_normalized_provider_error() -> None:
    w = World({"alpha": QuotaAdapter("alpha", fail_when="analysis_a")}, ["model-x", "model-y"])
    result = w.run(DIAMOND)
    assert not result.succeeded
    failed = next(n for n in result.report.nodes if n.node.node_key == "analysis_a")
    assert failed.node.status is ExecutionNodeStatus.FAILED
    assert failed.node.error == {
        "reason": "stage execution failed",
        "stage": "analysis_a",
        "provider_error_category": "quota_exceeded",
        "safe_message": "provider quota exhausted",
    }
    # the child's attempt trail rides the projected node (one derivation)
    assert failed.attempts and failed.attempts[-1].error is not None
    assert failed.attempts[-1].error.category is ProviderErrorCategory.QUOTA_EXCEEDED
    # succeeded / skipped siblings carry NO attempt trail and no stage error
    ok = next(n for n in result.report.nodes if n.node.node_key == "analysis_b")
    assert ok.attempts == () and ok.node.error is None
    skipped = next(n for n in result.report.nodes if n.node.node_key == "review")
    assert skipped.node.error == {"reason": "upstream stage failed"}
    assert result.report.execution.status is ExecutionStatus.FAILED


def test_api_mapping_reaches_the_real_category_and_names_the_stage() -> None:
    w = World({"alpha": QuotaAdapter("alpha", fail_when="analysis_a")}, ["model-x", "model-y"])
    report = w.run(DIAMOND).report
    provider_error = _last_provider_error(report)
    assert provider_error is not None
    assert provider_error.category is ProviderErrorCategory.QUOTA_EXCEEDED
    assert _failed_stage(report) == "analysis_a"
    detail = execution_failure_detail(
        str(report.execution.id), provider_error, stage=_failed_stage(report)
    )
    assert detail.code is ErrorCode.ENTITLEMENT_EXCEEDED  # not an opaque execution_failed
    assert detail.message == "provider quota exhausted"
    assert detail.details == {
        "execution_id": str(report.execution.id),
        "provider_error_category": "quota_exceeded",
        "stage": "analysis_a",
    }


def test_historical_shapes_are_unchanged_without_a_stage() -> None:
    execution_id = str(uuid4())
    plain = execution_failure_detail(execution_id, None)
    assert plain.code is ErrorCode.EXECUTION_FAILED
    assert plain.details == {"execution_id": execution_id}
    with_stage = execution_failure_detail(execution_id, None, stage="review")
    assert with_stage.details == {"execution_id": execution_id, "stage": "review"}
    # a single-node (non-strategy) failure has no stage key on its node
    w = World({"alpha": RecordingAdapter("alpha", fail_when="generate")}, ["model-x"])
    report = w.run(ExecutionStrategySpec(mode="auto")).report
    assert report.execution.status is ExecutionStatus.FAILED
    # auto composes a one-stage plan; its failed node still names the stage
    assert _failed_stage(report) == "generate"
