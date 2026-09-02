"""Execution service — consume a RoutingDecision, drive the ProviderAdapter port.

MVP Phase 5 slice 2 (41 §44: "single execution" + "pipeline execution").
Spec anchors:

- 02 §2 invariant 5: "Router decides; Execution executes." This service
  NEVER re-routes, re-scores, or second-guesses the decision — it traverses
  exactly the candidates the Router emitted, in the Router's order
  (``selected`` first, then ``fallback_candidates``).
- 03 §5: Execution / ExecutionNode domain records produced here use the
  contract entities verbatim (core/contracts/execution.py).
- 30 §8/§14: the adapter is the ONLY provider seam; every failure crossing
  it is the normalized ProviderError. Raw adapter exceptions are defensively
  routed through ``adapter.normalize_error`` (30 §14's stated purpose) and
  then treated as error DATA, never re-raised.
- 40 §4.6/§4.7: retry is error-aware (Retryable / Non-Retryable /
  Retry-After / Provider Failover) and bounded — no infinite retry.
- 20 §5: credentials cross this boundary as opaque references only; the
  service resolves provider_id -> credential_ref from injected
  configuration and never sees secret material.

Failure-routing posture (error-aware, 40 §4.6; recorded once, applied
uniformly):

- ``retryable=True``  -> retry the SAME candidate up to the bounded retry
  budget, honoring ``retry_after_ms`` via the injected sleeper; when the
  budget is exhausted, fail over to the next fallback candidate.
- ``retryable=False`` and the category indicts the ROUTE (auth_expired,
  invalid_credential, rate_limited, quota_exceeded, model_unavailable,
  provider_unavailable, unsupported_capability, timeout,
  retryable_server_error) -> fail over to the next candidate immediately
  ("Provider Failover", 40 §4.6; 30 §1: provider failover without changing
  model identity is a routed-candidate concern, not a re-route).
- the category indicts the REQUEST (bad_request) -> fail the node
  immediately; another provider cannot fix a malformed request.
- ``content_rejected`` -> fail the node immediately, NEVER shopped to
  another provider: retrying safety-rejected content across providers would
  launder a refusal (20 §4 deny-posture applied to safety outcomes).

Composition faults (adapter missing, credential ref missing, malformed
pipeline) raise BEFORE any provider work starts — fail-fast, no partial
execution on misconfiguration (core/execution/errors.py).

Usage accounting (T-IMPL-024; 41 §44 "usage reservation/settlement"; 03 §7):
when a :class:`~core.usage.ports.UsageAccountingPort` is bound, the service
reserves ``units_per_stage × stage-count`` BEFORE any provider work (a
denied reservation aborts the execution before a single adapter call) and
resolves the reservation exactly once afterwards — ``settle`` on success,
``fail`` on failure, both settling 1 unit per SUCCEEDED stage (the MVP
task-unit metric; provider-reported raw usage rides along as
``modality_costs`` data, 03 §7). Unbound (``usage=None``) keeps the
pre-T-IMPL-024 behavior: ``cost_snapshot.settlement`` says
``pending_usage_service`` and nothing is charged.

41 §19 billing rules (FINAL Phase 16, T-IMPL-065; recorded):

- "Cost Snapshot: fixed at Task start." — ``estimated_units`` is computed
  ONCE before any provider work and carried verbatim in ``cost_snapshot``
  (the 11 §10 documented key); nothing downstream recomputes it.
- "Internal retry/failover never multiplies the user's cost." — this is
  STRUCTURAL: both the reservation (``units_per_stage × stage-count``)
  and the settlement (``units_per_stage × SUCCEEDED stages``) are stage
  arithmetic; the attempt count appears in NEITHER formula, so a stage
  that succeeded after N retries/failovers costs exactly what a
  first-attempt success costs.
- Estimate→Reserve wiring (the 41 §19 flow): callers holding a
  complexity-based estimate (:class:`~core.usage.estimation.TaskUnitEstimator`
  over ``TaskAnalysis.complexity``) pass it as ``estimated_units``; it
  becomes BOTH the reservation amount and the fixed snapshot value.
  Absent, the recorded MVP stage metric holds (posture unchanged).
  Settlement is NOT overridden by the estimate — 03 §7 verbatim:
  "settled — reservation finalized from ACTUAL usage AFTER execution";
  the estimate prices the hold, actuals price the bill (recorded, not
  invented — a fixed-price settlement rule exists in no doc).

Scope notes (deliberate, not omissions):

- Non-model node types (tool_call, planner, ...), approval gates, and the
  durable workflow runtime (queues/leases/crash recovery, 12 §9) belong to
  the execution-graph phase; this MVP service runs model-call stages
  in-process per 41 §44.
- 41 §49 NOT-CLAIMED rule: this service is verified against hermetic fake
  adapters; end-to-end AI execution stays PENDING_REAL_PROVIDERS.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
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
from core.contracts.provider import (
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderOperation,
)
from core.contracts.routing import CandidateScore, RoutingDecision
from core.contracts.usage import UsageLedger
from core.execution.errors import (
    AdapterNotBound,
    CredentialNotConfigured,
    InvalidPipeline,
)
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import BindingRegistry
from core.usage.ports import UsageAccountingPort

# Categories that indict the REQUEST itself: no retry, no failover — another
# provider cannot fix a malformed request, and safety rejections are never
# shopped across providers (module docstring posture).
_REQUEST_INDICTING: frozenset[ProviderErrorCategory] = frozenset(
    {
        ProviderErrorCategory.BAD_REQUEST,
        ProviderErrorCategory.CONTENT_REJECTED,
    }
)

# Key under which a pipeline stage receives the previous stage's output
# (documented chaining contract of this MVP pipeline).
PREVIOUS_OUTPUT_KEY = "previous_output"


async def _default_sleeper(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass(frozen=True)
class PipelineStage:
    """One model-call stage of a pipeline execution.

    Each stage carries ITS OWN RoutingDecision — the Router decided per
    stage; this service only executes (02 invariant 5). ``node_key``
    identifies the stage in execution records (03 §5).
    """

    node_key: str
    decision: RoutingDecision
    operation: ProviderOperation
    payload: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class AttemptRecord:
    """One provider attempt — full explainability of the traversal."""

    node_key: str
    candidate: CandidateScore
    attempt: int  # 1-based within the candidate
    succeeded: bool
    error: ProviderError | None
    latency_ms: int | None


@dataclass(frozen=True)
class NodeReport:
    """One node's contract record plus its attempt trail and final response."""

    node: ExecutionNode
    attempts: tuple[AttemptRecord, ...]
    response: ProviderGenerateResponse | None


