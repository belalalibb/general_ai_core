"""AgentRuntime — shared Understand→Plan→Act→Observe→Reassess→Verify→Stop.

Design (P2 one rule per concern, P4 model proposes / code disposes, P6
everything is evidence):

- TOOLS: ``AgentToolSpec`` binds a core ``Tool`` (already registered in
  the ONE core ``ToolRegistry``) to a handler plus the firewall inputs the
  Capability Firewall needs. The runtime never invents permissions — the
  tenant's ``TenantPolicy`` in the shared firewall decides, through the
  shared ``ToolCallGate`` → ``ToolExecutor``. A consumer that wants a tool
  the tenant is not granted gets a REFUSED observation, not an exception.
- MODEL: the propose seam is the platform's OWN routing + execution path
  (``router.route`` → ``execution_service.execute_single``). Every
  reasoning call is a stored, labeled, budget-bounded Execution — no
  side-channel LLM, provider-agnostic by construction.
- PROMPT: ``build_agent_prompt`` states the closed proposal vocabulary the
  shared ``parse_agent_proposal`` already enforces, plus the tools the
  caller selected (progressive disclosure: only the admitted subset), the
  budget, and the observations so far (which include repeated-failure
  refusals and verification rejections — the model must reassess).
- VERIFY: ``evidence_verifier`` is the default deterministic verdict —
  a final that CITES evidence (``evidence`` list of step numbers) must
  cite steps that actually succeeded this run; a final with no citations
  passes only when the run has no evidence to cite (pure answer). Consumers
  may bind a stricter verifier; the loop composes it identically.
- BOUNDS: ``max_steps`` (capped), ``deadline_ms``, ``max_repeated_failures``
  — all enforced by the shared loop, never by the prompt.
- RECORD: ``agent_execution_report`` converts the loop's ``AgentRunReport``
  into the ``ExecutionReport`` shape the execution store already persists,
  so ``GET /v1/executions/{id}`` and the admin trace readers work unchanged
  for agent runs (strategy=agent, one node per step).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from core.audit.ports import AuditLogPort
from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNode, ExecutionNodeStatus, ExecutionNodeType
from core.contracts.model_policy import ModelPolicy
from core.contracts.provider import ProviderGenerateResponse, ProviderOperation
from core.contracts.routing import RoutingRequest
from core.contracts.security import ActorKind
from core.contracts.tools import Tool
from core.execution.agent import AgentToolBinding
from core.execution.loop import (
    DEFAULT_MAX_REPEATED_FAILURES,
    AgentLoop,
    AgentRunReport,
    VerifyFn,
)
from core.execution.service import ExecutionReport, ExecutionService, NodeReport
from core.identity.devices import DeviceRegistry
from core.routing.errors import RoutingError
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.security.firewall import CapabilityFirewall
from core.tools.executor import ToolExecutor, ToolHandler
from core.tools.gate import ToolCallGate
from core.tools.registry import ToolRegistry
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured
from core.usage.ports import UsageAccountingPort

#: Default and hard cap on proposals per run — a bound the CALLER cannot
#: exceed (S4 / flood posture): a run may ask for fewer steps, never more.
DEFAULT_AGENT_MAX_STEPS = 8
MAX_AGENT_MAX_STEPS = 32
#: Default wall-clock bound per run (S4). Consumers may lower it.
DEFAULT_AGENT_DEADLINE_MS = 120_000

#: Label every reasoning Execution carries (metadata, never authority).
AGENT_RUNTIME_LABEL_KEY = "agent_runtime"


class ReasoningFailed(Exception):
    """The propose seam could not obtain a model output.

    Raised INSIDE the propose callable so the shared loop records it as
    ``propose_failed`` (closed stop reason) — never a silent empty step.
    """


ResultCheck = Callable[[JsonObject], str | None]
"""Semantic success predicate for ONE tool's result: ``None`` = the result
satisfies the tool's own success rule; a string = the reason it does not."""


