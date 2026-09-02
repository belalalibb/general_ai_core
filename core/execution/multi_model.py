"""Multi-model execution — ExplicitModelsPolicy strategies (10 §13.4).

WHAT THIS IS
------------
The execution-side resolver for the two 10 §13.4 strategies that are
implementable without an evaluator subsystem:

- ``fallback_chain``   — "Try models in order until one succeeds."
  Each ModelRef is routed INDIVIDUALLY (as an ExplicitModelPolicy carrying
  the parent policy's fallback knobs) and executed; the first succeeded
  branch ends the chain. Routing refusals (ineligible model) count as
  branch failures and the chain continues — the NEXT model is the remedy.

- ``parallel_compare`` — "Send to multiple models, evaluate outputs,
  return best/aggregated result." All branches route first, then execute
  concurrently. With a ``judge_policy``: a judge model receives the
  original ask plus every succeeded branch's output and produces the
  final answer (the judge's output IS the result — evaluation by model,
  10 §13.4). Without a judge: the FIRST succeeded branch in policy order
  is the winner (deterministic, recorded MVP aggregation rule; all branch
  outputs remain in the report for the caller).

``allow_partial`` (10 §13.4): in parallel_compare, ``True`` lets the
compare proceed when SOME branches are refused by routing or fail;
``False``/unset refuses loudly on the first branch-level routing refusal
and fails the whole compare if any branch fails (deny-by-default).

WHAT THIS IS NOT
----------------
- best_of_n / debate / specialist_roles need the evaluator/agent
  subsystems — they REFUSE loudly here (UnsupportedStrategy), never
  silently degrade to a different strategy (40 §2 no-guessing).
- The Router still decides every branch (02 §2 invariant 5): this module
  never scores, never picks providers — it only sequences per-branch
  RoutingDecisions produced by the injected router and hands them to the
  injected ExecutionService.
- Judge recursion is refused: a judge_policy of type explicit_models
  would nest multi-model inside multi-model — outside this slice.

AGENT NODE MAPPING (10 §13.5)
-----------------------------
``resolve_node_policy`` applies the documented resolution order verbatim:
node policy > agent default > request model_policy > Router auto (None).
It is a pure function usable by both the single-execute path (node key
"single") and the graph planner.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from core.contracts.base import JsonObject
from core.contracts.model_policy import (
    AgentNodeMappingPolicy,
    ExplicitModelPolicy,
    ExplicitModelsPolicy,
    ModelRef,
    NodeModelPolicy,
    SelectionStrategy,
)
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingDecision, RoutingRequest
from core.execution.service import ExecutionReport, ExecutionService
from core.routing.errors import RoutingError
from core.routing.router import SimpleScoringRouter

#: Strategies implemented in this slice (module docstring: the other three
#: need evaluator/agent subsystems and refuse loudly).
SUPPORTED_STRATEGIES: frozenset[SelectionStrategy] = frozenset(
    {SelectionStrategy.FALLBACK_CHAIN, SelectionStrategy.PARALLEL_COMPARE}
)

#: Payload key under which the judge receives the candidate outputs.
JUDGE_CANDIDATES_KEY = "candidates"


class MultiModelError(Exception):
    """Base for multi-model execution refusals."""


class UnsupportedStrategy(MultiModelError):
    """Strategy outside SUPPORTED_STRATEGIES — refused, never degraded."""


class InvalidJudgePolicy(MultiModelError):
    """judge_policy that would nest multi-model execution — refused."""


#: S3 default in-flight bound for parallel compare. Small on purpose: the
#: compare set is operator-declared (a handful of models), and provider
#: rate limits punish bursts more than latency rewards them.
DEFAULT_MAX_PARALLEL = 4


class CompareRefused(MultiModelError):
    """parallel_compare could not satisfy the policy (allow_partial=False)."""


@dataclass(frozen=True)
class BranchResult:
    """One ModelRef's outcome — routing refusal OR an execution report."""

    model_id: str
    provider_id: str | None
    report: ExecutionReport | None
    routing_refusal: str | None

    @property
    def succeeded(self) -> bool:
        return self.report is not None and self.report.final_output is not None


