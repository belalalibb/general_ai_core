"""StrategyExecutor — executes a caller-defined ExecutionStrategySpec (R188 C2).

WHAT THIS IS
------------
The Core primitive that lets a caller control HOW a task is executed —
stages, roles, per-stage model policy, sequencing, bounded parallelism,
review/retest — WITHOUT a second router, a second execution service, or an
enforced methodology.

- ROUTING: every stage is resolved by the injected ``SimpleScoringRouter``
  (02 §2 invariant 5 — the Router decides). A stage's ``model_policy`` is
  the 10 §13.5 node union; ``None`` routes AUTO. Runtime resource signals
  (R188 A) apply automatically because they live inside the ONE router.
- EXECUTION: every stage is ONE ``ExecutionService.execute_single`` call —
  its own stored Execution, its own reservation/settlement, its own
  failover walk. The strategy never calls an adapter itself.
- COMPOSITION: stages run in topological waves (``spec.waves()``); a wave's
  stages run concurrently under a semaphore of ``spec.max_parallel``.
  Upstream outputs are threaded under the documented ``previous_output``
  key (one upstream) or ``upstream_outputs`` (many) — plus ``stage`` /
  ``role`` / ``instruction`` / ``kind`` as payload DATA the model sees.
- REVIEW / RETEST: a ``review`` stage receives the reviewed output as
  ``subject`` and is asked for a verdict; a ``retest`` stage re-runs its
  instruction against the upstream output. Both are ordinary model calls
  routed by policy — no hidden judge subsystem, no chain-of-thought exposure.
- FAILURE: a failed stage fails the strategy; stages that depended on it are
  SKIPPED (recorded, never hidden — 12 §12); independent stages in the same
  wave still complete so their work and cost are recorded truthfully.
- AUTO: ``mode="auto"`` composes a bounded, policy-valid plan: one
  ``generate`` stage carrying the request's model policy; a ``review``
  stage is added ONLY when the caller asked for verification
  (``auto_review=True``) — the Core never imposes a methodology.
- TEMPLATE: ``mode="template"`` resolves ``template_id`` in an OPTIONAL
  injected mapping; unknown id ⇒ loud :class:`UnknownTemplate`.
- REPORT: the strategy is projected onto the store's ``ExecutionReport``
  shape (strategy=``hybrid``, one node per stage, child execution ids in
  ``cost_snapshot``) so ``GET /v1/executions/{id}`` and traces work unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from core.contracts.base import JsonObject, utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.contracts.execution_strategy import (
    ExecutionStrategySpec,
    StageKind,
    StrategyStage,
)
from core.contracts.model_policy import NodeModelPolicy
from core.contracts.provider import ProviderGenerateResponse, ProviderOperation
from core.contracts.routing import RoutingRequest
from core.execution.service import ExecutionReport, ExecutionService, NodeReport
from core.routing.errors import RoutingError
from core.routing.router import SimpleScoringRouter

PREVIOUS_OUTPUT_KEY = "previous_output"
UPSTREAM_OUTPUTS_KEY = "upstream_outputs"


class StrategyError(Exception):
    """Base for strategy-level refusals (never silent degradation)."""


class UnknownTemplate(StrategyError):
    """``mode=template`` named an id the template registry does not hold."""


@dataclass(frozen=True)
class StageOutcome:
    """One stage's result: its routed/executed child report or its refusal."""

    stage: StrategyStage
    report: ExecutionReport | None
    routing_error: str | None = None
    skipped: bool = False

    @property
    def succeeded(self) -> bool:
        return (
            self.report is not None
            and self.report.execution.status is ExecutionStatus.SUCCEEDED
        )

    @property
    def output(self) -> JsonObject | None:
        return None if self.report is None else self.report.final_output


@dataclass(frozen=True)
class StrategyReport:
    """Whole-strategy result plus the projection the store persists."""

    spec: ExecutionStrategySpec
    outcomes: tuple[StageOutcome, ...]
    report: ExecutionReport

    @property
    def succeeded(self) -> bool:
        return self.report.execution.status is ExecutionStatus.SUCCEEDED