class ToolResultRejected(Exception):
    """A tool ran (transport succeeded) but its result failed its own rule.

    Raised INSIDE the bound handler so the ONE executor records the attempt
    as ``failed`` with this reason as data — the result never enters the
    evidence ledger and repeated identical calls trip the loop's
    repeated-failure refusal. Closes coding-benchmark weakness W1
    ("run_tests succeeded as a tool while the tests failed") generically.
    """

    def __init__(self, reason: str, result: JsonObject) -> None:
        self.reason = reason
        self.result = result
        super().__init__(
            f"{reason}; result={json.dumps(result, sort_keys=True, default=str)[:500]}"
        )


@dataclass(frozen=True)
class AgentToolSpec:
    """One agent-visible tool: core Tool + handler + firewall inputs.

    ``tool`` must already be registered in the core ``ToolRegistry`` the
    runtime is composed with (the runtime looks it up; it never registers).
    ``permission`` must be one of ``tool.permissions``. ``description`` and
    ``arguments`` are what the model is shown (progressive disclosure).
    ``verify_result`` (optional) is the tool's semantic success rule — see
    :class:`ToolResultRejected`.
    """

    tool: Tool
    handler: ToolHandler
    permission: str
    resource: str
    entitlement: str
    description: str
    arguments: JsonObject = field(default_factory=dict)
    scope: str = "tenant"
    risk_level: str = "low"
    estimated_units: float = 0.0
    verify_result: ResultCheck | None = None

    def __post_init__(self) -> None:
        if self.permission not in self.tool.permissions:
            msg = (
                f"permission {self.permission!r} is not declared by tool "
                f"{self.tool.name!r} ({sorted(self.tool.permissions)})"
            )
            raise ValueError(msg)

    @property
    def name(self) -> str:
        return self.tool.name

    def describe(self) -> JsonObject:
        return {
            "name": self.tool.name,
            "description": self.description,
            "arguments": dict(self.arguments),
            "permission": self.permission,
            "risk_level": self.risk_level,
        }

    def bound_handler(self) -> ToolHandler:
        """The handler the executor runs: raw, or wrapped by ``verify_result``."""
        check = self.verify_result
        if check is None:
            return self.handler
        handler = self.handler

        async def checked(arguments: JsonObject) -> JsonObject:
            result = await handler(arguments)
            reason = check(result)
            if reason is not None:
                raise ToolResultRejected(reason, result)
            return result

        return checked

    def binding(self) -> AgentToolBinding:
        return AgentToolBinding(
            tool_id=self.tool.id,
            permission=self.permission,
            resource=self.resource,
            scope=self.scope,
            entitlement=self.entitlement,
            risk_level=self.risk_level,
            estimated_units=self.estimated_units,
        )


@dataclass(frozen=True)
class AgentRunOutcome:
    """What one runtime run produced: the loop report + reasoning trail."""

    report: AgentRunReport
    #: Execution ids of every reasoning (model) call, in step order —
    #: each one is a stored Execution a reader can trace independently.
    reasoning_execution_ids: tuple[UUID, ...]
    #: The ExecutionReport-shaped record for the store (strategy=agent).
    execution_report: ExecutionReport


_PROTOCOL = (
    "You are an agent running inside a governed platform. Respond with ONLY "
    "one raw JSON object (no markdown fences, no prose) in EXACTLY one of "
    "these shapes:\n"
    '  {"action": "tool_call", "tool": "<name>", "arguments": {...}, '
    '"reasoning": "<short>"}\n'
    '  {"action": "final", "output": {"answer": "<text>", "evidence": '
    "[<step numbers whose tool results support the answer>]}, "
    '"reasoning": "<short>"}\n'
    "Rules: use only the tools listed (only their declared arguments); a "
    "tool call that already failed with the same arguments will be refused "
    "— change arguments, tool, or strategy; cite ONLY steps that succeeded; "
    "finalize before the budget runs out; if no tool applies, finalize "
    "with an honest answer and empty evidence.\n"
)