@dataclass(frozen=True)
class ExecutionReport:
    """Service result: the Execution record, per-node reports, status trail.

    ``usage`` is the resolved 03 §7 ledger entry when a usage-accounting
    port is bound to the service, else ``None`` (settlement pending).
    """

    execution: Execution
    nodes: tuple[NodeReport, ...]
    status_history: tuple[ExecutionStatus, ...]
    usage: UsageLedger | None = None

    @property
    def final_output(self) -> JsonObject | None:
        """Output of the last succeeded node, if the execution succeeded."""
        if self.execution.status is not ExecutionStatus.SUCCEEDED:
            return None
        last = self.nodes[-1].response
        return None if last is None else last.output


@dataclass(frozen=True)
class _NodeRun:
    """Internal: outcome of running one stage's candidate traversal."""

    attempts: tuple[AttemptRecord, ...]
    response: ProviderGenerateResponse | None
    error: ProviderError | None

    @property
    def succeeded(self) -> bool:
        return self.response is not None and self.response.succeeded


class ExecutionService:
    """Single + pipeline execution over RoutingDecisions (41 §44 slice 2).

    Dependencies are injected (no I/O of its own — hermetic by design):

    - ``adapters``: provider_id -> ProviderAdapterPort (the ONLY provider
      seam, 30 §8). Missing adapter for a routed provider = composition
      bug -> :class:`AdapterNotBound`.
    - ``credential_refs``: provider_id -> OPAQUE credential reference
      (20 §5). Missing ref = :class:`CredentialNotConfigured`.
    - ``bindings``: T-IMPL-019 BindingRegistry, resolving the
      provider-specific model name for each (provider, model) candidate.
    - ``max_retries_per_candidate``: bounded same-candidate retry budget
      for retryable errors (40 §4.6/§4.7 — no infinite retry).
    - ``usage``: optional UsageAccountingPort (T-IMPL-024). Bound: reserve
      before / settle-or-fail after (module docstring). ``None``: no
      accounting, ``cost_snapshot.settlement = pending_usage_service``.
    - ``units_per_stage``: MVP task-unit metric — units reserved per stage
      and settled per SUCCEEDED stage (10 §3 example: 2 units ≈ 2 stages).
    - ``sleeper`` / ``id_factory`` / ``clock``: seams for hermetic tests.
    """

    def __init__(
        self,
        *,
        adapters: Mapping[UUID, ProviderAdapterPort],
        credential_refs: Mapping[UUID, str],
        bindings: BindingRegistry,
        max_retries_per_candidate: int = 1,
        usage: UsageAccountingPort | None = None,
        units_per_stage: float = 1.0,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if max_retries_per_candidate < 0:
            msg = "max_retries_per_candidate must be >= 0"
            raise ValueError(msg)
        if units_per_stage < 0:
            msg = "units_per_stage must be >= 0"
            raise ValueError(msg)
        self._usage = usage
        self._units_per_stage = units_per_stage
        self._adapters = adapters
        self._credential_refs = credential_refs
        self._bindings = bindings
        self._max_retries = max_retries_per_candidate
        self._sleeper = sleeper if sleeper is not None else _default_sleeper
        self._id_factory = id_factory
        self._clock = clock

    # --- public API ---------------------------------------------------------------

    async def execute_single(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        decision: RoutingDecision,
        operation: ProviderOperation,
        payload: JsonObject,
        request_hash: str,
        idempotency_key: str | None = None,
        conversation_id: UUID | None = None,
        timeout_ms: int | None = None,
        estimated_units: float | None = None,
    ) -> ExecutionReport:
        """Run one model call (03 §5 strategy=single) over the decision.

        ``estimated_units`` (41 §19 Estimate step): an externally computed
        task-unit estimate; becomes the reservation amount and the fixed
        cost-snapshot value. ``None`` keeps the MVP stage metric.
        """
        stage = PipelineStage(
            node_key="single",
            decision=decision,
            operation=operation,
            payload=payload,
        )
        return await self._run(
            stages=[stage],
            strategy=ExecutionStrategy.SINGLE,
            tenant_id=tenant_id,
            user_id=user_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            conversation_id=conversation_id,
            timeout_ms=timeout_ms,
            estimated_units=estimated_units,
        )

    async def execute_pipeline(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        stages: Sequence[PipelineStage],
        request_hash: str,
        idempotency_key: str | None = None,
        conversation_id: UUID | None = None,
        timeout_ms: int | None = None,
        estimated_units: float | None = None,
    ) -> ExecutionReport:
        """Run stages sequentially (03 §5 strategy=pipeline).

        Each stage after the first receives the previous stage's output
        under :data:`PREVIOUS_OUTPUT_KEY` in its payload. A failed stage
        fails the execution and marks all remaining stages ``skipped``
        (12 §12 "partial failure" is recorded, never hidden).
        """
        if not stages:
            msg = "pipeline requires at least one stage"
            raise InvalidPipeline(msg)
        keys = [stage.node_key for stage in stages]
        if len(set(keys)) != len(keys):
            msg = f"pipeline node_keys must be unique, got {keys}"
            raise InvalidPipeline(msg)
        return await self._run(
            stages=stages,
            strategy=ExecutionStrategy.PIPELINE,
            tenant_id=tenant_id,
            user_id=user_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            conversation_id=conversation_id,
            timeout_ms=timeout_ms,
            estimated_units=estimated_units,
        )

    # --- orchestration ------------------------------------------------------------

    async def _run(
        self,
        *,
        stages: Sequence[PipelineStage],
        strategy: ExecutionStrategy,
        tenant_id: UUID,
        user_id: UUID,
        request_hash: str,
        idempotency_key: str | None,
        conversation_id: UUID | None,
        timeout_ms: int | None,
        estimated_units: float | None = None,
    ) -> ExecutionReport:
        # Fail-fast composition validation for the WHOLE route of EVERY
        # stage — misconfiguration must never interrupt an execution
        # mid-flight (errors module posture).
        for stage in stages:
            self._validate_route(stage.decision)

        execution_id = self._id_factory()
        created_at = self._clock()

        # --- cost estimate FIXED AT TASK START (41 §19; T-IMPL-065): computed
        # once BEFORE any provider work; the snapshot carries this value
        # verbatim — retries, failovers, and outcomes never recompute it.
        # An externally supplied estimate (the Estimate→Reserve wiring) wins;
        # absent, the recorded MVP stage metric prices the hold.
        if estimated_units is not None and estimated_units < 0:
            msg = "estimated_units must be >= 0"
            raise ValueError(msg)
        if estimated_units is None:
            estimated_units = self._units_per_stage * len(stages)

        # --- usage reservation (T-IMPL-024; 03 §7) BEFORE any provider work.
        # A denied reservation (budget/entitlement) raises here — no adapter
        # is ever called for work the tenant cannot pay for (20 §4 posture).
        reserved = False
        if self._usage is not None:
            self._usage.reserve(tenant_id, execution_id, estimated_units)
            reserved = True
        status_history: list[ExecutionStatus] = [
            ExecutionStatus.QUEUED,
            ExecutionStatus.RUNNING,
        ]

        node_reports: list[NodeReport] = []
        provider_usage: list[JsonObject] = []
        failed = False
        previous_output: JsonObject | None = None

        try:
            for stage in stages:
                if failed:
                    node_reports.append(
                        self._skipped_node(execution_id, stage, previous_output=None)
                    )
                    continue

                stage_payload = dict(stage.payload)
                if previous_output is not None:
                    stage_payload[PREVIOUS_OUTPUT_KEY] = previous_output

                run = await self._run_node(
                    stage=stage,
                    tenant_id=tenant_id,
                    payload=stage_payload,
                    timeout_ms=timeout_ms,
                )
                node_reports.append(self._completed_node(execution_id, stage, stage_payload, run))
                if run.succeeded and run.response is not None:
                    previous_output = run.response.output
                    if run.response.usage:
                        provider_usage.append(
                            {"node_key": stage.node_key, "usage": run.response.usage}
                        )
                else:
                    failed = True
        except BaseException:
            # A reservation must NEVER leak (03 §7 exactly-once resolution):
            # an unexpected crash mid-execution resolves it as failed with
            # zero settled units before the fault propagates.
            if reserved and self._usage is not None:
                self._usage.fail(execution_id, 0)
            raise

        final_status = ExecutionStatus.FAILED if failed else ExecutionStatus.SUCCEEDED
        status_history.append(final_status)

        # --- usage settlement (exactly-once resolution; 03 §7) -----------------
        # MVP metric: 1 × units_per_stage per SUCCEEDED stage; raw provider-
        # reported usage rides along as modality_costs data.
        ledger: UsageLedger | None = None
        if reserved and self._usage is not None:
            succeeded_stages = sum(
                1 for entry in node_reports if entry.node.status is ExecutionNodeStatus.SUCCEEDED
            )
            actual_units = self._units_per_stage * succeeded_stages
            modality_costs: JsonObject = {"provider_usage": provider_usage}
            if failed:
                ledger = self._usage.fail(execution_id, actual_units, modality_costs=modality_costs)
            else:
                ledger = self._usage.settle(
                    execution_id, actual_units, modality_costs=modality_costs
                )

        cost_snapshot: JsonObject = {
            # 11 §10 documented shape; value FIXED at task start (41 §19).
            "estimated_units": estimated_units,
            "provider_usage": provider_usage,
            "settlement": (
                "pending_usage_service"
                if ledger is None
                else {
                    "status": ledger.status.value,
                    "units_reserved": ledger.units_reserved,
                    "units_settled": ledger.units_settled,
                }
            ),
        }
        execution = Execution(
            id=execution_id,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            status=final_status,
            strategy=strategy,
            cost_snapshot=cost_snapshot,
            created_at=created_at,
            completed_at=self._clock(),
        )
        return ExecutionReport(
            execution=execution,
            nodes=tuple(node_reports),
            status_history=tuple(status_history),
            usage=ledger,
        )

    # --- candidate traversal (Router order, never re-scored) -----------------------

    async def _run_node(
        self,
        *,
        stage: PipelineStage,
        tenant_id: UUID,
        payload: JsonObject,
        timeout_ms: int | None,
    ) -> _NodeRun:
        decision = stage.decision
        route = [decision.selected, *decision.fallback_candidates]
        attempts: list[AttemptRecord] = []
        last_error: ProviderError | None = None

        for candidate in route:
            adapter = self._adapters[candidate.provider_id]
            binding = self._bindings.get(candidate.provider_id, candidate.model_id)
            credential_ref = self._credential_refs[candidate.provider_id]

            attempt = 0
            while attempt <= self._max_retries:
                attempt += 1
                request = ProviderGenerateRequest(
                    request_id=self._id_factory(),
                    tenant_id=tenant_id,
                    operation=stage.operation,
                    provider_model_name=binding.provider_model_name,
                    credential_ref=credential_ref,
                    account_id=candidate.account_id,
                    payload=payload,
                    timeout_ms=timeout_ms,
                )
                response, error = await self._attempt(adapter, request)
                attempts.append(
                    AttemptRecord(
                        node_key=stage.node_key,
                        candidate=candidate,
                        attempt=attempt,
                        succeeded=response is not None and response.succeeded,
                        error=error,
                        latency_ms=None if response is None else response.latency_ms,
                    )
                )
                if response is not None and response.succeeded:
                    return _NodeRun(attempts=tuple(attempts), response=response, error=None)

                assert error is not None  # non-success always carries an error
                last_error = error
                if error.category in _REQUEST_INDICTING:
                    # Request-inherent failure: no retry, no failover.
                    return _NodeRun(attempts=tuple(attempts), response=response, error=error)
                if error.retryable and attempt <= self._max_retries:
                    if error.retry_after_ms is not None and error.retry_after_ms > 0:
                        await self._sleeper(error.retry_after_ms / 1000.0)
                    continue  # bounded same-candidate retry (40 §4.6)
                break  # provider failover: next candidate in Router order

        return _NodeRun(attempts=tuple(attempts), response=None, error=last_error)

    async def _attempt(
        self, adapter: ProviderAdapterPort, request: ProviderGenerateRequest
    ) -> tuple[ProviderGenerateResponse | None, ProviderError | None]:
        """One adapter call; every failure becomes normalized error DATA.

        Adapters must not raise raw exceptions across the boundary (30 §8.1),
        but the service defends anyway: anything raised is passed through the
        adapter's own ``normalize_error`` (30 §14) — never re-raised, never
        interpreted by Core.
        """
        try:
            response = await adapter.generate(request)
        except Exception as exc:  # noqa: BLE001 — boundary normalization (30 §14)
            return None, adapter.normalize_error(exc)
        if response.succeeded:
            return response, None
        if response.error is not None:
            return response, response.error
        # Adapter contract breach (failed without a normalized error):
        # normalize the breach itself rather than inventing provider facts.
        return response, adapter.normalize_error(
            "adapter returned succeeded=false without a normalized error"
        )

    # --- record builders ------------------------------------------------------------

    def _completed_node(
        self,
        execution_id: UUID,
        stage: PipelineStage,
        payload: JsonObject,
        run: _NodeRun,
    ) -> NodeReport:
        succeeded = run.succeeded
        node = ExecutionNode(
            id=self._id_factory(),
            execution_id=execution_id,
            node_key=stage.node_key,
            type=ExecutionNodeType.MODEL_CALL,
            status=(ExecutionNodeStatus.SUCCEEDED if succeeded else ExecutionNodeStatus.FAILED),
            input_ref=payload,
            output_ref=(run.response.output if succeeded and run.response is not None else None),
            retry_count=max(len(run.attempts) - 1, 0),
            error=(
                None if run.error is None else run.error.model_dump(mode="json", exclude_none=True)
            ),
        )
        return NodeReport(node=node, attempts=run.attempts, response=run.response)

    def _skipped_node(
        self,
        execution_id: UUID,
        stage: PipelineStage,
        *,
        previous_output: JsonObject | None,
    ) -> NodeReport:
        del previous_output  # skipped stages never received an input chain
        node = ExecutionNode(
            id=self._id_factory(),
            execution_id=execution_id,
            node_key=stage.node_key,
            type=ExecutionNodeType.MODEL_CALL,
            status=ExecutionNodeStatus.SKIPPED,
            input_ref=dict(stage.payload),
            output_ref=None,
            retry_count=0,
            error=None,
        )
        return NodeReport(node=node, attempts=(), response=None)

    # --- composition validation -----------------------------------------------------

    def _validate_route(self, decision: RoutingDecision) -> None:
        """Every routed candidate must be executable BEFORE work starts."""
        for candidate in [decision.selected, *decision.fallback_candidates]:
            if candidate.provider_id not in self._adapters:
                raise AdapterNotBound(candidate.provider_id)
            if candidate.provider_id not in self._credential_refs:
                raise CredentialNotConfigured(candidate.provider_id)
            # Binding must exist (raises BindingNotFound loudly if not —
            # the Router built candidates FROM bindings, so absence is a
            # composition bug, not provider weather).
            self._bindings.get(candidate.provider_id, candidate.model_id)