def compose_auto_strategy(
    *, model_policy: NodeModelPolicy | None, auto_review: bool
) -> ExecutionStrategySpec:
    """AUTO: a bounded, policy-valid plan — never a hidden methodology."""
    stages = [StrategyStage(key="generate", kind=StageKind.GENERATE, model_policy=model_policy)]
    if auto_review:
        stages.append(
            StrategyStage(
                key="review",
                kind=StageKind.REVIEW,
                role="reviewer",
                instruction="Review the subject output for correctness; answer with a verdict.",
                depends_on=["generate"],
            )
        )
    return ExecutionStrategySpec(mode="custom", stages=stages)


class StrategyExecutor:
    """Runs an :class:`ExecutionStrategySpec` over the ONE router + ONE service."""

    def __init__(
        self,
        *,
        router: SimpleScoringRouter,
        execution: ExecutionService,
        templates: Mapping[str, ExecutionStrategySpec] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._router = router
        self._execution = execution
        self._templates: Mapping[str, ExecutionStrategySpec] = templates or {}
        self._id_factory = id_factory
        self._clock = clock

    def resolve(
        self,
        spec: ExecutionStrategySpec,
        *,
        request_model_policy: NodeModelPolicy | None = None,
        auto_review: bool = False,
    ) -> ExecutionStrategySpec:
        """Turn auto/template into a concrete custom plan (loud on unknown)."""
        if spec.mode == "custom":
            return spec
        if spec.mode == "auto":
            return compose_auto_strategy(model_policy=request_model_policy, auto_review=auto_review)
        assert spec.template_id is not None  # validated by the contract
        template = self._templates.get(spec.template_id)
        if template is None:
            msg = f"unknown strategy template {spec.template_id!r}"
            raise UnknownTemplate(msg)
        return template

    async def execute(
        self,
        *,
        spec: ExecutionStrategySpec,
        tenant_id: UUID,
        user_id: UUID,
        ask: str,
        request_hash: str,
        base_payload: JsonObject | None = None,
        operation: ProviderOperation = ProviderOperation.GENERATE_TEXT,
        required_capabilities: list[str] | None = None,
        timeout_ms: int | None = None,
        idempotency_key: str | None = None,
        conversation_id: UUID | None = None,
    ) -> StrategyReport:
        plan = spec if spec.mode == "custom" else self.resolve(spec)
        strategy_id = self._id_factory()
        created_at = self._clock()
        outcomes: dict[str, StageOutcome] = {}
        semaphore = asyncio.Semaphore(plan.max_parallel)
        failed = False

        for wave in plan.waves():
            runnable: list[StrategyStage] = []
            for stage in wave:
                blocked = failed and any(
                    not outcomes[dep].succeeded for dep in stage.depends_on if dep in outcomes
                )
                if blocked:
                    outcomes[stage.key] = StageOutcome(stage=stage, report=None, skipped=True)
                else:
                    runnable.append(stage)

            async def _run_stage(stage: StrategyStage) -> StageOutcome:
                async with semaphore:
                    return await self._execute_stage(
                        stage,
                        upstream={dep: outcomes[dep] for dep in stage.depends_on},
                        tenant_id=tenant_id,
                        user_id=user_id,
                        ask=ask,
                        base_payload=base_payload or {},
                        operation=operation,
                        required_capabilities=required_capabilities or [],
                        request_hash=f"{request_hash}:{stage.key}",
                        timeout_ms=timeout_ms,
                        idempotency_key=(
                            None if idempotency_key is None else f"{idempotency_key}:{stage.key}"
                        ),
                        conversation_id=conversation_id,
                    )

            results = await asyncio.gather(*(_run_stage(stage) for stage in runnable))
            for outcome in results:
                outcomes[outcome.stage.key] = outcome
                if not outcome.succeeded:
                    failed = True

        ordered = tuple(outcomes[stage.key] for stage in plan.stages)
        report = self._project(plan, ordered, strategy_id, tenant_id, user_id, request_hash,
                               created_at, idempotency_key, conversation_id)
        return StrategyReport(spec=plan, outcomes=ordered, report=report)

    # -- one stage = one routed, stored execution ------------------------------------

    async def _execute_stage(
        self,
        stage: StrategyStage,
        *,
        upstream: Mapping[str, StageOutcome],
        tenant_id: UUID,
        user_id: UUID,
        ask: str,
        base_payload: JsonObject,
        operation: ProviderOperation,
        required_capabilities: list[str],
        request_hash: str,
        timeout_ms: int | None,
        idempotency_key: str | None,
        conversation_id: UUID | None,
    ) -> StageOutcome:
        try:
            decision = self._router.route(
                RoutingRequest(
                    operation=operation,
                    model_policy=stage.model_policy,
                    required_capabilities=list(required_capabilities),
                )
            )
        except RoutingError as exc:
            return StageOutcome(stage=stage, report=None, routing_error=str(exc))

        payload: JsonObject = {**base_payload, "ask": ask, **dict(stage.payload)}
        payload["stage"] = {
            "key": stage.key,
            "kind": stage.kind.value,
            "role": stage.role,
            "instruction": stage.instruction,
        }
        upstream_outputs = {key: out.output for key, out in upstream.items()}
        if len(upstream_outputs) == 1:
            (only,) = upstream_outputs.values()
            payload[PREVIOUS_OUTPUT_KEY] = only
        elif upstream_outputs:
            payload[UPSTREAM_OUTPUTS_KEY] = upstream_outputs
        if stage.kind in (StageKind.REVIEW, StageKind.RETEST):
            payload["subject"] = upstream_outputs

        report = await self._execution.execute_single(
            tenant_id=tenant_id,
            user_id=user_id,
            decision=decision,
            operation=operation,
            payload=payload,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            conversation_id=conversation_id,
            timeout_ms=timeout_ms,
        )
        return StageOutcome(stage=stage, report=report)

    # -- projection onto the persisted shape ------------------------------------------

    def _project(
        self,
        plan: ExecutionStrategySpec,
        outcomes: tuple[StageOutcome, ...],
        strategy_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        request_hash: str,
        created_at: datetime,
        idempotency_key: str | None,
        conversation_id: UUID | None,
    ) -> ExecutionReport:
        nodes: list[NodeReport] = []
        for outcome in outcomes:
            if outcome.skipped:
                status = ExecutionNodeStatus.SKIPPED
                error: JsonObject | None = {"reason": "upstream stage failed"}
            elif outcome.report is None:
                status = ExecutionNodeStatus.FAILED
                error = {"reason": "routing refused", "detail": outcome.routing_error}
            elif outcome.succeeded:
                status, error = ExecutionNodeStatus.SUCCEEDED, None
            else:
                status = ExecutionNodeStatus.FAILED
                error = {"reason": "stage execution failed"}
            child = outcome.report
            node = ExecutionNode(
                id=self._id_factory(),
                execution_id=strategy_id,
                node_key=outcome.stage.key,
                type=ExecutionNodeType.MODEL_CALL,
                status=status,
                input_ref={
                    "kind": outcome.stage.kind.value,
                    "role": outcome.stage.role,
                    "depends_on": list(outcome.stage.depends_on),
                    "child_execution_id": None if child is None else str(child.execution.id),
                },
                output_ref=outcome.output if outcome.succeeded else None,
                retry_count=0,
                error=error,
            )
            response = (
                ProviderGenerateResponse(
                    request_id=strategy_id, succeeded=True, output=dict(outcome.output or {})
                )
                if outcome.succeeded
                else None
            )
            nodes.append(NodeReport(node=node, attempts=(), response=response))

        all_ok = all(o.succeeded for o in outcomes)
        execution = Execution(
            id=strategy_id,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            status=ExecutionStatus.SUCCEEDED if all_ok else ExecutionStatus.FAILED,
            strategy=ExecutionStrategy.HYBRID,
            cost_snapshot={
                "strategy": {
                    "mode": plan.mode,
                    "stages": [s.key for s in plan.stages],
                    "waves": [[s.key for s in wave] for wave in plan.waves()],
                    "max_parallel": plan.max_parallel,
                },
                "child_execution_ids": [
                    str(o.report.execution.id) for o in outcomes if o.report is not None
                ],
                "settlement": "per_stage_child_executions",
            },
            created_at=created_at,
            completed_at=self._clock(),
        )
        return ExecutionReport(
            execution=execution,
            nodes=tuple(nodes),
            status_history=(
                ExecutionStatus.QUEUED,
                ExecutionStatus.RUNNING,
                execution.status,
            ),
        )