def build_agent_prompt(
    *,
    task: JsonObject,
    tools: Sequence[JsonObject],
    observations: Sequence[JsonObject],
    budget: JsonObject,
) -> str:
    """Deterministic prompt: protocol + selected tools + budget + history."""
    parts = [
        _PROTOCOL,
        "Budget: " + json.dumps(budget, sort_keys=True),
        "Available tools:\n" + json.dumps(list(tools), ensure_ascii=False),
        "Task:\n" + json.dumps(task, ensure_ascii=False, default=str),
    ]
    if observations:
        parts.append(
            "Observations so far (step-ordered; 'refused'/'failed' mean the "
            "action did NOT happen):\n"
            + json.dumps(list(observations), ensure_ascii=False, default=str)
        )
    return "\n".join(parts)


async def evidence_verifier(request: JsonObject, output: JsonObject) -> JsonObject:
    """Default deterministic finalization verdict (P4, P6).

    Reads the run's evidence ledger the runtime threads into ``request``
    under ``_evidence_steps`` (set of succeeded step numbers). Rejects a
    final that cites steps which did not succeed (invented evidence), and
    a final whose ``output`` is not an object with a non-empty ``answer``.
    """
    steps_ok = request.get("_evidence_steps")
    ok: set[int] = set(steps_ok) if isinstance(steps_ok, list) else set()
    answer = output.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return {"verified": False, "reason": "final output must carry a non-empty 'answer'"}
    cited_raw = output.get("evidence", [])
    if not isinstance(cited_raw, list):
        return {"verified": False, "reason": "'evidence' must be a list of step numbers"}
    cited: list[int] = []
    for item in cited_raw:
        if isinstance(item, bool) or not isinstance(item, int):
            return {"verified": False, "reason": f"evidence item is not a step number: {item!r}"}
        cited.append(item)
    invented = sorted(set(cited) - ok)
    if invented:
        return {
            "verified": False,
            "reason": "cited evidence steps did not succeed this run",
            "invented": invented,
            "available": sorted(ok),
        }
    return {"verified": True, "cited": sorted(set(cited)), "available": sorted(ok)}


