"""ExecutionService semantics (T-IMPL-022; 41 §44 single + pipeline; 02 §2 #5).

Hermetic — fake adapters only, no network (41 §49: end-to-end AI execution
stays PENDING_REAL_PROVIDERS; the service is verified against the port).
Async methods are driven with asyncio.run (no pytest-asyncio; ADR-0001).

Covers the 12 §12 execution-test items applicable to this in-process slice:
single success, pipeline success, node retry, partial failure with fallback —
plus error-aware failure routing (40 §4.6), Router-order traversal without
re-scoring (02 invariant 5), record correctness (03 §5), opaque credential
handling (20 §5), composition fail-fast, and usage reservation/settlement
integration (T-IMPL-024; 03 §7 reserve-before / resolve-exactly-once-after).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    ProviderModelBinding,
)
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNodeStatus, ExecutionStrategy
from core.contracts.model_policy import AutoModelPolicy
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
    ProviderOperation,
)
from core.contracts.routing import CandidateScore, RoutingDecision, ScoringWeights
from core.contracts.usage import UsageLedgerStatus
from core.execution import (
    PREVIOUS_OUTPUT_KEY,
    AdapterNotBound,
    CredentialNotConfigured,
    ExecutionReport,
    ExecutionService,
    InvalidPipeline,
    PipelineStage,
)
from core.providers import BindingRegistry
from core.providers.errors import BindingNotFound
from core.usage import (
    BudgetExceeded,
    EntitlementNotConfigured,
    InMemoryUsageAccounting,
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- fake adapter ------------------------------------------------------------------


def _error(
    category: ProviderErrorCategory,
    *,
    retryable: bool = False,
    retry_after_ms: int | None = None,
) -> ProviderError:
    return ProviderError(
        category=category,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        safe_message=f"fake {category.value}",
    )


class FakeAdapter:
    """Scripted ProviderAdapterPort fake — replays outcomes in order.

    Script entries are either a ProviderError (attempt fails with it),
    an Exception instance (attempt RAISES it — boundary-defense path),
    or a dict (attempt succeeds with that output). After the script is
    exhausted, attempts succeed with ``{"ok": True}``.
    """

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []
        self.normalized: list[object] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"ok": True}
        if isinstance(step, Exception):
            raise step
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=step,
                latency_ms=7,
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=5,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        self.normalized.append(error)
        return _error(ProviderErrorCategory.NON_RETRYABLE_ERROR)


# --- world -------------------------------------------------------------------------


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        status=ModelStatus.ACTIVE,
    )


_SLEEPS: list[float] = []


async def _no_sleep(seconds: float) -> None:
    _SLEEPS.append(seconds)


@pytest.fixture(autouse=True)
def _clear_sleeps() -> None:
    _SLEEPS.clear()


class World:
    """One in-memory execution world: adapters, credentials, bindings."""

    def __init__(self) -> None:
        self.adapters: dict[UUID, FakeAdapter] = {}
        self.credential_refs: dict[UUID, str] = {}
        self.bindings = BindingRegistry()
        self.model = _model("m-alpha")

    def add_provider(
        self, script: list[object] | None = None, *, model: Model | None = None
    ) -> tuple[UUID, FakeAdapter]:
        provider_id = uuid4()
        adapter = FakeAdapter(script)
        self.adapters[provider_id] = adapter
        self.credential_refs[provider_id] = f"secret-ref://{provider_id}"
        target = model if model is not None else self.model
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider_id,
                model_id=target.id,
                provider_model_name=f"vendor/{target.model_key}",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        return provider_id, adapter

    def candidate(
        self, provider_id: UUID, *, model: Model | None = None, score: float = 0.9
    ) -> CandidateScore:
        target = model if model is not None else self.model
        return CandidateScore(model_id=target.id, provider_id=provider_id, score=score)

    def decision(self, selected: CandidateScore, *fallbacks: CandidateScore) -> RoutingDecision:
        return RoutingDecision(
            selected=selected,
            ranked=[selected, *fallbacks],
            fallback_candidates=list(fallbacks),
            policy_snapshot=AutoModelPolicy(type="auto"),
            weights=ScoringWeights(),
        )

    def service(
        self,
        *,
        max_retries: int = 1,
        usage: InMemoryUsageAccounting | None = None,
    ) -> ExecutionService:
        return ExecutionService(
            adapters=self.adapters,
            credential_refs=self.credential_refs,
            bindings=self.bindings,
            max_retries_per_candidate=max_retries,
            usage=usage,
            sleeper=_no_sleep,
        )


def _single(
    world: World,
    decision: RoutingDecision,
    *,
    service: ExecutionService | None = None,
    **overrides: Any,
) -> ExecutionReport:
    svc = service if service is not None else world.service()
    kwargs: dict[str, Any] = {
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "decision": decision,
        "operation": ProviderOperation.GENERATE_TEXT,
        "payload": {"prompt": "hi"},
        "request_hash": "hash-1",
    }
    kwargs.update(overrides)
    return run(svc.execute_single(**kwargs))


def _pipeline(world: World, stages: list[PipelineStage]) -> ExecutionReport:
    return run(
        world.service().execute_pipeline(
            tenant_id=uuid4(), user_id=uuid4(), stages=stages, request_hash="h"
        )
    )


def _stages(world: World, *decisions: RoutingDecision) -> list[PipelineStage]:
    return [
        PipelineStage(
            node_key=f"stage-{i}",
            decision=decision,
            operation=ProviderOperation.GENERATE_TEXT,
            payload={"stage": i},
        )
        for i, decision in enumerate(decisions, start=1)
    ]


# --- single success (12 §12) --------------------------------------------------------


def test_single_success_produces_succeeded_execution() -> None:
    world = World()
    provider_id, adapter = world.add_provider([{"text": "hello"}])
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.execution.strategy is ExecutionStrategy.SINGLE
    assert report.final_output == {"text": "hello"}
    assert len(adapter.requests) == 1


def test_single_status_history_is_queued_running_succeeded() -> None:
    world = World()
    provider_id, _ = world.add_provider()
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.status_history == (
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
        ExecutionStatus.SUCCEEDED,
    )


def test_single_node_record_fields() -> None:
    world = World()
    provider_id, _ = world.add_provider([{"text": "out"}])
    report = _single(world, world.decision(world.candidate(provider_id)))
    node = report.nodes[0].node
    assert node.node_key == "single"
    assert node.status is ExecutionNodeStatus.SUCCEEDED
    assert node.execution_id == report.execution.id
    assert node.input_ref == {"prompt": "hi"}
    assert node.output_ref == {"text": "out"}
    assert node.retry_count == 0
    assert node.error is None


def test_request_carries_opaque_credential_ref_and_binding_model_name() -> None:
    world = World()
    provider_id, adapter = world.add_provider()
    _single(world, world.decision(world.candidate(provider_id)))
    request = adapter.requests[0]
    assert request.credential_ref == f"secret-ref://{provider_id}"
    assert request.provider_model_name == "vendor/m-alpha"
    assert request.operation is ProviderOperation.GENERATE_TEXT


def test_execution_metadata_passthrough() -> None:
    world = World()
    provider_id, _ = world.add_provider()
    conversation = uuid4()
    report = _single(
        world,
        world.decision(world.candidate(provider_id)),
        idempotency_key="idem-1",
        conversation_id=conversation,
    )
    execution = report.execution
    assert execution.request_hash == "hash-1"
    assert execution.idempotency_key == "idem-1"
    assert execution.conversation_id == conversation
    assert execution.completed_at is not None


def test_cost_snapshot_carries_raw_usage_and_pending_settlement() -> None:
    world = World()
    provider_id, _ = world.add_provider([{"text": "x"}])
    report = _single(world, world.decision(world.candidate(provider_id)))
    snapshot = report.execution.cost_snapshot
    assert snapshot["settlement"] == "pending_usage_service"
    assert snapshot["provider_usage"] == [{"node_key": "single", "usage": {"units": 1}}]


# --- node retry (12 §12; 40 §4.6 bounded, error-aware) -------------------------------


def test_retryable_error_retries_same_candidate_then_succeeds() -> None:
    world = World()
    provider_id, adapter = world.add_provider(
        [
            _error(ProviderErrorCategory.RETRYABLE_SERVER_ERROR, retryable=True),
            {"text": "recovered"},
        ]
    )
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert len(adapter.requests) == 2
    node_report = report.nodes[0]
    assert node_report.node.retry_count == 1
    assert [a.attempt for a in node_report.attempts] == [1, 2]
    assert all(a.candidate.provider_id == provider_id for a in node_report.attempts)


def test_retry_budget_is_bounded_no_infinite_retry() -> None:
    world = World()
    always_fail: list[object] = [
        _error(ProviderErrorCategory.RETRYABLE_SERVER_ERROR, retryable=True)
    ] * 10
    provider_id, adapter = world.add_provider(always_fail)
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.execution.status is ExecutionStatus.FAILED
    # max_retries_per_candidate=1 => exactly 2 attempts (initial + 1 retry).
    assert len(adapter.requests) == 2


def test_retry_after_ms_is_honored_via_sleeper() -> None:
    world = World()
    provider_id, _ = world.add_provider(
        [
            _error(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=1500),
            {"text": "ok"},
        ]
    )
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert _SLEEPS == [1.5]


def test_zero_retry_budget_fails_over_immediately() -> None:
    world = World()
    p1, a1 = world.add_provider(
        [_error(ProviderErrorCategory.RETRYABLE_SERVER_ERROR, retryable=True)]
    )
    p2, a2 = world.add_provider([{"text": "fallback"}])
    decision = world.decision(world.candidate(p1), world.candidate(p2))
    report = _single(world, decision, service=world.service(max_retries=0))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert len(a1.requests) == 1
    assert len(a2.requests) == 1


# --- partial failure with fallback (12 §12; provider failover 40 §4.6) ---------------


def test_provider_failover_traverses_fallback_in_router_order() -> None:
    world = World()
    p1, a1 = world.add_provider([_error(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    p2, a2 = world.add_provider([_error(ProviderErrorCategory.MODEL_UNAVAILABLE)])
    p3, a3 = world.add_provider([{"text": "third"}])
    decision = world.decision(world.candidate(p1), world.candidate(p2), world.candidate(p3))
    report = _single(world, decision)
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.final_output == {"text": "third"}
    # Router order, never re-scored: p1 then p2 then p3.
    providers_tried = [a.candidate.provider_id for a in report.nodes[0].attempts]
    assert providers_tried == [p1, p2, p3]
    assert (len(a1.requests), len(a2.requests), len(a3.requests)) == (1, 1, 1)


def test_all_candidates_fail_yields_failed_execution_with_last_error() -> None:
    world = World()
    p1, _ = world.add_provider([_error(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    p2, _ = world.add_provider([_error(ProviderErrorCategory.QUOTA_EXCEEDED)])
    report = _single(world, world.decision(world.candidate(p1), world.candidate(p2)))
    assert report.execution.status is ExecutionStatus.FAILED
    node = report.nodes[0].node
    assert node.status is ExecutionNodeStatus.FAILED
    assert node.error is not None
    assert node.error["category"] == "quota_exceeded"  # LAST error preserved
    assert node.output_ref is None
    assert report.final_output is None


def test_route_indicting_nonretryable_fails_over_without_retry() -> None:
    world = World()
    p1, a1 = world.add_provider([_error(ProviderErrorCategory.INVALID_CREDENTIAL)])
    p2, a2 = world.add_provider([{"text": "ok"}])
    report = _single(world, world.decision(world.candidate(p1), world.candidate(p2)))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert len(a1.requests) == 1  # no same-candidate retry on non-retryable
    assert len(a2.requests) == 1


def test_bad_request_fails_node_immediately_no_failover() -> None:
    world = World()
    p1, a1 = world.add_provider([_error(ProviderErrorCategory.BAD_REQUEST)])
    p2, a2 = world.add_provider([{"text": "never"}])
    report = _single(world, world.decision(world.candidate(p1), world.candidate(p2)))
    assert report.execution.status is ExecutionStatus.FAILED
    assert len(a1.requests) == 1
    assert len(a2.requests) == 0  # request-inherent: never shopped


def test_content_rejected_is_never_shopped_to_another_provider() -> None:
    world = World()
    p1, _ = world.add_provider([_error(ProviderErrorCategory.CONTENT_REJECTED)])
    p2, a2 = world.add_provider([{"text": "never"}])
    report = _single(world, world.decision(world.candidate(p1), world.candidate(p2)))
    assert report.execution.status is ExecutionStatus.FAILED
    assert len(a2.requests) == 0
    node_error = report.nodes[0].node.error
    assert node_error is not None
    assert node_error["category"] == "content_rejected"


def test_raised_adapter_exception_is_normalized_not_reraised() -> None:
    world = World()
    p1, a1 = world.add_provider([RuntimeError("raw provider explosion")])
    p2, _ = world.add_provider([{"text": "ok"}])
    report = _single(world, world.decision(world.candidate(p1), world.candidate(p2)))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert len(a1.normalized) == 1  # normalize_error was consulted (30 §14)
    assert isinstance(a1.normalized[0], RuntimeError)


def test_failed_response_without_error_is_normalized_as_contract_breach() -> None:
    world = World()
    provider_id, adapter = world.add_provider()

    async def bad_generate(
        request: ProviderGenerateRequest,
    ) -> ProviderGenerateResponse:
        return ProviderGenerateResponse(request_id=request.request_id, succeeded=False)

    adapter.generate = bad_generate  # type: ignore[method-assign]
    report = _single(world, world.decision(world.candidate(provider_id)))
    assert report.execution.status is ExecutionStatus.FAILED
    assert adapter.normalized  # breach routed through normalize_error


# --- pipeline (12 §12 pipeline success + partial failure) ----------------------------


def test_pipeline_success_runs_stages_in_order_and_chains_output() -> None:
    world = World()
    p1, a1 = world.add_provider([{"draft": "v1"}])
    p2, a2 = world.add_provider([{"final": "v2"}])
    stages = _stages(
        world, world.decision(world.candidate(p1)), world.decision(world.candidate(p2))
    )
    report = _pipeline(world, stages)
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.execution.strategy is ExecutionStrategy.PIPELINE
    assert report.final_output == {"final": "v2"}
    # Stage 1 got its own payload only; stage 2 got the chained output.
    assert a1.requests[0].payload == {"stage": 1}
    assert a2.requests[0].payload == {
        "stage": 2,
        PREVIOUS_OUTPUT_KEY: {"draft": "v1"},
    }


def test_pipeline_first_stage_has_no_previous_output_key() -> None:
    world = World()
    p1, a1 = world.add_provider()
    report = _pipeline(world, _stages(world, world.decision(world.candidate(p1))))
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert PREVIOUS_OUTPUT_KEY not in a1.requests[0].payload


def test_pipeline_partial_failure_marks_remaining_stages_skipped() -> None:
    world = World()
    p1, _ = world.add_provider([{"ok": 1}])
    p2, _ = world.add_provider([_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)])
    p3, a3 = world.add_provider([{"never": True}])
    stages = _stages(
        world,
        world.decision(world.candidate(p1)),
        world.decision(world.candidate(p2)),
        world.decision(world.candidate(p3)),
    )
    report = _pipeline(world, stages)
    assert report.execution.status is ExecutionStatus.FAILED
    statuses = [n.node.status for n in report.nodes]
    assert statuses == [
        ExecutionNodeStatus.SUCCEEDED,
        ExecutionNodeStatus.FAILED,
        ExecutionNodeStatus.SKIPPED,
    ]
    assert len(a3.requests) == 0  # skipped stage never reached its provider
    assert report.final_output is None


def test_pipeline_stage_fallback_recovers_and_pipeline_continues() -> None:
    world = World()
    p1, _ = world.add_provider([{"ok": 1}])
    p2a, _ = world.add_provider([_error(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    p2b, _ = world.add_provider([{"ok": 2}])
    stages = _stages(
        world,
        world.decision(world.candidate(p1)),
        world.decision(world.candidate(p2a), world.candidate(p2b)),
    )
    report = _pipeline(world, stages)
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.final_output == {"ok": 2}
    assert len(report.nodes[1].attempts) == 2  # failover recorded


def test_pipeline_usage_aggregates_per_node() -> None:
    world = World()
    p1, _ = world.add_provider([{"a": 1}])
    p2, _ = world.add_provider([{"b": 2}])
    stages = _stages(
        world, world.decision(world.candidate(p1)), world.decision(world.candidate(p2))
    )
    report = _pipeline(world, stages)
    usage = report.execution.cost_snapshot["provider_usage"]
    assert isinstance(usage, list)
    assert [entry["node_key"] for entry in usage] == ["stage-1", "stage-2"]


def test_pipeline_rejects_empty_stage_list() -> None:
    world = World()
    with pytest.raises(InvalidPipeline):
        _pipeline(world, [])


def test_pipeline_rejects_duplicate_node_keys() -> None:
    world = World()
    p1, _ = world.add_provider()
    stage = PipelineStage(
        node_key="dup",
        decision=world.decision(world.candidate(p1)),
        operation=ProviderOperation.GENERATE_TEXT,
    )
    with pytest.raises(InvalidPipeline):
        _pipeline(world, [stage, stage])


# --- composition fail-fast (errors module posture) -----------------------------------


def test_adapter_not_bound_raises_before_any_provider_work() -> None:
    world = World()
    p1, a1 = world.add_provider()
    ghost = world.candidate(uuid4())  # provider with no adapter
    decision = world.decision(world.candidate(p1), ghost)
    with pytest.raises(AdapterNotBound):
        _single(world, decision)
    assert len(a1.requests) == 0  # fail-fast: selected candidate never ran


def test_credential_not_configured_raises() -> None:
    world = World()
    p1, _ = world.add_provider()
    del world.credential_refs[p1]
    with pytest.raises(CredentialNotConfigured):
        _single(world, world.decision(world.candidate(p1)))


def test_missing_binding_raises_binding_not_found() -> None:
    world = World()
    p1, _ = world.add_provider()
    other_model = _model("m-unbound")
    decision = world.decision(world.candidate(p1, model=other_model))
    with pytest.raises(BindingNotFound):
        _single(world, decision)


def test_pipeline_validates_all_stages_before_running_any() -> None:
    world = World()
    p1, a1 = world.add_provider([{"ok": 1}])
    ghost_decision = world.decision(world.candidate(uuid4()))
    stages = _stages(world, world.decision(world.candidate(p1)), ghost_decision)
    with pytest.raises(AdapterNotBound):
        _pipeline(world, stages)
    assert len(a1.requests) == 0  # stage 1 never started


def test_negative_retry_budget_rejected() -> None:
    world = World()
    with pytest.raises(ValueError, match="max_retries_per_candidate"):
        ExecutionService(
            adapters=world.adapters,
            credential_refs=world.credential_refs,
            bindings=world.bindings,
            max_retries_per_candidate=-1,
        )


# --- boundary + posture ---------------------------------------------------------------


def test_execution_module_stays_inside_core() -> None:
    import core.execution.errors as errors_mod
    import core.execution.service as service_mod

    for mod in (service_mod, errors_mod):
        assert mod.__file__ is not None
        source = Path(mod.__file__).read_text()
        for forbidden in ("import providers", "import infrastructure", "import apps"):
            assert forbidden not in source, f"{mod.__name__} imports {forbidden}"


def test_service_never_logs_or_stores_credential_material() -> None:
    """The service moves ONLY the opaque ref; it appears solely on the
    provider request (the documented 20 §5 crossing point)."""
    world = World()
    p1, adapter = world.add_provider()
    report = _single(world, world.decision(world.candidate(p1)))
    ref = f"secret-ref://{p1}"
    assert adapter.requests[0].credential_ref == ref
    # No execution/node record carries the credential ref.
    dumped = report.execution.model_dump_json() + "".join(
        n.node.model_dump_json() for n in report.nodes
    )
    assert ref not in dumped


def test_failed_single_status_history_ends_failed() -> None:
    world = World()
    p1, _ = world.add_provider([_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)])
    report = _single(world, world.decision(world.candidate(p1)))
    assert report.status_history[-1] is ExecutionStatus.FAILED
    assert report.final_output is None


# --- usage reservation/settlement integration (T-IMPL-024; 03 §7) --------------------


def _usage_world(limit: float = 10.0) -> tuple[World, InMemoryUsageAccounting, UUID]:
    world = World()
    accounting = InMemoryUsageAccounting()
    tenant_id = uuid4()
    accounting.configure_tenant(tenant_id, plan="pro", task_units_limit=limit)
    return world, accounting, tenant_id


def test_success_settles_one_unit_per_stage() -> None:
    world, accounting, tenant = _usage_world()
    p1, _ = world.add_provider([{"a": 1}])
    p2, _ = world.add_provider([{"b": 2}])
    stages = _stages(
        world, world.decision(world.candidate(p1)), world.decision(world.candidate(p2))
    )
    report = run(
        world.service(usage=accounting).execute_pipeline(
            tenant_id=tenant, user_id=uuid4(), stages=stages, request_hash="h"
        )
    )
    assert report.usage is not None
    assert report.usage.status is UsageLedgerStatus.SETTLED
    assert report.usage.units_reserved == 2.0  # 1 unit/stage × 2 stages held upfront
    assert report.usage.units_settled == 2.0
    summary = accounting.summary(tenant)
    assert summary.task_units.used == 2.0
    assert summary.task_units.remaining == 8.0


def test_failed_execution_resolves_ledger_as_failed_charging_succeeded_stages() -> None:
    world, accounting, tenant = _usage_world()
    p1, _ = world.add_provider([{"a": 1}])
    p2, _ = world.add_provider([_error(ProviderErrorCategory.NON_RETRYABLE_ERROR)])
    stages = _stages(
        world, world.decision(world.candidate(p1)), world.decision(world.candidate(p2))
    )
    report = run(
        world.service(usage=accounting).execute_pipeline(
            tenant_id=tenant, user_id=uuid4(), stages=stages, request_hash="h"
        )
    )
    assert report.execution.status is ExecutionStatus.FAILED
    assert report.usage is not None
    assert report.usage.status is UsageLedgerStatus.FAILED
    assert report.usage.units_settled == 1.0  # only stage-1 SUCCEEDED
    # The unconsumed hold was released, not kept charged.
    assert accounting.summary(tenant).task_units.remaining == 9.0


def test_budget_denial_aborts_before_any_provider_call() -> None:
    world, accounting, tenant = _usage_world(limit=1.0)
    p1, a1 = world.add_provider()
    p2, a2 = world.add_provider()
    stages = _stages(
        world, world.decision(world.candidate(p1)), world.decision(world.candidate(p2))
    )
    with pytest.raises(BudgetExceeded):
        run(
            world.service(usage=accounting).execute_pipeline(
                tenant_id=tenant, user_id=uuid4(), stages=stages, request_hash="h"
            )
        )
    assert len(a1.requests) == 0  # denied BEFORE provider work (20 §4)
    assert len(a2.requests) == 0
    assert accounting.summary(tenant).task_units.remaining == 1.0  # nothing held


def test_unconfigured_tenant_is_denied_by_default() -> None:
    world = World()
    accounting = InMemoryUsageAccounting()  # no configure_tenant call
    p1, a1 = world.add_provider()
    with pytest.raises(EntitlementNotConfigured):
        _single(
            world,
            world.decision(world.candidate(p1)),
            service=world.service(usage=accounting),
        )
    assert len(a1.requests) == 0


def test_unexpected_crash_resolves_reservation_before_propagating() -> None:
    """A mid-execution fault must not leak the hold (03 §7 exactly-once)."""
    world, accounting, tenant = _usage_world()
    p1, _ = world.add_provider()

    class Boom(Exception):
        pass

    async def _explode(seconds: float) -> None:
        raise Boom

    # Retryable error with retry_after triggers the sleeper, which explodes
    # mid-run — simulating an unexpected infrastructure fault.
    p2, _ = world.add_provider(
        [_error(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=50)]
    )
    decision = world.decision(world.candidate(p2))
    execution_ids: list[UUID] = []

    def _capture_id() -> UUID:
        execution_ids.append(uuid4())
        return execution_ids[-1]

    svc = ExecutionService(
        adapters=world.adapters,
        credential_refs=world.credential_refs,
        bindings=world.bindings,
        usage=accounting,
        sleeper=_explode,
        id_factory=_capture_id,
    )
    with pytest.raises(Boom):
        run(
            svc.execute_single(
                tenant_id=tenant,
                user_id=uuid4(),
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"prompt": "hi"},
                request_hash="h",
            )
        )
    ledger = accounting.get(execution_ids[0])
    assert ledger.status is UsageLedgerStatus.FAILED
    assert ledger.units_settled == 0
    assert accounting.summary(tenant).task_units.remaining == 10.0


def test_success_report_ledger_visible_in_cost_snapshot() -> None:
    world, accounting, tenant = _usage_world()
    p1, _ = world.add_provider([{"text": "x"}])
    report = _single(
        world,
        world.decision(world.candidate(p1)),
        service=world.service(usage=accounting),
        tenant_id=tenant,
    )
    settlement = report.execution.cost_snapshot["settlement"]
    assert settlement == {
        "status": "settled",
        "units_reserved": 1.0,
        "units_settled": 1.0,
    }


def test_unbound_usage_keeps_pending_settlement_and_none_ledger() -> None:
    world = World()
    p1, _ = world.add_provider()
    report = _single(world, world.decision(world.candidate(p1)))
    assert report.usage is None
    assert report.execution.cost_snapshot["settlement"] == "pending_usage_service"