@dataclass(frozen=True)
class MultiModelReport:
    """Full multi-model trail: branches, winner, optional judge run.

    ``final_report`` is what an API layer responds with — the winning
    branch's report (fallback_chain / no-judge compare), the judge's
    report (judged compare), or the LAST failed branch when nothing
    succeeded (its failure detail explains the outcome).
    """

    strategy: SelectionStrategy
    branches: tuple[BranchResult, ...]
    winner: BranchResult | None
    judge: ExecutionReport | None
    final_report: ExecutionReport


def resolve_node_policy(
    mapping: AgentNodeMappingPolicy,
    node_key: str,
) -> NodeModelPolicy | None:
    """10 §13.5 resolution order, pure: node > agent default > None (auto).

    The caller supplies the request-level fallback itself (rule 3) — this
    function resolves only the mapping's own two levels, returning None
    when the mapping is silent (rule 4: Router auto policy).
    """
    node_policy = mapping.node_model_policies.get(node_key)
    if node_policy is not None:
        return node_policy
    return mapping.default_model_policy


class MultiModelExecutor:
    """Sequence per-branch routing + execution for ExplicitModelsPolicy."""

    def __init__(
        self,
        *,
        router: SimpleScoringRouter,
        execution: ExecutionService,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
    ) -> None:
        if max_parallel < 1:
            msg = "max_parallel must be >= 1"
            raise ValueError(msg)
        self._router = router
        self._execution = execution
        # S3: bounded fan-out for PARALLEL_COMPARE. Every branch still runs,
        # results stay in policy order, allow_partial/failure semantics are
        # unchanged; only how many provider calls are in flight is capped.
        self._max_parallel = max_parallel

    async def execute(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        policy: ExplicitModelsPolicy,
        operation: ProviderOperation,
        payload: JsonObject,
        request_hash: str,
        idempotency_key: str | None = None,
        conversation_id: UUID | None = None,
        timeout_ms: int | None = None,
    ) -> MultiModelReport:
        """Run the policy's strategy; refuse anything outside this slice."""
        strategy = (
            policy.selection_strategy
            if policy.selection_strategy is not None
            else SelectionStrategy.FALLBACK_CHAIN
        )
        if strategy not in SUPPORTED_STRATEGIES:
            msg = (
                f"selection_strategy '{strategy.value}' requires the "
                "evaluator/agent subsystems and is not available in this "
                "slice (supported: fallback_chain, parallel_compare)"
            )
            raise UnsupportedStrategy(msg)
        if policy.judge_policy is not None and isinstance(
            policy.judge_policy, ExplicitModelsPolicy
        ):
            msg = "judge_policy must not itself be explicit_models (no nesting)"
            raise InvalidJudgePolicy(msg)

        if strategy is SelectionStrategy.FALLBACK_CHAIN:
            return await self._fallback_chain(
                policy,
                tenant_id=tenant_id,
                user_id=user_id,
                operation=operation,
                payload=payload,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
                conversation_id=conversation_id,
                timeout_ms=timeout_ms,
            )
        return await self._parallel_compare(
            policy,
            tenant_id=tenant_id,
            user_id=user_id,
            operation=operation,
            payload=payload,
            request_hash=request_hash,
            conversation_id=conversation_id,
            timeout_ms=timeout_ms,
        )

    # --- strategies --------------------------------------------------------------

    async def _fallback_chain(
        self,
        policy: ExplicitModelsPolicy,
        *,
        tenant_id: UUID,
        user_id: UUID,
        operation: ProviderOperation,
        payload: JsonObject,
        request_hash: str,
        idempotency_key: str | None,
        conversation_id: UUID | None,
        timeout_ms: int | None,
    ) -> MultiModelReport:
        branches: list[BranchResult] = []
        for ref in policy.models:
            decision, refusal = self._route_ref(ref, policy, operation)
            if decision is None:
                branches.append(
                    BranchResult(
                        model_id=ref.model_id,
                        provider_id=ref.provider_id,
                        report=None,
                        routing_refusal=refusal,
                    )
                )
                continue  # chain semantics: the next model is the remedy
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
            branch = BranchResult(
                model_id=ref.model_id,
                provider_id=ref.provider_id,
                report=report,
                routing_refusal=None,
            )
            branches.append(branch)
            if branch.succeeded:
                return MultiModelReport(
                    strategy=SelectionStrategy.FALLBACK_CHAIN,
                    branches=tuple(branches),
                    winner=branch,
                    judge=None,
                    final_report=report,
                )
        # Nothing succeeded: final_report = last EXECUTED branch's report;
        # if every branch was refused by routing there is no report at all.
        executed = [b for b in branches if b.report is not None]
        if not executed:
            refusals = "; ".join(b.routing_refusal or "?" for b in branches)
            msg = f"every model in the chain was refused by routing: {refusals}"
            raise CompareRefused(msg)
        last_report = executed[-1].report
        assert last_report is not None
        return MultiModelReport(
            strategy=SelectionStrategy.FALLBACK_CHAIN,
            branches=tuple(branches),
            winner=None,
            judge=None,
            final_report=last_report,
        )

    async def _parallel_compare(
        self,
        policy: ExplicitModelsPolicy,
        *,
        tenant_id: UUID,
        user_id: UUID,
        operation: ProviderOperation,
        payload: JsonObject,
        request_hash: str,
        conversation_id: UUID | None,
        timeout_ms: int | None,
    ) -> MultiModelReport:
        allow_partial = bool(policy.allow_partial)

        # Route EVERY branch first — refusals surface before any execution.
        routed: list[tuple[ModelRef, RoutingDecision | None, str | None]] = []
        for ref in policy.models:
            decision, refusal = self._route_ref(ref, policy, operation)
            if decision is None and not allow_partial:
                msg = (
                    f"model '{ref.model_id}' is not eligible and "
                    f"allow_partial is not true: {refusal}"
                )
                raise CompareRefused(msg)
            routed.append((ref, decision, refusal))

        eligible = [(r, d) for r, d, _ in routed if d is not None]
        if not eligible:
            msg = "no model in the compare set is eligible"
            raise CompareRefused(msg)

        async def _run(decision: RoutingDecision) -> ExecutionReport:
            return await self._execution.execute_single(
                tenant_id=tenant_id,
                user_id=user_id,
                decision=decision,
                operation=operation,
                payload=payload,
                request_hash=request_hash,
                # Branches must NOT share the caller's idempotency key —
                # they are distinct executions by design.
                idempotency_key=None,
                conversation_id=conversation_id,
                timeout_ms=timeout_ms,
            )

        # S3: bounded concurrency. gather() preserves input order so the
        # policy-order rebuild below is unchanged.
        semaphore = asyncio.Semaphore(self._max_parallel)

        async def _bounded(decision: RoutingDecision) -> ExecutionReport:
            async with semaphore:
                return await _run(decision)

        reports = await asyncio.gather(*(_bounded(d) for _, d in eligible))

        # Rebuild the full branch list in policy order.
        reports_iter = iter(reports)
        branches: list[BranchResult] = []
        for ref, decision, refusal in routed:
            if decision is None:
                branches.append(
                    BranchResult(
                        model_id=ref.model_id,
                        provider_id=ref.provider_id,
                        report=None,
                        routing_refusal=refusal,
                    )
                )
            else:
                branches.append(
                    BranchResult(
                        model_id=ref.model_id,
                        provider_id=ref.provider_id,
                        report=next(reports_iter),
                        routing_refusal=None,
                    )
                )

        succeeded = [b for b in branches if b.succeeded]
        failed_executed = [b for b in branches if b.report is not None and not b.succeeded]
        if not succeeded:
            # Nothing to compare — final_report is the last failed branch.
            assert failed_executed  # eligible was non-empty
            last_failed = failed_executed[-1].report
            assert last_failed is not None
            return MultiModelReport(
                strategy=SelectionStrategy.PARALLEL_COMPARE,
                branches=tuple(branches),
                winner=None,
                judge=None,
                final_report=last_failed,
            )
        if failed_executed and not allow_partial:
            msg = (
                f"{len(failed_executed)} of {len(branches)} branches failed "
                "and allow_partial is not true"
            )
            raise CompareRefused(msg)

        # --- judged compare ----------------------------------------------------
        if policy.judge_policy is not None:
            judge_report = await self._run_judge(
                judge_policy=policy.judge_policy,
                succeeded=succeeded,
                tenant_id=tenant_id,
                user_id=user_id,
                operation=operation,
                payload=payload,
                request_hash=request_hash,
                conversation_id=conversation_id,
                timeout_ms=timeout_ms,
            )
            if judge_report.final_output is not None:
                return MultiModelReport(
                    strategy=SelectionStrategy.PARALLEL_COMPARE,
                    branches=tuple(branches),
                    winner=None,  # the judge's answer supersedes branch picks
                    judge=judge_report,
                    final_report=judge_report,
                )
            # Judge failed: fall through to the deterministic no-judge rule —
            # the branches DID succeed; losing them to a judge failure would
            # punish the user for an internal step (documented degradation).
        winner = succeeded[0]  # policy order — deterministic, recorded rule
        winner_report = winner.report
        assert winner_report is not None
        return MultiModelReport(
            strategy=SelectionStrategy.PARALLEL_COMPARE,
            branches=tuple(branches),
            winner=winner,
            judge=None,
            final_report=winner_report,
        )

    # --- internals ---------------------------------------------------------------

    def _route_ref(
        self,
        ref: ModelRef,
        policy: ExplicitModelsPolicy,
        operation: ProviderOperation,
    ) -> tuple[RoutingDecision | None, str | None]:
        """Route ONE ModelRef as an ExplicitModelPolicy (10 §13.3 rules).

        The parent policy's fallback knobs ride along so per-branch provider
        failover behaves exactly as the caller asked (10 §13.4 fields).
        """
        branch_policy = ExplicitModelPolicy(
            type="explicit_model",
            model_id=ref.model_id,
            provider_id=ref.provider_id,
            allow_fallback=policy.allow_fallback,
            fallback_scope=policy.fallback_scope,
        )
        try:
            decision = self._router.route(
                RoutingRequest(operation=operation, model_policy=branch_policy)
            )
        except RoutingError as exc:
            return None, str(exc)
        return decision, None

    async def _run_judge(
        self,
        *,
        judge_policy: NodeModelPolicy,
        succeeded: list[BranchResult],
        tenant_id: UUID,
        user_id: UUID,
        operation: ProviderOperation,
        payload: JsonObject,
        request_hash: str,
        conversation_id: UUID | None,
        timeout_ms: int | None,
    ) -> ExecutionReport:
        """Route + execute the judge; its payload carries the candidates."""
        decision = self._router.route(
            RoutingRequest(operation=operation, model_policy=judge_policy)
        )
        judge_payload: JsonObject = dict(payload)
        candidates: list[JsonObject] = []
        for branch in succeeded:
            branch_report = branch.report
            assert branch_report is not None
            candidates.append({"model_id": branch.model_id, "output": branch_report.final_output})
        judge_payload[JUDGE_CANDIDATES_KEY] = candidates
        return await self._execution.execute_single(
            tenant_id=tenant_id,
            user_id=user_id,
            decision=decision,
            operation=operation,
            payload=judge_payload,
            request_hash=request_hash,
            idempotency_key=None,
            conversation_id=conversation_id,
            timeout_ms=timeout_ms,
        )