class AgentRuntime:
    """Composition root for agent turns over the shared seams (see module)."""

    def __init__(
        self,
        *,
        router: SimpleScoringRouter,
        execution_service: ExecutionService,
        tool_registry: ToolRegistry,
        firewall: CapabilityFirewall,
        devices: DeviceRegistry,
        audit: AuditLogPort,
        usage: UsageAccountingPort,
        store_report: Callable[[ExecutionReport], None] | None = None,
        max_steps: int = DEFAULT_AGENT_MAX_STEPS,
        deadline_ms: int | None = DEFAULT_AGENT_DEADLINE_MS,
        max_repeated_failures: int = DEFAULT_MAX_REPEATED_FAILURES,
    ) -> None:
        if not (1 <= max_steps <= MAX_AGENT_MAX_STEPS):
            msg = f"max_steps must be within [1, {MAX_AGENT_MAX_STEPS}]"
            raise ValueError(msg)
        self._router = router
        self._execution = execution_service
        self._tools = tool_registry
        self._firewall = firewall
        self._devices = devices
        self._audit = audit
        self._usage = usage
        self._store_report = store_report
        self._max_steps = max_steps
        self._deadline_ms = deadline_ms
        self._max_repeated_failures = max_repeated_failures

    # -- public --------------------------------------------------------------------

    @property
    def max_steps(self) -> int:
        return self._max_steps

    def admit_tools(self, specs: Sequence[AgentToolSpec]) -> list[AgentToolSpec]:
        """Composition-time admission: registered + selectable + unique names.

        Raises ``ValueError`` naming the first violation — these are wiring
        mistakes of the CONSUMER, never a runtime condition.
        """
        seen: set[str] = set()
        admitted: list[AgentToolSpec] = []
        for spec in specs:
            if spec.name in seen:
                msg = f"duplicate agent tool name: {spec.name!r}"
                raise ValueError(msg)
            seen.add(spec.name)
            self._tools.select(spec.tool.id)  # raises if unknown / not active
            admitted.append(spec)
        return admitted

    async def run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        task: JsonObject,
        tools: Sequence[AgentToolSpec],
        model_policy: ModelPolicy | None = None,
        max_steps: int | None = None,
        deadline_ms: int | None = None,
        verify: VerifyFn | None = None,
        actor: ActorKind = ActorKind.USER,
        conversation_id: UUID | None = None,
        idempotency_key: str | None = None,
        label: JsonObject | None = None,
    ) -> AgentRunOutcome:
        """One bounded agent run. Never raises for model/tool outcomes."""
        specs = self.admit_tools(tools)
        steps = self._max_steps if max_steps is None else max_steps
        if not (1 <= steps <= self._max_steps):
            msg = f"max_steps must be within [1, {self._max_steps}] for this runtime"
            raise ValueError(msg)
        deadline = self._deadline_ms if deadline_ms is None else deadline_ms
        if deadline is not None and self._deadline_ms is not None:
            deadline = min(deadline, self._deadline_ms)

        executor = ToolExecutor(
            gate=ToolCallGate(tools=self._tools, firewall=self._firewall, devices=self._devices),
            handlers={spec.tool.id: spec.bound_handler() for spec in specs},
            audit=self._audit,
            usage=self._usage,
        )
        bindings = {spec.name: spec.binding() for spec in specs}
        described = [spec.describe() for spec in specs]
        reasoning_ids: list[UUID] = []
        evidence_steps: list[int] = []

        async def propose(payload: JsonObject) -> JsonObject:
            observations = payload.get("observations")
            obs_list = observations if isinstance(observations, list) else []
            for entry in obs_list:
                if (
                    isinstance(entry, dict)
                    and entry.get("status") == "succeeded"
                    and isinstance(entry.get("step"), int)
                    and entry["step"] not in evidence_steps
                ):
                    evidence_steps.append(entry["step"])
            budget = payload.get("budget")
            prompt = build_agent_prompt(
                task=task,
                tools=described,
                observations=obs_list,
                budget=budget if isinstance(budget, dict) else {},
            )
            raw, execution_id = await self._reason(
                tenant_id=tenant_id,
                user_id=user_id,
                prompt=prompt,
                model_policy=model_policy,
                step=budget.get("step") if isinstance(budget, dict) else None,
                label=label,
            )
            if execution_id is not None:
                reasoning_ids.append(execution_id)
            return raw

        bound_verify: VerifyFn = verify if verify is not None else evidence_verifier

        async def verify_with_evidence(request: JsonObject, output: JsonObject) -> JsonObject:
            enriched = dict(request)
            enriched["_evidence_steps"] = list(evidence_steps)
            return await bound_verify(enriched, output)

        loop = AgentLoop(
            propose=propose,
            tools=executor,
            bindings=bindings,
            max_steps=steps,
            verify=verify_with_evidence,
            max_repeated_failures=self._max_repeated_failures,
            deadline_ms=deadline,
        )
        request_hash = hashlib.sha256(
            json.dumps(task, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        report = await loop.execute(
            tenant_id=tenant_id,
            user_id=user_id,
            request=task,
            request_hash=request_hash,
            actor=actor,
            actor_id=user_id,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
        )
        execution_report = agent_execution_report(report, reasoning_ids)
        if self._store_report is not None:
            self._store_report(execution_report)
        return AgentRunOutcome(
            report=report,
            reasoning_execution_ids=tuple(reasoning_ids),
            execution_report=execution_report,
        )

    # -- internals -----------------------------------------------------------------

    async def _reason(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        prompt: str,
        model_policy: ModelPolicy | None,
        step: int | None,
        label: JsonObject | None,
    ) -> tuple[JsonObject, UUID | None]:
        """The model call — through the platform's OWN route + execute path."""
        try:
            decision = self._router.route(
                RoutingRequest(operation=ProviderOperation.GENERATE_TEXT, model_policy=model_policy)
            )
        except (RoutingError, UnsupportedPolicyType) as exc:
            raise ReasoningFailed(f"routing: {type(exc).__name__}: {exc}") from exc
        metadata: JsonObject = {"kind": "reasoning", "step": step}
        if label:
            metadata.update(label)
        payload: JsonObject = {
            "ask": prompt,
            "context": {"metadata": {AGENT_RUNTIME_LABEL_KEY: metadata}},
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            result = await self._execution.execute_single(
                tenant_id=tenant_id,
                user_id=user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=request_hash,
            )
        except (BudgetExceeded, EntitlementNotConfigured) as exc:
            raise ReasoningFailed(f"budget: {type(exc).__name__}") from exc
        if self._store_report is not None:
            self._store_report(result)
        output = result.final_output
        if output is None:
            raise ReasoningFailed("reasoning execution did not succeed")
        content = output.get("content")
        if isinstance(content, dict):
            return content, result.execution.id
        if not isinstance(content, str):
            content = json.dumps(output)
        return _parse_json_object(content), result.execution.id


def _parse_json_object(text: str) -> JsonObject:
    """Strict-but-tolerant JSON extraction: exact object, or the first
    ``{...}`` span (models wrap in fences). Non-JSON is returned as a
    non-dict marker so the shared validator refuses it as invalid_proposal.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        parsed = json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            return {"action": "invalid_json", "raw": text[:500]}
        try:
            parsed = json.loads(stripped[start : end + 1])
        except ValueError:
            return {"action": "invalid_json", "raw": text[:500]}
    if not isinstance(parsed, dict):
        return {"action": "invalid_json", "raw": text[:500]}
    return parsed


def agent_execution_report(
    report: AgentRunReport, reasoning_ids: Sequence[UUID]
) -> ExecutionReport:
    """Project the loop report onto the store's ``ExecutionReport`` shape.

    The final output rides a terminal ``final`` node's ``output_ref`` and
    surfaces via a synthetic ``response`` so ``ExecutionReport.final_output``
    (last node's response.output on success) keeps working for agent runs.
    The loop's evidence, verification, stop reason and reasoning ids are
    recorded in ``cost_snapshot`` (already the loop summary).
    """
    execution = report.execution.model_copy(
        update={
            "cost_snapshot": {
                **dict(report.execution.cost_snapshot),
                "reasoning_execution_ids": [str(i) for i in reasoning_ids],
                "verification": report.verification,
                "evidence": list(report.evidence),
            }
        }
    )
    nodes: list[NodeReport] = [
        NodeReport(node=node, attempts=(), response=None) for node in report.nodes
    ]
    if report.execution.status is ExecutionStatus.SUCCEEDED and report.final_output is not None:
        final_node = ExecutionNode(
            id=report.execution.id,
            execution_id=report.execution.id,
            node_key="final",
            type=ExecutionNodeType.MODEL_CALL,
            status=ExecutionNodeStatus.SUCCEEDED,
            input_ref={"stop_reason": report.stop_reason},
            output_ref=dict(report.final_output),
            retry_count=0,
        )
        nodes.append(
            NodeReport(
                node=final_node,
                attempts=(),
                response=ProviderGenerateResponse(
                    request_id=report.execution.id,
                    succeeded=True,
                    output=dict(report.final_output),
                ),
            )
        )
    return ExecutionReport(
        execution=execution,
        nodes=tuple(nodes),
        status_history=report.status_history,
    )
